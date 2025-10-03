# gunicorn.conf.py (FINAL, CORRECTED VERSION)

# CRITICAL FIX: Import the os module to use os.environ.get
import os 
import gevent.monkey
gevent.monkey.patch_all() 

# --- SERVER CONFIGURATION ---

# Set the number of workers (e.g., based on CPU cores)
# FIX: os is now imported and available
workers = os.environ.get('WEB_CONCURRENCY', 2)

# Set the worker class to gevent (as requested)
worker_class = "gevent"

# Set the timeout for workers
timeout = 30 

# Optional: Set access logs and error logs
accesslog = "-" # Log to stdout
errorlog = "-"  # Log to stderr
