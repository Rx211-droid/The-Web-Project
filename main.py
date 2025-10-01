import os
import json
from dotenv import load_dotenv

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
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
# Use the negative ID you get when the bot joins the group.
PREMIUM_GROUPS = {-100123456789: "Test Premium GC"} # REPLACE WITH YOUR GROUP ID


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
    """Handles all incoming updates"""
