# app.py (FINAL SYNCHRONIZED API BACKEND)

from flask import Flask, jsonify, request, render_template, redirect, url_for
from flask_cors import CORS
from dotenv import load_dotenv
import os
import secrets
import json
from datetime import datetime, timedelta
import random
import psycopg2
import logging

# Gevent imports are kept for asynchronous database operations if required, but the core logic is synchronous
import gevent
# NOTE: Removed all Telegram imports (Bot, Update, Application, etc.)

# 🚨 CRITICAL IMPORTS from db_manager.py 🚨
from db_manager import initialize_db, get_db_connection, fetch_group_analytics, log_analytic_metric

# Load environment variables
load_dotenv()

# --- 1. CONFIGURATION & SETUP ---
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__, template_folder='templates') 
CORS(app, resources={r"/api/*": {"origins": ["*", "http://127.0.0.1:5000"]}})

# Global Constants
BOT_TOKEN = os.getenv("BOT_TOKEN") # Kept for potential future use (e.g., sending admin alerts)
OWNER_ID = os.getenv("OWNER_ID") 
RENDER_SERVICE_URL = os.getenv("RENDER_SERVICE_URL", "http://127.0.0.1:5000") 
PORT = int(os.environ.get("PORT", 5000))

# NOTE: application and bot globals removed as they are no longer needed for a pure API backend.

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
    """Fetches group data by login code from DB."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT gc_id, group_name, tier, premium_expiry FROM groups WHERE login_code = %s", (login_code,))
    group_data = cur.fetchone()
    cur.close()
    conn.close()
    return group_data

# NOTE: sync_await is removed as the webhook logic is also being removed.


# --- 3. FLASK API ENDPOINTS (BOT INTERFACE) ---

@app.route('/api/bot/register', methods=['POST'])
def api_bot_register():
    """Handles registration requests coming from bot.py and grants trial."""
    data = request.json
    gc_id = data.get('gc_id')
    owner_id = data.get('owner_id')
    group_name = data.get('group_name')

    if not all([gc_id, owner_id, group_name]):
        return jsonify({"status": "error", "message": "Missing parameters."}), 400

    login_code = generate_login_code() 

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Insert/Update group data, starting a 3-day premium trial
        cur.execute("""
            INSERT INTO groups (gc_id, owner_id, login_code, group_name, tier, premium_expiry)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (gc_id) DO UPDATE SET login_code = EXCLUDED.login_code, owner_id = EXCLUDED.owner_id
            RETURNING login_code;
        """, (gc_id, owner_id, login_code, group_name, 'PREMIUM', datetime.now() + timedelta(days=3)))
        
        final_code = cur.fetchone()[0]
        cur.close()
        conn.close()

        # Log initial members count (bot must provide the actual count, here we log 0/1 as a placeholder)
        log_analytic_metric(gc_id, 'total_members', 0) 
        
        return jsonify({"status": "success", "login_code": final_code}), 200

    except Exception as e:
        logger.error(f"API Bot Register Error: {e}")
        return jsonify({"status": "error", "message": "Server error during registration."}), 500


@app.route('/api/complaint', methods=['POST'])
def api_complaint():
    """Handles complaint submissions from bot.py and performs abuse check."""
    data = request.json
    gc_id = data.get('gc_id')
    complainer_id = data.get('complainer_id')
    complaint_text = data.get('text')

    if not all([gc_id, complainer_id, complaint_text]):
        return jsonify({"status": "error", "message": "Missing parameters."}), 400

    is_abusive = check_abusive_language(complaint_text) 
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO complaints (gc_id, complainer_id, complaint_text, is_abusive)
            VALUES (%s, %s, %s, %s)
        """, (gc_id, complainer_id, complaint_text, is_abusive))
        cur.close()
        conn.close()
        
        return jsonify({"status": "success", "is_abusive_flagged": is_abusive}), 200

    except Exception as e:
        logger.error(f"API Complaint Error: {e}")
        return jsonify({"status": "error", "message": "Server error during complaint submission."}), 500


@app.route('/api/bot/log_message', methods=['POST'])
def api_bot_log_message():
    """Increments the total_messages count by 1 (called by bot.py on every message)."""
    data = request.json
    gc_id = data.get('gc_id')

    if not gc_id:
        return jsonify({"status": "error", "message": "Missing gc_id."}), 400

    try:
        # 1. Fetch current count (synchronous call to db_manager)
        analytics_data = fetch_group_analytics(gc_id) 
        current_count = analytics_data.get('total_messages', 0) if analytics_data and analytics_data.get('status') == 'success' else 0

        new_count = current_count + 1
        
        # 2. Log the new count (synchronous call to db_manager)
        log_analytic_metric(
            gc_id=gc_id,
            metric_type='total_messages',
            value=new_count
        )
        
        # Note: We return 202 (Accepted) for non-critical logging to keep the bot fast
        return jsonify({"status": "success", "new_count": new_count}), 202

    except Exception as e:
        logger.error(f"API Log Message Error for {gc_id}: {e}")
        return jsonify({"status": "warning", "message": "Database update failed."}), 202


# --- 4. FLASK WEBHOOK SETUP (REMOVED - Webhook is not needed here) ---
# NOTE: Removed the /webhook and /set_webhook routes as they are now fully handled 
# by the polling bot.py or should be in a dedicated webhook consumer.
# For a pure API backend, these are unnecessary.


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
