"""
audit.py -- audit logging and lightweight anomaly detection.

The audit table is append-only. Handlers write events here, and admin tooling in
later phases can read the same table for reports.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import Any

from config import ANOMALY_THRESHOLD
from db import get_connection

logger = logging.getLogger(__name__)

ACTION_QUERY_BIN = "query_bin"
ANOMALY_WINDOW_MINUTES = 60

_WRITE_LOCK = threading.Lock()


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _utc_cutoff(minutes: int) -> str:
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    return cutoff.replace(microsecond=0).isoformat()


def log_event(user_id: int, action: str, detail: str | None = None) -> None:
    with _WRITE_LOCK:
        conn = get_connection()
        try:
            conn.execute(
                """
                INSERT INTO audit_log (user_id, action, detail, ts)
                VALUES (?, ?, ?, ?)
                """,
                (user_id, action, detail, _utc_now()),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            logger.exception(
                "Failed to write audit event action=%s user_id=%s.", action, user_id
            )
            raise
        finally:
            conn.close()


def count_recent_events(
    user_id: int,
    action: str,
    minutes: int = ANOMALY_WINDOW_MINUTES,
) -> int:
    conn = get_connection()
    try:
        row = conn.execute(
            """
            SELECT COUNT(*) AS event_count
            FROM audit_log
            WHERE user_id = ?
              AND action = ?
              AND ts >= ?
            """,
            (user_id, action, _utc_cutoff(minutes)),
        ).fetchone()
        return int(row["event_count"])
    finally:
        conn.close()


def get_audit_events(limit: int = 20, user_id: int | None = None) -> list[dict[str, Any]]:
    limit = max(1, min(limit, 100))

    conn = get_connection()
    try:
        if user_id is None:
            rows = conn.execute(
                """
                SELECT id, user_id, action, detail, ts
                FROM audit_log
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT id, user_id, action, detail, ts
                FROM audit_log
                WHERE user_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (user_id, limit),
            ).fetchall()

        return [dict(row) for row in rows]
    finally:
        conn.close()


def check_query_anomaly(user_id: int) -> int | None:
    """
    Return the recent query count when the user just reaches the threshold.

    Alerting only at the threshold avoids sending a new admin alert for every
    additional query after a user is already over the limit.
    """
    if ANOMALY_THRESHOLD <= 0:
        return None

    count = count_recent_events(user_id, ACTION_QUERY_BIN)
    if count == ANOMALY_THRESHOLD:
        return count
    return None
