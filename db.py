"""
db.py — Database initialisation and connection factory.

Responsibilities:
  - Define the SQLite schema (users, audit_log).
  - Expose get_connection() for use by auth.py and audit.py.
  - Expose init_db() called once at bot startup.

Deliberately contains NO business logic — CRUD lives in auth.py / audit.py.
"""

import sqlite3
import logging

from config import DB_PATH

logger = logging.getLogger(__name__)


def get_connection() -> sqlite3.Connection:
    """
    Open a new SQLite connection.

    WAL journal mode is set on every connection so concurrent reads
    don't block writes and vice-versa — important because python-telegram-bot
    runs handlers in a thread pool.

    Caller is responsible for closing the connection (use as a context manager
    or call .close() explicitly).
    """
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row          # rows behave like dicts
    conn.execute("PRAGMA journal_mode=WAL") # better concurrent access
    conn.execute("PRAGMA foreign_keys=ON")  # enforce FK constraints
    return conn


def init_db() -> None:
    """
    Create tables if they don't already exist.
    Safe to call on every startup — all statements use IF NOT EXISTS.
    """
    conn = get_connection()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id      INTEGER PRIMARY KEY,   -- Telegram numeric ID (permanent key)
                first_name   TEXT,
                username     TEXT,                  -- stored for display only; NEVER used as key
                status       TEXT NOT NULL DEFAULT 'pending',
                                                    -- 'pending' | 'approved' | 'rejected' | 'revoked'
                requested_at TEXT NOT NULL,         -- ISO-8601 UTC timestamp
                approved_at  TEXT,                  -- NULL until actioned
                approved_by  INTEGER                -- admin user_id who approved/rejected/revoked
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id  INTEGER NOT NULL,
                action   TEXT    NOT NULL,  -- 'query_bin' | 'approved' | 'rejected' | 'revoked'
                detail   TEXT,              -- BIN value queried, or free-text reason
                ts       TEXT    NOT NULL   -- ISO-8601 UTC timestamp
            )
        """)

        conn.commit()
        logger.info("Database ready at '%s'.", DB_PATH)

    except Exception:
        conn.rollback()
        logger.exception("Failed to initialise database.")
        raise

    finally:
        conn.close()