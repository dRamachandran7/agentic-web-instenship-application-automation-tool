"""Persistence for scraped listings.

A single SQLite file at the repo root (`data/app.db`) is shared by
search_listings and analyze_listing: search_listings writes rows here so
listings survive past the request/response cycle, and analyze_listing later
attaches its `values` output to the same row by `listing_id`. SQLite (rather
than a standalone DB service) is enough for a single-machine tool with no
concurrent writers to coordinate.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from .config import settings
from .models import Listing

_SCHEMA = """
CREATE TABLE IF NOT EXISTS listings (
    listing_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    company TEXT NOT NULL,
    location TEXT,
    url TEXT NOT NULL,
    description_text TEXT,
    scraped_at TEXT NOT NULL,
    values_json TEXT,
    analyzed_at TEXT
);
"""


def _connect() -> sqlite3.Connection:
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.execute(_SCHEMA)


def save_listings(listings: list[Listing]) -> None:
    """Upsert scraped listings, leaving any prior analysis untouched."""
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.executemany(
            """
            INSERT INTO listings
                (listing_id, title, company, location, url, description_text, scraped_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(listing_id) DO UPDATE SET
                title=excluded.title,
                company=excluded.company,
                location=excluded.location,
                url=excluded.url,
                description_text=excluded.description_text,
                scraped_at=excluded.scraped_at
            """,
            [
                (l.listingId, l.title, l.company, l.location, l.url, l.descriptionText, now)
                for l in listings
            ],
        )


def get_listings() -> list[sqlite3.Row]:
    with _connect() as conn:
        return conn.execute(
            "SELECT * FROM listings ORDER BY scraped_at DESC"
        ).fetchall()


def get_listing(listing_id: str) -> sqlite3.Row | None:
    with _connect() as conn:
        return conn.execute(
            "SELECT * FROM listings WHERE listing_id = ?", (listing_id,)
        ).fetchone()
