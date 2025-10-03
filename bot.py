# bot.py (FINAL SYNCHRONIZED VERSION)

import logging
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv
import os
import requests # For API calls to your Flask backend

load_dotenv()

# --- CONFIG ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
# 🚨 CRITICAL: Use the RENDER URL environment variable if available
RENDER_SERVICE_URL = os.getenv("RENDER_SERVICE_URL") 
API_URL = RENDER_SERVICE_URL if RENDER_SERVICE_URL else "http://127.0.0.1:5000" 
OWNER_ID = int(os.getenv("OWNER_ID"))
BOT_USERNAME = "YourBotUsername" # Change this

# Logging setup
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# --- BOT COMMANDS ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a message when the command /start is issued."""
    if update.effective_chat.type == 'private':
        text = (
            "👋 Hello! I am your Group Management and Analytics Bot.\n\n"
            "To get started, add me to your group and make me an admin.\n\n"
            "**Owner Commands:**\n"
            "1. `/register` (In your group) - To register the group and start your FREE 3-Day Premium Trial! (MANDATORY)\n"
            "2. `/info` - Get group stats.\n"
            "3. `/complain <text>` (Here in DM) - Complain to your group owner anonymously.\n"
            f"\n[Dashboard Link]({API_URL}/login)"
        )
    else:
        text = f"Hello! Use `/register` to start your analytics trial.\n[Dashboard Link]({API_URL}/login)"
        
    await update.message.reply_text(text, parse_mode='Markdown')

async def register_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Registers the group by calling the Flask API."""
    if update.effective_chat.type == 'private':
        await update.message.reply_text("Please use this command inside the group you own.")
        return

    # 1. Check if the user is the group owner/admin
    member = await context.bot.get_chat_member(update.effective_chat.id, update.effective_user.id)
    if member.status not in ['creator', 'administrator']:
        await update.message.reply_text("Only the Group Owner or an Admin can register the group.")
        return
        
    # 2. Call the Flask API to register and get the login code
    try:
        # 🚨 Calling the new API endpoint in app.py
        response = requests.post(
            f"{API_URL}/api/bot/register",
            json={
                "gc_id": update.effective_chat.id,
                "owner_id": update.effective_user.id,
                "group_name": update.effective_chat.title
            }
        )
        response.raise_for_status() 
        
        result = response.json()
        login_code = result.get('login_code')
        
        # 3. Send success and trial message
        welcome_text = (
            f"🎉 **Registration Successful!**\n\n"
            f"Your group, *{update.effective_chat.title}*, has been registered.\n"
            f"You have been granted a **3-Day FREE Premium Trial**! 🚀\n\n"
            f"**Your Dashboard Login Code:** `{login_code}`\n\n"
            f"Access your Analytics Dashboard now:\n"
            f"[Dashboard Link]({API_URL}/login)"
        )
        await update.message.reply_text(welcome_text, parse_mode='Markdown')

    except requests.RequestException as e:
        logger.error(f"API Registration Error: {e}")
        await update.message.reply_text("❌ Registration failed due to a server error. Please ensure the API is running and try again.")
    except Exception as e:
        logger.error(f"General Registration Error: {e}")
        await update.message.reply_text("An unexpected error occurred during registration.")


async def complain_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Allows a user to submit a complaint/suggestion to the group owner via Flask API."""
    if update.effective_chat.type != 'private':
        await update.message.reply_text("Please use the `/complain` command in a private chat with me for anonymity.")
        return

    if not context.args:
        await update.message.reply_text("Usage: `/complain <Your Complaint/Suggestion>`")
        return
    
    complaint_text = " ".join(context.args)
    # ⚠️ For the sake of simplicity, we mock a GC ID. In production, you'd lookup the user's group.
    MOCK_GC_ID = -100123456789 
    
    try:
        # 🚨 Calling the new API endpoint in app.py
        response = requests.post(
            f"{API_URL}/api/complaint",
            json={
                "gc_id": MOCK_GC_ID, 
                "complainer_id": update.effective_user.id,
                "text": complaint_text
            }
        )
        response.raise_for_status()
        result = response.json()

        await update.message.reply_text(
            "✅ Thank you! Your complaint/suggestion has been recorded and the group admins will be notified.\n"
            f"Note: Your identity is kept confidential from the group admin/owner."
        )

        # Notify the actual bot owner about the complaint
        await context.bot.send_message(
            chat_id=OWNER_ID,
            text=f"🚨 **NEW COMPLAINT/SUGGESTION** (GC: {MOCK_GC_ID})\n"
                 f"Complainer ID: `{update.effective_user.id}` (Private)\n"
                 f"Abusive Flag: {result.get('is_abusive_flagged', False)}\n"
                 f"Text: {complaint_text}",
            parse_mode='Markdown'
        )

    except requests.RequestException as e:
        logger.error(f"Complaint API Error: {e}")
        await update.message.reply_text("❌ Server is offline. Could not submit the complaint.")


# --- MANAGEMENT/ANALYTICS HANDLERS ---

async def handle_messages(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Records all messages for analytics by calling the API to increment the count.
    This also handles simple admin checks like /ban.
    """
    if update.effective_chat.type not in ['group', 'supergroup']:
        return
        
    gc_id = update.effective_chat.id

    # 1. Log Message Count/Text in DB (via Flask API)
    try:
        # 🚨 Using a dedicated endpoint in app.py for fast message counting
        requests.post(
            f"{API_URL}/api/bot/log_message",
            json={"gc_id": gc_id, "user_id": update.effective_user.id, "text": update.message.text},
            timeout=1 # Set a very short timeout to avoid blocking the Telegram update.
        )
    except requests.RequestException:
        # Message logging is non-critical, so we just log the warning and continue.
        logger.warning(f"Failed to log message for {gc_id}. API might be slow or down.")

    # 2. Check for admin commands (Example: Ban logic)
    if update.message.text and update.message.text.startswith('/ban'):
        # Admin check logic (omitted for brevity, but this is where it would go)
        await update.message.reply_text("Ban command executed (Placeholder).")


# --- MAIN BOT LOOP ---

def main() -> None:
    """Start the bot."""
    # Ensure Bot initialization is correct
    application = Application.builder().token(BOT_TOKEN).build()

    # Public Commands
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("register", register_command))
    
    # Private Commands
    application.add_handler(CommandHandler("complain", complain_command, filters=filters.ChatType.PRIVATE))

    # Message Handler (Must handle all text messages to count them)
    # The message logging logic is now inside handle_messages.
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_messages))

    # Event Handlers (These would also ideally call a dedicated API endpoint for Join/Leave logs)
    # For now, we only log to console to show where the logic goes.
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, handle_messages))
    application.add_handler(MessageHandler(filters.StatusUpdate.LEFT_CHAT_MEMBER, handle_messages))

    # Start the Bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    # ⚠️ IMPORTANT: When running this bot, ensure your app.py (Flask API) is also running 
    # and accessible via the API_URL, especially for logging messages.
    main()
