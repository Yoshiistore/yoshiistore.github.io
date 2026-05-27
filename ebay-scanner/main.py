#!/usr/bin/env python3
"""
main.py — Entry-point for the eBay Console Scanner Bot.

USAGE
-----
    # Run once immediately then exit:
    python main.py --once

    # Run on a loop (default: every 5 minutes, configurable via SCAN_INTERVAL_MINUTES):
    python main.py

    # Custom interval (minutes):
    python main.py --interval 10

    # Quiet mode (WARNING level only):
    python main.py --quiet

ENVIRONMENT / CONFIG
--------------------
    Copy .env.example → .env and fill in your credentials before running.
    All settings are documented in config.py.

RUNNING CONTINUOUSLY
--------------------
    Linux/macOS (background):
        nohup python main.py >> scanner.log 2>&1 &

    With systemd (see README.md for a full unit-file example):
        systemctl start ebay-scanner

    With Docker:
        docker-compose up -d
"""

import argparse
import logging
import signal
import sys
import time

import schedule

import config
import database
from scanner import run_scan
from discord_notifier import send_startup_message, send_error_message


# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

def configure_logging(quiet: bool = False) -> None:
    """Set up console + file logging."""
    level = logging.WARNING if quiet else logging.INFO

    formatter = logging.Formatter(
        fmt='%(asctime)s  %(levelname)-8s  %(name)s — %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(level)

    # File handler (always INFO or above)
    file_handler = logging.FileHandler('scanner.log', encoding='utf-8')
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)   # Let handlers filter individually
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    # Suppress noisy third-party loggers
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('requests').setLevel(logging.WARNING)
    logging.getLogger('schedule').setLevel(logging.WARNING)


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Graceful shutdown
# ---------------------------------------------------------------------------

_shutdown = False


def _handle_signal(signum, frame):
    global _shutdown
    logger.info("Shutdown signal received (signal %d). Finishing current cycle…", signum)
    _shutdown = True


# ---------------------------------------------------------------------------
# Scheduled scan wrapper
# ---------------------------------------------------------------------------

def _scheduled_run() -> None:
    """Wrapper around run_scan() with top-level error handling."""
    try:
        stats = run_scan()
        logger.info(
            "Run complete — new: %d | fetched: %d | seen: %d | filtered: %d",
            stats['new_matches'],
            stats['total_fetched'],
            stats['already_seen'],
            stats['filtered_out'],
        )
    except Exception as exc:
        msg = f"{type(exc).__name__}: {exc}"
        logger.exception("Unhandled error during scan: %s", msg)
        try:
            send_error_message(msg)
        except Exception:
            pass   # Don't let Discord errors mask the real one


# ---------------------------------------------------------------------------
# CLI argument parsing
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='eBay Console Scanner Bot — monitors eBay parts listings.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        '--once',
        action='store_true',
        help='Run a single scan and exit (no loop).',
    )
    parser.add_argument(
        '--interval',
        type=int,
        default=config.SCAN_INTERVAL_MINUTES,
        metavar='MINUTES',
        help=f'Scan interval in minutes (default: {config.SCAN_INTERVAL_MINUTES}).',
    )
    parser.add_argument(
        '--quiet',
        action='store_true',
        help='Suppress INFO logs; show WARNING and above only.',
    )
    parser.add_argument(
        '--no-startup-message',
        action='store_true',
        help='Skip the Discord startup notification.',
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Main entry-point
# ---------------------------------------------------------------------------

def main() -> None:
    args = parse_args()
    configure_logging(quiet=args.quiet)

    logger.info("=" * 60)
    logger.info("  eBay Console Scanner Bot  —  starting up")
    logger.info("=" * 60)

    # Validate critical config
    if not config.DISCORD_WEBHOOK_URL:
        logger.warning(
            "DISCORD_WEBHOOK_URL is not set. Alerts will be logged but NOT sent to Discord."
        )
    if not config.EBAY_APP_ID:
        logger.warning(
            "EBAY_APP_ID not set — falling back to web scraping (less reliable)."
        )

    # Initialise the database
    database.init_db()
    seen_total = database.get_seen_count()
    logger.info("Database ready. %d items tracked so far.", seen_total)

    # Optionally purge very old entries to keep the DB trim
    database.purge_old_items(days=90)

    # Register signal handlers for graceful Ctrl+C / SIGTERM
    signal.signal(signal.SIGINT,  _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    # One-shot mode
    if args.once:
        logger.info("Running single scan (--once mode)…")
        _scheduled_run()
        logger.info("Done.")
        return

    # Send a Discord startup notification
    if not args.no_startup_message:
        send_startup_message(list(config.CONSOLE_SEARCHES.keys()))

    # --- Continuous loop ---
    interval = args.interval
    logger.info("Scheduling scans every %d minute(s). Press Ctrl+C to stop.", interval)

    # Run immediately on startup, then on the schedule
    _scheduled_run()

    schedule.every(interval).minutes.do(_scheduled_run)

    while not _shutdown:
        schedule.run_pending()
        time.sleep(15)   # Poll the scheduler every 15 seconds

    logger.info("Bot stopped cleanly.")


if __name__ == '__main__':
    main()
