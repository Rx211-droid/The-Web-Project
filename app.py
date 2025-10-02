# app.py (Single Service: Flask API + DB Manager + Bot Webhook - FINAL FIXED VERSION)

from flask import Flask, jsonify, request, render_template, redirect, url_for
from flask_cors import CORS
from dotenv import load_dotenv
import os
import secrets
import json
from datetime import datetime, timedelta
import random
import psycopg2
# IMPORTANT: gevent must be imported if using gunicorn with --worker-class gevent
import gevent.monkey 
gevent.monkey.patch_all()

from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import logging

# Load environment variables
load_dotenv()

# --- 1. CONFIGURATION & SETUP ---
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder='static', template_folder='static')
CORS(app, resources={r"/api/*": {"origins": ["*", "http://127.0.0.1:5000"]}})

# Global Constants
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = os.getenv("OWNER_ID") 
RENDER_SERVICE_URL = os.getenv("RENDER_SERVICE_URL", "http://127.0.0.1:5000") 
PORT = int(os.environ.get("PORT", 5000))

# Telegram Bot Setup (v20+ Application method)
application = None
bot = None
if BOT_TOKEN:
    # Initialize Application only if BOT_TOKEN exists
    application = Application.builder().token(BOT_TOKEN).read_timeout(7).build() 
    bot = application.bot
    logger.info("✅ Bot Application initialized.")
else:
    logger.error("❌ BOT_TOKEN not found. Bot functionality will be disabled.")


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
        if current_db_index >= len(DATABASE_URLS):
            raise Exception("All databases are currently full or unreachable.")
            
        db_url = DATABASE_URLS[current_db_index]
        try:
            # Note: Ensure DB URLs have `?sslmode=require` if hosted on Neon/Render
            conn = psycopg2.connect(db_url)
            conn.autocommit = True
            return conn
        
        except (psycopg2.OperationalError, Exception) as e:
            error_message = str(e)
            if "disk is full" in error_message or "could not translate host name" in error_message:
                logger.warning(f"⚠️ DB {current_db_index + 1} FULL/FAILED. Switching.")
                current_db_index += 1
                if current_db_index == start_index:
                     raise Exception("All databases are currently full or unreachable.")
                continue
            else:
                raise

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

# Initialize DB on startup
if DATABASE_URLS:
    initialize_db()


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

def get_mock_analytics(gc_id):
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

# --- 4. TELEGRAM BOT HANDLERS (Webhook Mode) ---

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

        await context.bot.send_message(
            chat_id=OWNER_ID,
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

# --- 5. FLASK WEBHOOK SETUP ---

if application: # <-- FIX B: Check for application object before adding handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("register", register_command))
    application.add_handler(CommandHandler("complain", complain_command, filters=filters.ChatType.PRIVATE))
    logger.info("🤖 Bot application handler setup complete.")

# Flask route to handle Telegram updates 
@app.route('/webhook', methods=['POST'])
async def webhook(): 
    if not application:
        return jsonify({"status": "error", "message": "Bot not configured"}), 500
        
    if request.method == "POST":
        try:
            # FIX: request.get_json() is synchronous, so NO 'await'
            update = Update.de_json(request.get_json(force=True), application.bot) 
            
            # application.process_update() is async, so MUST use 'await'
            await application.process_update(update) 
            
            return 'ok'
        except Exception as e:
            # The Application initialization error is caught here
            logger.error(f"Error processing webhook update: {e}")
            return 'ok', 202 # Return 202 to Telegram to stop retries

    return 'ok'

# Route to set the webhook
@app.route('/set_webhook')
async def set_webhook():
    if not bot:
        return "Bot not configured", 500
        
    webhook_url = f"{RENDER_SERVICE_URL}/webhook"
    s = await bot.set_webhook(url=webhook_url)
    if s:
        return f"✅ Webhook set to: {webhook_url}"
    else:
        return "❌ Webhook setup failed! Check server logs."

# --- 6. FLASK API & HTML ROUTES ---

@app.route('/')
def root_redirect():
    return redirect(url_for('dashboard_login'))

@app.route('/login')
def dashboard_login():
    return render_template('login.html')

@app.route('/analytics/<int:gc_id>')
def analytics_page(gc_id):
    return render_template('analytics.html')

@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.json
    login_code = data.get('code', '').upper()
    
    if len(login_code) != 6:
        return jsonify({"status": "error", "message": "Invalid code format."}), 400

    group_data = get_group_by_code(login_code)
    
    if group_data:
        gc_id, group_name, tier, expiry = group_data
        return jsonify({
            "status": "success", "gc_id": gc_id, "group_name": group_name, "tier": tier
        })
    else:
        return jsonify({"status": "error", "message": "Invalid login code."}), 401

@app.route('/api/data/<int:gc_id>', methods=['GET'])
def get_analytics_data(gc_id):
    data = get_mock_analytics(gc_id) 
    return jsonify(data)


# --- 7. MAIN EXECUTION ---

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=PORT, debug=True)
