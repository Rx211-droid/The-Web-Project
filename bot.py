# bot.py

import logging
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv
import os
import requests # For API calls to your Flask backend

load_dotenv()

# --- CONFIG ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_URL = "http://127.0.0.1:5000" # Replace with your Render URL for production
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
            "1. `/register` (In your group) - To register the group and start your FREE 3-Day Premium Trial!\n"
            "2. `/info` - Get group stats.\n"
            "3. `/complain <text>` (Here in DM) - Complain to your group owner anonymously.\n"
            "\n**Management Commands:**\n"
            "/ban, /mute, /pin, /setwelcome, etc. (Full list in group help)."
        )
    else:
        text = "Hello! Use `/register` to start your analytics trial."
        
    await update.message.reply_text(text, parse_mode='Markdown')

async def register_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Registers the group and starts the 3-day premium trial."""
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
        response = requests.post(
            f"{API_URL}/api/bot/register",
            json={
                "gc_id": update.effective_chat.id,
                "owner_id": update.effective_user.id,
                "group_name": update.effective_chat.title
            }
        )
        response.raise_for_status() # Raise an exception for bad status codes
        
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
        await update.message.reply_text("❌ Registration failed due to a server error. Please try again later.")
    except Exception as e:
        logger.error(f"General Registration Error: {e}")
        await update.message.reply_text("An unexpected error occurred during registration.")


async def complain_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Allows a user to submit a complaint/suggestion to their group owner."""
    if update.effective_chat.type != 'private':
        await update.message.reply_text("Please use the `/complain` command in a private chat with me for anonymity.")
        return

    if not context.args:
        await update.message.reply_text("Usage: `/complain <Your Complaint/Suggestion>`")
        return
    
    complaint_text = " ".join(context.args)
    # The bot needs to know which group the user is complaining about. 
    # This requires looking up the user's active groups, which is complex.
    # For a simple solution, we assume the user only belongs to one or the owner is specific.

    # 1. Call the Flask API to submit the complaint
    # NOTE: You need to set the correct GC ID here. For this example, we mock a GC ID.
    MOCK_GC_ID = -100123456789 
    
    try:
        response = requests.post(
            f"{API_URL}/api/complaint",
            json={
                "gc_id": MOCK_GC_ID, # FIX THIS IN PRODUCTION
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

        # 2. Notify the actual bot owner about the complaint
        await context.bot.send_message(
            chat_id=OWNER_ID,
            text=f"🚨 **NEW COMPLAINT/SUGGESTION** (GC: {MOCK_GC_ID})\n"
                 f"Complainer ID: `{update.effective_user.id}` (Private)\n"
                 f"Abusive Flag: {result.get('is_abusive_flagged', False)}\n"
                 f"Text: {complaint_text}",
            parse_mode='Markdown'
        )

    except requests.RequestException as e:
        await update.message.reply_text("❌ Server is offline. Could not submit the complaint.")


# --- MANAGEMENT/ANALYTICS HANDLERS ---

async def handle_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Records join events and sends welcome."""
    for member in update.message.new_chat_members:
        # 1. Store Join Event in DB (using Flask API)
        # 2. Send Welcome Message (Needs a /setwelcome command handler to define the message)
        logger.info(f"New member joined: {member.id} in {update.effective_chat.id}")


async def handle_left_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Records leave events."""
    # 1. Store Leave Event in DB (using Flask API)
    logger.info(f"Member left: {update.message.left_chat_member.id} in {update.effective_chat.id}")


async def handle_messages(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Records all messages for analytics."""
    # 1. Store Message Count/Text in DB (using Flask API)
    # 2. Check for ban/mute triggers (e.g., /ban <user>)
    
    # Simple Admin Check
    if update.message.text and update.message.text.startswith('/ban'):
        # Admin check logic
        await update.message.reply_text("Ban command executed (Placeholder).")

# --- MAIN BOT LOOP ---

def main() -> None:
    """Start the bot."""
    application = Application.builder().token(BOT_TOKEN).build()

    # Public Commands
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("register", register_command))
    
    # Private Commands
    application.add_handler(CommandHandler("complain", complain_command, filters=filters.ChatType.PRIVATE))

    # Event Handlers (for analytics)
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, handle_new_member))
    application.add_handler(MessageHandler(filters.StatusUpdate.LEFT_CHAT_MEMBER, handle_left_member))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_messages))


    # Start the Bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
