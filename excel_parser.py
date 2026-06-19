# For connecting to Google Sheets and caching the dataframe
import gspread
import pandas as pd
import logging
from google.oauth2.service_account import Credentials
from config import SHEET_ID, CREDS_PATH
from gspread.exceptions import APIError, SpreadsheetNotFound
import threading
import json, os

# For time caching the dataframe to avoid hitting Google Sheets API too often
import time

# Column names from config
from config import (
    SHEET_ID,
    SHEET_NAME,
    CREDS_PATH,
    COL_BIN,
    COL_NAME,
    COL_RISK_CURR,
    COL_RISK_PREV,
    COL_DESCRIPTION,
    QUARTER_COLS
)

logger = logging.getLogger(__name__)

_cache = {"df": None, "ts": 0}
CACHE_TTL = 300 # 5 mins

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

_cache_lock = threading.Lock()

# Functions to connect to Google Sheets and fetch data
def _connect() -> gspread.Worksheet:
    creds_json = os.getenv("GOOGLE_CREDS_JSON")
    if creds_json:
        creds_dict = json.loads(creds_json)
        creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    else:
        # Fallback for local dev with credentials.json
        creds = Credentials.from_service_account_file(CREDS_PATH, scopes=SCOPES)
    
    client = gspread.authorize(creds)
    return client.open_by_key(SHEET_ID).worksheet(SHEET_NAME)
 
 
def _fetch_dataframe() -> pd.DataFrame:
    worksheet = _connect()
    values = worksheet.get_all_values()
    
    if not values:
        return pd.DataFrame()
    
    headers = values[0]
    rows = values[1:]
    
    df = pd.DataFrame(rows, columns = headers)
    df.columns = df.columns.str.strip()
    df = df.loc[:, df.columns.str.strip() != ""]
    df = df.dropna(how="all").reset_index(drop=True)
    
    df[COL_BIN] = df[COL_BIN].astype(str).str.strip()
    return df

# Functions to manage the dataframe cache
def get_dataframe() -> pd.DataFrame:
    now = time.monotonic()
    
    with _cache_lock:
        if _cache["df"] is None or (now - _cache["ts"]) > CACHE_TTL:
            logger.info("Cache expired or empty — fetching fresh data from Google Sheets.")
            _cache["df"] = _fetch_dataframe()
            _cache["ts"] = now
        
        logger.info("Sheet columns list: %s", list(_cache["df"].columns))
        return _cache["df"]
 
 
def invalidate_cache() -> None:
    _cache["df"] = None
    _cache["ts"] = 0.0
    logger.info("Cache manually invalidated.")
    

def find_company(bin_query: str) -> pd.Series | None: # Main searching function
    """
    Search for a company by БИН.
    Returns the matching row as a Series, or None if not found.
    """
    try:
        df = get_dataframe()
    except SpreadsheetNotFound:
        logger.error("Spreadsheet not found. Check SHEET_ID in .env.")
        raise
    except APIError as e:
        logger.error(f"Google Sheets API error: {e}")
        raise
    except Exception as e:
        logger.exception("Unexpected error reading sheet.")
        raise
 
    match = df[df[COL_BIN] == bin_query.strip()]
 
    if match.empty:
        return None
 
    return match.iloc[0]


# Extracting data
def get_profile(row: pd.Series) -> dict:
    description = str(row[COL_DESCRIPTION]) if COL_DESCRIPTION in row.index else "Описание недоступно"
    return {
        "name": str(row[COL_NAME]),
        "bin": str(row[COL_BIN]),
        "decription": description if description.lower() not in ("nan", "") else "Описание недоступно",
        "risk_curr": str(row[COL_RISK_CURR]),
        "risk_prev": str(row[COL_RISK_PREV])
    }
    
def get_history(row: pd.Series) -> list[tuple[str, str]]:
    history = []
    
    for col in QUARTER_COLS:
        if col not in row.index:
            continue
        value = row[col]
        if pd.isna(value) or str(value).strip() == "":
            continue
        history.append((col, str(value).strip()))
    return history
