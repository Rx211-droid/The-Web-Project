# app.py

from flask import Flask, jsonify, request, render_template, redirect, url_for
from flask_cors import CORS
from dotenv import load_dotenv
import os
import secrets
import json
from datetime import datetime, timedelta
import random
import psycopg2
import asyncio 
import logging

# Gevent imports for async handling in Flask/Gunicorn environment
import gevent
import gevent.event
import gevent.pool

from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# 🚨 CRITICAL IMPORTS from db_manager.py 🚨
# fetch_group_analytics aur log_analytic_metric ab synchronized hain.
from db_manager import initialize_db, get_db_connection, fetch_group_analytics, log_analytic_metric

# Load environment variables
load_dotenv()

# --- 1. CONFIGURATION & SETUP ---
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__, template_folder='templates') 
CORS(app, resources={r"/api/*": {"origins": ["*", "http://127.0.0.1:5000"]}})

# Global Constants
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = os.getenv("OWNER_ID") 
RENDER_SERVICE_URL = os.getenv("RENDER_SERVICE_URL", "http://127.0.0.1:5000") 
PORT = int(os.environ.get("PORT", 5000))

application = None 
bot = None

# Initialize DB on startup (using the imported function)
try:
    initialize_db() 
except Exception as e:
    logger.error(f"⚠️ Non-critical DB init failed on startup: {e}") 


# --- 2. HELPER FUNCTIONS ---

def generate_login_code():
    return secrets.token_urlsafe(6).upper()[:6]

def check_abusive_language(text):
    return any(word in text.lower() for word in ["fuck", "bitch", "gali", "madarchod", "behenchod"])

def get_group_by_code(login_code):
    """Fetches group data by login code from DB (using db_manager connection logic)."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT gc_id, group_name, tier, premium_expiry FROM groups WHERE login_code = %s", (login_code,))
    group_data = cur.fetchone()
    cur.close()
    conn.close()
    return group_data

def sync_await(coro):
    """Runs an awaitable coroutine synchronously, ensuring a clean loop environment."""
    def run_coro():
        try:
            asyncio.set_event_loop(None) 
            loop = asyncio.new_event_loop() 
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(coro)
        except Exception as e:
            raise e
    greenlet = gevent.spawn(run_coro)
    try:
        return greenlet.get()
    except Exception as e:
        raise e


# --- 3. TELEGRAM BOT HANDLERS ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "👋 Hello! I am your Group Management and Analytics Bot.\n\n"
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

        # 🚀 LOG INITIAL MEMBERS (CRITICAL FOR DASHBOARD DATA)
        try:
            member_count = await context.bot.get_chat_member_count(gc_id)
            log_analytic_metric(gc_id, 'total_members', member_count)
        except Exception:
             logger.warning(f"Could not log initial member count for {gc_id}")
        
        welcome_text = (
            f"🎉 **Registration Successful!**\n\n"
            f"Your group, *{update.effective_chat.title}*, has been registered.\n"
            f"**Your Dashboard Login Code:** `{login_code}`\n\n"
            f"Access your Analytics Dashboard now:\n"
            f"[Dashboard Link]({RENDER_SERVICE_URL}/login)"
        )
        await update.message.reply_text(welcome_text, parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Registration Error: {e}")
        await update.message.reply_text("❌ Registration failed due to a server error.")

async def complain_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # ... (complaint logic remains the same)
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
        
        await update.message.reply_text("✅ Thank you! Your complaint/suggestion has been recorded.")

    except Exception as e:
        logger.error(f"Complaint Submission Error: {e}")
        await update.message.reply_text("❌ Server is offline. Could not submit the complaint.")


# 🚀 HANDLER FOR MESSAGE COUNTING (CRITICAL FOR DASHBOARD DATA)
async def handle_and_log_messages(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat.type not in ['group', 'supergroup']:
        return 

    gc_id = update.effective_chat.id
    
    try:
        # 1. Fetch current total_messages
        # Fetching latest data for current count from DB
        analytics_data = fetch_group_analytics(gc_id) 
        # Safely get the current count, default to 0
        current_count = analytics_data.get('total_messages', 0) if analytics_data and analytics_data.get('status') == 'success' else 0

        new_count = current_count + 1
        
        # 2. Log the new count
        log_analytic_metric(
            gc_id=gc_id,
            metric_type='total_messages',
            value=new_count
        )
        
    except Exception as e:
        # Log the error but don't stop the bot
        logger.warning(f"Error logging message count for {gc_id}: {e}")
        

# --- 4. FLASK WEBHOOK SETUP (Synchronous Routes) ---

@app.route('/webhook', methods=['POST'])
def webhook(): 
    if not application:
        logger.error("FATAL: Webhook called but 'application' is None.")
        return jsonify({"status": "error", "message": "Bot not configured in worker"}), 500
        
    if request.method == "POST":
        try:
            update = Update.de_json(request.get_json(force=True), application.bot) 
            
            def process_async_update(upd):
                import asyncio
                
                async def initialize_and_process():
                    try: await application.initialize() 
                    except Exception: logger.warning("Application initialization check skipped.")

                    await application.process_update(upd)
                
                asyncio.set_event_loop(None) 
                loop = asyncio.new_event_loop() 
                asyncio.set_event_loop(loop)
                loop.run_until_complete(initialize_and_process())

            gevent.spawn(process_async_update, update)

            return 'ok', 202 
        except Exception as e:
            logger.error(f"Error processing webhook update: {e}")
            return 'ok', 202

    return 'ok'

@app.route('/set_webhook')
def set_webhook(): 
    if not bot: 
        return "Bot not configured in worker. Check BOT_TOKEN and logs.", 500
        
    webhook_url = f"{RENDER_SERVICE_URL}/webhook"
    try:
        s = sync_await(bot.set_webhook(url=webhook_url))
        
        if s:
            return f"✅ Webhook set to: {webhook_url}"
        else:
            return "❌ Webhook setup failed! Check server logs."
    except Exception as e:
        logger.error(f"Webhook setup failed: {e}")
        return f"❌ Webhook setup failed! Error: {e}", 500


# --- 5. FLASK API & HTML ROUTES (Dashboard) ---

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
        return jsonify({
            "status": "success", "gc_id": gc_id, "group_name": group_name, "tier": tier
        })
    else:
        return jsonify({"status": "error", "message": "Invalid login code."}), 401

# Fetching REAL Data
@app.route('/api/data/<string:gc_id>', methods=['GET'])
def get_analytics_data(gc_id):
    """Fetches real analytics data using the dedicated function from db_manager."""
    try:
        gc_id_int = int(gc_id)
        
        analytics_result = fetch_group_analytics(gc_id_int) 
        
        if not analytics_result:
            return jsonify({
                "status": "error", 
                "message": f"Group ID {gc_id} not registered. Use /register in the group."
            }), 404
            
        return jsonify(analytics_result)
        
    except ValueError:
        return jsonify({"status": "error", "message": "Invalid group ID format."}), 400
    except Exception as e:
        logger.error(f"API Data Fetch Error for {gc_id}: {e}")
        return jsonify({"status": "error", "message": "Server error during data retrieval."}), 500


# --- 6. MAIN EXECUTION ---
if __name__ == '__main__':
    # Use for local testing only
    app.run(host='0.0.0.0', port=PORT, debug=True)
