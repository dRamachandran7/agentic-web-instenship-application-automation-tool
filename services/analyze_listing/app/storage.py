"""Attaches analysis results to the listing rows search_listings saved.

Reads/writes the same SQLite file as search_listings' app/storage.py (see
that module for the schema). This service never creates the table — if it
doesn't exist yet, no search has been run, and there's nothing to attach to.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

from .config import settings


def _connect() -> sqlite3.Connection:
    return sqlite3.connect(settings.db_path)


def save_analysis(listing_id: str, values: dict) -> bool:
    """Attach `values` to the row for `listing_id`. Returns False if no such
    row exists (e.g. the DB/table hasn't been created by search_listings, or
    the id doesn't match a saved listing) — non-fatal, just nothing to update."""
    if not settings.db_path.exists():
        return False
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE listings SET values_json = ?, analyzed_at = ? WHERE listing_id = ?",
            (json.dumps(values), now, listing_id),
        )
        return cur.rowcount > 0
