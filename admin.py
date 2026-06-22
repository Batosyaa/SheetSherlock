"""
admin.py -- admin-only approval callbacks.

Phase 2 only handles inline approve/reject buttons. Phase 4 can extend this
module with full admin commands without changing the auth gate.
"""

import logging
from functools import wraps
from typing import Awaitable, Callable

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

import strings
from audit import get_audit_events, log_event
from auth import (
    STATUS_APPROVED,
    STATUS_PENDING,
    STATUS_REJECTED,
    STATUS_REVOKED,
    approve_user,
    get_user,
    list_users,
    reject_user,
    revoke_user,
)
from config import ADMIN_ID

logger = logging.getLogger(__name__)
VALID_USER_STATUSES = {STATUS_PENDING, STATUS_APPROVED, STATUS_REJECTED, STATUS_REVOKED}


def _format_user(user: dict) -> tuple[str, str]:
    first_name = strings.escape(user.get("first_name") or "Unknown")
    username = user.get("username")
    username = strings.escape(f"@{username}" if username else "N/A")
    return first_name, username


def _admin_only(
    handler: Callable[[Update, ContextTypes.DEFAULT_TYPE], Awaitable[None]]
) -> Callable[[Update, ContextTypes.DEFAULT_TYPE], Awaitable[None]]:
    @wraps(handler)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        if user is None or user.id != ADMIN_ID:
            if update.message:
                await update.message.reply_text(
                    strings.ADMIN_NOT_AUTHORIZED,
                    parse_mode=ParseMode.MARKDOWN_V2,
                )
            return

        await handler(update, context)

    return wrapper


def _parse_int(value: str) -> int | None:
    try:
        return int(value)
    except ValueError:
        return None


def _user_line(user: dict) -> str:
    first_name, username = _format_user(user)
    return (
        f"`{user['user_id']}` \\| *{strings.escape(user['status'])}* \\| "
        f"{first_name} \\({username}\\)"
    )


async def handle_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user

    if query is None or user is None:
        return
    
    await query.answer()

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
        audit_action = STATUS_APPROVED
    elif action == "reject":
        updated = reject_user(target_id, admin_id=user.id)
        user_message = strings.AUTH_REJECTED_USER
        admin_message = strings.ADMIN_REJECTED_NOTIFY
        audit_action = STATUS_REJECTED
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

    log_event(target_id, audit_action, detail=f"admin:{user.id}")
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


@_admin_only
async def cmd_listusers(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    status = context.args[0].lower() if context.args else None
    if status and status not in VALID_USER_STATUSES:
        await update.message.reply_text(
            strings.ADMIN_LISTUSERS_USAGE,
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    users = list_users(status=status)
    if not users:
        await update.message.reply_text(
            strings.ADMIN_LISTUSERS_EMPTY,
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    title = strings.ADMIN_LISTUSERS_TITLE.format(
        status=strings.escape(status or "all"),
        count=len(users),
    )
    lines = [title, ""]
    lines.extend(_user_line(user) for user in users)

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode=ParseMode.MARKDOWN_V2,
    )


@_admin_only
async def cmd_revokeuser(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) != 1:
        await update.message.reply_text(
            strings.ADMIN_REVOKE_USAGE,
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    target_id = _parse_int(context.args[0])
    if target_id is None:
        await update.message.reply_text(
            strings.ADMIN_REVOKE_USAGE,
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    target = get_user(target_id)
    if target is None:
        await update.message.reply_text(
            strings.ADMIN_USER_NOT_FOUND,
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    if not revoke_user(target_id, admin_id=update.effective_user.id):
        await update.message.reply_text(
            strings.ADMIN_USER_NOT_FOUND,
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    log_event(target_id, STATUS_REVOKED, detail=f"admin:{update.effective_user.id}")
    first_name, username = _format_user(target)
    await update.message.reply_text(
        strings.ADMIN_REVOKED_NOTIFY.format(
            first_name=first_name,
            username=username,
            user_id=target_id,
        ),
        parse_mode=ParseMode.MARKDOWN_V2,
    )


@_admin_only
async def cmd_auditlog(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    limit = 20
    user_id = None

    if context.args:
        parsed_limit = _parse_int(context.args[0])
        if parsed_limit is None:
            await update.message.reply_text(
                strings.ADMIN_AUDITLOG_USAGE,
                parse_mode=ParseMode.MARKDOWN_V2,
            )
            return
        limit = parsed_limit

    if len(context.args) > 1:
        user_id = _parse_int(context.args[1])
        if user_id is None:
            await update.message.reply_text(
                strings.ADMIN_AUDITLOG_USAGE,
                parse_mode=ParseMode.MARKDOWN_V2,
            )
            return

    if len(context.args) > 2:
        await update.message.reply_text(
            strings.ADMIN_AUDITLOG_USAGE,
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    events = get_audit_events(limit=limit, user_id=user_id)
    if not events:
        await update.message.reply_text(
            strings.ADMIN_AUDITLOG_EMPTY,
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    lines = [strings.ADMIN_AUDITLOG_TITLE.format(count=len(events)), ""]
    for event in events:
        detail = strings.escape(event["detail"] or "-")
        lines.append(
            f"`{event['id']}` \\| `{event['ts']}` \\| `{event['user_id']}` \\| "
            f"*{strings.escape(event['action'])}* \\| {detail}"
        )

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode=ParseMode.MARKDOWN_V2,
    )

@_admin_only
async def cmd_pending(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List pending users and offer re-notification."""
    users = list_users(status=STATUS_PENDING)
    if not users:
        await update.message.reply_text("No pending users\\.", parse_mode=ParseMode.MARKDOWN_V2)
        return

    lines = [f"*Pending users:* `{len(users)}`\n"]
    for u in users:
        lines.append(f"`{u['user_id']}` — {strings.escape(u.get('first_name') or 'Unknown')}")

    await update.message.reply_text(
        "\n".join(lines), parse_mode=ParseMode.MARKDOWN_V2
    )

@_admin_only
async def cmd_approveuser(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) != 1:
        await update.message.reply_text(
            "Использование: `/approveuser <user_id>`",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    target_id = _parse_int(context.args[0])
    if target_id is None:
        await update.message.reply_text(
            "Использование: `/approveuser <user_id>`",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    target = get_user(target_id)
    if target is None:
        await update.message.reply_text(
            strings.ADMIN_USER_NOT_FOUND,
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    if not approve_user(target_id, admin_id=update.effective_user.id):
        await update.message.reply_text(
            strings.ADMIN_USER_NOT_FOUND,
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    log_event(target_id, STATUS_APPROVED, detail=f"admin:{update.effective_user.id}")
    first_name, username = _format_user(target)

    try:
        await context.bot.send_message(
            chat_id=target_id,
            text=strings.AUTH_APPROVED_USER,
            parse_mode=ParseMode.MARKDOWN_V2,
        )
    except Exception:
        logger.exception("Failed to notify user_id=%s about approval.", target_id)

    await update.message.reply_text(
        strings.ADMIN_APPROVED_NOTIFY.format(
            first_name=first_name,
            username=username,
            user_id=target_id,
        ),
        parse_mode=ParseMode.MARKDOWN_V2,
    )