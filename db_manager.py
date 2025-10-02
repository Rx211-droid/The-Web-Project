# db_manager.py

import psycopg2
import os

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
        if current_db_index >= len(DATABASE_URLS):
            raise Exception("All databases are currently full or unreachable.")
            
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
                if current_db_index == start_index: # Checked all and back to start
                     raise Exception("All databases are currently full or unreachable.")
                continue
            else:
                raise
        except Exception:
            # Move to the next DB if connection error
            current_db_index += 1
            if current_db_index == start_index:
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
                gc_id BIGINT REFERENCES groups(gc_id),
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
        # In a real app, Render should fail deployment if DB init fails

# Ensure tables are created in the currently selected working DB on startup
initialize_db()
