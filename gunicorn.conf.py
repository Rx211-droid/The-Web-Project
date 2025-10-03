# gunicorn.conf.py

# CRITICAL FIX 1: Gevent patching must be done at the top level.
# This ensures monkey-patching happens before Gunicorn loads workers.
import gevent.monkey
gevent.monkey.patch_all() 

# Note: We do NOT import sys, import_module, or Application here
# to avoid Gunicorn confusing them with configuration settings.

def post_fork(server, worker):
    """Re-initialize Telegram Application in each worker process after forking."""

    # CRITICAL FIX 2: Imports are moved INSIDE the hook function 
    # to avoid the 'Invalid value for reload' error.
    import os, sys
    from importlib import import_module, reload
    from telegram.ext import Application, CommandHandler, filters

    worker.log.info("Starting Telegram Application initialization in worker.")

    try:
        # Load/Reload the app module to get the worker-specific context
        if 'app' in sys.modules:
            # Reload existing module to update global variables
            app_module = reload(sys.modules['app']) 
        else:
            # Import if it somehow wasn't loaded in the master process
            app_module = import_module('app') 

    except Exception as e:
        worker.log.error(f"❌ Could not import/reload app module: {e}")
        return

    # Get BOT_TOKEN with fallback
    BOT_TOKEN = getattr(app_module, 'BOT_TOKEN', None) or os.getenv("BOT_TOKEN")
    if not BOT_TOKEN:
        worker.log.error("❌ BOT_TOKEN missing. Cannot initialize Application.")
        return

    try:
        # Build the new Application instance for this worker
        application = (
            Application.builder()
            .token(BOT_TOKEN)
            .read_timeout(7)
            .build()
        )

        # CRITICAL FIX 3: Update the global 'application' and 'bot' variables 
        # in the reloaded 'app' module for this specific worker.
        app_module.application = application
        app_module.bot = application.bot

        # Handlers
        application.add_handler(CommandHandler("start", app_module.start_command))
        application.add_handler(CommandHandler("register", app_module.register_command))
        # Ensure filters.ChatType.PRIVATE is accessed correctly via the imported filters
        application.add_handler(CommandHandler("complain", app_module.complain_command, filters.ChatType.PRIVATE)) 

        worker.log.info("✅ Telegram Application initialized and handlers added in worker.")

    except Exception as e:
        worker.log.error(f"❌ Failed to initialize Application: {e}")
