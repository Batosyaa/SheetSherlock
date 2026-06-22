"""
handlers.py — Telegram command and message handlers.
"""

import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from gspread.exceptions import APIError, SpreadsheetNotFound

import strings
from audit import ACTION_QUERY_BIN, check_query_anomaly, log_event
from auth import (
    STATUS_PENDING,
    STATUS_REJECTED,
    STATUS_REVOKED,
    is_approved,
    get_user_status,
    notify_admin_request,
    register_access_request,
    require_auth,
)
from config import ADMIN_ID
from excel_parser import find_company, get_profile, get_history
from rate_limiter import is_rate_limited

logger = logging.getLogger(__name__)

BIN_LENGTH = 12
_RATE_LIMITED_MSG = "⏳ Слишком много запросов\\. Подождите немного и попробуйте снова\\."


# ── keyboards ─────────────────────────────────────────────────────────────────

def _company_keyboard(bin_number: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("📋 История", callback_data=f"history:{bin_number}"),
        InlineKeyboardButton("🔄 Заново",  callback_data="restart"),
    ]])


def _restart_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🔄 Заново", callback_data="restart"),
    ]])


# ── sheet lookup helper ───────────────────────────────────────────────────────

_ERROR = object()


async def _sheet_lookup(bin_number: str, context_label: str):
    try:
        return find_company(bin_number)
    except SpreadsheetNotFound:
        logger.error("[%s] Spreadsheet not found. Check SHEET_ID in .env.", context_label)
        return _ERROR
    except APIError as e:
        logger.error("[%s] Google Sheets API error: %s", context_label, e)
        return _ERROR
    except Exception:
        logger.exception("[%s] Unexpected error during sheet lookup.", context_label)
        return _ERROR


# ── /start ────────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Entry point for every user.

    Approved / admin  →  WELCOME only.
    Pending           →  AUTH_ALREADY_PENDING only.
    Rejected / revoked→  AUTH_DENIED only.
    New user          →  AUTH_REQUEST_SENT (first) + WELCOME (second),
                         admin notified with Approve / Reject buttons.
    """
    user    = update.effective_user
    user_id = user.id

    # ── approved or admin ─────────────────────────────────────────────────────
    if is_approved(user_id):
        await update.message.reply_text(
            strings.WELCOME, parse_mode=ParseMode.MARKDOWN_V2
        )
        return

    status = get_user_status(user_id)

    # ── already waiting ───────────────────────────────────────────────────────
    if status == STATUS_PENDING:
        await update.message.reply_text(
            strings.AUTH_REQUEST_SENT, parse_mode=ParseMode.MARKDOWN_V2
        )
        return

    # ── explicitly blocked ────────────────────────────────────────────────────
    if status in (STATUS_REJECTED, STATUS_REVOKED):
        await update.message.reply_text(
            strings.AUTH_DENIED, parse_mode=ParseMode.MARKDOWN_V2
        )
        return

    # ── new user ──────────────────────────────────────────────────────────────
    # Register first so the DB row exists before we do anything else.
    created = register_access_request(user)
    if created:
        await notify_admin_request(context, user)

    # Auth message appears above WELCOME so the user understands the context.
    await update.message.reply_text(
        strings.AUTH_REQUEST_SENT, parse_mode=ParseMode.MARKDOWN_V2
    )


# ── /help ─────────────────────────────────────────────────────────────────────

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(strings.HELP, parse_mode=ParseMode.MARKDOWN_V2)


# ── message handler ───────────────────────────────────────────────────────────

@require_auth
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id

    if is_rate_limited(user_id):
        await update.message.reply_text(
            _RATE_LIMITED_MSG, parse_mode=ParseMode.MARKDOWN_V2
        )
        return

    text = update.message.text.strip()

    if not text.isdigit() or len(text) != BIN_LENGTH:
        await update.message.reply_text(
            strings.INVALID_INPUT, parse_mode=ParseMode.MARKDOWN_V2
        )
        return

    result = await _sheet_lookup(text, context_label=f"message uid={user_id}")

    if result is _ERROR:
        await update.message.reply_text(
            strings.SHEET_ERROR, parse_mode=ParseMode.MARKDOWN_V2
        )
        return

    if result is None:
        await update.message.reply_text(
            strings.NOT_FOUND.format(bin=text), parse_mode=ParseMode.MARKDOWN_V2
        )
        return

    profile = get_profile(result)

    try:
        log_event(user_id, ACTION_QUERY_BIN, detail=profile["bin"])
        anomaly_count = check_query_anomaly(user_id)
        if anomaly_count is not None:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=strings.ADMIN_ANOMALY_ALERT.format(
                    user_id=user_id,
                    count=anomaly_count,
                    bin=profile["bin"],
                ),
                parse_mode=ParseMode.MARKDOWN_V2,
            )
    except Exception:
        logger.exception(
            "Failed to audit successful BIN query for user_id=%s.", user_id
        )

    description_line = (
        f"📝 {strings.escape(profile['description'])}\n\n"
        if profile["description"]
        else ""
    )

    message = strings.PROFILE.format(
        name=strings.escape(profile["name"]),
        bin=profile["bin"],
        description=description_line,
        risk_curr=strings.escape(profile["risk_curr"]),
        risk_curr_icon=strings.risk_icon(profile["risk_curr"]),
        risk_prev=strings.escape(profile["risk_prev"]),
        risk_prev_icon=strings.risk_icon(profile["risk_prev"]),
    )
    await update.message.reply_text(
        message,
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=_company_keyboard(profile["bin"]),
    )


# ── callback handler ──────────────────────────────────────────────────────────

@require_auth
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id

    if is_rate_limited(user_id):
        await query.message.reply_text(
            _RATE_LIMITED_MSG, parse_mode=ParseMode.MARKDOWN_V2
        )
        return

    if query.data == "restart":
        await query.message.reply_text(
            strings.WELCOME, parse_mode=ParseMode.MARKDOWN_V2
        )
        return

    if query.data.startswith("history:"):
        bin_number = query.data.split(":", 1)[1]
        result     = await _sheet_lookup(
            bin_number, context_label=f"history uid={user_id}"
        )

        if result is _ERROR:
            await query.message.reply_text(
                strings.SHEET_ERROR, parse_mode=ParseMode.MARKDOWN_V2
            )
            return

        if result is None:
            await query.message.reply_text(
                strings.NOT_FOUND.format(bin=bin_number),
                parse_mode=ParseMode.MARKDOWN_V2,
            )
            return

        profile = get_profile(result)
        history = get_history(result)

        if not history:
            await query.message.reply_text(
                strings.HISTORY_EMPTY,
                parse_mode=ParseMode.MARKDOWN_V2,
                reply_markup=_restart_keyboard(),
            )
            return

        lines = [strings.HISTORY_HEADER.format(name=strings.escape(profile["name"]))]
        for quarter, risk in history:
            lines.append(strings.HISTORY_ROW.format(
                icon=strings.risk_icon(risk),
                quarter=strings.escape(quarter),
                risk=strings.escape(risk),
            ))

        await query.message.reply_text(
            "\n".join(lines),
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=_restart_keyboard(),
        )