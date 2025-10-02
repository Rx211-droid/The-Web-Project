# gunicorn.conf.py
import gevent.monkey
import logging
from telegram.ext import Application
import os

logger = logging.getLogger(__name__)

# This function runs BEFORE the workers are forked. We use it to patch gevent.
def pre_load(worker):
    gevent.monkey.patch_all()

# This function runs AFTER the worker has been forked.
# It ensures each worker has a fresh, initialized Application object.
def post_fork(server, worker):
    from app import application, bot, BOT_TOKEN, RENDER_SERVICE_URL # Import global variables

    if BOT_TOKEN:
        # Re-initialize Application in the context of the new worker
        app_builder = Application.builder().token(BOT_TOKEN).read_timeout(7)

        # Re-initialize the global application and bot objects
        application = app_builder.build()
        worker.app.application = application # Update app's reference

        worker.log.info("✅ Telegram Application re-initialized in worker.")

        # Re-add handlers (since app was re-initialized)
        from app import start_command, register_command, complain_command, filters, CommandHandler # Import handlers
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CommandHandler("register", register_command))
        application.add_handler(CommandHandler("complain", complain_command, filters=filters.ChatType.PRIVATE))
        
        worker.log.info("🤖 Bot application handlers re-setup.")
    else:
        worker.log.error("❌ BOT_TOKEN missing. Bot functionality disabled in worker.")

    # We don't need to manually run application.run_polling() or application.run_webhook()
    # Gunicorn is handling the lifecycle, and Flask handles the webhook requests.
