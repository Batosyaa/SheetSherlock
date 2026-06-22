"""
auth.py -- user registry and access checks.

Unknown users are registered as pending and the admin is notified once.
Approved users may use protected handlers; rejected/revoked users are blocked.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Awaitable, Callable

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, User
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

import strings
from config import ADMIN_ID, AUTH_CACHE_TTL
from db import get_connection

logger = logging.getLogger(__name__)

STATUS_PENDING = "pending"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"
STATUS_REVOKED = "revoked"

_WRITE_LOCK = threading.Lock()
_auth_cache: dict[int, tuple[str, float]] = {}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _user_display(user: User) -> tuple[str, str]:
    first_name = strings.escape(user.first_name or "Unknown")
    username = f"@{user.username}" if user.username else "N/A"
    return first_name, strings.escape(username)


def invalidate_auth_cache(user_id: int | None = None) -> None:
    """Clear one cached auth status, or the whole auth cache."""
    if user_id is None:
        _auth_cache.clear()
        return
    _auth_cache.pop(user_id, None)


def get_user(user_id: int) -> dict[str, Any] | None:
    conn = get_connection()
    try:
        row = conn.execute(
            """
            SELECT user_id, first_name, username, status,
                   requested_at, approved_at, approved_by
            FROM users
            WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_users(status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        if status:
            rows = conn.execute(
                """
                SELECT user_id, first_name, username, status,
                       requested_at, approved_at, approved_by
                FROM users
                WHERE status = ?
                ORDER BY requested_at DESC
                LIMIT ?
                """,
                (status, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT user_id, first_name, username, status,
                       requested_at, approved_at, approved_by
                FROM users
                ORDER BY requested_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_user_status(user_id: int) -> str | None:
    """
    Return the user's current status, using the in-memory cache where possible.
    Returns None if the user is not in the DB at all.
    """
    cached = _auth_cache.get(user_id)
    now    = time.monotonic()
    if cached and cached[1] > now:
        return cached[0]

    user   = get_user(user_id)
    status = user["status"] if user else None
    if status is not None:
        _auth_cache[user_id] = (status, now + AUTH_CACHE_TTL)
    return status


def is_approved(user_id: int) -> bool:
    """
    Fast check: is this user allowed to use the bot?
    Admin is always approved without a DB hit.
    """
    if user_id == ADMIN_ID:
        return True
    return get_user_status(user_id) == STATUS_APPROVED


def register_access_request(user: User) -> bool:
    """
    Insert an unknown user as pending.
    Returns True only when a new row was created — prevents notifying the
    admin repeatedly for the same pending user.
    """
    with _WRITE_LOCK:
        conn = get_connection()
        try:
            existing = conn.execute(
                "SELECT status FROM users WHERE user_id = ?",
                (user.id,),
            ).fetchone()
            if existing:
                return False

            conn.execute(
                """
                INSERT INTO users
                    (user_id, first_name, username, status, requested_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user.id, user.first_name, user.username, STATUS_PENDING, _utc_now()),
            )
            conn.commit()
            invalidate_auth_cache(user.id)
            return True
        except Exception:
            conn.rollback()
            logger.exception(
                "Failed to register access request for user_id=%s.", user.id
            )
            raise
        finally:
            conn.close()


def set_user_status(user_id: int, status: str, admin_id: int) -> bool:
    if status not in {STATUS_APPROVED, STATUS_REJECTED, STATUS_REVOKED}:
        raise ValueError(f"Unsupported user status: {status}")

    with _WRITE_LOCK:
        conn = get_connection()
        try:
            cursor = conn.execute(
                """
                UPDATE users
                   SET status = ?, approved_at = ?, approved_by = ?
                 WHERE user_id = ?
                """,
                (status, _utc_now(), admin_id, user_id),
            )
            conn.commit()
            invalidate_auth_cache(user_id)
            return cursor.rowcount > 0
        except Exception:
            conn.rollback()
            logger.exception(
                "Failed to set status=%s for user_id=%s.", status, user_id
            )
            raise
        finally:
            conn.close()


def approve_user(user_id: int, admin_id: int = ADMIN_ID) -> bool:
    return set_user_status(user_id, STATUS_APPROVED, admin_id)


def reject_user(user_id: int, admin_id: int = ADMIN_ID) -> bool:
    return set_user_status(user_id, STATUS_REJECTED, admin_id)


def revoke_user(user_id: int, admin_id: int = ADMIN_ID) -> bool:
    return set_user_status(user_id, STATUS_REVOKED, admin_id)


# ── Admin notification ────────────────────────────────────────────────────────

async def notify_admin_request(
    context: ContextTypes.DEFAULT_TYPE, user: User
) -> None:
    """
    Send the admin a notification with Approve / Reject buttons.

    Public so cmd_start can call it directly.
    Failures are logged but never re-raised — the caller should always
    send the user their confirmation regardless of whether admin ping works.
    """
    first_name, username = _user_display(user)
    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=strings.ADMIN_NEW_REQUEST.format(
                first_name=first_name,
                username=username,
                user_id=user.id,
                ts=_utc_now(),          # inside backticks — must NOT be escaped
            ),
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    "✅ Одобрить", callback_data=f"admin:approve:{user.id}"
                ),
                InlineKeyboardButton(
                    "❌ Отклонить", callback_data=f"admin:reject:{user.id}"
                ),
            ]]),
        )
    except Exception:
        logger.exception(
            "Could not send admin notification for user_id=%s. "
            "Make sure ADMIN_ID has started the bot at least once.", user.id
        )


# ── Auth reply helpers ────────────────────────────────────────────────────────

async def _send_auth_reply(update: Update, text: str) -> None:
    """Send a reply that works for both message and callback-query updates."""
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.reply_text(
            text, parse_mode=ParseMode.MARKDOWN_V2
        )
        return
    if update.message:
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)


# ── require_auth decorator ────────────────────────────────────────────────────

def require_auth(
    handler: Callable[[Update, ContextTypes.DEFAULT_TYPE], Awaitable[None]]
) -> Callable[[Update, ContextTypes.DEFAULT_TYPE], Awaitable[None]]:
    @wraps(handler)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        if user is None:
            logger.warning("Blocked update without effective_user.")
            return

        if is_approved(user.id):
            return await handler(update, context)

        status = get_user_status(user.id)

        if status == STATUS_PENDING:
            await _send_auth_reply(update, strings.AUTH_ALREADY_PENDING)
            return

        if status in {STATUS_REJECTED, STATUS_REVOKED}:
            await _send_auth_reply(update, strings.AUTH_DENIED)
            return

        # No record — user bypassed /start entirely; register and notify.
        created = register_access_request(user)
        if created:
            await notify_admin_request(context, user)

        await _send_auth_reply(update, strings.AUTH_REQUEST_SENT)

    return wrapper