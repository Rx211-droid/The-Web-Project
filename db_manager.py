import psycopg2
import os
from datetime import datetime
import json
import random # Temporary import for placeholders until real data is available
import logging

# Setup basic logging for db_manager
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Fetch DB URLs from environment variables
DATABASE_URLS = [
    os.getenv("NEON_DB_URL_1"),
    os.getenv("NEON_DB_URL_2"),
    os.getenv("NEON_DB_URL_3"),
]
DATABASE_URLS = [url for url in DATABASE_URLS if url] # Remove None entries

current_db_index = 0

def get_db_connection():
    """
    Connects to the current active DB. Switches to the next DB if the current one is full/unreachable.
    """
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
        
        except psycopg2.OperationalError as e:
            error_message = str(e)
            
            # Common PostgreSQL "database full" error or critical connection error
            if "disk is full" in error_message or "could not translate host name" in error_message:
                print(f"⚠️ DATABASE {current_db_index + 1} FULL OR FAILED. SWITCHING...")
                current_db_index += 1
                if current_db_index >= len(DATABASE_URLS) or current_db_index == start_index:
                    current_db_index = 0
                    raise Exception("All databases are currently full or unreachable.")
                continue
            else:
                raise
        except Exception:
            # Move to the next DB if connection error
            current_db_index += 1
            if current_db_index >= len(DATABASE_URLS) or current_db_index == start_index:
                current_db_index = 0
                raise Exception("All databases are currently full or unreachable.")
            continue


def initialize_db():
    """Create necessary tables (Group, User, Analytics, Complaints) in the active DB."""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Core Tables
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
                id SERIAL PRIMARY KEY,
                gc_id BIGINT REFERENCES groups(gc_id),
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                metric_type VARCHAR(100) NOT NULL,
                details JSONB
            );
            
            CREATE TABLE IF NOT EXISTS complaints (
                id SERIAL PRIMARY KEY,
                gc_id BIGINT, 
                complainer_id BIGINT,
                complaint_text TEXT NOT NULL,
                is_abusive BOOLEAN DEFAULT FALSE,
                status VARCHAR(50) DEFAULT 'OPEN',
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()
        cur.close()
        conn.close()
        print(f"✅ Database tables created/checked in DB {current_db_index + 1}.")
        
    except Exception as e:
        print(f"CRITICAL DB INIT ERROR: {e}")

# --- MAIN ANALYTICS DATA FETCHING FUNCTION ---

def fetch_group_analytics(gc_id):
    """
    Fetches all required analytics data for the dashboard from the database.
    
    :param gc_id: The ID of the group chat (BIGINT).
    :return: A dictionary including 'status: "success"' if registered, or None if not registered.
    """
    data = {}
    conn = None
    cur = None
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # 1. Fetch Basic Group Info (Name, Tier)
        cur.execute("SELECT group_name, tier, premium_expiry FROM groups WHERE gc_id = %s", (gc_id,))
        group_info = cur.fetchone()
        
        if not group_info:
            return None # Group not registered

        group_name, tier, premium_expiry = group_info
        data['group_name'] = group_name
        data['tier'] = tier
        
        # Determine AI Tip based on tier/expiry
        if tier == 'PREMIUM' and premium_expiry and premium_expiry > datetime.now():
            data['ai_growth_tip'] = "Your premium trial is active! Focus on engagement."
        else:
            data['ai_growth_tip'] = "Consider upgrading to Premium for deeper sentiment analysis."
            
        
        # 2. Fetch Core Metrics (Total Members, Messages, Engagement, Quality Score)
        # Fetch the latest value for each key metric
        cur.execute("""
            SELECT DISTINCT ON (metric_type) metric_type, details->>'value' 
            FROM analytics_data 
            WHERE gc_id = %s AND metric_type IN 
            ('total_members', 'total_messages', 'engagement_rate', 'quality_score')
            ORDER BY metric_type, timestamp DESC;
        """, (gc_id,))
        
        metrics = dict(cur.fetchall())
        
        # Safely convert and set main stats
        data['total_members'] = int(metrics.get('total_members', 0))
        data['total_messages'] = int(metrics.get('total_messages', 0))
        # Ensure that values are floats/strings as expected by the frontend
        data['engagement_rate'] = float(metrics.get('engagement_rate', 0.0))
        data['content_quality_score'] = float(metrics.get('quality_score', 0.0))
        
        
        # 3. Fetch Nested Data (Leaderboard, Charts, Topics)

        def fetch_latest_json(metric_type, default_value):
            cur.execute(f"""
                SELECT details FROM analytics_data 
                WHERE gc_id = %s AND metric_type = %s
                ORDER BY timestamp DESC LIMIT 1
            """, (gc_id, metric_type))
            result = cur.fetchone()
            return result[0] if result else default_value
        
        data['leaderboard'] = fetch_latest_json('leaderboard', [])

        data['gc_health_data'] = fetch_latest_json('gc_health', {"labels": ["W1", "W2"], "joins": [0,0], "leaves": [0,0]})

        # The 'hourly_activity' detail is expected to be a JSON array of 24 numbers
        data['hourly_activity'] = fetch_latest_json('hourly_activity', [random.randint(100, 500) for _ in range(24)])
        
        data['retention_data'] = fetch_latest_json('retention', {"labels": ["M1"], "retention_rate": [0], "churn_rate": [0]})
        
        data['trending_topics'] = fetch_latest_json('trending_topics', [])
        
        
    except Exception as e:
        # Re-raise the exception after logging for app.py to handle the 500 error
        logger.error(f"ERROR in fetch_group_analytics for {gc_id}: {e}")
        raise
        
    finally:
        if cur: cur.close()
        if conn: conn.close()
        
    # 🌟 CRITICAL FIX: Adding "status": "success" for frontend compatibility
    return {"status": "success", **data}
