"""Agent 3: check every named owner against external and local sources.

This agent chooses which tools to run per owner rather than calling a model.
The decision is cheap and rule-based: skip placeholders, always check the local
red-flag table, and only spend a network round trip on names that could resolve.
Sources that fail are reported as warnings so the verdict agent knows the
cross-reference was incomplete rather than clean.
"""

from typing import List, Tuple

from ..schema import crossref_hit, ownership_event
from ..tools.lookup_tools import (
    is_vague_owner,
    search_getty_ulan,
    search_lostart_cache,
    search_red_flag_list,
    search_wikidata,
)

# Words that mean the "owner" is a sale event, not a party we can look up.
non_party_markers = ["present owner", "above sale", "thence by descent", "the above"]


def _is_lookupable(event: ownership_event) -> bool:
    name = event.owner_name.strip().lower()
    if len(name) < 4:
        return False
    if event.is_vague or is_vague_owner(name):
        return False
    return not any(marker in name for marker in non_party_markers)


def cross_reference(
    events: List[ownership_event], max_lookups: int = 8
) -> Tuple[List[crossref_hit], List[str]]:
    """Look up each distinct owner. Returns hits and any source warnings.

    `max_lookups` bounds the number of network calls so a long chain cannot
    turn one audit into dozens of outbound requests.
    """
    hits: List[crossref_hit] = []
    warnings: List[str] = []
    seen: set[str] = set()
    network_lookups = 0

    for event in events:
        name = event.owner_name.strip()
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)

        # The local red-flag table is free, so it runs for every owner,
        # including vague ones where the placeholder text may still name a party.
        hits.extend(search_red_flag_list(name))
        hits.extend(search_lostart_cache(name))

        if not _is_lookupable(event) or network_lookups >= max_lookups:
            continue

        wikidata_hits, wikidata_warnings = search_wikidata(name)
        hits.extend(wikidata_hits)
        warnings.extend(wikidata_warnings)

        getty_hits, getty_warnings = search_getty_ulan(name)
        hits.extend(getty_hits)
        warnings.extend(getty_warnings)

        network_lookups += 1

    if network_lookups >= max_lookups:
        warnings.append(
            f"Only the first {max_lookups} named owners were checked against "
            "Wikidata and Getty, to bound the number of outbound requests."
        )

    return hits, warnings


def summarise_for_model(hits: List[crossref_hit], limit: int = 20) -> str:
    """Compact the hits into the short text block the verdict agent reads.

    Only the fields that affect a verdict are included. Sending the full hit
    list would roughly double the verdict prompt for no gain in quality.
    """
    if not hits:
        return "No cross-reference matches were found for any named owner."

    # Red flags must survive truncation, so they are listed first.
    ordered = sorted(hits, key=lambda h: not h.is_red_flag)
    lines: List[str] = []
    for hit in ordered[:limit]:
        marker = "RED FLAG" if hit.is_red_flag else "match"
        note = hit.note[:160].strip()
        lines.append(
            f"- [{marker}] '{hit.owner_name}' matched '{hit.matched_label}' "
            f"in {hit.source}"
            + (f" ({hit.identifier})" if hit.identifier else "")
            + (f": {note}" if note else "")
        )
    if len(ordered) > limit:
        lines.append(f"- ...and {len(ordered) - limit} further routine matches.")
    return "\n".join(lines)
