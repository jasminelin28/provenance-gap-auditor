"""Turn the findings into a 0-100 provenance confidence score.

100 means nothing was found to doubt. 0 means the chain is as bad as this app
can describe. The number runs in that direction on purpose: a high score is
good news, which is how a reader expects a score to behave.

The whole calculation is deterministic and every deduction is returned as a
labelled component, so the app can show its working and a reader can disagree
with a specific line rather than with an opaque number. No model is involved.

The weights below are judgement calls, not measured constants. They are set so
that the categories restitution researchers treat as most serious cost the most
points. They are stated here, in one place, so the report can defend them and a
user can see what drove a given score.
"""

from typing import List

from .schema import (
    artwork,
    risk_verdict,
    crossref_hit,
    gap_kind,
    gap_severity,
    provenance_gap,
    provenance_score,
    score_component,
)

# Base cost of a gap, by how serious the rules judged it.
severity_cost = {
    gap_severity.high: 16.0,
    gap_severity.medium: 7.0,
    gap_severity.low: 2.5,
}

# A documented Nazi-era dealer in the chain is the single strongest signal the
# app can find, so it is priced above any individual gap.
red_flag_cost = 28.0

# Repeated gaps of the same kind say less than the first one did, so each
# further gap of a kind is discounted. This stops a long chain from scoring
# badly merely for being long and well documented.
repeat_discount = 0.55

# Caps, so no single category can sink a score on its own.
max_gap_deduction = 62.0
max_red_flag_deduction = 34.0

band_thresholds = [
    (85, "Well documented"),
    (70, "Minor questions"),
    (50, "Needs research"),
    (30, "Serious concerns"),
    (0, "Unsafe without expert review"),
]


def _band_for(value: int) -> str:
    for threshold, label in band_thresholds:
        if value >= threshold:
            return label
    return band_thresholds[-1][1]


def _gap_deductions(gaps: List[provenance_gap]) -> List[score_component]:
    """Price the gaps, discounting repeats of the same kind."""
    if not gaps:
        return []

    seen_kinds: dict[gap_kind, int] = {}
    ordered = sorted(gaps, key=lambda g: -severity_cost[g.severity])
    components: List[score_component] = []
    running = 0.0

    for gap in ordered:
        occurrence = seen_kinds.get(gap.kind, 0)
        seen_kinds[gap.kind] = occurrence + 1

        cost = severity_cost[gap.severity] * (repeat_discount**occurrence)
        if running + cost > max_gap_deduction:
            cost = max(max_gap_deduction - running, 0.0)
        if cost <= 0:
            continue
        running += cost

        label = gap.kind.value.replace("_", " ").capitalize()
        if occurrence:
            label += f" (further instance)"
        components.append(
            score_component(
                label=label,
                points=-round(cost, 1),
                detail=f"{gap.severity.value} severity. {gap.description[:120]}",
            )
        )
    return components


def _red_flag_deductions(hits: List[crossref_hit]) -> List[score_component]:
    """Price each distinct red-flag name once, however often it matched."""
    names = sorted({hit.matched_label for hit in hits if hit.is_red_flag})
    components: List[score_component] = []
    running = 0.0
    for index, name in enumerate(names):
        cost = red_flag_cost * (repeat_discount**index)
        if running + cost > max_red_flag_deduction:
            cost = max(max_red_flag_deduction - running, 0.0)
        if cost <= 0:
            continue
        running += cost
        components.append(
            score_component(
                label=f"Red-flag name in chain: {name}",
                points=-round(cost, 1),
                detail="Documented in the app's table of Nazi-era dealers, "
                "agents and looting bodies.",
            )
        )
    return components


def _context_adjustments(
    work: artwork, gaps: List[provenance_gap], era_relevant: bool
) -> List[score_component]:
    """Adjust for how much the object's own context raises the stakes.

    These are small compared with the gap deductions. Context changes how much
    a gap matters; it is never itself evidence of a problem.
    """
    components: List[score_component] = []
    has_gaps = bool(gaps)

    # 1. Age. A work made before 1933 had to survive the period, so its chain
    #    carries a burden a post-war work does not.
    if work.year_created is not None:
        if work.year_created < 1933 and era_relevant and has_gaps:
            components.append(
                score_component(
                    label="Existed before 1933",
                    points=-6.0,
                    detail=(
                        f"Made in {work.year_created}, so the work was already in "
                        "existence during the Nazi period and its chain has to "
                        "account for those years."
                    ),
                )
            )
        elif work.year_created > 1945:
            components.append(
                score_component(
                    label="Made after 1945",
                    points=+5.0,
                    detail=(
                        f"Created in {work.year_created}, after the war, so the "
                        "1933-1945 question does not arise."
                    ),
                )
            )

    # 2. Prominence. A well known work is normally well published, so a hole in
    #    its record is harder to explain away as mere obscurity.
    if work.sitelink_count >= 12 and has_gaps:
        components.append(
            score_component(
                label="Prominent work or artist",
                points=-5.0,
                detail=(
                    f"Covered in {work.sitelink_count} Wikipedia language editions. "
                    "A gap in a widely published work is less easily explained by "
                    "poor record keeping."
                ),
            )
        )
    elif 0 < work.sitelink_count < 4 and has_gaps:
        components.append(
            score_component(
                label="Little public record",
                points=-2.0,
                detail=(
                    "Barely covered in public reference sources, so the "
                    "cross-reference step had little to check against."
                ),
            )
        )

    # 3. Identification. An unidentifiable object cannot really be cleared.
    if not work.artist and not work.title:
        components.append(
            score_component(
                label="Work not identified",
                points=-8.0,
                detail=(
                    "Neither an artist nor a title could be read from the record, "
                    "so nothing could be checked against external sources."
                ),
            )
        )

    return components


def _chain_quality(events_count: int, documented_count: int) -> List[score_component]:
    """Reward a chain that actually names and dates its owners."""
    if events_count == 0:
        return [
            score_component(
                label="No ownership chain",
                points=-45.0,
                detail="No ownership events could be read from the record at all.",
            )
        ]
    if events_count < 3:
        return [
            score_component(
                label="Very short chain",
                points=-7.0,
                detail=(
                    f"Only {events_count} ownership event(s) were found, which is "
                    "too little to call a history."
                ),
            )
        ]

    share = documented_count / events_count
    if share >= 0.8:
        return [
            score_component(
                label="Well documented chain",
                points=+4.0,
                detail=(
                    f"{documented_count} of {events_count} owners are named and dated."
                ),
            )
        ]
    return []


# A score must never contradict the verdict shown beside it. These ceilings
# keep the two readings consistent: a high-risk work cannot also display a
# score in a reassuring band, however well documented its chain happens to be.
verdict_ceiling = {
    risk_verdict.high_risk: 49,
    risk_verdict.review: 84,
    risk_verdict.clear: 100,
}


def compute_score(
    work: artwork,
    events,
    gaps: List[provenance_gap],
    hits: List[crossref_hit],
    era_relevant: bool,
    verdict: risk_verdict = risk_verdict.review,
) -> provenance_score:
    """Assemble the score from its parts. Deterministic, no model call."""
    components: List[score_component] = []

    components.extend(_red_flag_deductions(hits))
    components.extend(_gap_deductions(gaps))

    documented = sum(
        1 for event in events if not event.is_vague and event.start_year is not None
    )
    components.extend(_chain_quality(len(events), documented))
    components.extend(_context_adjustments(work, gaps, era_relevant))

    total = 100.0 + sum(component.points for component in components)
    value = int(round(min(max(total, 0.0), 100.0)))

    ceiling = verdict_ceiling.get(verdict, 100)
    if value > ceiling:
        components.append(
            score_component(
                label=f"Capped by the {verdict.value.replace('_', ' ')} verdict",
                points=-(value - ceiling),
                detail=(
                    "The chain is better documented than this score suggests, but "
                    "a score in a reassuring band would contradict the verdict "
                    "shown beside it."
                ),
            )
        )
        value = ceiling

    return provenance_score(
        value=value,
        band=_band_for(value),
        components=components,
        method_note=(
            "Starts at 100 and deducts for each gap by severity, for each "
            "red-flag name, and for a thin or undated chain, then adjusts for "
            "the work's date and how well published it is. Repeated gaps of the "
            "same kind count less than the first. The weights are stated in "
            "provenance_auditor/scoring.py and are judgement calls, not measured "
            "constants. The result is then capped so it cannot contradict the "
            "verdict."
        ),
    )
