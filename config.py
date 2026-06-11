from dotenv import load_dotenv
import os
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
SHEET_ID = os.getenv("SHEET_ID")
CREDS_PATH = os.getenv("CREDS_PATH", "credentials.json")
SHEET_NAME = os.getenv("SHEET_NAME", "sheet1")


COL_BIN = os.getenv("COL_BIN", "БИН")
COL_NAME = os.getenv("COL_NAME", "Наименование")
COL_RISK_CURR = os.getenv("COL_RISK_CURR", "степень риска 1 кв.2026")
COL_RISK_PREV = os.getenv("COL_RISK_PREV", "степень риска 4 кв.2025")

# Update this list as new quarters are added to the sheet
QUARTER_COLS = [
    "степень риска 1 кв.2025",
    "степень риска 2 кв.2025",
    "степень риска 3 кв.2025",
    "степень риска 4 кв.2025",
    "степень риска 1 кв.2026",
    "степень риска 2 кв.2026",
]