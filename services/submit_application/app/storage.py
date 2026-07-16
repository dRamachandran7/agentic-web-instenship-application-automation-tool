"""Attaches submission outcomes to the listing rows search_listings saved.

Reads/writes the same SQLite file as search_listings' app/storage.py. Like
analyze_listing, this service never creates the `listings` table — if it
doesn't exist yet, no search has been run and there's nothing to attach to.
Unlike analyze_listing, the columns it writes don't exist in the original
schema, so they're added defensively on first use.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Optional

from .config import settings

_NEW_COLUMNS = {
    "submission_status": "TEXT",
    "confirmation_id": "TEXT",
    "submission_error": "TEXT",
    "submitted_at": "TEXT",
}


def _connect() -> sqlite3.Connection:
    return sqlite3.connect(settings.db_path)


def _ensure_columns(conn: sqlite3.Connection) -> None:
    existing = {row[1] for row in conn.execute("PRAGMA table_info(listings)")}
    for name, col_type in _NEW_COLUMNS.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE listings ADD COLUMN {name} {col_type}")


def save_submission(
    listing_id: str,
    *,
    status: str,
    confirmation_id: Optional[str] = None,
    error: Optional[str] = None,
) -> bool:
    """Record the outcome on the row search_listings created. Returns False if
    no such row/table exists yet — non-fatal, just nothing to update."""
    if not settings.db_path.exists():
        return False
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        try:
            _ensure_columns(conn)
        except sqlite3.OperationalError:
            return False  # table doesn't exist yet
        cur = conn.execute(
            "UPDATE listings SET submission_status = ?, confirmation_id = ?, "
            "submission_error = ?, submitted_at = ? WHERE listing_id = ?",
            (status, confirmation_id, error, now, listing_id),
        )
        return cur.rowcount > 0
