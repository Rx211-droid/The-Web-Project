# gunicorn.conf.py (CLEANED FOR SEPARATE API BACKEND)

# CRITICAL FIX 1: Gevent patching must be done at the top level.
# This ensures monkey-patching happens before Gunicorn loads workers.
import gevent.monkey
gevent.monkey.patch_all() 

# --- SERVER CONFIGURATION ---

# Set the number of workers (e.g., based on CPU cores)
workers = os.environ.get('WEB_CONCURRENCY', 2)

# Set the worker class to gevent (as requested)
worker_class = "gevent"

# Set the timeout for workers
timeout = 30 

# Optional: Set access logs and error logs
accesslog = "-" # Log to stdout
errorlog = "-"  # Log to stderr

# Note: The 'post_fork' function and all Telegram imports are REMOVED.
# This eliminates the 'no attribute start_command' error.
