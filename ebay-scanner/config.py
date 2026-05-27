"""
config.py — Central configuration for the eBay Console Scanner Bot.

HOW TO CONFIGURE:
  1. Copy .env.example to .env in this same directory.
  2. Fill in your eBay API credentials and Discord Webhook URL.
  3. Tweak CONSOLE_SEARCHES, REQUIRED_KEYWORDS, EXCLUDED_KEYWORDS as needed.

eBay Developer Account (free):
  https://developer.ebay.com/my/keys → create a Keyset → grab App ID & Cert ID

Discord Webhook:
  Server Settings → Integrations → Webhooks → New Webhook → Copy URL
"""

import os
from dotenv import load_dotenv

# Load .env file from the same directory as this script
_env_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(_env_path)


# ---------------------------------------------------------------------------
# eBay API Credentials  (set these in .env)
# ---------------------------------------------------------------------------
EBAY_APP_ID  = os.getenv('EBAY_APP_ID',  '')   # Client ID  (e.g. "YourName-Bot-PRD-…")
EBAY_CERT_ID = os.getenv('EBAY_CERT_ID', '')   # Client Secret / Cert ID

# Use 'production' normally; 'sandbox' for testing with sandbox credentials
EBAY_ENVIRONMENT = os.getenv('EBAY_ENVIRONMENT', 'production')


# ---------------------------------------------------------------------------
# Discord Configuration  (set this in .env)
# ---------------------------------------------------------------------------
DISCORD_WEBHOOK_URL = os.getenv('DISCORD_WEBHOOK_URL', '')


# ---------------------------------------------------------------------------
# Scan Settings
# ---------------------------------------------------------------------------
SCAN_INTERVAL_MINUTES = int(os.getenv('SCAN_INTERVAL_MINUTES', '5'))   # How often to scan
MAX_RESULTS_PER_QUERY = int(os.getenv('MAX_RESULTS_PER_QUERY', '50'))  # eBay results per search
MAX_PRICE             = float(os.getenv('MAX_PRICE', '300'))            # Skip listings above this
MIN_PRICE             = float(os.getenv('MIN_PRICE', '0'))              # Skip listings below this (0=off)


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------
DB_PATH = os.getenv('DB_PATH', os.path.join(os.path.dirname(__file__), 'seen_items.db'))


# ---------------------------------------------------------------------------
# Target Consoles
# Each entry maps a human-readable console name to:
#   queries  – search strings sent to eBay (kept focused so results are relevant)
#   color    – Discord embed sidebar color (hex int)
#   emoji    – prefix shown in Discord notification
# ---------------------------------------------------------------------------
CONSOLE_SEARCHES = {
    'Nintendo Switch': {
        'queries': [
            'Nintendo Switch broken charging port parts',
            'Nintendo Switch USB-C port damaged parts',
            'Nintendo Switch charge port bent pins parts',
        ],
        'color':  0xE4000F,   # Nintendo red
        'emoji':  '🟥',
    },
    'PlayStation 5': {
        'queries': [
            'PS5 broken power port parts not working',
            'PlayStation 5 USB port broken parts',
            'PS5 power jack damaged parts',
        ],
        'color':  0x003791,   # PlayStation blue
        'emoji':  '🔵',
    },
    'Xbox Series X': {
        'queries': [
            'Xbox Series X broken power jack parts not working',
            'Xbox Series X port damaged parts repair',
        ],
        'color':  0x107C10,   # Xbox green
        'emoji':  '🟢',
    },
    'Xbox Series S': {
        'queries': [
            'Xbox Series S broken power jack parts not working',
            'Xbox Series S port damaged parts repair',
        ],
        'color':  0x107C10,
        'emoji':  '🟢',
    },
    'Steam Deck': {
        'queries': [
            'Steam Deck broken charging port parts not working',
            'Steam Deck USB-C port damaged parts',
            'Steam Deck charge port bent pins parts',
        ],
        'color':  0x1A9FFF,   # Steam blue
        'emoji':  '🔷',
    },
}


# ---------------------------------------------------------------------------
# Keyword Filters  (matched against item TITLE, case-insensitive)
# ---------------------------------------------------------------------------

# At least ONE of these must appear in the title for the item to be reported.
# Leave empty [] to disable this filter (report all "parts" listings).
REQUIRED_KEYWORDS = [
    'charging port',
    'charge port',
    'usb-c',
    'usb c',
    'usb port',
    'bent pin',
    "won't charge",
    'wont charge',
    'does not charge',
    "doesn't charge",
    'doesnt charge',
    'no charge',
    'not charging',
    'power jack',
    'power port',
    'power plug',
    'charger port',
    'charging issue',
    'dock port',
]

# If ANY of these appear in the title the item is silently skipped.
EXCLUDED_KEYWORDS = [
    'water damage',
    'water damaged',
    'liquid damage',
    'flood',
    'run over',
    'snapped in half',
    'snapped in two',
    'crushed',
    'burned',
    'burnt',
    'fire damage',
    'fire damaged',
    'motherboard fried',
    'fried motherboard',
    'board fried',
    'completely destroyed',
    'beyond repair',
    'hit by car',
    'ran over',
]


# ---------------------------------------------------------------------------
# eBay Condition
# ---------------------------------------------------------------------------
PARTS_CONDITION_ID = '7000'   # "For parts or not working"


# ---------------------------------------------------------------------------
# eBay API Endpoints  (do not change unless eBay changes them)
# ---------------------------------------------------------------------------
EBAY_OAUTH_URL = {
    'production': 'https://api.ebay.com/identity/v1/oauth2/token',
    'sandbox':    'https://api.sandbox.ebay.com/identity/v1/oauth2/token',
}
EBAY_BROWSE_API_URL = {
    'production': 'https://api.ebay.com/buy/browse/v1/item_summary/search',
    'sandbox':    'https://api.sandbox.ebay.com/buy/browse/v1/item_summary/search',
}

# Scraping fallback base URL
EBAY_SEARCH_URL = 'https://www.ebay.com/sch/i.html'


# ---------------------------------------------------------------------------
# Request Delays (seconds) — be polite to eBay's servers
# ---------------------------------------------------------------------------
REQUEST_DELAY_MIN = float(os.getenv('REQUEST_DELAY_MIN', '1.5'))
REQUEST_DELAY_MAX = float(os.getenv('REQUEST_DELAY_MAX', '3.5'))
