"""
discord_notifier.py — Discord Webhook integration for the eBay Console Scanner Bot.

Sends rich embed messages to a Discord channel when a matching listing is found.

Embed layout:
  ┌────────────────────────────────────────────────────────┐
  │ [Thumbnail]  🟥 Nintendo Switch — eBay Parts Alert     │
  │              Title of the eBay listing                 │
  │                                                        │
  │  💰 Price      🚚 Shipping   🛒 Format   🔧 Condition  │
  │  $XX.XX        Free          Buy It Now  Parts         │
  │                                                        │
  │  🔗 View Listing                                       │
  └────────────────────────────────────────────────────────┘
"""

import logging
from datetime import datetime, timezone
from typing import Optional

import requests

import config

logger = logging.getLogger(__name__)


def send_discord_alert(
    item: dict,
    console_name: str,
) -> bool:
    """
    POST a Discord embed to the configured webhook URL.

    Args:
        item:         Normalised item dict from ebay_client (must contain:
                      item_id, title, price, currency, shipping_cost,
                      is_buy_now, url, image_url).
        console_name: Human-readable console name (e.g. "Nintendo Switch").

    Returns:
        True if the webhook call succeeded (HTTP 2xx), False otherwise.
    """
    if not config.DISCORD_WEBHOOK_URL:
        logger.warning("DISCORD_WEBHOOK_URL is not set — skipping notification.")
        return False

    console_cfg = config.CONSOLE_SEARCHES.get(console_name, {})
    emoji       = console_cfg.get('emoji', '🎮')
    color       = console_cfg.get('color', 0x7289DA)  # Discord blurple as default

    # Build human-readable price strings
    price_str    = _format_price(item['price'], item.get('currency', 'USD'))
    shipping_str = _format_shipping(item['shipping_cost'], item.get('currency', 'USD'))
    total_cost   = item['price'] + item['shipping_cost']
    total_str    = _format_price(total_cost, item.get('currency', 'USD'))

    # Buying format label
    format_label = '**Buy It Now**' if item.get('is_buy_now') else '🔨 **Auction**'

    # Timestamp
    now_utc = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')

    # Construct the embed payload
    embed = {
        'title':       f"{emoji} {console_name} — Parts Listing Found!",
        'description': f"**{item['title']}**",
        'url':         item['url'],
        'color':       color,
        'fields': [
            {
                'name':   '💰 Price',
                'value':  price_str,
                'inline': True,
            },
            {
                'name':   '🚚 Shipping',
                'value':  shipping_str,
                'inline': True,
            },
            {
                'name':   '📦 Total Est.',
                'value':  total_str,
                'inline': True,
            },
            {
                'name':   '🛒 Format',
                'value':  format_label,
                'inline': True,
            },
            {
                'name':   '🔧 Condition',
                'value':  item.get('condition', 'For parts or not working'),
                'inline': True,
            },
            {
                'name':   '🆔 Item ID',
                'value':  f"`{item['item_id']}`",
                'inline': True,
            },
            {
                'name':   '🔗 View Listing',
                'value':  f"[Click to open on eBay]({item['url']})",
                'inline': False,
            },
        ],
        'footer': {
            'text': f"eBay Console Scanner • {now_utc}",
        },
    }

    # Attach image thumbnail if available
    if item.get('image_url'):
        embed['thumbnail'] = {'url': item['image_url']}

    payload = {
        'username':   'eBay Console Scanner',
        'avatar_url': 'https://upload.wikimedia.org/wikipedia/commons/thumb/1/1b/EBay_logo.svg/800px-EBay_logo.svg.png',
        'embeds':     [embed],
    }

    try:
        response = requests.post(
            config.DISCORD_WEBHOOK_URL,
            json=payload,
            timeout=10,
        )
        # Discord returns 204 No Content on success
        if response.status_code in (200, 204):
            logger.info("Discord alert sent for item %s ('%s').", item['item_id'], item['title'][:60])
            return True
        else:
            logger.error(
                "Discord webhook returned HTTP %d for item %s. Body: %s",
                response.status_code, item['item_id'], response.text[:200],
            )
            return False
    except requests.exceptions.RequestException as exc:
        logger.error("Failed to send Discord alert for item %s: %s", item['item_id'], exc)
        return False


def send_startup_message(console_names: list[str]) -> None:
    """
    Send a simple startup notification to Discord so you know the bot is alive.
    Fires once when the bot starts.
    """
    if not config.DISCORD_WEBHOOK_URL:
        return

    consoles_formatted = '\n'.join(f"  • {name}" for name in console_names)
    embed = {
        'title':       '🤖 eBay Console Scanner — Started',
        'description': (
            f"Bot is now scanning eBay every **{config.SCAN_INTERVAL_MINUTES} minutes** "
            f"for broken-port video game console parts listings.\n\n"
            f"**Target consoles:**\n{consoles_formatted}\n\n"
            f"**Condition filter:** For parts or not working (ID 7000)\n"
            f"**Max price:** ${config.MAX_PRICE:.2f}"
        ),
        'color': 0x57F287,   # Discord green
        'footer': {
            'text': f"Started at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        },
    }

    payload = {
        'username': 'eBay Console Scanner',
        'embeds':   [embed],
    }

    try:
        requests.post(config.DISCORD_WEBHOOK_URL, json=payload, timeout=10)
    except requests.exceptions.RequestException as exc:
        logger.warning("Could not send startup message to Discord: %s", exc)


def send_error_message(error_summary: str) -> None:
    """
    Send a warning embed to Discord when the bot encounters a significant error.
    Keeps you informed without spamming — only call for important failures.
    """
    if not config.DISCORD_WEBHOOK_URL:
        return

    embed = {
        'title':       '⚠️ eBay Console Scanner — Error',
        'description': f"```\n{error_summary[:1800]}\n```",
        'color':       0xED4245,   # Discord red
        'footer': {
            'text': f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        },
    }
    payload = {'username': 'eBay Console Scanner', 'embeds': [embed]}

    try:
        requests.post(config.DISCORD_WEBHOOK_URL, json=payload, timeout=10)
    except requests.exceptions.RequestException:
        pass  # Silent — we're already handling an error


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _format_price(amount: float, currency: str = 'USD') -> str:
    """Format a price nicely, e.g. '$42.99'."""
    symbols = {'USD': '$', 'GBP': '£', 'EUR': '€', 'CAD': 'C$', 'AUD': 'A$'}
    symbol = symbols.get(currency, currency + ' ')
    return f"{symbol}{amount:,.2f}"


def _format_shipping(cost: float, currency: str = 'USD') -> str:
    """Format shipping cost, or 'Free Shipping' when cost is zero."""
    if cost == 0.0:
        return '✅ Free'
    return _format_price(cost, currency)
