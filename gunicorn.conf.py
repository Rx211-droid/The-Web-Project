# gunicorn.conf.py

import gevent.monkey
from telegram.ext import Application
from gunicorn import util # Required to import the application module

# 1. Patch gevent before any real code runs
def pre_load(worker):
    gevent.monkey.patch_all()
    worker.log.info("✅ Gevent monkey-patching successful.")

# 2. Re-initialize Telegram Application for *EACH* worker
def post_fork(server, worker):
    # Import the main application module (app) and the necessary variables
    # This loads app.py again in the context of the new worker
    app_module = util.import_app(worker.cfg.app_uri) 
    
    BOT_TOKEN = app_module.BOT_TOKEN
    
    if BOT_TOKEN:
        # Re-initialize Application
        app_builder = Application.builder().token(BOT_TOKEN).read_timeout(7)
        new_application = app_builder.build()

        # IMPORTANT: Update the references in the main application module
        # Worker.app is the reference to the Flask app object
        app_module.application = new_application
        app_module.bot = new_application.bot

        # Re-add handlers (since the application object is new)
        app_module.application.add_handler(app_module.CommandHandler("start", app_module.start_command))
        app_module.application.add_handler(app_module.CommandHandler("register", app_module.register_command))
        app_module.application.add_handler(app_module.CommandHandler("complain", app_module.complain_command, app_module.filters.ChatType.PRIVATE))
        
        worker.log.info("✅ Telegram Application successfully re-initialized in worker.")
    else:
        worker.log.error("❌ BOT_TOKEN missing. Telegram functionality disabled.")

# Set worker class in the config (optional, since it's in the start command)
# worker_class = 'gevent'
