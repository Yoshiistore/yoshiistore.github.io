# 🎮 eBay Console Scanner Bot

A Python bot that continuously monitors eBay for **video game consoles listed "For parts or not working"** where the primary fault is a **broken/damaged charging port, power jack, or USB-C port** — exactly the kind of cheap, fixable flip.

Sends rich **Discord notifications** the instant a new matching listing appears.

---

## ✨ Features

| Feature | Detail |
|---|---|
| **Targeted consoles** | Nintendo Switch, PS5, Xbox Series X/S, Steam Deck |
| **Condition filter** | eBay Condition ID 7000 — "For parts or not working" |
| **Keyword inclusion** | Only alerts on titles mentioning charging/port issues |
| **Keyword exclusion** | Silently skips water damage, crushed, beyond repair, etc. |
| **Deduplication** | SQLite DB tracks every seen item — no duplicate alerts |
| **Discord alerts** | Rich embeds with title, price, shipping, format, image & link |
| **Dual fetch strategy** | eBay Browse API (official, primary) → scraping fallback |
| **Scheduled loop** | Runs every N minutes (default 5), configurable |
| **Graceful shutdown** | Handles Ctrl+C / SIGTERM cleanly |

---

## 📂 Project Structure

```
ebay-scanner/
├── config.py            ← All settings (loaded from .env)
├── database.py          ← SQLite "seen items" tracker
├── ebay_client.py       ← eBay Browse API + scraping fallback
├── discord_notifier.py  ← Discord webhook rich embeds
├── scanner.py           ← Core orchestration logic
├── main.py              ← Entry-point + scheduler loop
├── requirements.txt
├── .env.example         ← Template — copy to .env and fill in
└── .gitignore
```

---

## 🚀 Quick Start

### 1 — Prerequisites

- Python **3.10** or newer
- A **Discord server** where you can create webhooks
- (Optional but recommended) A **free eBay Developer account** for API access

---

### 2 — Install Dependencies

```bash
cd ebay-scanner
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

---

### 3 — Configure Your Credentials

```bash
cp .env.example .env
```

Open `.env` and fill in:

#### Discord Webhook (required)

1. Open Discord → your server → **Server Settings → Integrations → Webhooks**
2. Click **New Webhook**, choose a channel, copy the URL
3. Paste it as `DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...`

#### eBay API Credentials (optional but recommended)

The official eBay Browse API is faster and more reliable than scraping. It's **free**.

1. Go to [developer.ebay.com/my/keys](https://developer.ebay.com/my/keys)
2. Sign in with your eBay account
3. Click **Get a Free Key** → create a **Production** keyset
4. Copy **App ID (Client ID)** → `EBAY_APP_ID=`
5. Copy **Cert ID (Client Secret)** → `EBAY_CERT_ID=`

> **No API keys?** Leave both blank — the bot automatically falls back to web scraping.  
> Scraping works but is slower, less stable, and may occasionally miss listings.

---

### 4 — Run the Bot

```bash
# Continuous mode (runs every 5 minutes by default):
python main.py

# Run once and exit (great for cron or testing):
python main.py --once

# Custom scan interval:
python main.py --interval 10

# See all options:
python main.py --help
```

On startup the bot will:
1. Send a **green startup embed** to your Discord channel
2. Immediately run the first scan
3. Continue scanning on the configured interval

---

## ⚙️ Customisation

All customisation lives in `config.py` (or via `.env`).

### Add / remove consoles

Edit `CONSOLE_SEARCHES` in `config.py`:

```python
CONSOLE_SEARCHES = {
    'Game Boy Advance': {
        'queries': [
            'Game Boy Advance broken charging parts',
        ],
        'color':  0x8B5CF6,   # Purple
        'emoji':  '🟣',
    },
    # ...
}
```

### Adjust keywords

```python
# Add "dc jack" to required keywords:
REQUIRED_KEYWORDS = [
    'charging port', 'charge port', 'usb-c', 'dc jack', ...
]

# Add "flood" to exclusions:
EXCLUDED_KEYWORDS = [
    'water damage', 'flood', ...
]
```

### Change price ceiling

In `.env`:
```
MAX_PRICE=150
```

---

## 📬 Discord Alert Preview

```
🟥 Nintendo Switch — Parts Listing Found!
Nintendo Switch Broken USB-C Charging Port - For Parts

💰 Price      🚚 Shipping   📦 Total Est.  🛒 Format    🔧 Condition
$34.99        ✅ Free       $34.99         Buy It Now   For parts or not working

🔗 View Listing — [Click to open on eBay]
```

*(With item thumbnail on the right side of the embed)*

---

## 🔄 Running Continuously

### Background process (Linux/macOS)

```bash
nohup python main.py >> scanner.log 2>&1 &
echo $! > bot.pid         # Save the PID so you can kill it later
kill $(cat bot.pid)        # Stop the bot
```

### systemd Service (Linux — runs on boot, restarts on crash)

Create `/etc/systemd/system/ebay-scanner.service`:

```ini
[Unit]
Description=eBay Console Scanner Bot
After=network-online.target

[Service]
Type=simple
User=youruser
WorkingDirectory=/path/to/ebay-scanner
ExecStart=/path/to/ebay-scanner/venv/bin/python main.py
Restart=on-failure
RestartSec=30
StandardOutput=append:/path/to/ebay-scanner/scanner.log
StandardError=inherit

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable ebay-scanner
sudo systemctl start ebay-scanner
sudo systemctl status ebay-scanner
```

### cron (runs every 5 minutes)

```bash
crontab -e
```
Add:
```
*/5 * * * * cd /path/to/ebay-scanner && /path/to/venv/bin/python main.py --once >> scanner.log 2>&1
```

> **Tip:** Use `--once` with cron so cron handles the scheduling. Use the continuous loop (`python main.py`) with systemd or nohup.

---

## 🐋 Docker (optional)

Create a `Dockerfile` in the `ebay-scanner/` directory:

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "main.py"]
```

```bash
docker build -t ebay-scanner .
docker run -d \
  --name ebay-scanner \
  --restart unless-stopped \
  -v $(pwd)/seen_items.db:/app/seen_items.db \
  --env-file .env \
  ebay-scanner
```

---

## 🛠 Troubleshooting

| Problem | Fix |
|---|---|
| No Discord alerts | Check `DISCORD_WEBHOOK_URL` in `.env`. Run `python main.py --once` and watch the console. |
| eBay API 401 errors | Verify `EBAY_APP_ID` and `EBAY_CERT_ID` are correct and the keyset is **Production**, not Sandbox. |
| Bot finds 0 items | eBay may have temporarily rate-limited scraping. Try again in 10 min or add API credentials. |
| Duplicate alerts | Check `seen_items.db` exists and isn't deleted between runs. |
| Too many alerts | Lower `MAX_PRICE` or tighten `REQUIRED_KEYWORDS` in `config.py`. |
| Missing listings | Add more queries to `CONSOLE_SEARCHES` or broaden `REQUIRED_KEYWORDS`. |

---

## 📋 Logs

The bot writes logs to both the console and `scanner.log`:

```
2025-05-27 14:32:01  INFO      __main__ — === Scan cycle started ===
2025-05-27 14:32:01  INFO      scanner  — Scanning: Nintendo Switch
2025-05-27 14:32:03  INFO      scanner  — ✅ NEW: [Nintendo Switch] Nintendo Switch Broken USB C Charging Port For Parts — $34.99
2025-05-27 14:32:03  INFO      discord… — Discord alert sent for item 387654321098
2025-05-27 14:32:07  INFO      __main__ — Run complete — new: 1 | fetched: 43 | seen: 312 | filtered: 18
```

---

## ⚖️ Legal & Ethics

- This bot is for **personal, non-commercial use**.
- Comply with [eBay's API Terms of Use](https://developer.ebay.com/api-docs/static/ebay-apis-terms.html) when using the official API.
- When using the scraping fallback, respect rate limits — don't set `SCAN_INTERVAL_MINUTES` below 5.
- Never use this bot to artificially inflate prices, snipe bids unfairly, or violate eBay's policies.
