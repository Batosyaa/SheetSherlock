"""
admin.py -- admin-only approval callbacks.

Phase 2 only handles inline approve/reject buttons. Phase 4 can extend this
module with full admin commands without changing the auth gate.
"""

import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

import strings
from auth import approve_user, get_user, reject_user
from config import ADMIN_ID

logger = logging.getLogger(__name__)


def _format_user(user: dict) -> tuple[str, str]:
    first_name = strings.escape(user.get("first_name") or "Unknown")
    username = user.get("username")
    username = strings.escape(f"@{username}" if username else "N/A")
    return first_name, username


async def handle_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user

    if query is None or user is None:
        return

    if user.id != ADMIN_ID:
        await query.answer()
        await query.message.reply_text(
            strings.ADMIN_NOT_AUTHORIZED,
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    try:
        _, action, target_id_raw = query.data.split(":", 2)
        target_id = int(target_id_raw)
    except (AttributeError, ValueError):
        await query.answer()
        logger.warning("Invalid admin callback data: %r", query.data)
        return

    target = get_user(target_id)
    if target is None:
        await query.answer()
        await query.message.reply_text(
            strings.ADMIN_USER_NOT_FOUND,
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    if action == "approve":
        updated = approve_user(target_id, admin_id=user.id)
        user_message = strings.AUTH_APPROVED_USER
        admin_message = strings.ADMIN_APPROVED_NOTIFY
    elif action == "reject":
        updated = reject_user(target_id, admin_id=user.id)
        user_message = strings.AUTH_REJECTED_USER
        admin_message = strings.ADMIN_REJECTED_NOTIFY
    else:
        await query.answer()
        logger.warning("Unknown admin action in callback data: %r", query.data)
        return

    if not updated:
        await query.answer()
        await query.message.reply_text(
            strings.ADMIN_USER_NOT_FOUND,
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    first_name, username = _format_user(target)

    try:
        await context.bot.send_message(
            chat_id=target_id,
            text=user_message,
            parse_mode=ParseMode.MARKDOWN_V2,
        )
    except Exception:
        logger.exception("Failed to notify user_id=%s about auth action.", target_id)

    await query.edit_message_reply_markup(reply_markup=None)
    await query.message.reply_text(
        admin_message.format(
            first_name=first_name,
            username=username,
            user_id=target_id,
        ),
        parse_mode=ParseMode.MARKDOWN_V2,
    )
    await query.answer()
