# db_manager.py

import psycopg2
import os
from datetime import datetime
import json
import random 
import logging

# Setup basic logging
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

# --- DATABASE CONNECTION & INIT ---

def get_db_connection():
    """Connects to the current active DB with DB rotation logic."""
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
            current_db_index += 1
            if current_db_index >= len(DATABASE_URLS) or current_db_index == start_index:
                current_db_index = 0
                raise Exception("All databases are currently full or unreachable.")
            continue


def initialize_db():
    """Create necessary tables (Group, Analytics, Complaints)."""
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
                id SERIAL PRIMARY KEY,
                gc_id BIGINT, 
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


# --- DATA LOGGING HELPER ---

def log_analytic_metric(gc_id, metric_type, value):
    """
    Logs a metric value (like total_members) or a complex JSON payload (like leaderboard) 
    into the analytics_data table in the required format {"value": "..."} or raw JSON.
    """
    conn = None
    cur = None
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        if isinstance(value, (int, float, str)):
            # Core metrics use the {"value": "..."} format for easy fetching
            details_json = json.dumps({"value": str(value)})
        else:
            # Complex metrics (charts, lists) are logged directly as JSON
            details_json = json.dumps(value)
            
        cur.execute("""
            INSERT INTO analytics_data (gc_id, metric_type, details)
            VALUES (%s, %s, %s::jsonb)
        """, (gc_id, metric_type, details_json))
        
        conn.commit()
        
    except Exception as e:
        logger.error(f"Error logging analytic data for {gc_id}, {metric_type}: {e}")
        
    finally:
        if cur: cur.close()
        if conn: conn.close()


# --- ANALYTICS DATA FETCHING FUNCTION ---

def fetch_group_analytics(gc_id):
    """
    Fetches all required analytics data for the dashboard from the database.
    """
    data = {}
    conn = None
    cur = None
    
    # Robust Type Casting Functions
    def safe_int(val):
        """Converts string value to int, defaulting to 0."""
        try: return int(float(val)) if val else 0
        except (ValueError, TypeError): return 0
            
    def safe_float(val):
        """Converts string value to float, defaulting to 0.0."""
        try: return float(val) if val else 0.0
        except (ValueError, TypeError): return 0.0

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # 1. Fetch Basic Group Info
        cur.execute("SELECT group_name, tier, premium_expiry FROM groups WHERE gc_id = %s", (gc_id,))
        group_info = cur.fetchone()
        
        if not group_info:
            return None

        group_name, tier, premium_expiry = group_info
        data['group_name'] = group_name
        data['tier'] = tier
        
        if tier == 'PREMIUM' and premium_expiry and premium_expiry > datetime.now():
            data['ai_growth_tip'] = "Your premium trial is active! Focus on engagement."
        else:
            data['ai_growth_tip'] = "Consider upgrading to Premium for deeper sentiment analysis."
            
        # 2. Fetch Core Metrics (Uses DISTINCT ON for latest value)
        cur.execute("""
            SELECT DISTINCT ON (metric_type) metric_type, details->>'value' 
            FROM analytics_data 
            WHERE gc_id = %s AND metric_type IN 
            ('total_members', 'total_messages', 'engagement_rate', 'quality_score')
            ORDER BY metric_type, timestamp DESC;
        """, (gc_id,))
        
        metrics = dict(cur.fetchall())
        
        # Apply robust casting to fetched data
        data['total_members'] = safe_int(metrics.get('total_members', 0))
        data['total_messages'] = safe_int(metrics.get('total_messages', 0))
        data['engagement_rate'] = safe_float(metrics.get('engagement_rate', 0.0))
        data['content_quality_score'] = safe_float(metrics.get('quality_score', 0.0))
        
        
        # 3. Fetch Nested Data Helper
        def fetch_latest_json(metric_type, default_value):
            cur.execute(f"""
                SELECT details FROM analytics_data 
                WHERE gc_id = %s AND metric_type = %s
                ORDER BY timestamp DESC LIMIT 1
            """, (gc_id, metric_type))
            result = cur.fetchone()
            return result[0] if result else default_value
        
        # Fetching charts and lists
        data['leaderboard'] = fetch_latest_json('leaderboard', [])
        data['gc_health_data'] = fetch_latest_json('gc_health', {"labels": ["W1", "W2"], "joins": [0,0], "leaves": [0,0]})
        data['hourly_activity'] = fetch_latest_json('hourly_activity', [random.randint(100, 500) for _ in range(24)])
        data['retention_data'] = fetch_latest_json('retention', {"labels": ["M1"], "retention_rate": [0], "churn_rate": [0]})
        data['trending_topics'] = fetch_latest_json('trending_topics', [])
        
    except Exception as e:
        logger.error(f"ERROR in fetch_group_analytics for {gc_id}: {e}")
        raise
        
    finally:
        if cur: cur.close()
        if conn: conn.close()
        
    return {"status": "success", **data}
