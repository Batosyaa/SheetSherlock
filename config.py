from dotenv import load_dotenv
import os

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is not set. Check your .env file.")

_admin_id = os.getenv("ADMIN_ID")
if not _admin_id:
    raise ValueError("ADMIN_ID is not set. Check your .env file.")
try:
    ADMIN_ID: int = int(_admin_id)
except ValueError:
    raise ValueError("ADMIN_ID is not a valid integer. Check your .env file.")


SHEET_ID = os.getenv("SHEET_ID")
CREDS_PATH = os.getenv("CREDS_PATH", "credentials.json")
SHEET_NAME = os.getenv("SHEET_NAME", "Лист1")


COL_BIN = os.getenv("COL_BIN", "БИН")
COL_NAME = os.getenv("COL_NAME", "Проект")
COL_DESCRIPTION = os.getenv("COL_DESCRIPTION", "Описание проекта")
COL_RISK_CURR = os.getenv("COL_RISK_CURR", "степень риска 1 кв.2026")
COL_RISK_PREV = os.getenv("COL_RISK_PREV", "степень риска 4 кв.2025")

# Update this list as new quarters are added to the sheet
QUARTER_COLS = [
    "степень риска 1 кв.25",
    "степень риска 3 кв.25",
    "степень риска 4 кв.2025",
    "степень риска 1 кв.2026",
]

DB_PATH = os.getenv("DB_PATH", "sherlock.db")

AUTH_CACHE_TTL = int(os.getenv("AUTH_CACHE_TTL", 300))

ANOMALY_THRESHOLD = int(os.getenv("ANOMALY_THRESHOLD", "20"))