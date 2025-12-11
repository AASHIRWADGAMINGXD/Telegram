import os
import re
import logging
import json
import socket # For the dummy server health check
from threading import Thread # For running polling and server concurrently
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)
from functools import wraps
from typing import Set, Dict, Any
from flask import Flask # Required for the dummy web server

# --- 1. Configuration & Setup ---

# Set up logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Environment variable for the bot token
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError(
        "BOT_TOKEN environment variable not set. Please set it before running."
    )

# Configuration constants
AUTH_PASSWORD = "bala"  # <--- MUST CHANGE THIS
ADMIN_USER_IDS: Set[int] = {7915800827,6920845760,1389356052,}  # <--- ADD YOUR ADMIN USER IDs
ADMIN_USERNAMES: Set[str] = {"@your_admin_username"}  # Optional admin usernames
DATA_FILE = "bot_data.json" # File for persistent storage

# Global State (Initialized, will be loaded/saved)
authenticated_users: Set[int] = set()
auto_replies: Dict[str, str] = {}
blocked_users: Set[int] = set()

# --- 2. Persistent Data Management ---

def load_data() -> None:
    """Loads state data from a JSON file."""
    global authenticated_users, auto_replies, blocked_users
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                data: Dict[str, Any] = json.load(f)
                
                # Convert list of strings back to set of integers for user IDs
                authenticated_users = set(map(int, data.get('authenticated_users', [])))
                blocked_users = set(map(int, data.get('blocked_users', [])))
                auto_replies = data.get('auto_replies', {})
            logger.info(f"Bot data loaded successfully. {len(authenticated_users)} users authenticated.")
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding JSON data: {e}. Starting with empty data.")
        except Exception as e:
            logger.error(f"Error loading data: {e}. Starting with empty data.")
    else:
        logger.warning("Data file not found. Starting with fresh state.")

def save_data() -> None:
    """Saves the current state to a JSON file."""
    data = {
        # Convert sets of integers to lists of strings for JSON serialization
        'authenticated_users': list(map(str, authenticated_users)),
        'blocked_users': list(map(str, blocked_users)),
        'auto_replies': auto_replies
    }
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
        logger.debug("Bot data saved successfully.")
    except Exception as e:
        logger.error(f"Error saving data: {e}")

# --- 3. Decorators & Access Control ---

def check_auth(func):
    """Decorator to restrict access to authenticated users."""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if not user or user.id not in authenticated_users:
            message_source = update.callback_query or update.message
            await message_source.reply_text(
                "💀 *Access Denied, Mere Dost.*\n"
                "Pehle *password* de, phir baat kar.\n"
                "Use the command: `/login <password>`",
                parse_mode="Markdown",
            )
            return
        return await func(update, context)
    return wrapper


def check_admin(func):
    """Decorator to restrict access to admin users."""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if not user:
            return
            
        is_admin = (
            user.id in ADMIN_USER_IDS or user.username in ADMIN_USERNAMES
        )
        if not is_admin:
            message_source = update.callback_query or update.message
            await message_source.reply_text(
                "❌ *Hatt Ja, Chhote!*\n"
                "Yeh tera **baap** wala kaam hai. Admin permission chahiyye.",
                parse_mode="Markdown",
            )
            return
        return await func(update, context)
    return wrapper

# --- 4. Core Handlers: Auth & Info ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends bilingual greeting and checks persistent login status."""
    user_id = update.effective_user.id
    if user_id in authenticated_users:
        await update.message.reply_text(
            "✅ *Welcome back, Boss!* *Session Abhi Bhi Chalu Hai.*\n"
            "Tu *fully loaded* hai. Commands maar, *System* hila de. Commands ke liye `/help`.",
            parse_mode="Markdown",
        )
    else:
        await update.message.reply_text(
            "👋 *Kya Haal, Bhai!* I'm your private Mod-Bot.\n"
            "Sabse pehle, *login* kar. Command: `/login <password>`",
            parse_mode="Markdown",
        )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Provides a list of all commands."""
    help_message = (
        "📜 **Command List (Tera System)**\n\n"
        "**Access (Sabke Liye):**\n"
        "`/start` - Check status, *shuruaat*.\n"
        "`/login <pass>` - *Andar aao*, session chalu karo.\n"
        "`/logout` - *Bahar jao*, session khatam karo.\n\n"
        "**Mods & Control (Admin Chahiye):**\n"
        "`/kick` (Reply) - *Dhaka de*.\n"
        "`/ban` (Reply) - *Hamesha ke liye bhagao*.\n"
        "`/mute` (Reply) - *Chup karao* (5 min).\n"
        "`/del` (Reply) - *Mita do*.\n"
        "`/nuke` - *Pain Mode* on, bulk delete panel.\n\n"
        "**Custom & Broadcast (Auth Chahiye):**\n"
        "`/shout <msg>` - *Zor se bolo* (strict filter ke saath).\n"
        "`/addreply <trigger> <response>` - *Naya jawab set karo*.\n"
        "`/delreply <trigger>` - *Jawab hatao*.\n"
        "`/block` (Reply) - User ko bot se *baat karne se roko*.\n"
        "`/unblock` (Reply) - Block *hatao*.\n"
    )
    await update.message.reply_text(help_message, parse_mode="Markdown")


async def login_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles user login with password authentication and saves session."""
    user_id = update.effective_user.id
    if user_id in authenticated_users:
        await update.message.reply_text("😎 *Tu Toh Pehle Se Hi Andar Hai, Boss!*")
        return

    if not context.args or context.args[0] != AUTH_PASSWORD:
        await update.message.reply_text("❌ *Galat Password, Chhote.*")
        return

    authenticated_users.add(user_id)
    save_data() 
    await update.message.reply_text(
        "✅ *Welcome back, Boss!* *Aaya Tu!*\n"
        "Ab tu *fully loaded* hai. Commands maar, *System* hila de.",
        parse_mode="Markdown",
    )


async def logout_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Logs out an authenticated user and saves state."""
    user_id = update.effective_user.id
    if user_id in authenticated_users:
        authenticated_users.remove(user_id)
        save_data() 
        await update.message.reply_text(
            "👋 *Theek Hai, Ja.* Tera *session* khatam. Agli baar *password* laana."
        )
    else:
        await update.message.reply_text("🤔 *Tu Pehle Se Hi Bahar Hai.*")

# --- 5. Moderation Handlers ---

@check_auth
@check_admin
async def kick_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Kicks a user."""
    if not update.message.reply_to_message:
        await update.message.reply_text("👆 Reply kar uss bande ke message par.")
        return
    
    target_user = update.message.reply_to_message.from_user
    chat_id = update.effective_chat.id
    
    try:
        await context.bot.ban_chat_member(chat_id, target_user.id)
        await context.bot.unban_chat_member(chat_id, target_user.id) 
        await update.message.reply_text(
            f"💥 *BAHAR!* **{target_user.full_name}** ko *dhakka* de diya.",
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error(f"Kick error: {e}")
        await update.message.reply_text("❌ *Kuchh Gadbad Hai!* Ya toh main admin nahi, ya yeh banda *bada aadmi* hai.")

@check_auth
@check_admin
async def ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Bans a user."""
    if not update.message.reply_to_message:
        await update.message.reply_text("👆 Reply kar uss bande ke message par.")
        return
    
    target_user = update.message.reply_to_message.from_user
    chat_id = update.effective_chat.id
    
    try:
        await context.bot.ban_chat_member(chat_id, target_user.id)
        await update.message.reply_text(
            f"🔨 *PAKKA BAN!* **{target_user.full_name}** *sada* ke liye gaya.",
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error(f"Ban error: {e}")
        await update.message.reply_text("❌ *Kuchh Gadbad Hai!*")

@check_auth
@check_admin
async def mute_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mutes a user for 5 minutes."""
    if not update.message.reply_to_message:
        await update.message.reply_text("👆 Reply kar uss bande ke message par.")
        return

    target_user = update.message.reply_to_message.from_user
    chat_id = update.effective_chat.id
    until_date = int(update.message.date.timestamp()) + 300 # Mute for 5 minutes

    try:
        await context.bot.restrict_chat_member(
            chat_id,
            target_user.id,
            can_send_messages=False,
            until_date=until_date,
        )
        await update.message.reply_text(
            f"🤫 *SHHH!* **{target_user.full_name}** ko *chuppi* de di. 5 minute *baad* aana.",
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error(f"Mute error: {e}")
        await update.message.reply_text("❌ *Mute nahi hua, Boss!*")

@check_auth
@check_admin
async def del_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Simple delete command for message replied to."""
    if update.message.reply_to_message:
        try:
            await update.message.reply_to_message.delete()
            await update.message.delete()
            # Send a silent confirmation that self-deletes shortly after
            await context.bot.send_message(
                update.effective_chat.id, 
                "🗑️ *Tabaah!*",
                message_thread_id=update.message.message_thread_id if update.message.message_thread_id else None,
            )
        except Exception:
            await context.bot.send_message(
                update.effective_chat.id, 
                "❌ *Delete Failed.* Admin rights confirm kar."
            )

# --- 6. Nuke Command ---

@check_auth
@check_admin
async def nuke_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Deletes messages using button options (Naruto Pain themed)."""
    
    nuke_options = [
        [InlineKeyboardButton("10 Messages", callback_data='nuke_10')],
        [InlineKeyboardButton("20 Messages", callback_data='nuke_20')],
        [InlineKeyboardButton("500 Messages", callback_data='nuke_500')],
        [InlineKeyboardButton("1000 Messages", callback_data='nuke_1000')]
    ]
    
    reply_markup = InlineKeyboardMarkup(nuke_options)

    await update.message.reply_text(
        "🌀 **Shinra Tensei: Message Deletion Panel Activated!** \n\n"
        "Kitne *sandese* (messages) ko *raakh* (ash) karna hai, **Boss**?",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

@check_auth
@check_admin
async def nuke_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles button clicks from the Nuke panel."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    if not data.startswith('nuke_'):
        return

    try:
        count = int(data.split('_')[1])
    except ValueError:
        await query.edit_message_text("❌ *Bhai, Error Hua.* Number sahi nahi mila.")
        return

    chat_id = query.message.chat_id
    current_message_id = query.message.message_id
    
    deleted_count = 0
    messages_to_delete = [current_message_id - i for i in range(1, count + 1)]

    for msg_id in messages_to_delete:
        try:
            await context.bot.delete_message(chat_id, msg_id)
            deleted_count += 1
        except Exception:
            pass 
    
    try:
        await context.bot.delete_message(chat_id, current_message_id)
    except Exception:
        pass

    await context.bot.send_message(
        chat_id,
        f"💥 **Nuke Successful!** *Pain* ne **{deleted_count}** *sandese* (messages) *raakh* kar diye.",
        parse_mode="Markdown"
    )


# --- 7. Shout Command ---

@check_auth
@check_admin
async def shout_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Broadcasts a message with specific content restrictions."""
    if not context.args:
        await update.message.reply_text("📢 *Bolo Kya Chhapaun?* Sahi tareeka: `/shout <tera_message>`")
        return

    message_text = " ".join(context.args)
    restricted_phrases = {"aashirwad ki", "sp ki", "anant ki", "jhaa ki", "levi ki"}
    
    for phrase in restricted_phrases:
        # Regex to match the phrase with optional dots/spaces between characters
        char_pattern = r'[.\s]*'.join(re.escape(c) for c in phrase if c != ' ')
        final_pattern = r'\b' + char_pattern + r'\b'
        
        if re.search(final_pattern, message_text, re.IGNORECASE):
            await update.message.reply_text(
                "🛑 *Shout Blocked.* Yeh *maal* **ban** hai. *Doosra* message bhej."
            )
            return

    await update.message.reply_text(
        f"📣 *BIGG NEWS FROM THE TOP!* \n\n**{message_text}**",
        parse_mode="Markdown"
    )
    try:
        await update.message.delete()
    except Exception:
        pass


# --- 8. Auto-Reply & Block/Unblock Handlers ---

@check_auth
async def add_reply_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Adds a customizable auto-reply and saves state."""
    if len(context.args) < 2:
        await update.message.reply_text("⚙️ Sahi tareeka: `/addreply <trigger_word> <response_text>`")
        return

    trigger = context.args[0].lower()
    response = " ".join(context.args[1:])
    auto_replies[trigger] = response
    save_data() 
    
    await update.message.reply_text(
        f"🎯 *Auto-Reply Set!* Trigger: *{trigger.upper()}*",
        parse_mode="Markdown"
    )

@check_auth
async def delete_reply_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Removes a configured auto-reply and saves state."""
    if not context.args:
        await update.message.reply_text("🗑️ Sahi tareeka: `/delreply <trigger_word>`")
        return

    trigger = context.args[0].lower()
    if trigger in auto_replies:
        del auto_replies[trigger]
        save_data() 
        await update.message.reply_text(f"✅ *Reply Deleted!* *{trigger.upper()}* ab *chup* rahega.", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"🤔 *Yeh Trigger Mila Hi Nahi.*")

@check_auth
@check_admin
async def block_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Blocks a user from bot interaction and saves state."""
    if not update.message.reply_to_message:
        await update.message.reply_text("👆 Reply kar uske message par.")
        return

    target_id = update.message.reply_to_message.from_user.id
    if target_id == update.effective_user.id:
        await update.message.reply_text("✋ *Khud Ko Nahi!*")
        return
    
    blocked_users.add(target_id)
    save_data() 
    await update.message.reply_text(
        f"🚫 *BLOCK!* **{update.message.reply_to_message.from_user.full_name}** ab *bot* se baat nahi kar sakta.",
        parse_mode="Markdown"
    )

@check_auth
@check_admin
async def unblock_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Unblocks a user and saves state."""
    if not update.message.reply_to_message:
        await update.message.reply_text("👆 Reply kar uske message par.")
        return

    target_id = update.message.reply_to_message.from_user.id
    
    if target_id in blocked_users:
        blocked_users.remove(target_id)
        save_data() 
        await update.message.reply_text(
            f"🔓 *UNBLOCK!* **{update.message.reply_to_message.from_user.full_name}** *wapis aa gaya*.",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("🤷‍♂️ *Yeh Banda Blocked Nahi Tha.*")

# --- 9. Custom Message Handler ---

async def custom_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles blocked users, Thala logic, YouTube filter (ignore), and auto-replies."""
    if not update.message or not update.message.text:
        return

    user_id = update.effective_user.id
    message_text = update.message.text
    
    # 1. Blocked User Check
    if user_id in blocked_users:
        return 
    
    # 2. YouTube Link Filter (If '7' is present, DO NOTHING/ALLOW)
    youtube_pattern = r'(?:https?://)?(?:www\.)?(?:youtube\.com|youtu\.be)/(?:watch\?v=)?[\w\-_]+'
    youtube_links = re.findall(youtube_pattern, message_text, re.IGNORECASE)
    
    for link in youtube_links:
        if '7' in link:
            # We explicitly skip any action, allowing the message to pass through.
            logger.info(f"YouTube link with '7' detected: {link}. Allowed as per user request.")
            pass 


    # 3. Thala Logic (Fixed)
    if re.search(r"Thala", message_text, re.IGNORECASE):
        # Check if dot or space is present
        dot_or_space_present = re.search(r"[.\s]", message_text)
        
        # Remove all non-alphanumeric characters for the length check
        text_cleaned_for_7 = re.sub(r'[^a-zA-Z0-9]', '', message_text) 
        
        # Check if 'Thala' is present AND dot/space is present
        if dot_or_space_present:
            response = "👑 **Tere Upar Bala Send**"
            
            # Check for the magic number 7 in the cleaned text length
            if len(text_cleaned_for_7) == 7:
                response += "\nAur Sun, *7 Detected*, Bhai! *Perfect*!"
            
            await update.message.reply_text(response, parse_mode="Markdown")
            return

    # 4. Auto-Reply System
    for trigger, response in auto_replies.items():
        if trigger in message_text.lower():
            await update.message.reply_text(response)
            return

# --- 10. Web Server (Dummy) for Hosting Platforms ---

def run_dummy_server():
    """Runs a basic Flask server on the required port (e.g., 8080) to satisfy the host health check."""
    # Render or similar services usually provide the PORT via an environment variable
    port = int(os.environ.get('PORT', 8080))
    
    app = Flask('dummy_app')

    @app.route('/')
    def home():
        return "Telegram Bot Worker is running.", 200

    print(f"Flask dummy server starting on port {port}...")
    try:
        # Run Flask in a non-blocking way
        app.run(host='0.0.0.0', port=port, debug=False)
    except socket.error as e:
        print(f"Error starting Flask server: {e}")


# --- 11. Main Application ---

def main() -> None:
    """Start the bot and the dummy server concurrently."""
    
    load_data() # Load persistent data at startup

    # --- 1. Start the Bot Polling Application ---
    application = Application.builder().token(BOT_TOKEN).build()

    # Handlers Setup
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command)) 
    application.add_handler(CommandHandler("login", login_command))
    application.add_handler(CommandHandler("logout", logout_command))

    application.add_handler(CommandHandler("kick", kick_command))
    application.add_handler(CommandHandler("ban", ban_command))
    application.add_handler(CommandHandler("mute", mute_command))
    
    application.add_handler(CommandHandler("shout", shout_command))
    application.add_handler(CommandHandler("nuke", nuke_command))
    application.add_handler(CallbackQueryHandler(nuke_callback_handler, pattern=r'^nuke_')) 
    application.add_handler(CommandHandler("del", del_command)) 

    application.add_handler(CommandHandler("addreply", add_reply_command))
    application.add_handler(CommandHandler("delreply", delete_reply_command))

    application.add_handler(CommandHandler("block", block_command))
    application.add_handler(CommandHandler("unblock", unblock_command))
    
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, custom_message_handler)
    )

    # --- 2. Start the Dummy Web Server in a separate thread ---
    # This solves the "Port scan timeout" issue on Web Service deployments.
    server_thread = Thread(target=run_dummy_server)
    server_thread.daemon = True 
    server_thread.start()

    # --- 3. Start Polling (Main Bot Logic) ---
    logger.info("Bot is starting polling...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
