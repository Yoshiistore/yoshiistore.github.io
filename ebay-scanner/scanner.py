"""
scanner.py — Core scanning orchestration for the eBay Console Scanner Bot.

EbayScanner.run() is the single entry-point for one full scan cycle.
It:
  1. Iterates over every console + every search query defined in config.py
  2. Fetches results from eBay (via Browse API or scraping)
  3. Applies keyword inclusion / exclusion filters on the title
  4. Deduplicates against the SQLite database
  5. Sends Discord alerts for any new matching items
  6. Marks alerted items as seen in the database
"""

import logging
from typing import Optional

import config
import database
import discord_notifier
from ebay_client import get_ebay_client

logger = logging.getLogger(__name__)


class EbayScanner:
    """
    Orchestrates one complete scan cycle across all target consoles.

    Attributes:
        client:      eBay API/scraping client instance
        stats:       dict tracking per-run statistics
    """

    def __init__(self) -> None:
        self.client = get_ebay_client()
        self.stats = {
            'total_fetched':  0,
            'new_matches':    0,
            'already_seen':   0,
            'filtered_out':   0,
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self) -> dict:
        """
        Execute one full scan cycle.

        Returns:
            stats dict with counts for this run.
        """
        logger.info("=== Scan cycle started ===")
        self.stats = {k: 0 for k in self.stats}

        for console_name, console_cfg in config.CONSOLE_SEARCHES.items():
            self._scan_console(console_name, console_cfg)

        logger.info(
            "=== Scan complete | fetched=%d  new=%d  seen=%d  filtered=%d ===",
            self.stats['total_fetched'],
            self.stats['new_matches'],
            self.stats['already_seen'],
            self.stats['filtered_out'],
        )
        return self.stats

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _scan_console(self, console_name: str, console_cfg: dict) -> None:
        """Run all search queries for a single console."""
        logger.info("Scanning: %s", console_name)
        seen_this_run: set[str] = set()   # Deduplicate within this run

        for query in console_cfg.get('queries', []):
            logger.debug("  Query: %s", query)
            items = self.client.search(query, condition_id=config.PARTS_CONDITION_ID)
            self.stats['total_fetched'] += len(items)

            for item in items:
                item_id = item.get('item_id', '')

                # --- Skip empty / malformed items ---
                if not item_id or not item.get('title'):
                    continue

                # --- Deduplicate within this run (same item from multiple queries) ---
                if item_id in seen_this_run:
                    continue
                seen_this_run.add(item_id)

                # --- Apply title-based keyword filters ---
                if not self._passes_filters(item['title']):
                    self.stats['filtered_out'] += 1
                    logger.debug("    Filtered: %s", item['title'][:80])
                    continue

                # --- Already seen in DB? ---
                if database.is_seen(item_id):
                    self.stats['already_seen'] += 1
                    continue

                # --- NEW match — alert and record ---
                logger.info("  ✅ NEW: [%s] %s — $%.2f", console_name, item['title'][:70], item['price'])
                success = discord_notifier.send_discord_alert(item, console_name)

                if success or True:
                    # Mark as seen even if Discord failed (to avoid duplicate spam on retry)
                    database.mark_seen(
                        item_id   = item_id,
                        title     = item['title'],
                        price     = item['price'],
                        console   = console_name,
                        url       = item['url'],
                    )
                    self.stats['new_matches'] += 1

    # ------------------------------------------------------------------
    # Keyword filters
    # ------------------------------------------------------------------

    @staticmethod
    def _passes_filters(title: str) -> bool:
        """
        Return True if the item title passes both the required and excluded
        keyword checks.

        Rules:
          1. If EXCLUDED_KEYWORDS is non-empty, any match → False.
          2. If REQUIRED_KEYWORDS is non-empty, at least one must match → True;
             if none match → False.
          3. If both lists are empty, everything passes.

        Matching is case-insensitive.
        """
        title_lower = title.lower()

        # --- Exclusion check ---
        for excl in config.EXCLUDED_KEYWORDS:
            if excl.lower() in title_lower:
                return False

        # --- Inclusion check ---
        if config.REQUIRED_KEYWORDS:
            for req in config.REQUIRED_KEYWORDS:
                if req.lower() in title_lower:
                    return True
            return False   # No required keyword found

        return True   # No required keywords configured — allow all


# ---------------------------------------------------------------------------
# Convenience function (used by main.py)
# ---------------------------------------------------------------------------

def run_scan() -> dict:
    """Initialise the DB and run one scan cycle.  Returns the stats dict."""
    database.init_db()
    scanner = EbayScanner()
    return scanner.run()
