import os
import sys 
import uuid
import random
from dotenv import load_dotenv

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, ChatMemberHandler, MessageHandler, filters
)
from telegram.constants import ParseMode

from google import genai
from google.genai import types

# 🚨 RENDER PATH FIX: 
# Yeh line Python ko current file ki directory se relative paths resolve karne mein help karti hai.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# --- 1. CONFIGURATION AND INITIALIZATION ---

load_dotenv()

# Environment Variables 
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not all([TELEGRAM_BOT_TOKEN, WEBHOOK_URL, GEMINI_API_KEY]):
    print("FATAL: Missing essential environment variables.")

app = FastAPI()

try:
    gemini_client = genai.Client(api_key=GEMINI_API_KEY)
except Exception as e:
    print(f"Gemini Client Initialization Failed: {e}")


# --- 2. DATA STORE (Simulated Database) ---

MESSAGE_COUNTS = {}      
BAD_WORD_TRACKER = {}    

ACTIVE_CHATS = {
    # Replace with your actual group ID and unique code
    -1003043341331: {"name": "Pro Analytics Hub", "tier": "ELITE", "dashboard_code": "PRO-A1", "chat_title": "Pro Analytics Group"}, 
    -1002000000000: {"name": "Basic Testing Group", "tier": "BASIC", "dashboard_code": "BASIC-B2", "chat_title": "Basic Testing Group"} 
}
MOCK_USER_NAMES = {
    12345678: "Alice Tech",
    87654321: "Bob Crypto",
    30433413: "Chris Analyst",
    99887766: "Diana Admin",
}

# --- 3. AI & CORE UTILITY FUNCTIONS ---

def get_gemini_tip(data_summary: str, is_elite: bool) -> str:
    """Generates an actionable tip using Gemini Flash."""
    if not is_elite:
        return "Upgrade to ELITE for AI-powered Growth Tips and Moderation Advice!"

    prompt = f"Based on the following group data summary, provide one concise, actionable tip for the group owner to improve engagement or health. The tone should be highly professional and direct. Summary: {data_summary}"
    
    try:
        response = gemini_client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt
        )
        return response.text.replace('*', '').strip()
    except Exception:
        return "AI Tip generation failed due to a service error."

def track_message(chat_id: int, user_id: int):
    if chat_id not in MESSAGE_COUNTS:
        MESSAGE_COUNTS[chat_id] = {}
    MESSAGE_COUNTS[chat_id][user_id] = MESSAGE_COUNTS[chat_id].get(user_id, 0) + 1

def check_for_abuse(chat_id: int, user_id: int, text: str):
    if ACTIVE_CHATS.get(chat_id, {}).get("tier") == "ELITE":
        if "bad word" in text.lower() or "scam" in text.lower():
            if chat_id not in BAD_WORD_TRACKER:
                BAD_WORD_TRACKER[chat_id] = {}
            BAD_WORD_TRACKER[chat_id][user_id] = BAD_WORD_TRACKER[chat_id].get(user_id, 0) + 1
    pass


# --- 4. TELEGRAM HANDLERS ---

async def handle_bot_added(update: Update, context: object) -> None:
    chat_id = update.my_chat_member.chat.id
    new_status = update.my_chat_member.new_chat_member.status
    old_status = update.my_chat_member.old_chat_member.status
    chat_title = update.my_chat_member.chat.title or f"Group {abs(chat_id)}"

    if new_status in ['member', 'administrator'] and old_status in ['left', 'kicked']:
        if chat_id not in ACTIVE_CHATS:
            code = str(uuid.uuid4()).split('-')[0].upper()
            ACTIVE_CHATS[chat_id] = {"name": chat_title, "tier": "BASIC", "dashboard_code": f"BASIC-{code}", "chat_title": chat_title}
            
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"🤖 Hello! I'm the **Analytics & Management Bot**.\n"
                     f"Your **Dashboard Code** is: `{ACTIVE_CHATS[chat_id]['dashboard_code']}`. "
                     f"Use it on my website to view analytics!",
                parse_mode=ParseMode.MARKDOWN
            )

async def send_welcome_message(update: Update, context: object) -> None:
    for member in update.message.new_chat_members:
        if member.id != context.bot.id:
            welcome_text = (
                f"👋 Welcome, **{member.first_name}**!\n"
                f"Type **/start** to get your Dashboard Code."
            )
            await update.message.reply_text(welcome_text, parse_mode=ParseMode.MARKDOWN)

async def start_command(update: Update, context: object) -> None:
    chat_id = update.effective_chat.id
    group_data = ACTIVE_CHATS.get(chat_id, {})
    
    code = group_data.get('dashboard_code', 'N/A')
    tier = group_data.get('tier', 'BASIC')
    
    welcome_message = (
        f"🤖 **GC Analytics & Management Bot**\n\n"
        f"**Group:** {group_data.get('name', 'N/A')}\n"
        f"**Tier:** **{tier} 🌟**\n"
        f"**Dashboard Code:** `{code}`\n\n"
        f"➡️ Visit the main website to access your dashboard!"
    )
    await update.message.reply_text(welcome_message, parse_mode=ParseMode.MARKDOWN)


async def ban_user_command(update: Update, context: object) -> None:
    if update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user
        try:
            await context.bot.ban_chat_member(update.effective_chat.id, target_user.id)
            await update.message.reply_text(f"✅ User {target_user.first_name} banned.")
        except Exception:
            await update.message.reply_text("❌ Failed to ban. I need admin rights with 'Ban Users' permission.")
    else:
        await update.message.reply_text("Reply to the user you want to ban with /ban.")

async def message_tracking_handler(update: Update, context: object) -> None:
    """Handles all incoming text messages for tracking."""
    if update.message and update.message.text and update.message.chat_id and update.message.from_user:
        chat_id = update.message.chat_id
        user_id = update.message.from_user.id
        text = update.message.text
        
        # Core Tracking Functions
        track_message(chat_id, user_id)
        check_for_abuse(chat_id, user_id, text)
        
# --- 5. TELEGRAM WEBHOOK HANDLER ---

async def webhook_handler(request: Request):
    tg_application = app.state.tg_application
    data = await request.json()
    update = Update.de_json(data, tg_application.bot)

    try:
        await tg_application.process_update(update)
    except Exception as e:
        print(f"Error processing Telegram update: {e}")
        pass 

    return {"message": "Update processed"}


# --- 6. FASTAPI ROUTES & INITIALIZATION ---

@app.on_event("startup")
async def on_startup():
    print("Initializing Telegram Application...")
    bot_app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.state.tg_application = bot_app 
    
    # Register All Handlers
    bot_app.add_handler(CommandHandler("start", start_command))
    bot_app.add_handler(CommandHandler("ban", ban_user_command))
    bot_app.add_handler(
        ChatMemberHandler(handle_bot_added, ChatMemberHandler.MY_CHAT_MEMBER)
    )
    bot_app.add_handler(
        MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, send_welcome_message)
    )
    bot_app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, message_tracking_handler)
    )
    
    if WEBHOOK_URL:
        await bot_app.bot.set_webhook(url=f"{WEBHOOK_URL}/webhook")
        print(f"Webhook set to: {WEBHOOK_URL}/webhook")
    else:
        print("WEBHOOK_URL not set. Skipping webhook configuration.")

@app.post("/webhook")
async def telegram_webhook(request: Request):
    return await webhook_handler(request)

# --- 7. FRONTEND API ENDPOINTS ---

@app.get("/", response_class=HTMLResponse)
async def serve_group_list_page():
    try:
        return FileResponse(os.path.join(STATIC_FILES_DIR, "list.html"), media_type="text/html")
    except FileNotFoundError:
        return HTMLResponse("<h1>Error: list.html not found! Check your 'static' folder.</h1>", status_code=404)

@app.get("/analytics/{chat_id}", response_class=HTMLResponse)
def serve_analytics_dashboard(chat_id: int):
    try:
        return FileResponse(os.path.join(STATIC_FILES_DIR, "analytics.html"), media_type="text/html")
    except FileNotFoundError:
        return HTMLResponse("<h1>Error: analytics.html not found! Check your 'static' folder.</h1>", status_code=404)

@app.get("/api/code/{code}")
def resolve_code_to_id(code: str):
    code = code.upper().strip()
    for chat_id, data in ACTIVE_CHATS.items():
        if data.get("dashboard_code") == code:
            return {"status": "success", "chat_id": abs(chat_id)}
    return {"status": "error", "message": "Invalid Access Code. Please check your bot's /start message."}, 404


@app.get("/api/data/{chat_id}")
def get_analytics_data(chat_id: int):
    """Provides JSON data for the full analytics dashboard."""
    actual_chat_id = -abs(chat_id) 

    group_data = ACTIVE_CHATS.get(actual_chat_id, {})
    is_elite = group_data.get("tier") == "ELITE"
    tier = group_data.get("tier", "BASIC")

    # CORE METRICS & CALCULATIONS
    total_messages = sum(MESSAGE_COUNTS.get(actual_chat_id, {}).values())
    TOTAL_MEMBERS = 550 # Mock for testing
    engagement_rate = round((total_messages / TOTAL_MEMBERS) * 100, 2) if TOTAL_MEMBERS > 0 else 0
    
    # Leaderboard Calculation
    chat_message_counts = MESSAGE_COUNTS.get(actual_chat_id, {})
    leaderboard_data = sorted(chat_message_counts.items(), key=lambda item: item[1], reverse=True)[:10]
    
    leaderboard = []
    for user_id, count in leaderboard_data:
        name = MOCK_USER_NAMES.get(user_id, f"User {str(user_id)[-4:]}")
        leaderboard.append({"id": user_id, "messages": count, "name": name})
    
    # MOCK DATA for Charts
    mock_gc_health = {
        "labels": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        "joins": [random.randint(5, 15) for _ in range(7)],
        "leaves": [random.randint(1, 10) for _ in range(7)]
    }
    mock_retention = {
        "labels": ["Wk 1", "Wk 2", "Wk 3", "Wk 4"],
        "retention_rate": [75, 65, 50, 40],
        "churn_rate": [25, 35, 50, 60]
    }
    mock_hourly_activity = [0, 0, 1, 2, 3, 5, 10, 25, 40, 55, 60, 50, 45, 40, 30, 35, 50, 70, 90, 100, 80, 60, 40, 20]
    mock_topics = [
        {"topic": "Crypto Trading", "percentage": 45},
        {"topic": "Weekend Plans", "percentage": 30},
        {"topic": "Render Deploy", "percentage": 15}
    ]
    mock_member_details = [
        {"id": 12345678, "name": MOCK_USER_NAMES.get(12345678, "Alice"), "is_admin": True, "messages": 1050},
        {"id": 87654321, "name": MOCK_USER_NAMES.get(87654321, "Bob"), "is_admin": False, "messages": 890},
    ]
    content_quality_score = 7.8 
    
    # AI Tip generation
    data_summary = f"Total messages: {total_messages}, Engagement: {engagement_rate}%, Content Score: {content_quality_score}/10."
    ai_tip = get_gemini_tip(data_summary, is_elite)

    # FINAL RETURN
    return {
        "status": "success",
        "chat_id": actual_chat_id,
        "is_elite": is_elite,
        "tier": tier,
        "group_name": group_data.get("chat_title", f"Group {abs(actual_chat_id)}"),
        "total_messages": total_messages,
        "total_members": TOTAL_MEMBERS,
        "engagement_rate": engagement_rate,
        "content_quality_score": content_quality_score,
        "ai_growth_tip": ai_tip,
        
        "gc_health_data": mock_gc_health,
        "retention_data": mock_retention,
        "hourly_activity": mock_hourly_activity,
        "trending_topics": mock_topics,
        
        "leaderboard": leaderboard, 
        "member_list": mock_member_details if is_elite else "PREMIUM_LOCKED",
        "bad_word_tracker": BAD_WORD_TRACKER.get(actual_chat_id, {}) if is_elite else "LOCKED"
    }

# --- 8. STATIC FILES (Final Path Resolution) ---

# Get the directory of the current file (main.py)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Construct the absolute path to the static folder
STATIC_FILES_DIR = os.path.join(BASE_DIR, "static")

# Mount the static directory using the resolved absolute path
app.mount("/static", StaticFiles(directory=STATIC_FILES_DIR), name="static")
