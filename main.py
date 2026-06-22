
import logging
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

from config import BOT_TOKEN
from admin import cmd_auditlog, cmd_listusers, cmd_revokeuser, handle_admin_callback, cmd_pending, cmd_approveuser
from db import init_db
from handlers import cmd_start, cmd_help, handle_message, handle_callback

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)

def main() -> None:
    init_db()
    
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help",  cmd_help))
    app.add_handler(CommandHandler("listusers", cmd_listusers))
    app.add_handler(CommandHandler("revokeuser", cmd_revokeuser))
    app.add_handler(CommandHandler("auditlog", cmd_auditlog))
    app.add_handler(CallbackQueryHandler(handle_admin_callback, pattern=r"^admin:(approve|reject):"))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CommandHandler("pending", cmd_pending))
    app.add_handler(CommandHandler("approveuser", cmd_approveuser))

    logger.info("SheetSherlock is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
