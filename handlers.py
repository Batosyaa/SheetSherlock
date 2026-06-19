"""
handlers.py — Telegram command and message handlers.

Fixes applied vs original:
  1. Rate limiting: every text message and callback checks is_rate_limited()
     before doing any work.
  2. Exception handling: SpreadsheetNotFound, APIError, and unexpected errors
     are caught separately so the log always shows the real cause.
"""

import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from gspread.exceptions import APIError, SpreadsheetNotFound
import pandas as pd

import strings
from excel_parser import find_company, get_profile, get_history
from rate_limiter import is_rate_limited   # FIX 1

logger = logging.getLogger(__name__)

BIN_LENGTH = 12
_RATE_LIMITED_MSG = "⏳ Слишком много запросов\\. Подождите немного и попробуйте снова\\."


# ── keyboards ────────────────────────────────────────────────────────────────

def _company_keyboard(bin_number: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("📋 История", callback_data=f"history:{bin_number}"),
        InlineKeyboardButton("🔄 Заново",  callback_data="restart"),
    ]])


def _restart_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🔄 Заново", callback_data="restart"),
    ]])


# ── shared helpers ───────────────────────────────────────────────────────────

_ERROR = object()

async def _sheet_lookup(bin_number: str, context_label: str):
    try:
        return find_company(bin_number)
    except SpreadsheetNotFound:
        logger.error("[%s] Spreadsheet not found. Check SHEET_ID in .env.", context_label)
        return _ERROR          # ← sentinel, not string
    except APIError as e:
        logger.error("[%s] Google Sheets API error: %s", context_label, e)
        return _ERROR
    except Exception:
        logger.exception("[%s] Unexpected error during sheet lookup.", context_label)
        return _ERROR


# ── commands ─────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(strings.WELCOME, parse_mode=ParseMode.MARKDOWN_V2)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(strings.HELP, parse_mode=ParseMode.MARKDOWN_V2)


# ── message handler ──────────────────────────────────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id

    # FIX 1: rate-limit check before any processing.
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
    
    description_line = f"📝 {_escape(profile['description'])}\n\n" if profile["description"] else ""
    
    message = strings.PROFILE.format(
        name=_escape(profile["name"]),
        bin=profile["bin"],
        description=description_line,
        risk_curr=_escape(profile["risk_curr"]),
        risk_curr_icon=strings.risk_icon(profile["risk_curr"]),
        risk_prev=_escape(profile["risk_prev"]),
        risk_prev_icon=strings.risk_icon(profile["risk_prev"]),
    )
    await update.message.reply_text(
        message,
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=_company_keyboard(profile["bin"]),
    )


# ── callback handler ─────────────────────────────────────────────────────────

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id

    # FIX 1: rate-limit applies to callbacks too (history button can hit the sheet).
    if is_rate_limited(user_id):
        await query.message.reply_text(
            _RATE_LIMITED_MSG, parse_mode=ParseMode.MARKDOWN_V2
        )
        return

    if query.data == "restart":
        await query.message.reply_text(strings.WELCOME, parse_mode=ParseMode.MARKDOWN_V2)
        return

    if query.data.startswith("history:"):
        bin_number = query.data.split(":", 1)[1]

        # FIX 2: same separated handling for callbacks.
        result = await _sheet_lookup(bin_number, context_label=f"history uid={user_id}")

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

        lines = [strings.HISTORY_HEADER.format(name=_escape(profile["name"]))]
        for quarter, risk in history:
            lines.append(strings.HISTORY_ROW.format(
                icon=strings.risk_icon(risk),
                quarter=_escape(quarter),
                risk=_escape(risk),
            ))

        await query.message.reply_text(
            "\n".join(lines),
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=_restart_keyboard(),
        )


# ── MarkdownV2 escaping ──────────────────────────────────────────────────────

_ESCAPE_CHARS = r"\_*[]()~`>#+-=|{}.!"

def _escape(text: str) -> str:
    """Escape special characters for Telegram MarkdownV2."""
    for ch in _ESCAPE_CHARS:
        text = text.replace(ch, f"\\{ch}")
    return text