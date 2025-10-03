# gunicorn.conf.py
# This configuration ensures Telegram's Application object is properly
# initialized in every Gunicorn worker process, preventing the 'Application was not initialized' error.

import gevent.monkey
from telegram.ext import Application

# 1. Pre-load Hook: Runs once before workers are forked.
def pre_load(worker):
    """Apply monkey-patching to allow sync-style code to run concurrently."""
    gevent.monkey.patch_all()
    worker.log.info("✅ Gevent monkey-patching successful.")

# 2. Post-fork Hook: Runs *after* each worker process starts.
def post_fork(server, worker):
    """Re-initialize the Telegram Application object in each new worker."""
    
    # FIX: Get the application module directly from the worker's application loader.
    # 'app_module' is essentially the content of your app.py file loaded in the worker context.
    # We use worker.app.wsgi to safely access the module object.
    app_module = worker.app.wsgi

    # Safely access the necessary variables from the loaded app module
    BOT_TOKEN = getattr(app_module, 'BOT_TOKEN', None)
    
    if BOT_TOKEN:
        # Re-initialize Application builder
        app_builder = Application.builder().token(BOT_TOKEN).read_timeout(7)
        new_application = app_builder.build()

        # IMPORTANT: Update the references in the main application module
        # This fixes the "Application was not initialized" error
        app_module.application = new_application
        app_module.bot = new_application.bot

        # Re-add handlers (Import all necessary handlers from the app_module)
        app_module.application.add_handler(app_module.CommandHandler("start", app_module.start_command))
        app_module.application.add_handler(app_module.CommandHandler("register", app_module.register_command))
        app_module.application.add_handler(app_module.CommandHandler("complain", app_module.complain_command, app_module.filters.ChatType.PRIVATE))
        
        worker.log.info("✅ Telegram Application successfully re-initialized and handlers re-attached.")
    else:
        worker.log.error("❌ BOT_TOKEN missing. Telegram functionality disabled.")
