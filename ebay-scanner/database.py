"""
database.py — SQLite state management for the eBay Console Scanner Bot.

Tracks every item ID the bot has already seen so it only alerts on NEW listings.
The database file is created automatically on first run.
"""

import sqlite3
import logging
from datetime import datetime
import config   # Import the module, not a value — so runtime changes to config.DB_PATH take effect

logger = logging.getLogger(__name__)


def get_connection() -> sqlite3.Connection:
    """Return a connection to the SQLite database, creating it if needed."""
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row  # Allow dict-style column access
    return conn


def init_db() -> None:
    """
    Create the seen_items table if it does not already exist.
    Called once on bot startup.
    """
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS seen_items (
                item_id    TEXT PRIMARY KEY,
                title      TEXT,
                price      REAL,
                console    TEXT,
                url        TEXT,
                found_at   TEXT       -- ISO-8601 timestamp
            )
        """)
        # Index for quick "have I seen this?" lookups
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_seen_items_item_id
            ON seen_items (item_id)
        """)
        conn.commit()
    logger.debug("Database initialised at %s", config.DB_PATH)


def is_seen(item_id: str) -> bool:
    """Return True if this eBay item ID is already in the database."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM seen_items WHERE item_id = ?", (item_id,)
        ).fetchone()
    return row is not None


def mark_seen(item_id: str, title: str, price: float, console: str, url: str) -> None:
    """
    Insert a new item into the database so it won't be alerted about again.

    Args:
        item_id:  eBay item ID string (e.g. "123456789012")
        title:    Listing title
        price:    Price as a float
        console:  Console name (e.g. "Nintendo Switch")
        url:      Direct URL to the eBay listing
    """
    found_at = datetime.utcnow().isoformat()
    try:
        with get_connection() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO seen_items (item_id, title, price, console, url, found_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (item_id, title, price, console, url, found_at),
            )
            conn.commit()
        logger.debug("Marked item %s as seen.", item_id)
    except sqlite3.Error as exc:
        logger.error("DB error while marking item %s: %s", item_id, exc)


def get_seen_count() -> int:
    """Return the total number of items tracked so far."""
    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) FROM seen_items").fetchone()
    return row[0] if row else 0


def purge_old_items(days: int = 90) -> int:
    """
    Remove items older than `days` days to keep the database small.
    Returns the number of rows deleted.
    """
    cutoff = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    from datetime import timedelta
    cutoff -= timedelta(days=days)
    cutoff_str = cutoff.isoformat()

    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM seen_items WHERE found_at < ?", (cutoff_str,)
        )
        conn.commit()
    deleted = cursor.rowcount
    if deleted:
        logger.info("Purged %d old items (older than %d days).", deleted, days)
    return deleted
