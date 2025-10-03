# gunicorn.conf.py
# This configuration ensures Telegram's Application object is properly
# initialized in every Gunicorn worker process, preventing the 'Application was not initialized' error.

import gevent.monkey
from telegram.ext import Application
import os

# 1. Pre-load Hook: Runs once before workers are forked.
def pre_load(worker):
    """Apply monkey-patching to allow sync-style code to run concurrently."""
    gevent.monkey.patch_all()
    worker.log.info("✅ Gevent monkey-patching successful.")

# 2. Post-fork Hook: Runs *after* each worker process starts.
def post_fork(server, worker):
    """Re-initialize the Telegram Application object in each new worker."""
    
    # Get the application module (app.py) from the worker's context
    app_module = worker.app.wsgi

    # Safely access the necessary variables from the loaded app module
    # We prioritize the environment variable directly as a fallback to ensure we get the token.
    BOT_TOKEN = getattr(app_module, 'BOT_TOKEN', None)
    if not BOT_TOKEN:
        # Fallback to direct environment variable access for worker
        BOT_TOKEN = os.getenv("BOT_TOKEN") 
    
    if BOT_TOKEN:
        # Re-initialize Application
        app_builder = Application.builder().token(BOT_TOKEN).read_timeout(7)
        new_application = app_builder.build()

        # IMPORTANT: Update the references in the main application module
        # This fixes the "Application was not initialized" and BOT_TOKEN missing errors
        app_module.application = new_application
        app_module.bot = new_application.bot

        # Re-add handlers (Import all necessary handlers from the app_module)
        app_module.application.add_handler(app_module.CommandHandler("start", app_module.start_command))
        app_module.application.add_handler(app_module.CommandHandler("register", app_module.register_command))
        app_module.application.add_handler(app_module.CommandHandler("complain", app_module.complain_command, app_module.filters.ChatType.PRIVATE))
        
        worker.log.info("✅ Telegram Application successfully re-initialized and handlers re-attached.")
    else:
        worker.log.error("❌ BOT_TOKEN missing. Telegram functionality disabled.")
