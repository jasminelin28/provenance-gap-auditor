"""Agent 2: find the defects in a parsed ownership chain.

This agent uses deterministic rules rather than a model call. Gap detection is
arithmetic over years and string checks over owner names, so a model adds cost
and a hallucination risk without adding accuracy. Keeping this step rule-based
is one of the cost reductions reported in the tokenomics section, and it means
every gap the app reports can be traced to a specific rule.
"""

from typing import List

from ..schema import (
    acquisition_method,
    owner_role,
    gap_kind,
    gap_severity,
    ownership_event,
    provenance_gap,
)

# The window of Nazi persecution and wartime looting. A chain that is silent or
# vague across these years is the single most important thing this app detects.
nazi_era_start = 1933
nazi_era_end = 1945

# A chain rarely records every handover, so only flag meaningful silences.
minor_gap_years = 3
major_gap_years = 10


def chain_reaches_nazi_era(events: List[ownership_event]) -> bool:
    """True when any dated point in the chain is at or before 1945.

    A chain whose earliest known year is after the war cannot have a Nazi-era
    problem, and must not be escalated as if it might. Without this check a
    1965 print whose first owner has no start year gets treated as spanning
    1933-45 and rated high risk, which would make the app cry wolf.
    """
    known_years = [
        year
        for event in events
        for year in (event.start_year, event.end_year)
        if year is not None
    ]
    if not known_years:
        # Nothing is dated at all, so we cannot rule the period out.
        return True
    return min(known_years) <= nazi_era_end


def _overlaps_nazi_era(
    start: int | None, end: int | None, era_relevant: bool = True
) -> bool:
    if not era_relevant:
        return False
    if start is None and end is None:
        return True
    # An open-ended side is only assumed to reach into the window when the
    # other side does not already place the event clear of it.
    low = start if start is not None else nazi_era_start
    high = end if end is not None else nazi_era_end
    if start is None and end is not None and end > nazi_era_end:
        # Ownership ended after the war with no stated start: it may or may not
        # reach back, so only flag when nothing else dates the chain earlier.
        low = nazi_era_start
    return low <= nazi_era_end and high >= nazi_era_start


def detect_gaps(events: List[ownership_event]) -> List[provenance_gap]:
    """Apply every rule and return the gaps found, worst first."""
    gaps: List[provenance_gap] = []

    if not events:
        return [
            provenance_gap(
                kind=gap_kind.chain_start_unclear,
                severity=gap_severity.high,
                description=(
                    "No ownership events could be read from this record, so the "
                    "chain cannot be assessed at all."
                ),
            )
        ]

    era_relevant = chain_reaches_nazi_era(events)

    gaps.extend(_find_unaccounted_years(events, era_relevant))
    gaps.extend(_find_vague_owners(events, era_relevant))
    gaps.extend(_find_unexplained_location_changes(events, era_relevant))
    gaps.extend(_find_missing_methods(events, era_relevant))
    gaps.extend(_find_unclear_start(events, era_relevant))

    severity_rank = {gap_severity.high: 0, gap_severity.medium: 1, gap_severity.low: 2}
    gaps.sort(key=lambda g: (severity_rank[g.severity], g.start_year or 0))
    return gaps


def _find_unaccounted_years(
    events: List[ownership_event], era_relevant: bool
) -> List[provenance_gap]:
    """Silences between one owner letting go and the next taking over."""
    found: List[provenance_gap] = []
    for index in range(len(events) - 1):
        current, following = events[index], events[index + 1]
        left = current.end_year or current.start_year
        right = following.start_year or following.end_year
        if left is None or right is None:
            continue
        span = right - left
        if span < minor_gap_years:
            continue

        in_nazi_era = _overlaps_nazi_era(left, right, era_relevant)
        if in_nazi_era:
            severity = gap_severity.high
        elif span >= major_gap_years:
            severity = gap_severity.medium
        else:
            severity = gap_severity.low

        description = (
            f"{span} years are unaccounted for between {current.owner_name} "
            f"({left}) and {following.owner_name} ({right})."
        )
        if in_nazi_era:
            description += (
                " This silence overlaps 1933-1945, the period of Nazi "
                "confiscation and forced sales."
            )
        found.append(
            provenance_gap(
                kind=gap_kind.nazi_era_window if in_nazi_era else gap_kind.unaccounted_years,
                severity=severity,
                description=description,
                start_year=left,
                end_year=right,
                related_event_indexes=[index, index + 1],
            )
        )
    return found


def _find_vague_owners(
    events: List[ownership_event], era_relevant: bool
) -> List[provenance_gap]:
    """Placeholder owners that name nobody, worst when they sit in 1933-45."""
    found: List[provenance_gap] = []
    for index, event in enumerate(events):
        if not event.is_vague:
            continue
        in_nazi_era = _overlaps_nazi_era(
            event.start_year, event.end_year, era_relevant
        )
        years = _describe_years(event)
        description = (
            f"'{event.owner_name}' names no identifiable party{years}, so this "
            "link in the chain cannot be verified against any public record."
        )
        if in_nazi_era:
            description += (
                " It also covers part of 1933-1945, when an unnamed holder is a "
                "recognised warning sign."
            )
        found.append(
            provenance_gap(
                kind=gap_kind.nazi_era_window if in_nazi_era else gap_kind.vague_owner,
                severity=gap_severity.high if in_nazi_era else gap_severity.medium,
                description=description,
                start_year=event.start_year,
                end_year=event.end_year,
                related_event_indexes=[index],
            )
        )
    return found


def _find_unexplained_location_changes(
    events: List[ownership_event], era_relevant: bool
) -> List[provenance_gap]:
    """A work crossing borders with no stated sale, gift, or transfer."""
    found: List[provenance_gap] = []
    for index in range(len(events) - 1):
        current, following = events[index], events[index + 1]
        if not current.location or not following.location:
            continue
        if _same_place(current.location, following.location):
            continue
        if following.method is not acquisition_method.unknown:
            continue

        in_nazi_era = _overlaps_nazi_era(
            current.end_year or current.start_year,
            following.start_year or following.end_year,
            era_relevant,
        )
        found.append(
            provenance_gap(
                kind=gap_kind.unexplained_location_change,
                severity=gap_severity.high if in_nazi_era else gap_severity.low,
                description=(
                    f"The work moved from {current.location} to {following.location} "
                    "with no stated method of transfer."
                    + (
                        " Movement across borders during 1933-1945 without a "
                        "recorded sale warrants scrutiny."
                        if in_nazi_era
                        else ""
                    )
                ),
                start_year=current.end_year or current.start_year,
                end_year=following.start_year or following.end_year,
                related_event_indexes=[index, index + 1],
            )
        )
    return found


def _find_missing_methods(
    events: List[ownership_event], era_relevant: bool
) -> List[provenance_gap]:
    """Nazi-era handovers that never say how the work changed hands."""
    found: List[provenance_gap] = []
    for index, event in enumerate(events):
        if event.method is not acquisition_method.unknown:
            continue
        # The artist holding their own new work is not an acquisition.
        if event.role is owner_role.artist:
            continue
        if not _overlaps_nazi_era(event.start_year, event.end_year, era_relevant):
            continue
        if event.start_year is None and event.end_year is None:
            continue
        found.append(
            provenance_gap(
                kind=gap_kind.missing_acquisition_method,
                severity=gap_severity.medium,
                description=(
                    f"The record does not say how {event.owner_name} acquired the "
                    "work, and this transfer falls inside 1933-1945."
                ),
                start_year=event.start_year,
                end_year=event.end_year,
                related_event_indexes=[index],
            )
        )
    return found


def _find_unclear_start(
    events: List[ownership_event], era_relevant: bool
) -> List[provenance_gap]:
    """A chain that does not reach back to the artist or a dated first owner."""
    first = events[0]
    if first.role is owner_role.artist:
        return []
    if not era_relevant:
        # The whole chain postdates the war; an undated start is not a red flag.
        return []
    if first.start_year is not None and first.start_year <= nazi_era_start:
        return []
    if first.start_year is None:
        return [
            provenance_gap(
                kind=gap_kind.chain_start_unclear,
                severity=gap_severity.medium,
                description=(
                    f"The chain begins with {first.owner_name} with no date, so "
                    "there is no way to tell how far back the documented history goes."
                ),
                related_event_indexes=[0],
            )
        ]
    if first.start_year > nazi_era_end:
        return [
            provenance_gap(
                kind=gap_kind.chain_start_unclear,
                severity=gap_severity.high,
                description=(
                    f"The documented chain only starts in {first.start_year}, after "
                    "1945. Everything before that, including the entire Nazi era, "
                    "is undocumented."
                ),
                start_year=first.start_year,
                related_event_indexes=[0],
            )
        ]
    return []


def _describe_years(event: ownership_event) -> str:
    if event.start_year and event.end_year:
        return f" for the period {event.start_year}-{event.end_year}"
    if event.start_year:
        return f" from {event.start_year}"
    if event.end_year:
        return f" up to {event.end_year}"
    return " and gives no dates"


def _same_place(left: str, right: str) -> bool:
    """Loose comparison so 'Paris' and 'Paris, France' count as one place."""
    left_parts = {p.strip().lower() for p in left.split(",") if p.strip()}
    right_parts = {p.strip().lower() for p in right.split(",") if p.strip()}
    return bool(left_parts & right_parts)
