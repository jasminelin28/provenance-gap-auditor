"""Turn the place names in a chain into points on a map.

Geocoding runs off a built-in table rather than a web service. The set of
places that appear in art provenance is small and stable - a few dozen cities
carry almost all of it - and a local table means the map draws instantly,
works offline, and cannot fail on the teaching staff's machine.

Unrecognised places are reported rather than guessed at, so the map never
invents a journey the record does not support.
"""

import re
from typing import Dict, List, Optional, Tuple

# (latitude, longitude). Cities first, then countries as a coarse fallback.
place_coordinates: Dict[str, Tuple[float, float]] = {
    # Centres of the European art trade
    "paris": (48.857, 2.352),
    "berlin": (52.520, 13.405),
    "munich": (48.135, 11.582),
    "vienna": (48.209, 16.373),
    "london": (51.507, -0.128),
    "amsterdam": (52.370, 4.895),
    "the hague": (52.078, 4.288),
    "brussels": (50.851, 4.352),
    "antwerp": (51.220, 4.402),
    "zurich": (47.377, 8.542),
    "lucerne": (47.050, 8.307),
    "luzern": (47.050, 8.307),
    "geneva": (46.204, 6.143),
    "basel": (47.559, 7.589),
    "bern": (46.948, 7.447),
    "rome": (41.903, 12.496),
    "florence": (43.770, 11.256),
    "venice": (45.440, 12.316),
    "milan": (45.464, 9.190),
    "madrid": (40.417, -3.704),
    "barcelona": (41.385, 2.173),
    "lisbon": (38.722, -9.139),
    "dresden": (51.050, 13.738),
    "hamburg": (53.551, 9.994),
    "cologne": (50.938, 6.960),
    "frankfurt": (50.111, 8.682),
    "dusseldorf": (51.228, 6.773),
    "stuttgart": (48.776, 9.183),
    "leipzig": (51.340, 12.375),
    "linz": (48.306, 14.286),
    "salzburg": (47.809, 13.055),
    "prague": (50.076, 14.438),
    "budapest": (47.498, 19.040),
    "warsaw": (52.230, 21.012),
    "krakow": (50.065, 19.945),
    "copenhagen": (55.677, 12.569),
    "stockholm": (59.329, 18.069),
    "oslo": (59.914, 10.752),
    "moscow": (55.756, 37.617),
    "st petersburg": (59.934, 30.335),
    "saint petersburg": (59.934, 30.335),
    "leningrad": (59.934, 30.335),
    # Beyond Europe
    "new york": (40.713, -74.006),
    "boston": (42.360, -71.059),
    "philadelphia": (39.953, -75.165),
    "washington": (38.907, -77.037),
    "chicago": (41.878, -87.630),
    "los angeles": (34.052, -118.244),
    "san francisco": (37.775, -122.419),
    "toronto": (43.653, -79.383),
    "buenos aires": (-34.604, -58.382),
    "sao paulo": (-23.551, -46.633),
    "mexico city": (19.433, -99.133),
    "tokyo": (35.690, 139.692),
    "hong kong": (22.320, 114.174),
    "sydney": (-33.869, 151.209),
    "tel aviv": (32.085, 34.781),
    "jerusalem": (31.769, 35.214),
    "istanbul": (41.008, 28.978),
    # Country-level fallbacks, used only when no city is named
    "france": (46.6, 2.4),
    "germany": (51.2, 10.4),
    "austria": (47.6, 14.1),
    "switzerland": (46.8, 8.2),
    "united kingdom": (54.0, -2.0),
    "england": (52.4, -1.5),
    "netherlands": (52.1, 5.3),
    "belgium": (50.5, 4.5),
    "italy": (42.8, 12.6),
    "spain": (40.0, -3.7),
    "portugal": (39.4, -8.2),
    "poland": (52.0, 19.1),
    "czechia": (49.8, 15.5),
    "hungary": (47.2, 19.5),
    "sweden": (60.1, 18.6),
    "denmark": (56.3, 9.5),
    "norway": (60.5, 8.5),
    "russia": (55.8, 37.6),
    "united states": (39.8, -98.6),
    "usa": (39.8, -98.6),
    "canada": (56.1, -106.3),
    "israel": (31.5, 34.8),
    "japan": (36.2, 138.3),
    "argentina": (-38.4, -63.6),
    "brazil": (-14.2, -51.9),
    "australia": (-25.3, 133.8),
}


def locate(place: Optional[str]) -> Optional[Tuple[float, float, str]]:
    """Resolve a stated place to coordinates and the name actually matched.

    Tries each comma-separated part, most specific first, so "Lucerne,
    Switzerland" resolves to the city rather than the country.
    """
    if not place:
        return None
    parts = [p.strip() for p in str(place).split(",") if p.strip()]
    for part in parts:
        cleaned = re.sub(r"[^a-z ]", "", part.lower()).strip()
        if not cleaned:
            continue
        if cleaned in place_coordinates:
            latitude, longitude = place_coordinates[cleaned]
            return latitude, longitude, part.strip()
        # Handle "near Munich" or "Munich area" without a dictionary entry each.
        for key, (latitude, longitude) in place_coordinates.items():
            if len(key) > 4 and key in cleaned:
                return latitude, longitude, part.strip()
    return None


def build_journey(events) -> Tuple[List[dict], List[str]]:
    """Turn the chain into an ordered list of mapped stops.

    Consecutive events in the same place collapse into one stop, so the map
    shows movement rather than a stack of identical pins.
    """
    stops: List[dict] = []
    unresolved: List[str] = []

    for index, event in enumerate(events):
        found = locate(event.location)
        if not found:
            if event.location:
                unresolved.append(event.location)
            continue
        latitude, longitude, matched = found

        if stops and stops[-1]["latitude"] == latitude and stops[-1]["longitude"] == longitude:
            stops[-1]["owners"].append(event.owner_name)
            stops[-1]["event_indexes"].append(index)
            if event.end_year:
                stops[-1]["year_to"] = event.end_year
            continue

        stops.append(
            {
                "latitude": latitude,
                "longitude": longitude,
                "place": matched,
                "owners": [event.owner_name],
                "event_indexes": [index],
                "year_from": event.start_year,
                "year_to": event.end_year,
            }
        )

    return stops, sorted(set(unresolved))
