# app.py (FINAL STABLE VERSION: Fixed Negative Group ID Route and Gevent Conflicts)

from flask import Flask, jsonify, request, render_template, redirect, url_for
from flask_cors import CORS
from dotenv import load_dotenv
import os
import secrets
import json
from datetime import datetime, timedelta
import random
import psycopg2
# Gevent imports are here for use in the Flask routes
import gevent
import gevent.event
import gevent.pool
import asyncio # Must be imported for the loop fix

from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import logging

# =========================================================================
# 🚨 REQUIRED IMPORT FOR REAL DATA 🚨
# Assuming 'db_manager.py' exists in the same directory and contains the fetch_group_analytics function.
from db_manager import fetch_group_analytics # Yeh line yahan rehni chahiye
# =========================================================================


# Load environment variables
load_dotenv()

# --- 1. CONFIGURATION & SETUP ---
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# CRITICAL FIX 3: Explicitly define template folder for clean deployment
app = Flask(__name__, template_folder='templates') # Assuming your HTML files are in 'templates/'
CORS(app, resources={r"/api/*": {"origins": ["*", "http://127.0.0.1:5000"]}})

# Global Constants - MUST be defined for gunicorn.conf.py to access
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = os.getenv("OWNER_ID") 
RENDER_SERVICE_URL = os.getenv("RENDER_SERVICE_URL", "http://127.0.0.1:5000") 
PORT = int(os.environ.get("PORT", 5000))

# Telegram Bot Setup (v20+ Application method)
# Must be set to None, as gunicorn.conf.py initializes this per worker.
application = None 
bot = None


# --- 2. DATABASE MANAGER (Integrated with Rotation Logic) ---

DATABASE_URLS = [
    os.getenv("NEON_DB_URL_1"),
    os.getenv("NEON_DB_URL_2"),
    os.getenv("NEON_DB_URL_3"),
]
DATABASE_URLS = [url for url in DATABASE_URLS if url]
current_db_index = 0

def get_db_connection():
    """Tries to connect, switches DB if current one is full/unreachable."""
    global current_db_index
    start_index = current_db_index
    
    while True:
        if not DATABASE_URLS:
            raise Exception("No database URLs configured.")
        
        db_url = DATABASE_URLS[current_db_index]
        try:
            conn = psycopg2.connect(db_url)
            conn.autocommit = True
            return conn
        
        except (psycopg2.OperationalError, Exception) as e:
            error_message = str(e)
            logger.warning(f"⚠️ DB {current_db_index + 1} FAILED: {error_message}. Switching.")
            current_db_index += 1
            if current_db_index >= len(DATABASE_URLS):
                 current_db_index = 0 # Go back to start
            if current_db_index == start_index:
                 # Prevent infinite loop if only one DB is set and fails
                 raise Exception("All databases are currently full or unreachable.")
            continue
        
def initialize_db():
    """Create necessary tables."""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS groups (
                gc_id BIGINT PRIMARY KEY,
                owner_id BIGINT NOT NULL,
                login_code CHAR(6) UNIQUE NOT NULL,
                group_name VARCHAR(255) NOT NULL,
                tier VARCHAR(50) DEFAULT 'BASIC',
                premium_expiry TIMESTAMP NULL
            );
            CREATE TABLE IF NOT EXISTS analytics_data (
                id SERIAL PRIMARY KEY, gc_id BIGINT, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                metric_type VARCHAR(100) NOT NULL, details JSONB
            );
            CREATE TABLE IF NOT EXISTS complaints (
                id SERIAL PRIMARY KEY, gc_id BIGINT, complainer_id BIGINT, complaint_text TEXT NOT NULL,
                is_abusive BOOLEAN DEFAULT FALSE, status VARCHAR(50) DEFAULT 'OPEN', timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()
        cur.close()
        conn.close()
        logger.info(f"✅ DB tables created/checked in DB {current_db_index + 1}.")
    except Exception as e:
        logger.error(f"CRITICAL DB INIT ERROR: {e}")

# Initialize DB on startup (Wrapped in try/except to prevent Flask crash)
if DATABASE_URLS:
    try:
        initialize_db() 
    except Exception as e:
        logger.error(f"⚠️ Non-critical DB init failed on startup: {e}") 


# --- 3. HELPER & MOCK FUNCTIONS ---

def generate_login_code():
    return secrets.token_urlsafe(6).upper()[:6]

def get_group_by_code(login_code):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT gc_id, group_name, tier, premium_expiry FROM groups WHERE login_code = %s", (login_code,))
    group_data = cur.fetchone()
    cur.close()
    conn.close()
    return group_data

def check_abusive_language(text):
    return any(word in text.lower() for word in ["fuck", "bitch", "gali", "madarchod", "behenchod"])

# ⚠️ YEH MOCK FUNCTION AB SIRF BACKUP HAI ⚠️
def get_mock_analytics(gc_id):
    # This function expects an integer gc_id, so we'll convert it in the API route
    leaderboard = [{"name": f"User {i}", "messages": random.randint(500, 2000)} for i in range(10)]
    leaderboard.sort(key=lambda x: x['messages'], reverse=True)
    return {
        "status": "success", "group_name": "Pro Coders Club - Mock", "tier": "PREMIUM", 
        "total_members": random.randint(800, 1500), "total_messages": random.randint(50000, 100000),
        "engagement_rate": random.randint(30, 60), "content_quality_score": round(random.uniform(6.0, 9.5), 1),
        "ai_growth_tip": "Focus on interactive polls every Tuesday.", "leaderboard": leaderboard,
        "gc_health_data": {"labels": ["W1", "W2", "W3", "W4"], "joins": [100, 120, 90, 150], "leaves": [20, 25, 15, 30]},
        "hourly_activity": [random.randint(200, 800) for _ in range(24)],
        "retention_data": {"labels": ["Jan", "Feb", "Mar", "Apr", "May"], "retention_rate": [80, 75, 82, 78, 85], "churn_rate": [20, 25, 18, 22, 15]},
        "trending_topics": [{"topic": "Python", "percentage": 35}, {"topic": "AI/ML", "percentage": 25}, {"topic": "DevOps", "percentage": 15}],
    }

# Helper function for running async Telegram methods synchronously in gevent
# CRITICAL FIX: Explicitly set a new event loop for the spawned greenlet
def sync_await(coro):
    """Runs an awaitable coroutine synchronously, ensuring a clean loop environment."""
    
    def run_coro():
        try:
            # CRITICAL FIX 1: Cleanly set up the loop to avoid "bound to a different event loop"
            asyncio.set_event_loop(None) 
            loop = asyncio.new_event_loop() 
            asyncio.set_event_loop(loop)
            
            # Now run the coroutine on this dedicated loop
            return loop.run_until_complete(coro)

        except Exception as e:
            # Re-raise the exception from the greenlet
            raise e

    # Spawn the greenlet and block with .get() to wait for the result/exception
    greenlet = gevent.spawn(run_coro)
    
    try:
        return greenlet.get() # .get() blocks until the greenlet finishes
    except Exception as e:
        # Re-raise the exception from the greenlet
        raise e


# --- 4. TELEGRAM BOT HANDLERS (Must be async) ---
# ... (Commands like start_command, register_command, complain_command remain unchanged) ...

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "👋 Hello! I am your Group Management and Analytics Bot.\n\n"
        "To get started, add me to your group and make me an admin.\n"
        "Use `/register` in your group to get your **Login Code** and start your FREE 3-Day Premium Trial! 🚀\n"
        f"[Dashboard Link]({RENDER_SERVICE_URL}/login)"
    )
    await update.message.reply_text(text, parse_mode='Markdown')

async def register_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat.type == 'private':
        await update.message.reply_text("Please use this command inside the group you own.")
        return

    member = await context.bot.get_chat_member(update.effective_chat.id, update.effective_user.id)
    if member.status not in ['creator', 'administrator']:
        await update.message.reply_text("Only the Group Owner or an Admin can register the group.")
        return
        
    login_code = generate_login_code()
    gc_id = update.effective_chat.id
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("""
            INSERT INTO groups (gc_id, owner_id, login_code, group_name, tier, premium_expiry)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (gc_id) DO UPDATE SET login_code = EXCLUDED.login_code, owner_id = EXCLUDED.owner_id
        """, (gc_id, update.effective_user.id, login_code, update.effective_chat.title, 'PREMIUM', datetime.now() + timedelta(days=3)))
        
        cur.close()
        conn.close()
        
        welcome_text = (
            f"🎉 **Registration Successful!**\n\n"
            f"Your group, *{update.effective_chat.title}*, has been registered.\n"
            f"You have been granted a **3-Day FREE Premium Trial**! 🚀\n\n"
            f"**Your Dashboard Login Code:** `{login_code}`\n\n"
            f"Access your Analytics Dashboard now:\n"
            f"[Dashboard Link]({RENDER_SERVICE_URL}/login)"
        )
        await update.message.reply_text(welcome_text, parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Registration Error: {e}")
        await update.message.reply_text("❌ Registration failed due to a server error.")

async def complain_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat.type != 'private':
        await update.message.reply_text("Please use the `/complain` command in a private chat with me for anonymity.")
        return

    if not context.args:
        await update.message.reply_text("Usage: `/complain <Your Complaint/Suggestion>`")
        return
    
    complaint_text = " ".join(context.args)
    MOCK_GC_ID = -100123456789 
    is_abusive = check_abusive_language(complaint_text) 

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO complaints (gc_id, complainer_id, complaint_text, is_abusive)
            VALUES (%s, %s, %s, %s)
        """, (MOCK_GC_ID, update.effective_user.id, complaint_text, is_abusive))
        cur.close()
        conn.close()
        
        await update.message.reply_text("✅ Thank you! Your complaint/suggestion has been recorded. The group admins will be notified soon.")

        owner_id_int = int(OWNER_ID) if OWNER_ID and OWNER_ID.isdigit() else None
        if owner_id_int and bot: 
             await context.bot.send_message(
                chat_id=owner_id_int,
                text=f"🚨 **NEW COMPLAINT/SUGGESTION** (GC: {MOCK_GC_ID})\n"
                     f"Complainer ID: `{update.effective_user.id}`\n"
                     f"Abusive Flag: {is_abusive}\n"
                     f"Text: {complaint_text}\n"
                     f"[Check Dashboard]({RENDER_SERVICE_URL}/login)",
                parse_mode='Markdown'
            )

    except Exception as e:
        logger.error(f"Complaint Submission Error: {e}")
        await update.message.reply_text("❌ Server is offline. Could not submit the complaint.")


# --- 5. FLASK WEBHOOK SETUP (Synchronous Routes) ---
# ... (webhook and set_webhook routes remain unchanged) ...

@app.route('/webhook', methods=['POST'])
def webhook(): 
    # Application is accessed from the module's global scope
    if not application:
        logger.error("FATAL: Webhook called but 'application' is None.")
        return jsonify({"status": "error", "message": "Bot not configured in worker"}), 500
        
    if request.method == "POST":
        try:
            update = Update.de_json(request.get_json(force=True), application.bot) 
            
            # --- CRITICAL FIX 2 & 3: Initialization and Warning Fix ---
            def process_async_update(upd):
                import asyncio
                
                async def initialize_and_process():
                    # 1. Initialize: Fixes "Application was not initialized" RuntimeError
                    try:
                        await application.initialize() 
                    except Exception:
                         # Log a warning but continue if already initialized or minor issue
                         logger.warning("Application initialization check skipped or failed non-critically.")

                    # 2. Process the Update
                    await application.process_update(upd)
                
                # Setup asyncio loop for Greenlet (MUST mirror sync_await's clean setup)
                asyncio.set_event_loop(None) 
                loop = asyncio.new_event_loop() 
                asyncio.set_event_loop(loop)
                
                # Run the combined initialization and processing coroutine
                loop.run_until_complete(initialize_and_process())

            # Spawn the wrapper function
            gevent.spawn(process_async_update, update)

            # Return fast 202 accepted
            return 'ok', 202 
        except Exception as e:
            logger.error(f"Error processing webhook update: {e}")
            return 'ok', 202

    return 'ok'

# Route to set the webhook (Run this once after successful deployment)
@app.route('/set_webhook')
def set_webhook(): 
    # bot is accessed from the module's global scope
    if not bot: 
        return "Bot not configured in worker. Check BOT_TOKEN and logs.", 500
        
    webhook_url = f"{RENDER_SERVICE_URL}/webhook"
    try:
        # Use the synchronous helper to run the async bot method and wait
        s = sync_await(bot.set_webhook(url=webhook_url))
        
        if s:
            return f"✅ Webhook set to: {webhook_url}"
        else:
            return "❌ Webhook setup failed! Check server logs."
    except Exception as e:
        logger.error(f"Webhook setup failed: {e}")
        return f"❌ Webhook setup failed! Error: {e}", 500


# --- 6. FLASK API & HTML ROUTES (Dashboard) ---

@app.route('/')
def root_redirect():
    return redirect(url_for('dashboard_login'))

@app.route('/login')
def dashboard_login():
    return render_template('login.html')

@app.route('/analytics/<string:gc_id>')
def analytics_page(gc_id):
    return render_template('analytics.html')

@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.json
    login_code = data.get('code', '').upper()
    
    if len(login_code) != 6:
        return jsonify({"status": "error", "message": "Invalid code format."}), 400

    try:
        group_data = get_group_by_code(login_code)
    except Exception as e:
        logger.error(f"API Login DB Error: {e}")
        return jsonify({"status": "error", "message": "Server error during login."}), 500

    if group_data:
        gc_id, group_name, tier, expiry = group_data
        # Note: The gc_id returned here is a BIGINT (int), which is fine for DB/backend usage.
        return jsonify({
            "status": "success", "gc_id": gc_id, "group_name": group_name, "tier": tier
        })
    else:
        return jsonify({"status": "error", "message": "Invalid login code."}), 401

# 🚨 CRITICAL FIX FOR REAL DATA: MOCK FUNCTION REMOVED 🚨
@app.route('/api/data/<string:gc_id>', methods=['GET'])
def get_analytics_data(gc_id):
    """
    Fetches real analytics data using the dedicated function from db_manager.
    """
    try:
        gc_id_int = int(gc_id)
        # ⚠️ Yahan REAL DATA FETCHING function use ho raha hai
        analytics_data = fetch_group_analytics(gc_id_int) 
        
        if not analytics_data:
            return jsonify({"status": "error", "message": f"Data not found for group {gc_id}."}), 404
            
        # Data ka structure wahi rahega jo frontend (analytics.html) expect karta hai
        return jsonify(analytics_data)
        
    except ValueError:
        return jsonify({"status": "error", "message": "Invalid group ID format."}), 400
    except Exception as e:
        logger.error(f"API Data Fetch Error for {gc_id}: {e}")
        # Agar db_manager mein koi error ho toh yahan handle hoga
        return jsonify({"status": "error", "message": "Server error during data retrieval."}), 500


# --- 7. MAIN EXECUTION ---
# ... (remains unchanged) ...

if __name__ == '__main__':
    # Use for local testing only
    app.run(host='0.0.0.0', port=PORT, debug=True)
