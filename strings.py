# markdown escape characters
_ESCAPE_CHARS = r"\_*[]()~`>#+-=|{}.!$"

def escape(text: str) -> str:
    for ch in _ESCAPE_CHARS:
        text = text.replace(ch, f"\\{ch}")
    return text


escape_markdown = escape


# Telegram bot messages

WELCOME = (
    "*Monitoring\|Check Bot* на связи\\.\n\n"
    "Введите *БИН* компании, чтобы получить описание, уровни риска за последние 2 квартала и историю компании\\.\n\n"
    "Пример: `123456789012`"
)

HELP = (
    "*Справка по использованию*\n\n"
    "• Введите *12\\-значный БИН* компании в чат\n"
    "• Бот найдёт компанию и покажет уровень риска за текущий и предыдущий кварталы\n"
    "• Нажмите *История*, чтобы увидеть все доступные кварталы\n"
    "• Нажмите *Заново*, чтобы начать новый поиск\n\n"
    "По вопросам обращайтесь к администратору бота\\."
)

PROFILE = (
    "Наименование компании: *{name}*\n"
    "БИН: `{bin}`\n\n"
    "{description}\n\n"
    "Риск \\(текущий квартал\\): {risk_curr_icon} *{risk_curr}*\n"
    "Риск \\(прошлый квартал\\): {risk_prev_icon} *{risk_prev}*"
)

HISTORY_HEADER = "*История рисков — {name}*\n"
HISTORY_ROW    = "{icon} {quarter}: *{risk}*"
HISTORY_EMPTY  = "История рисков для этой компании недоступна\\."

NOT_FOUND      = "❌ Компания с БИН `{bin}` не найдена\\.\n\nПроверьте правильность номера и попробуйте снова\\."
INVALID_INPUT  = "⚠️ Введите корректный *12\\-значный БИН* \\(только цифры\\)\\."
SHEET_ERROR    = "🔴 Не удалось получить данные из таблицы\\. Попробуйте через несколько секунд или свяжитесь с администратором\\."

# Authentication strings

AUTH_REQUEST_SENT = (
    "🔐 *Доступ ограничен*\n\n"
    "Ваш запрос отправлен администратору\\. "
    "Как только он будет одобрен, вы получите уведомление\\."
)

AUTH_ALREADY_PENDING = (
    "⏳ Ваш запрос уже на рассмотрении\\.\n\n"
    "Пожалуйста, дождитесь подтверждения от администратора\\."
)

AUTH_DENIED = (
    "🚫 Доступ запрещён\\.\n\n"
    "Обратитесь к администратору бота\\."
)

AUTH_APPROVED_USER = (
    "✅ Доступ предоставлен\\!\n\n"
    "Теперь введите *БИН* компании для поиска\\."
)

AUTH_REJECTED_USER = (
    "❌ Ваш запрос на доступ отклонён\\.\n\n"
    "Обратитесь к администратору бота\\."
)

# Admin strings

ADMIN_NEW_REQUEST = (
    "🔔 *Новый запрос на доступ*\n\n"
    "Имя: {first_name}\n"
    "Username: {username}\n"
    "ID: `{user_id}`\n"
    "Время: `{ts}`"
)

ADMIN_APPROVED_NOTIFY = (
    "✅ Запрос на доступ одобрен\\.\n\n"
    "Пользователь: {first_name} \\({username}\\)\n"
    "ID: `{user_id}`"
)

ADMIN_REJECTED_NOTIFY = (
    "❌ Запрос на доступ отклонён\\.\n\n"
    "Пользователь: {first_name} \\({username}\\)\n"
    "ID: `{user_id}`"
)

ADMIN_NOT_AUTHORIZED = (
    "🚫 Доступ запрещён\\.\n\n"
    "Обратитесь к администратору бота\\."
)

ADMIN_USER_NOT_FOUND = "⚠️ Пользователь не найден в реестре\\."

ADMIN_ANOMALY_ALERT = (
    "⚠️ *Подозрительная активность*\n\n"
    "Пользователь `{user_id}` выполнил `{count}` запросов БИН за последний час\\.\n"
    "Последний БИН: `{bin}`"
)

ADMIN_LISTUSERS_USAGE = "Использование: `/listusers [pending|approved|rejected|revoked]`"
ADMIN_LISTUSERS_EMPTY = "Пользователи не найдены\\."
ADMIN_LISTUSERS_TITLE = "*Пользователи* \\({status}\\): `{count}`"

ADMIN_REVOKE_USAGE = "Использование: `/revokeuser <user_id>`"
ADMIN_REVOKED_NOTIFY = (
    "🚫 Доступ отозван\\.\n\n"
    "Пользователь: {first_name} \\({username}\\)\n"
    "ID: `{user_id}`"
)

ADMIN_AUDITLOG_USAGE = "Использование: `/auditlog [limit] [user_id]`"
ADMIN_AUDITLOG_EMPTY = "Журнал аудита пуст\\."
ADMIN_AUDITLOG_TITLE = "*Последние события аудита*: `{count}`"

# Risk icons

RISK_ICONS = {
    "высокий":  "🔴",
    "средний":  "🟡",
    "низкий":   "🟢",
}
DEFAULT_ICON = "⚪"


def risk_icon(level: str) -> str:
    return RISK_ICONS.get(level.lower().strip(), DEFAULT_ICON)
