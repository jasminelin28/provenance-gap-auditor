"""Tools the cross-reference agent can call.

Each tool returns a list of `crossref_hit` and never raises: a source being
down must degrade the audit, not crash it. Failures surface as warnings.
"""

import re
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

import requests

from .. import config
from ..schema import crossref_hit

# Owner names repeat across records, and the same record is often audited more
# than once while a user is comparing results. Caching the public lookups cuts
# the latency of a repeat audit and keeps us well inside the rate limits of
# free endpoints we do not pay for. Wikidata throttled us during development
# without it.
_response_cache: Dict[str, Tuple[float, Any]] = {}
_cache_lock = threading.Lock()
cache_ttl_seconds = 1800


def _cached_get(url: str, params: Optional[dict], warnings: List[str], label: str):
    """GET returning parsed JSON, memoised for the process lifetime.

    Returns None on any failure, appending a warning. Callers must treat a
    missing result as 'not checked', never as 'nothing found'.
    """
    key = f"{url}?{sorted((params or {}).items())}"
    now = time.monotonic()

    with _cache_lock:
        entry = _response_cache.get(key)
        if entry and now - entry[0] < cache_ttl_seconds:
            return entry[1]

    try:
        response = requests.get(
            url,
            params=params,
            headers={"User-Agent": config.http_user_agent},
            timeout=config.http_timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as error:
        warnings.append(f"{label} failed: {type(error).__name__}.")
        return None

    with _cache_lock:
        _response_cache[key] = (now, payload)
    return payload

# Placeholder owners that name nobody. Matching these is how the parser's
# `is_vague` flag gets a second, deterministic check.
vague_owner_patterns = [
    r"^private collection$",
    r"^private collection,?\s",
    r"^anonymous",
    r"^unknown",
    r"^a european (private )?collector$",
    r"^(the )?family of",
    r"^estate of$",
    r"^swiss private collection$",
    r"^\[?\.\.\.\]?$",
]


def is_vague_owner(name: str) -> bool:
    cleaned = name.strip().lower().rstrip(".")
    return any(re.search(pattern, cleaned) for pattern in vague_owner_patterns)


def search_red_flag_list(owner_name: str) -> List[crossref_hit]:
    """Match an owner against the local table of documented Nazi-era dealers."""
    hits: List[crossref_hit] = []
    if not config.database_path.exists():
        return hits
    needle = owner_name.strip().lower()
    if len(needle) < 4:
        return hits
    try:
        with sqlite3.connect(config.database_path) as connection:
            rows = connection.execute(
                "SELECT canonical_name, aliases, role, location, severity, note "
                "FROM red_flag_dealer"
            ).fetchall()
    except sqlite3.Error:
        return hits

    for canonical, aliases, role, location, severity, note in rows:
        candidates = [canonical] + [a for a in aliases.split("|") if a]
        for candidate in candidates:
            # Match whole words only. A plain substring test lets the short
            # alias "ERR" fire inside "Osterreichische", which wrongly brands
            # the Belvedere a looting agency. A false red flag is worse than a
            # missed one here, because it is the finding users act on.
            if _names_overlap(needle, candidate.lower()):
                hits.append(
                    crossref_hit(
                        owner_name=owner_name,
                        source="red_flag_list",
                        matched_label=canonical,
                        identifier=None,
                        note=f"{note} (recorded role: {role}, {location})",
                        is_red_flag=True,
                    )
                )
                break
    return hits


def _names_overlap(haystack: str, candidate: str) -> bool:
    """True when `candidate` appears in `haystack` as whole words, or vice versa.

    Both directions are needed so that "Gurlitt, Hildebrand" in the table and
    "sold through Hildebrand Gurlitt" in a record still meet.
    """
    if not candidate or not haystack:
        return False
    # Acronyms and very short aliases only count as an exact standalone token.
    if len(candidate) <= 4:
        return bool(
            re.search(rf"(?<![\w]){re.escape(candidate)}(?![\w])", haystack)
        ) and candidate.upper() in {
            token.upper() for token in re.findall(r"[A-Za-z]+", haystack)
        }
    for outer, inner in ((haystack, candidate), (candidate, haystack)):
        if re.search(rf"(?<![\w]){re.escape(inner)}(?![\w])", outer):
            return True
    return False


def search_lostart_cache(owner_name: str) -> List[crossref_hit]:
    """Search the committed snapshot of Lost Art Database records."""
    hits: List[crossref_hit] = []
    if not config.database_path.exists() or len(owner_name.strip()) < 4:
        return hits
    needle = owner_name.strip()
    try:
        with sqlite3.connect(config.database_path) as connection:
            rows = connection.execute(
                "SELECT lostart_id, title, artist, description, source_url, fetched_at "
                "FROM lostart_record WHERE description LIKE ? OR artist LIKE ? LIMIT 5",
                (f"%{needle}%", f"%{needle}%"),
            ).fetchall()
    except sqlite3.Error:
        return hits

    for lostart_id, title, artist, _description, url, fetched_at in rows:
        hits.append(
            crossref_hit(
                owner_name=needle,
                source="lostart_cache",
                matched_label=f"{title or 'Untitled'} ({artist or 'unknown artist'})",
                identifier=lostart_id,
                note=(
                    f"Lost Art Database record, snapshot taken {fetched_at}. {url or ''}"
                ).strip(),
                is_red_flag=True,
            )
        )
    return hits


def search_wikidata(owner_name: str) -> Tuple[List[crossref_hit], List[str]]:
    """Resolve an owner or dealer name against Wikidata."""
    hits: List[crossref_hit] = []
    warnings: List[str] = []
    name = owner_name.strip()
    if len(name) < 4 or is_vague_owner(name):
        return hits, warnings

    payload = _cached_get(
        "https://www.wikidata.org/w/api.php",
        {
            "action": "wbsearchentities",
            "search": name,
            "language": "en",
            "format": "json",
            "limit": 3,
            "type": "item",
        },
        warnings,
        f"Wikidata lookup for '{name}'",
    )
    if payload is None:
        return hits, warnings

    for entry in payload.get("search", []):
        hits.append(
            crossref_hit(
                owner_name=name,
                source="wikidata",
                matched_label=entry.get("label", name),
                identifier=entry.get("id"),
                note=entry.get("description", "") or "",
                is_red_flag=False,
            )
        )
    return hits, warnings


getty_query_template = """PREFIX gvp: <http://vocab.getty.edu/ontology#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
PREFIX xl: <http://www.w3.org/2008/05/skos-xl#>
SELECT ?subject ?label WHERE {
  ?subject skos:inScheme <http://vocab.getty.edu/ulan/> ;
           xl:prefLabel/xl:literalForm ?label .
  FILTER(CONTAINS(LCASE(?label), LCASE("NEEDLE")))
} LIMIT 4"""


def search_getty_ulan(owner_name: str) -> Tuple[List[crossref_hit], List[str]]:
    """Resolve a name against the Getty Union List of Artist Names."""
    hits: List[crossref_hit] = []
    warnings: List[str] = []
    name = owner_name.strip()
    if len(name) < 4 or is_vague_owner(name):
        return hits, warnings

    # Surname alone matches ULAN's "Surname, Forename" ordering far more often.
    surname = name.split(",")[0].split()[-1] if name.split() else name
    safe = re.sub(r"[^A-Za-z\- ]", "", surname)
    if len(safe) < 3:
        return hits, warnings

    payload = _cached_get(
        "https://vocab.getty.edu/sparql.json",
        {"query": getty_query_template.replace("NEEDLE", safe)},
        warnings,
        f"Getty ULAN lookup for '{name}'",
    )
    if payload is None:
        return hits, warnings
    bindings = payload.get("results", {}).get("bindings", [])

    for binding in bindings:
        uri = binding.get("subject", {}).get("value", "")
        hits.append(
            crossref_hit(
                owner_name=name,
                source="getty_ulan",
                matched_label=binding.get("label", {}).get("value", ""),
                identifier=uri.rsplit("/", 1)[-1] if uri else None,
                note=uri,
                is_red_flag=False,
            )
        )
    return hits, warnings


def enrich_artwork(work) -> Tuple[object, List[str]]:
    """Find the work (or failing that the artist) on Wikidata.

    Returns an image URL and a sitelink count. The sitelink count is used as a
    rough public measure of prominence: how many Wikipedia language editions
    carry an article. It is a proxy, not a measure of value or importance, and
    the app says so where it is shown.
    """
    warnings: List[str] = []
    queries: List[Tuple[str, bool]] = []

    if work.title and work.artist:
        queries.append((f"{work.title} {work.artist}", True))
    if work.title:
        queries.append((work.title, True))
    if work.artist:
        queries.append((work.artist, False))

    for term, is_work in queries:
        entity_id = _search_entity(term, warnings)
        if not entity_id:
            continue
        details = _entity_details(entity_id, warnings)
        if not details:
            continue
        image, sitelinks, label = details
        # Only accept a work-level match if it actually carries an image;
        # otherwise fall through to the artist, which usually has a portrait.
        if is_work and not image and len(queries) > 1:
            # Found the work but it carries no picture. Keep the prominence
            # figure and fall through to the artist for something to show.
            work.wikidata_id = work.wikidata_id or entity_id
            work.sitelink_count = max(work.sitelink_count, sitelinks)
            continue
        work.image_url = image
        work.wikidata_id = entity_id
        work.sitelink_count = max(work.sitelink_count, sitelinks)
        work.matched_label = label
        work.match_kind = "work" if is_work else "artist"
        return work, warnings

    return work, warnings


def _search_entity(term: str, warnings: List[str]) -> Optional[str]:
    payload = _cached_get(
        "https://www.wikidata.org/w/api.php",
        {
            "action": "wbsearchentities",
            "search": term[:120],
            "language": "en",
            "format": "json",
            "limit": 1,
            "type": "item",
        },
        warnings,
        "Artwork lookup",
    )
    if payload is None:
        return None
    results = payload.get("search", [])
    return results[0].get("id") if results else None


def _entity_details(
    entity_id: str, warnings: List[str]
) -> Optional[Tuple[Optional[str], int, Optional[str]]]:
    """Fetch the image (P18) and sitelink count for one entity."""
    payload = _cached_get(
        f"https://www.wikidata.org/wiki/Special:EntityData/{entity_id}.json",
        None,
        warnings,
        "Artwork detail lookup",
    )
    if payload is None:
        return None
    entity = payload.get("entities", {}).get(entity_id, {})

    label = (entity.get("labels", {}).get("en", {}) or {}).get("value")
    sitelinks = len(entity.get("sitelinks", {}) or {})

    image_url = None
    claims = (entity.get("claims", {}) or {}).get("P18") or []
    if claims:
        filename = (
            claims[0].get("mainsnak", {}).get("datavalue", {}).get("value")
        )
        if isinstance(filename, str) and filename:
            # Commons serves a scaled copy through this redirect endpoint.
            encoded = requests.utils.quote(filename.replace(" ", "_"))
            image_url = (
                "https://commons.wikimedia.org/wiki/Special:FilePath/"
                f"{encoded}?width=420"
            )
    return image_url, sitelinks, label
