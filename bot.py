# app.py

from flask import Flask, jsonify, request, render_template, redirect, url_for
from flask_cors import CORS
from dotenv import load_dotenv
import os
import secrets
import json
from datetime import datetime, timedelta
import random

# Import database manager
from db_manager import get_db_connection, initialize_db

# Load environment variables
load_dotenv()

# --- CONFIG ---
app = Flask(__name__, static_folder='static', template_folder='static')
# Production: Set origins to your frontend domain
CORS(app, resources={r"/api/*": {"origins": ["*", "http://127.0.0.1:5000"]}})
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = os.getenv("OWNER_ID")
# Render needs the server to listen on 0.0.0.0 and port from ENV
PORT = int(os.environ.get("PORT", 5000))

# --- HELPER FUNCTIONS ---

def generate_login_code():
    """Generates a unique 6-digit alphanumeric code."""
    return secrets.token_urlsafe(6).upper()[:6]

def get_group_by_code(login_code):
    """Fetches GC details using the unique login code."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT gc_id, group_name, tier, premium_expiry FROM groups WHERE login_code = %s", (login_code,))
    group_data = cur.fetchone()
    cur.close()
    conn.close()
    return group_data

def set_group_tier(gc_id, tier, days=0):
    """Sets the tier and expiry date for the premium trial."""
    expiry_date = None
    if tier == 'PREMIUM' and days > 0:
        expiry_date = datetime.now() + timedelta(days=days)
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE groups SET tier = %s, premium_expiry = %s WHERE gc_id = %s", (tier, expiry_date, gc_id))
    cur.close()
    conn.close()
    return True


# --- AI PLACEHOLDERS (Replace with your actual Gemini/HF code) ---

def check_abusive_language(text):
    """Simulated AI check for abusive language."""
    # In production, use Gemini/HF here. For now, a simple check.
    if any(word in text.lower() for word in ["fuck", "bitch", "gali"]):
        return True
    return False

def get_mock_analytics(gc_id):
    """Generates mock analytics data structure."""
    
    # Mock Leaderboard
    leaderboard = [
        {"name": f"User {random.randint(10, 99)}", "messages": random.randint(500, 2000)} for _ in range(10)
    ]
    leaderboard.sort(key=lambda x: x['messages'], reverse=True)
    
    # Mock data based on discussion
    return {
        "status": "success",
        "group_name": "Pro Coders Club - Mock Data",
        "tier": "PREMIUM", # Mock tier, should be fetched from DB
        "total_members": random.randint(800, 1500),
        "total_messages": random.randint(50000, 100000),
        "engagement_rate": random.randint(30, 60),
        "content_quality_score": round(random.uniform(6.0, 9.5), 1),
        "ai_growth_tip": "Focus on interactive polls every Tuesday to boost member retention.",
        "leaderboard": leaderboard,
        "gc_health_data": {
            "labels": ["W1", "W2", "W3", "W4"],
            "joins": [random.randint(50, 150), random.randint(50, 150), random.randint(50, 150), random.randint(50, 150)],
            "leaves": [random.randint(10, 40), random.randint(10, 40), random.randint(10, 40), random.randint(10, 40)],
        },
        "hourly_activity": [random.randint(200, 800) for _ in range(24)],
        "retention_data": {
            "labels": ["Jan", "Feb", "Mar", "Apr", "May"],
            "retention_rate": [80, 75, 82, 78, 85],
            "churn_rate": [20, 25, 18, 22, 15],
        },
        "trending_topics": [
            {"topic": "Python", "percentage": 35},
            {"topic": "DevOps", "percentage": 25},
            {"topic": "AI/ML", "percentage": 15},
            {"topic": "Queries", "percentage": 10},
        ]
    }


# --- FLASK ROUTES ---

@app.route('/')
def root_redirect():
    return redirect(url_for('dashboard_login'))

# 1. Dashboard Login Page
@app.route('/login')
def dashboard_login():
    """Serve the sleek login page."""
    # We will serve the final login.html
    return render_template('login.html')

# 2. Analytics Dashboard (After successful login)
@app.route('/analytics/<int:gc_id>')
def analytics_page(gc_id):
    """Serves the main analytics dashboard HTML."""
    # Production Security: Check if user has a valid session for this gc_id
    # For simplicity, we just render the template for now
    return render_template('analytics.html')

# 3. Login Logic API
@app.route('/api/login', methods=['POST'])
def api_login():
    """Validates the GC Login Code."""
    data = request.json
    login_code = data.get('code', '').upper()
    
    if len(login_code) != 6:
        return jsonify({"status": "error", "message": "Invalid code format."}), 400

    group_data = get_group_by_code(login_code)
    
    if group_data:
        gc_id, group_name, tier, expiry = group_data
        # Successful login, return GC ID for dashboard access
        return jsonify({
            "status": "success",
            "gc_id": gc_id,
            "group_name": group_name,
            "tier": tier
        })
    else:
        return jsonify({"status": "error", "message": "Invalid login code."}), 401

# 4. Analytics Data API
@app.route('/api/data/<int:gc_id>', methods=['GET'])
def get_analytics_data(gc_id):
    """Serves the data for the analytics dashboard."""
    # Production Security Check: Add Token/Session check here!

    # Fetch real data (Currently mock data)
    data = get_mock_analytics(gc_id) 
    
    # You would fetch real data and check tier here:
    # group_info = fetch_group_info(gc_id) 
    # if group_info.tier == 'BASIC' and request.path accesses a PREMIUM feature:
    #     return jsonify({"status": "access_denied", "message": "Premium access required."})

    return jsonify(data)

# 5. Bot Registration (From Bot)
@app.route('/api/bot/register', methods=['POST'])
def bot_register_gc():
    """Endpoint for bot to register a new group and initiate free trial."""
    data = request.json
    gc_id = data.get('gc_id')
    owner_id = data.get('owner_id')
    group_name = data.get('group_name', 'Unnamed Group')
    
    if not gc_id or not owner_id:
        return jsonify({"status": "error", "message": "Missing GC ID or Owner ID."}), 400

    login_code = generate_login_code()
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Insert/Update group info
        cur.execute("""
            INSERT INTO groups (gc_id, owner_id, login_code, group_name, tier, premium_expiry)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (gc_id) DO UPDATE SET login_code = EXCLUDED.login_code, owner_id = EXCLUDED.owner_id
        """, (gc_id, owner_id, login_code, group_name, 'PREMIUM', datetime.now() + timedelta(days=3)))
        
        cur.close()
        conn.close()
        
        # 🤖 Bot Notification Logic (You'll implement this in the bot file):
        # Bot should send: "Congratulations! 3-day premium trial is active. Login code: [CODE]"

        return jsonify({
            "status": "success", 
            "message": "Group registered. Trial started.", 
            "login_code": login_code
        }), 201

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# 6. Complaint Submission API
@app.route('/api/complaint', methods=['POST'])
def submit_complaint():
    """Handles submission of complaints/suggestions."""
    data = request.json
    gc_id = data.get('gc_id')
    complainer_id = data.get('complainer_id', 0)
    complaint_text = data.get('text')

    if not gc_id or not complaint_text:
        return jsonify({"status": "error", "message": "Missing GC ID or complaint text."}), 400

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
        
        # 🤖 Bot Notification Logic: Bot ko yahan trigger karo GC owner ko message bhejene ke liye.
        # This usually involves sending a request back to the bot's server or calling the Telegram API directly.

        return jsonify({
            "status": "success", 
            "message": "Complaint recorded. Admins will be notified.",
            "is_abusive_flagged": is_abusive
        }), 201

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == '__main__':
    print(f"🚀 Starting server on port {PORT}")
    app.run(host='0.0.0.0', port=PORT)
