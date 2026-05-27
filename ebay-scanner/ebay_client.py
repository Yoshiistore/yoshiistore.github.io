"""
ebay_client.py — eBay data fetching layer.

Provides two strategies:

  1. BrowseAPIClient  (PRIMARY, recommended)
     Uses the official eBay Browse API with OAuth 2.0 Client-Credentials flow.
     Requires EBAY_APP_ID and EBAY_CERT_ID in your .env file.
     Register for free at https://developer.ebay.com/my/keys

  2. ScrapingClient  (FALLBACK)
     Uses requests + BeautifulSoup to scrape eBay search results.
     No API key required, but more fragile and subject to rate-limiting.
     Use only if you cannot get API credentials.

The public interface for both is identical:
    client.search(query, condition_id) -> list[dict]

Each returned dict has at minimum:
    item_id, title, price, currency, shipping_cost, is_buy_now,
    url, image_url
"""

import base64
import logging
import random
import time
from typing import Optional

import requests
from bs4 import BeautifulSoup

import config

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared user-agent pool — rotated on every scraping request
# ---------------------------------------------------------------------------
_USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/605.1.15 '
    '(KHTML, like Gecko) Version/17.4.1 Safari/605.1.15',
]


def _random_delay() -> None:
    """Sleep a random amount between REQUEST_DELAY_MIN and REQUEST_DELAY_MAX seconds."""
    delay = random.uniform(config.REQUEST_DELAY_MIN, config.REQUEST_DELAY_MAX)
    time.sleep(delay)


# ===========================================================================
# Strategy 1 — eBay Browse API  (official, recommended)
# ===========================================================================

class BrowseAPIClient:
    """
    Wraps eBay's Browse API v1.

    Authentication:
      The Browse API uses OAuth 2.0 Client Credentials flow.
      The access token is cached and automatically refreshed when it expires.
    """

    def __init__(self) -> None:
        self._access_token:    Optional[str]   = None
        self._token_expires_at: float          = 0.0
        self._session = requests.Session()

    # ------------------------------------------------------------------
    # Auth helpers
    # ------------------------------------------------------------------

    def _get_access_token(self) -> str:
        """
        Return a valid OAuth access token, refreshing it if necessary.
        Tokens are cached for their full validity window minus a small buffer.
        """
        if self._access_token and time.time() < self._token_expires_at:
            return self._access_token

        logger.debug("Fetching new eBay OAuth token…")
        env = config.EBAY_ENVIRONMENT
        token_url = config.EBAY_OAUTH_URL[env]

        # Basic auth: base64(app_id:cert_id)
        credentials = f"{config.EBAY_APP_ID}:{config.EBAY_CERT_ID}"
        encoded = base64.b64encode(credentials.encode()).decode()

        response = self._session.post(
            token_url,
            headers={
                'Authorization': f'Basic {encoded}',
                'Content-Type':  'application/x-www-form-urlencoded',
            },
            data={
                'grant_type': 'client_credentials',
                'scope':      'https://api.ebay.com/oauth/api_scope',
            },
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()

        self._access_token    = data['access_token']
        # Subtract 60 s buffer so we refresh before actual expiry
        self._token_expires_at = time.time() + int(data.get('expires_in', 7200)) - 60
        logger.debug("New eBay token obtained; expires in ~%ds.", data.get('expires_in', 7200))
        return self._access_token

    # ------------------------------------------------------------------
    # Public search method
    # ------------------------------------------------------------------

    def search(self, query: str, condition_id: str = '7000') -> list[dict]:
        """
        Search eBay for items matching `query` with the given condition ID.

        Args:
            query:        Free-text search string (e.g. "Nintendo Switch charging port broken")
            condition_id: eBay condition ID string. 7000 = "For parts or not working".

        Returns:
            List of normalised item dicts.  Empty list on error.
        """
        env = config.EBAY_ENVIRONMENT
        url = config.EBAY_BROWSE_API_URL[env]

        # Build filter string
        filters = [f"conditionIds:{{{condition_id}}}"]

        # Optional price bounds
        if config.MAX_PRICE > 0:
            filters.append(f"price:[{config.MIN_PRICE}..{config.MAX_PRICE}]")
            filters.append("priceCurrency:USD")

        params = {
            'q':          query,
            'filter':     ','.join(filters),
            'limit':      str(config.MAX_RESULTS_PER_QUERY),
            'sort':       'newlyListed',  # newest first
            'fieldgroups': 'EXTENDED',   # includes shipping details
        }

        try:
            token = self._get_access_token()
            response = self._session.get(
                url,
                headers={
                    'Authorization': f'Bearer {token}',
                    'X-EBAY-C-MARKETPLACE-ID': 'EBAY_US',
                    'Content-Type':  'application/json',
                },
                params=params,
                timeout=20,
            )
            response.raise_for_status()
        except requests.exceptions.HTTPError as exc:
            logger.error("eBay Browse API HTTP error for query '%s': %s", query, exc)
            return []
        except requests.exceptions.RequestException as exc:
            logger.error("eBay Browse API request failed for query '%s': %s", query, exc)
            return []

        data = response.json()
        items_raw = data.get('itemSummaries', [])

        results = []
        for raw in items_raw:
            item = self._normalise(raw)
            if item:
                results.append(item)

        logger.debug("Browse API returned %d items for query: %s", len(results), query)
        _random_delay()
        return results

    # ------------------------------------------------------------------
    # Normalisation
    # ------------------------------------------------------------------

    @staticmethod
    def _normalise(raw: dict) -> Optional[dict]:
        """Convert a raw Browse API item summary dict into our standard format."""
        try:
            item_id = raw.get('itemId', '')
            # Strip the "v1|" prefix eBay sometimes adds
            if '|' in item_id:
                item_id = item_id.split('|')[1]

            # Price
            price_obj = raw.get('price', {})
            price      = float(price_obj.get('value', 0))
            currency   = price_obj.get('currency', 'USD')

            # Shipping cost — use first option if available
            shipping_cost = 0.0
            shipping_options = raw.get('shippingOptions', [])
            if shipping_options:
                sc = shipping_options[0].get('shippingCost', {})
                shipping_cost = float(sc.get('value', 0))

            # Buying options
            buying_options = raw.get('buyingOptions', [])
            is_buy_now = 'FIXED_PRICE' in buying_options

            # Image URL — prefer the largest available
            image_url = ''
            image_obj = raw.get('image', {})
            if image_obj:
                image_url = image_obj.get('imageUrl', '')

            # Additional images as fallback
            if not image_url:
                additional = raw.get('additionalImages', [])
                if additional:
                    image_url = additional[0].get('imageUrl', '')

            return {
                'item_id':       item_id,
                'title':         raw.get('title', '').strip(),
                'price':         price,
                'currency':      currency,
                'shipping_cost': shipping_cost,
                'is_buy_now':    is_buy_now,
                'url':           raw.get('itemWebUrl', ''),
                'image_url':     image_url,
                'condition':     raw.get('condition', ''),
                'condition_id':  raw.get('conditionId', ''),
            }
        except (KeyError, ValueError, TypeError) as exc:
            logger.warning("Could not normalise Browse API item: %s — %s", raw.get('itemId'), exc)
            return None


# ===========================================================================
# Strategy 2 — Web Scraping fallback  (no API key needed)
# ===========================================================================

class ScrapingClient:
    """
    Scrapes eBay search results using requests + BeautifulSoup.

    Use this only when you don't have eBay API credentials.
    It is inherently more fragile than the official API.

    Includes:
      - Rotating user-agents on every request
      - Randomised delays between requests
      - A persistent session with realistic headers
    """

    def __init__(self) -> None:
        self._session = requests.Session()
        self._session.headers.update({
            'Accept':          'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection':      'keep-alive',
            'DNT':             '1',
        })

    def _headers(self) -> dict:
        """Build a fresh header dict with a random user-agent."""
        return {
            **self._session.headers,
            'User-Agent': random.choice(_USER_AGENTS),
        }

    def search(self, query: str, condition_id: str = '7000') -> list[dict]:
        """
        Scrape eBay for items matching `query` with the given condition.

        Args:
            query:        Search string
            condition_id: eBay condition ID (7000 = parts / not working)

        Returns:
            List of normalised item dicts.  Empty list on error.
        """
        params = {
            '_nkw':              query,
            'LH_ItemCondition':  condition_id,
            '_sop':              '10',     # Sort: newly listed
            '_ipg':              '60',     # Items per page
        }

        # Optional price filter
        if config.MAX_PRICE > 0:
            params['_udhi'] = str(int(config.MAX_PRICE))
        if config.MIN_PRICE > 0:
            params['_udlo'] = str(int(config.MIN_PRICE))

        try:
            response = self._session.get(
                config.EBAY_SEARCH_URL,
                params=params,
                headers=self._headers(),
                timeout=20,
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as exc:
            logger.error("Scraping request failed for query '%s': %s", query, exc)
            return []

        results = self._parse_results(response.text)
        logger.debug("Scraping returned %d items for query: %s", len(results), query)
        _random_delay()
        return results

    # ------------------------------------------------------------------
    # HTML parsing
    # ------------------------------------------------------------------

    def _parse_results(self, html: str) -> list[dict]:
        """Parse eBay search result HTML and return list of normalised item dicts."""
        soup = BeautifulSoup(html, 'html.parser')
        items = []

        # eBay wraps each listing in a <li class="s-item …"> element
        for card in soup.select('li.s-item'):
            item = self._parse_card(card)
            if item:
                items.append(item)

        return items

    @staticmethod
    def _parse_card(card) -> Optional[dict]:
        """Extract fields from one eBay result card <li> element."""
        try:
            # --- Title & URL ---
            link_tag = card.select_one('a.s-item__link')
            if not link_tag:
                return None
            raw_url = link_tag.get('href', '')
            title_tag = card.select_one('h3.s-item__title')
            if not title_tag:
                return None
            title = title_tag.get_text(strip=True)

            # Skip eBay's placeholder "Shop on eBay" ghost cards
            if 'shop on ebay' in title.lower():
                return None

            # --- Item ID (from URL) ---
            item_id = ''
            if '/itm/' in raw_url:
                # URL looks like: https://www.ebay.com/itm/123456789012?...
                part = raw_url.split('/itm/')[-1]
                item_id = part.split('?')[0].split('/')[0].strip()

            if not item_id:
                return None

            # --- Price ---
            price = 0.0
            price_tag = card.select_one('span.s-item__price')
            if price_tag:
                price_text = price_tag.get_text(strip=True)
                # Handle ranges like "$10.00 to $20.00" — take the lower bound
                price_text = price_text.split(' to ')[0]
                # Strip non-numeric chars except '.'
                price_digits = ''.join(c for c in price_text if c.isdigit() or c == '.')
                price = float(price_digits) if price_digits else 0.0

            # --- Shipping ---
            shipping_cost = 0.0
            shipping_tag = card.select_one('span.s-item__shipping, span.s-item__freeXDays')
            if shipping_tag:
                ship_text = shipping_tag.get_text(strip=True).lower()
                if 'free' in ship_text:
                    shipping_cost = 0.0
                else:
                    ship_digits = ''.join(c for c in ship_text if c.isdigit() or c == '.')
                    shipping_cost = float(ship_digits) if ship_digits else 0.0

            # --- Buying format (BIN vs Auction) ---
            is_buy_now = False
            format_tag = card.select_one('span.s-item__purchase-options-with-icon')
            if format_tag:
                is_buy_now = 'buy it now' in format_tag.get_text(strip=True).lower()
            # Also check for bid count (indicates auction)
            bid_tag = card.select_one('span.s-item__bids')
            if bid_tag:
                is_buy_now = False  # If bids are shown, it's an auction

            # --- Image ---
            image_url = ''
            img_tag = card.select_one('img.s-item__image-img')
            if img_tag:
                # Prefer data-src (lazy-loaded) over src (placeholder)
                image_url = img_tag.get('data-src') or img_tag.get('src', '')
                # Upgrade image to higher resolution: s-l225 → s-l500
                image_url = image_url.replace('s-l225', 's-l500').replace('s-l140', 's-l500')

            # Clean URL — strip tracking params
            clean_url = raw_url.split('?')[0] if raw_url else ''

            return {
                'item_id':       item_id,
                'title':         title,
                'price':         price,
                'currency':      'USD',
                'shipping_cost': shipping_cost,
                'is_buy_now':    is_buy_now,
                'url':           clean_url,
                'image_url':     image_url,
                'condition':     'For parts or not working',
                'condition_id':  '7000',
            }

        except (AttributeError, ValueError, TypeError) as exc:
            logger.debug("Could not parse scraping card: %s", exc)
            return None


# ===========================================================================
# Factory — pick the right client automatically
# ===========================================================================

def get_ebay_client():
    """
    Return the best available eBay client.

    If both EBAY_APP_ID and EBAY_CERT_ID are set, uses the official Browse API.
    Otherwise falls back to web scraping with a warning.
    """
    if config.EBAY_APP_ID and config.EBAY_CERT_ID:
        logger.info("Using eBay Browse API (official).")
        return BrowseAPIClient()
    else:
        logger.warning(
            "EBAY_APP_ID / EBAY_CERT_ID not set — falling back to web scraping. "
            "For better reliability, add API credentials to your .env file."
        )
        return ScrapingClient()
