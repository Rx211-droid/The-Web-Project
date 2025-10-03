# gunicorn.conf.py
# FINAL FIX: Imports moved inside post_fork to avoid Gunicorn config error

import gevent.monkey
# Patching globally (outside a function) is fine for gevent.
gevent.monkey.patch_all() 

# WARNING: Do NOT import reload, sys, or Application here!

def post_fork(server, worker):
    """Re-initialize Telegram Application after forking."""
    
    # CRITICAL FIX: Move ALL imports inside the worker hook
    import os, sys
    from importlib import import_module, reload
    from telegram.ext import Application, CommandHandler, filters

    try:
        # Load/Reload the app module
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
        # Build Application
        application = (
            Application.builder()
            .token(BOT_TOKEN)
            .read_timeout(7)
            .build()
        )

        # Update globals in the app module
        app_module.application = application
        app_module.bot = application.bot

        # Handlers
        application.add_handler(CommandHandler("start", app_module.start_command))
        application.add_handler(CommandHandler("register", app_module.register_command))
        application.add_handler(CommandHandler("complain", app_module.complain_command, app_module.filters.ChatType.PRIVATE)) 

        worker.log.info("✅ Telegram Application initialized in worker.")

    except Exception as e:
        worker.log.error(f"❌ Failed to initialize Application: {e}")

# Note: pre_load is removed since gevent.monkey.patch_all() is global.
