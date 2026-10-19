"""Build the SQLite database shipped with the repo.

Creates two tables:
  red_flag_dealer   - documented Nazi-era art dealers and agents
  lostart_record    - a cached snapshot of Lost Art Database entries

Lostart.de publishes no API, so the snapshot is fetched once and committed as
the small test dataset. Re-run this script to refresh it.

Usage:  python data/build_database.py
"""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from provenance_auditor import config

# Figures repeatedly documented in restitution scholarship and the 2013 Gurlitt
# findings. `aliases` is a pipe-separated list to catch spelling variants.
red_flag_dealers = [
    (
        "Hildebrand Gurlitt",
        "Hildebrandt Gurlitt|H. Gurlitt|Gurlitt, Hildebrand",
        "dealer",
        "Germany",
        "high",
        "One of four dealers authorised to sell art confiscated as 'degenerate' "
        "and a buyer for the planned Linz Fuhrermuseum. His holdings became the "
        "2012 Munich Art Trove.",
    ),
    (
        "Karl Haberstock",
        "Haberstock, Karl|Galerie Haberstock",
        "dealer",
        "Berlin, Germany",
        "high",
        "Principal purchasing agent for the Linz museum project; traded heavily "
        "in works taken from Jewish collections.",
    ),
    (
        "Bruno Lohse",
        "Lohse, Bruno",
        "dealer",
        "Paris, France",
        "high",
        "Deputy head of the ERR looting operation in Paris and a buyer for "
        "Hermann Goering.",
    ),
    (
        "Maria Almas-Dietrich",
        "Maria Dietrich|Almas-Dietrich|Dietrich, Maria",
        "dealer",
        "Munich, Germany",
        "high",
        "Among the largest suppliers of paintings to Hitler's Linz collection.",
    ),
    (
        "Einsatzstab Reichsleiter Rosenberg",
        "ERR|Rosenberg Task Force",
        "government",
        "Germany and occupied Europe",
        "high",
        "The Nazi agency that systematically confiscated cultural property in "
        "occupied territories.",
    ),
    (
        "Hermann Goering",
        "Hermann Goring|Goering, Hermann|Goring",
        "collector",
        "Germany",
        "high",
        "Assembled a large collection through confiscation and coerced sales.",
    ),
    (
        "Gustav Rochlitz",
        "Rochlitz, Gustav",
        "dealer",
        "Paris, France",
        "high",
        "Exchanged modern works with the ERR for old master paintings.",
    ),
    (
        "Theodor Fischer",
        "Fischer, Theodor|Galerie Fischer",
        "auction_house",
        "Lucerne, Switzerland",
        "medium",
        "Ran the 1939 Lucerne auction of works purged from German museums.",
    ),
]


def build(connection: sqlite3.Connection) -> None:
    cursor = connection.cursor()
    cursor.executescript(
        """
        DROP TABLE IF EXISTS red_flag_dealer;
        CREATE TABLE red_flag_dealer (
            dealer_id     INTEGER PRIMARY KEY,
            canonical_name TEXT NOT NULL,
            aliases       TEXT NOT NULL DEFAULT '',
            role          TEXT NOT NULL DEFAULT 'dealer',
            location      TEXT,
            severity      TEXT NOT NULL DEFAULT 'high',
            note          TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS lostart_record (
            record_id     INTEGER PRIMARY KEY,
            lostart_id    TEXT UNIQUE,
            title         TEXT,
            artist        TEXT,
            object_type   TEXT,
            description   TEXT,
            source_url    TEXT,
            fetched_at    TEXT
        );
        """
    )
    cursor.executemany(
        "INSERT INTO red_flag_dealer "
        "(canonical_name, aliases, role, location, severity, note) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        red_flag_dealers,
    )
    connection.commit()


if __name__ == "__main__":
    config.database_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(config.database_path) as connection:
        build(connection)
        count = connection.execute("SELECT COUNT(*) FROM red_flag_dealer").fetchone()[0]
    print(f"Built {config.database_path} with {count} red-flag entries.")
