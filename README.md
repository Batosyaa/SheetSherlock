# SheetSherlock

A Telegram bot that searches company risk data from a Google Sheet by БИН and returns structured, readable results in chat.

---

## Table of contents

- [How it works](#how-it-works)
- [Project structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Setup](#setup)
  - [1. Create the Telegram bot](#1-create-the-telegram-bot)
  - [2. Set up Google Cloud](#2-set-up-google-cloud)
  - [3. Share the Google Sheet](#3-share-the-google-sheet)
  - [4. Clone and install](#4-clone-and-install)
  - [5. Configure .env](#5-configure-env)
- [Running locally](#running-locally)
- [Running tests](#running-tests)
- [Deployment](#deployment)
  - [Option A — VPS with systemd](#option-a--vps-with-systemd)
  - [Option B — Railway](#option-b--railway)
- [Updating the data](#updating-the-data)
- [Troubleshooting](#troubleshooting)

---

## How it works

```
User sends БИН → Bot searches Google Sheet → Returns company profile
                                           → "История" button → Full risk history
                                           → "Заново" button  → Start over
```

Data is fetched from Google Sheets via the Sheets API using a service account and cached locally for **5 minutes** to stay within API rate limits and keep responses fast.

---

## Project structure

```
sheetsherlock/
├── main.py            # Entry point — builds the app and registers handlers
├── handlers.py        # All Telegram handler functions
├── sheet_parser.py    # Google Sheets connection, caching, search, data extraction
├── strings.py         # All bot message templates and risk icon mapping
├── config.py          # Loads environment variables from .env
├── .env               # Secrets and column config (never commit to Git)
├── credentials.json   # Google service account key (never commit to Git)
├── test_parser.py     # Unit tests for sheet_parser
├── test_handlers.py   # Unit tests for strings and handler utilities
└── requirements.txt   # Python dependencies
```

---

## Prerequisites

- Python 3.11+
- A Telegram account
- A Google account with access to Google Cloud Console
- The target Google Sheet (you need edit access to share it)

---

## Setup

### 1. Create the Telegram bot

1. Open Telegram and search for `@BotFather`
2. Send `/newbot` and follow the prompts
3. Give it the name **SheetSherlock** and a unique username (e.g. `@SheetSherlockBot`)
4. Copy the **API token** — you'll need it for `.env`

---

### 2. Set up Google Cloud

1. Go to [console.cloud.google.com](https://console.cloud.google.com) and create a new project (e.g. `sheetsherlock`)

2. In the sidebar go to **APIs & Services → Library**, search for **Google Sheets API** and click **Enable**

3. Go to **APIs & Services → Credentials → Create Credentials → Service Account**
   - Give it any name (e.g. `sheetsherlock-reader`)
   - Role: **Viewer** is enough
   - Click **Done**

4. Click the newly created service account → **Keys** tab → **Add Key → Create new key → JSON**
   - A file downloads automatically — rename it to `credentials.json` and move it to the project root
   - The file contains a `client_email` field — copy that address, you'll need it in the next step

> ⚠️ Never commit `credentials.json` to Git. It is listed in `.gitignore`.

---

### 3. Share the Google Sheet

1. Open your Google Sheet
2. Click **Share**
3. Paste the `client_email` from `credentials.json` (looks like `name@project.iam.gserviceaccount.com`)
4. Set permission to **Viewer**
5. Click **Send**

The bot will now be able to read the sheet without any user login.

---

### 4. Clone and install

```bash
git clone https://github.com/your-org/sheetsherlock.git
cd sheetsherlock

python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

pip install -r requirements.txt
```

**requirements.txt**
```
python-telegram-bot==22.7
gspread==6.1.4
google-auth==2.35.0
pandas==2.2.3
openpyxl==3.1.5
python-dotenv==1.0.1
```

---

### 5. Configure .env

Create a `.env` file in the project root:

```env
# Telegram
BOT_TOKEN=123456789:AABBCCxxxxxxxxxxx

# Google Sheets
SHEET_ID=1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms
CREDS_PATH=credentials.json

# Column names — must match the header row in your sheet exactly
COL_BIN=БИН
COL_NAME=Наименование
COL_RISK_CURR=Риск Q2 2026
COL_RISK_PREV=Риск Q1 2026
```

**Where to find the Sheet ID:**
In the Google Sheets URL — the long string between `/d/` and `/edit`:
```
https://docs.google.com/spreadsheets/d/▶ 1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms ◀/edit
```

**Column names** must match your sheet's header row character-for-character, including spaces and capitalisation. If the column is called `БИН ` with a trailing space, add the space.

> Each quarter, update `COL_RISK_CURR` and `COL_RISK_PREV` in `.env` and restart the bot. No code changes needed.

---

## Running locally

```bash
source venv/bin/activate
python main.py
```

You should see:
```
2026-06-09 12:00:00 | INFO | __main__ | SheetSherlock is running...
```

Open Telegram, find your bot, and send `/start`.

---

## Running tests

Tests use mocks — no real Google Sheets connection or Telegram token required.

```bash
# Parser tests (Google Sheets search and data extraction)
python test_parser.py

# Handler tests (message formatting and string utilities)
python test_handlers.py
```

Expected output:
```
✓ find_company — existing БИН found
✓ find_company — unknown БИН returns None
✓ get_profile — returns correct name and risk levels
✓ get_history — returns all 4 quarters in order
✓ get_history — skips empty quarter values
✓ find_company — handles БИН with leading/trailing spaces

6/6 tests passed.

✓ risk_icon — Высокий → 🔴
...
10/10 tests passed.
```

---

## Deployment

### Option A — VPS with systemd

1. Upload project files to your server (e.g. via `scp` or `git clone`)
2. Upload `credentials.json` manually — do not put it in the repo
3. Set up the virtual environment and install dependencies on the server
4. Create a systemd service file:

```bash
sudo nano /etc/systemd/system/sheetsherlock.service
```

```ini
[Unit]
Description=SheetSherlock Telegram Bot
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/sheetsherlock
ExecStart=/home/ubuntu/sheetsherlock/venv/bin/python main.py
Restart=always
RestartSec=5
EnvironmentFile=/home/ubuntu/sheetsherlock/.env

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable sheetsherlock
sudo systemctl start sheetsherlock

# Check status
sudo systemctl status sheetsherlock

# View live logs
sudo journalctl -u sheetsherlock -f
```

---

### Option B — Railway

1. Push your code to GitHub (**without** `.env` and `credentials.json`)
2. Create a new project on [railway.app](https://railway.app) and connect your repo
3. Add all `.env` variables in Railway's **Variables** tab
4. For `credentials.json`, paste its entire contents as a single environment variable:

```env
GOOGLE_CREDS_JSON={"type":"service_account","project_id":"..."}
```

Then update `config.py` and `sheet_parser.py` to load it from the environment:

```python
# In sheet_parser.py, replace Credentials.from_service_account_file() with:
import json, os
from google.oauth2.service_account import Credentials

creds_dict = json.loads(os.getenv("GOOGLE_CREDS_JSON"))
creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
```

5. Railway will automatically detect `requirements.txt` and build the project

---

## Updating the data

| What changed | What to do |
|---|---|
| New quarter column added to the sheet | Add the column name to `QUARTER_COLS` in `config.py` and update `COL_RISK_CURR` / `COL_RISK_PREV` in `.env`, then restart the bot |
| Column renamed in the sheet | Update the matching variable in `.env`, restart the bot |
| Data updated in the sheet | Nothing — the cache refreshes automatically every 5 minutes |
| Cache feels stale and you need immediate refresh | Restart the bot — this clears the in-memory cache |
| Sheet moved to a new Google account | Share the new sheet with the same service account email and update `SHEET_ID` in `.env` |

---

## Troubleshooting

**Bot doesn't respond at all**
- Check that `BOT_TOKEN` in `.env` is correct
- Confirm the bot process is running: `sudo systemctl status sheetsherlock`
- Check logs: `sudo journalctl -u sheetsherlock -f`

**"Не удалось получить данные из таблицы" error**
- Confirm the service account email has been shared on the Google Sheet with Viewer access
- Verify `SHEET_ID` in `.env` is correct
- Check Google Cloud Console → APIs & Services → confirm the Sheets API is enabled

**Company is in the sheet but returns "не найдено"**
- The `COL_BIN` column name in `.env` must match the sheet header exactly
- Check if БИН values in the sheet have leading/trailing spaces or are stored as numbers not strings
- Run `python test_parser.py` — if tests pass, the issue is with the real sheet data format

**MarkdownV2 formatting errors in messages**
- If a company name or risk level contains special characters like `-`, `.`, `(`, `)`, the `_escape()` function in `handlers.py` should handle them automatically
- If you add new message templates in `strings.py`, make sure dynamic values are wrapped with `_escape()`

**Bot stops responding after a while**
- This usually means the process crashed; systemd will restart it automatically within 5 seconds
- Check logs for the error: `sudo journalctl -u sheetsherlock -n 50`