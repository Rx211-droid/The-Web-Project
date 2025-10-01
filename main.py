# main.py

import os
import json
from dotenv import load_dotenv

from fastapi import FastAPI, Request, HTTPException
from telegram import Update
from telegram.ext import Application
from telegram.constants import ParseMode

from google import genai
from google.genai import types

# --- 1. CONFIGURATION AND INITIALIZATION ---

# Load environment variables (for local testing)
load_dotenv()

# Get tokens from environment variables
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")  # Your Render URL
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not all([TELEGRAM_BOT_TOKEN, WEBHOOK_URL, GEMINI_API_KEY]):
    raise ValueError("Missing essential environment variables (Tokens/Keys)")

# Initialize FastAPI and Telegram Bot Application
app = FastAPI()
application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

# Initialize Gemini Client
gemini_client = genai.Client(api_key=GEMINI_API_KEY)


# --- 2. IN-MEMORY DATA STORE (TEMPORARY) ---

# Stores group_id -> { user_id: message_count }
MESSAGE_COUNTS = {}
# Stores group_id -> { user_id: bad_word_count }
BAD_WORD_TRACKER = {}
# Stores group IDs that have premium access to AI features
PREMIUM_GROUPS = {-100123456789: "Test"} # REPLACE with your test group's actual ID


# --- 3. CORE ANALYTICS AND AI FUNCTIONS ---

def track_message(chat_id: int, user_id: int):
    """Basic message counting."""
    if chat_id not in MESSAGE_COUNTS:
        MESSAGE_COUNTS[chat_id] = {}
    
    # Increment message count for leaderboard
    MESSAGE_COUNTS[chat_id][user_id] = MESSAGE_COUNTS[chat_id].get(user_id, 0) + 1

def check_for_abuse(chat_id: int, user_id: int, text: str):
    """
    Uses Gemini 2.5 to check for abuse/spam. 
    This feature is exclusive to PREMIUM_GROUPS.
    """
    if chat_id not in PREMIUM_GROUPS:
        return

    # A simple, effective prompt for abuse detection
    prompt = f"Analyze the following message for abusive language, hate speech, or excessive spam. Respond ONLY with a single JSON object. If abusive/spam, use: {{\"flagged\": true, \"reason\": \"[Brief reason]\"}}. If clean, use: {{\"flagged\": false}}.\n\nMessage: \"{text}\""

    try:
        response = gemini_client.models.generate_content(
            model='gemini-2.5-pro', # Use a strong model for reliable classification
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema={
                    "type": "object",
                    "properties": {
                        "flagged": {"type": "boolean"},
                        "reason": {"type": "string"}
                    },
                    "required": ["flagged"]
                }
            )
        )
        
        # Parse the JSON response
        data = json.loads(response.text)
        
        if data.get('flagged'):
            if chat_id not in BAD_WORD_TRACKER:
                BAD_WORD_TRACKER[chat_id] = {}
            
            # Log the incident
            BAD_WORD_TRACKER[chat_id][user_id] = BAD_WORD_TRACKER[chat_id].get(user_id, 0) + 1
            print(f"Abuse detected in {chat_id} by {user_id}. Reason: {data.get('reason')}")
            
    except Exception as e:
        print(f"Gemini AI check failed: {e}")

# --- 4. TELEGRAM HANDLER (MAIN WEBHOOK ENTRY POINT) ---

async def webhook_handler(request: Request):
    """Handles all incoming updates from Telegram."""
    try:
        data = await request.json()
        update = Update.de_json(data, application.bot)

        # Check for message and process analytics
        if update.message and update.message.text:
            chat_id = update.message.chat_id
            user_id = update.message.from_user.id
            text = update.message.text
            
            # 1. Update Leaderboard data (Basic Feature)
            track_message(chat_id, user_id)
            
            # 2. Run AI Abuse Check (Premium Feature)
            check_for_abuse(chat_id, user_id, text)
            
            # [Add more handlers here for commands like /start, /dashboard etc.]
            
    except Exception as e:
        # Catch and log any errors without crashing the server
        print(f"Error processing Telegram update: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

    return {"message": "Update processed"}

# --- 5. FASTAPI ROUTES ---

@app.on_event("startup")
async def on_startup():
    """Set the webhook URL when the server starts."""
    await application.bot.set_webhook(url=f"{WEBHOOK_URL}/webhook")
    print(f"Webhook set to: {WEBHOOK_URL}/webhook")

@app.post("/webhook")
async def telegram_webhook(request: Request):
    """Route for Telegram to send updates."""
    return await webhook_handler(request)

@app.get("/")
def read_root():
    """Simple health check route."""
    return {"status": "ok", "message": "Telegram Analytics Service is running."}

@app.get("/analytics/{chat_id}")
def get_analytics(chat_id: int):
    """
    Frontend API: Provides basic analytics data. 
    (This is the endpoint your Mini App will call)
    """
    chat_id = -int(chat_id) # Ensure chat_id is negative for a group

    # 1. Leaderboard (Basic)
    leaderboard = sorted(
        MESSAGE_COUNTS.get(chat_id, {}).items(), 
        key=lambda item: item[1], 
        reverse=True
    )[:10]

    # 2. Bad Word Tracker (Premium/Elite)
    bad_word_leaderboard = sorted(
        BAD_WORD_TRACKER.get(chat_id, {}).items(), 
        key=lambda item: item[1], 
        reverse=True
    )
    
    is_premium = chat_id in PREMIUM_GROUPS
    
    return {
        "status": "success",
        "chat_id": chat_id,
        "is_premium": is_premium,
        "leaderboard": leaderboard,
        "total_messages": sum(MESSAGE_COUNTS.get(chat_id, {}).values()),
        "bad_word_tracker": bad_word_leaderboard if is_premium else "PREMIUM_FEATURE_LOCKED"
    }

# --- 6. RENDER DEPLOYMENT COMMAND ---

# Render needs a command to start the server. 
# This should be in your Render service configuration:
# Command: uvicorn main:app --host 0.0.0.0 --port $PORT
