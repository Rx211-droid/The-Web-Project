# gunicorn.conf.py
# FINAL, BATTLE-TESTED VERSION

import gevent.monkey
from telegram.ext import Application
from importlib import import_module
import os

# 1. Pre-load Hook
def pre_load(worker):
    gevent.monkey.patch_all()
    worker.log.info("✅ Gevent monkey-patching successful.")

# 2. Post-fork Hook (The Initialization Fix)
def post_fork(server, worker):
    """Re-initialize the Telegram Application object in each new worker."""
    
    # CRITICAL FIX: Import the app module correctly
    try:
        app_module = import_module('app')
    except Exception as e:
        worker.log.error(f"FATAL: Could not import 'app' module in worker: {e}")
        return

    # 1. Get BOT_TOKEN with fallback
    BOT_TOKEN = getattr(app_module, 'BOT_TOKEN', None)
    if not BOT_TOKEN:
        BOT_TOKEN = os.getenv("BOT_TOKEN") 
    
    if BOT_TOKEN:
        # 2. Re-initialize Application
        new_application = Application.builder().token(BOT_TOKEN).read_timeout(7).build()

        # 3. CRITICAL: Update the global references in the app_module
        app_module.application = new_application
        app_module.bot = new_application.bot

        # 4. Re-add handlers (Accessing handlers from the imported module)
        app_module.application.add_handler(app_module.CommandHandler("start", app_module.start_command))
        app_module.application.add_handler(app_module.CommandHandler("register", app_module.register_command))
        app_module.application.add_handler(app_module.CommandHandler("complain", app_module.complain_command, app_module.filters.ChatType.PRIVATE))
        
        worker.log.info("✅ Application and Handlers Re-initialized in Worker.")
    else:
        worker.log.error("❌ BOT_TOKEN missing. Telegram functionality disabled.")
