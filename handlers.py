import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from gspread.exceptions import APIError

import strings
from excel_parser import find_company, get_profile, get_history

logger = logging.getLogger(__name__)

BIN_LENGTH = 12


# Keyboards

def _company_keyboard(bin_number: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("📋 История",  callback_data=f"history:{bin_number}"),
        InlineKeyboardButton("🔄 Заново",   callback_data="restart"),
    ]])


def _restart_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🔄 Заново", callback_data="restart"),
    ]])


# Commands

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        strings.WELCOME,
        parse_mode=ParseMode.MARKDOWN_V2,
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        strings.HELP,
        parse_mode=ParseMode.MARKDOWN_V2,
    )


# Message handler

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text.strip()

    if not text.isdigit() or len(text) != BIN_LENGTH:
        await update.message.reply_text(
            strings.INVALID_INPUT,
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    try:
        row = find_company(text)
    except (APIError, Exception) as e:
        logger.error(f"Sheet error during search for БИН {text}: {e}")
        await update.message.reply_text(
            strings.SHEET_ERROR,
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    if row is None:
        await update.message.reply_text(
            strings.NOT_FOUND.format(bin=text),
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    profile = get_profile(row)
    message = strings.PROFILE.format(
        name=_escape(profile["name"]),
        bin=profile["bin"],
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


# Callback handler

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    if query.data == "restart":
        await query.message.reply_text(
            strings.WELCOME,
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    if query.data.startswith("history:"):
        bin_number = query.data.split(":", 1)[1]

        try:
            row = find_company(bin_number)
        except (APIError, Exception) as e:
            logger.error(f"Sheet error fetching history for БИН {bin_number}: {e}")
            await query.message.reply_text(
                strings.SHEET_ERROR,
                parse_mode=ParseMode.MARKDOWN_V2,
            )
            return

        if row is None:
            await query.message.reply_text(
                strings.NOT_FOUND.format(bin=bin_number),
                parse_mode=ParseMode.MARKDOWN_V2,
            )
            return

        profile = get_profile(row)
        history = get_history(row)

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



# Characters that must be escaped in MarkdownV2
_ESCAPE_CHARS = r"\_*[]()~`>#+-=|{}.!"

def _escape(text: str) -> str:
    """Escape special characters for Telegram MarkdownV2."""
    for ch in _ESCAPE_CHARS:
        text = text.replace(ch, f"\\{ch}")
    return text