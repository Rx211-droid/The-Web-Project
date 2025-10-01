import os
import json
from dotenv import load_dotenv

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse # NEW IMPORT for the 404 Fix
from telegram import Update
from telegram.ext import Application, CommandHandler
from telegram.constants import ParseMode

from google import genai
from google.genai import types

# --- 1. CONFIGURATION AND INITIALIZATION ---

load_dotenv()

# Get tokens from environment variables (RENDER will provide these)
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")  
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not all([TELEGRAM_BOT_TOKEN, WEBHOOK_URL, GEMINI_API_KEY]):
    print("FATAL: Missing essential environment variables (Tokens/Keys).")

# Initialize FastAPI and Telegram Bot Application
app = FastAPI()
application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

# Initialize Gemini Client
try:
    gemini_client = genai.Client(api_key=GEMINI_API_KEY)
except Exception as e:
    print(f"Gemini Client Initialization Failed: {e}")


# --- 2. IN-MEMORY DATA STORE (TEMPORARY) ---

MESSAGE_COUNTS = {}      
BAD_WORD_TRACKER = {}    

# IMPORTANT: Replace with your actual negative group ID for testing Premium features.
# E.g., if your group ID is -100123456789, use that value here.
PREMIUM_GROUPS = {-1003043341331: "Test Premium GC"} # REPLACE WITH YOUR GROUP ID


# --- 3. CORE ANALYTICS AND AI FUNCTIONS ---

def track_message(chat_id: int, user_id: int):
    """Basic message counting for the leaderboard."""
    if chat_id not in MESSAGE_COUNTS:
        MESSAGE_COUNTS[chat_id] = {}
    
    MESSAGE_COUNTS[chat_id][user_id] = MESSAGE_COUNTS[chat_id].get(user_id, 0) + 1

def check_for_abuse(chat_id: int, user_id: int, text: str):
    """Uses Gemini 2.5 Pro to check for abusive language (Premium Feature)."""
    if chat_id not in PREMIUM_GROUPS:
        return

    prompt = f"Analyze the following message for abusive language, hate speech, or excessive spam. Respond ONLY with a single JSON object. If abusive/spam, use: {{\"flagged\": true, \"reason\": \"[Brief reason]\"}}. If clean, use: {{\"flagged\": false}}.\n\nMessage: \"{text}\""

    try:
        response = gemini_client.models.generate_content(
            model='gemini-2.5-pro',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema={"type": "object", "properties": {"flagged": {"type": "boolean"}, "reason": {"type": "string"}}, "required": ["flagged"]}
            )
        )
        
        data = json.loads(response.text)
        
        if data.get('flagged'):
            if chat_id not in BAD_WORD_TRACKER:
                BAD_WORD_TRACKER[chat_id] = {}
            
            BAD_WORD_TRACKER[chat_id][user_id] = BAD_WORD_TRACKER[chat_id].get(user_id, 0) + 1
            print(f"Abuse detected in {chat_id} by {user_id}. Reason: {data.get('reason')}")
            
    except Exception as e:
        print(f"Gemini AI check failed: {e}")

# --- 4. TELEGRAM COMMAND HANDLER ---

async def start_command(update: Update, context: object) -> None:
    """Handles the /start command and gives instructions."""
    chat_id = update.effective_chat.id
    
    is_premium = chat_id in PREMIUM_GROUPS
    
    welcome_message = (
        f"🤖 **Welcome to the GC Analytics Bot!**\n\n"
        f"I am active in this group.\n"
        f"**Your Chat ID (for Dashboard):** `{abs(chat_id)}`\n\n"
        f"**Tier:** **{ 'PREMIUM 🌟' if is_premium else 'BASIC' }**\n\n"
        f"**➡️ To view the Dashboard:**\n"
        f"Go to your service URL and manually replace the ID in the URL:\n"
        f"`{WEBHOOK_URL}/analytics/{abs(chat_id)}`"
    )
    
    await update.message.reply_text(welcome_message, parse_mode=ParseMode.MARKDOWN)


# --- 5. TELEGRAM WEBHOOK HANDLER (MAIN ENTRY POINT) ---

async def webhook_handler(request: Request):
    """Handles all incoming updates from Telegram."""
    
    data = await request.json()
    update = Update.de_json(data, application.bot)

    # Dispatch the update to the command handler and other handlers
    try:
        await application.process_update(update)
    except Exception as e:
        print(f"Error processing Telegram update in handler: {e}")
        pass 

    # Check for a regular message after command processing
    if update.message and update.message.text:
        chat_id = update.message.chat_id
        user_id = update.message.from_user.id
        text = update.message.text
        
        # 1. Update Leaderboard data (Basic Feature)
        track_message(chat_id, user_id)
        
        # 2. Run AI Abuse Check (Premium Feature)
        check_for_abuse(chat_id, user_id, text)
        
        print(f"Processed message from {user_id} in chat {chat_id}")
        
    return {"message": "Update processed"}


# --- 6. FASTAPI ROUTES & INITIALIZATION ---

# Register Command Handler (FIX for /start command)
application.add_handler(CommandHandler("start", start_command))

@app.on_event("startup")
async def on_startup():
    """Sets the webhook URL when the server starts."""
    await application.bot.set_webhook(url=f"{WEBHOOK_URL}/webhook")
    print(f"Webhook set to: {WEBHOOK_URL}/webhook")

@app.post("/webhook")
async def telegram_webhook(request: Request):
    """Route for Telegram to send updates."""
    return await webhook_handler(request)

@app.get("/analytics/{chat_id}")
def get_analytics(chat_id: int):
    """Frontend API: Provides JSON data for the dashboard."""
    actual_chat_id = -abs(chat_id) 

    leaderboard = sorted(
        MESSAGE_COUNTS.get(actual_chat_id, {}).items(), 
        key=lambda item: item[1], 
        reverse=True
    )[:10]

    bad_word_leaderboard = sorted(
        BAD_WORD_TRACKER.get(actual_chat_id, {}).items(), 
        key=lambda item: item[1], 
        reverse=True
    )
    
    is_premium = actual_chat_id in PREMIUM_GROUPS
    
    return {
        "status": "success",
        "chat_id": actual_chat_id,
        "is_premium": is_premium,
        "leaderboard": leaderboard,
        "total_messages": sum(MESSAGE_COUNTS.get(actual_chat_id, {}).values()),
        "bad_word_tracker": bad_word_leaderboard if is_premium else "PREMIUM_FEATURE_LOCKED"
    }

# --- 7. STATIC FILES (FRONTEND) - 404 FIX HERE! ---

# The /static/ route is used for linked CSS/JS/images
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def serve_dashboard():
    """
    Serves the main index.html file at the root URL (404 FIX).
    This explicitly tells FastAPI to load the dashboard.
    """
    try:
        # FileResponse is the most reliable way to serve a root index.html
        return FileResponse("static/index.html", media_type="text/html")
    except FileNotFoundError:
        return {"error": "Dashboard file not found (404) - Check 'static/index.html' path."}, 404
