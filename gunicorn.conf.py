# gunicorn.conf.py
# FINAL VERSION - Fixes all worker and Application initialization issues.

import gevent.monkey
from telegram.ext import Application
from importlib import import_module # <-- New Import
import os

# 1. Pre-load Hook: Runs once before workers are forked.
def pre_load(worker):
    """Apply monkey-patching to allow sync-style code to run concurrently."""
    gevent.monkey.patch_all()
    worker.log.info("✅ Gevent monkey-patching successful.")

# 2. Post-fork Hook: Runs *after* each worker process starts.
def post_fork(server, worker):
    """Re-initialize the Telegram Application object in each new worker."""
    
    # FIX: Import app module correctly to access its global variables (application, bot)
    # The 'app' string comes from the Start Command: 'app:app'
    app_module = import_module('app') # <-- THIS IS THE CRITICAL FIX

    # Safely access the necessary variables from the loaded app module
    BOT_TOKEN = getattr(app_module, 'BOT_TOKEN', None)
    if not BOT_TOKEN:
        # Fallback to direct environment variable access for worker
        BOT_TOKEN = os.getenv("BOT_TOKEN") 
    
    if BOT_TOKEN:
        # Re-initialize Application
        app_builder = Application.builder().token(BOT_TOKEN).read_timeout(7)
        new_application = app_builder.build()

        # IMPORTANT: Update the global references in the main application module
        app_module.application = new_application # Line that failed is now fixed
        app_module.bot = new_application.bot

        # Re-add handlers
        app_module.application.add_handler(app_module.CommandHandler("start", app_module.start_command))
        app_module.application.add_handler(app_module.CommandHandler("register", app_module.register_command))
        app_module.application.add_handler(app_module.CommandHandler("complain", app_module.complain_command, app_module.filters.ChatType.PRIVATE))
        
        worker.log.info("✅ Telegram Application successfully re-initialized and handlers re-attached.")
    else:
        worker.log.error("❌ BOT_TOKEN missing. Telegram functionality disabled.")
