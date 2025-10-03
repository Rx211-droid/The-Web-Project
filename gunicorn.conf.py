# gunicorn.conf.py
# FINAL, CLEAN VERSION - Fixes all worker, import, and initialization issues.

import gevent.monkey
# Patching globally to ensure it happens before Gunicorn loads workers
gevent.monkey.patch_all() 

import os, sys
from importlib import import_module, reload
from telegram.ext import Application, CommandHandler, filters


# We removed the redundant pre_load function.

def post_fork(server, worker):
    """Re-initialize Telegram Application after forking."""

    try:
        # CRITICAL FIX: Reload logic to ensure we get the updated app module
        if 'app' in sys.modules:
            app_module = reload(sys.modules['app'])
        else:
            app_module = import_module('app')

    except Exception as e:
        worker.log.error(f"❌ Could not import app module: {e}")
        return

    # Get BOT_TOKEN with fallback
    BOT_TOKEN = getattr(app_module, 'BOT_TOKEN', None) or os.getenv("BOT_TOKEN")
    if not BOT_TOKEN:
        worker.log.error("❌ BOT_TOKEN missing. Cannot initialize Application.")
        return

    try:
        application = (
            Application.builder()
            .token(BOT_TOKEN)
            .read_timeout(7)
            .build()
        )

        # CRITICAL FIX: Update globals in the app module for the worker
        app_module.application = application
        app_module.bot = application.bot

        # Handlers
        application.add_handler(CommandHandler("start", app_module.start_command))
        application.add_handler(CommandHandler("register", app_module.register_command))
        # Note: filters needs to be accessed via app_module too if it's used inside app.py
        application.add_handler(CommandHandler("complain", app_module.complain_command, app_module.filters.ChatType.PRIVATE)) 

        worker.log.info("✅ Telegram Application initialized in worker.")

    except Exception as e:
        worker.log.error(f"❌ Failed to initialize Application: {e}")
