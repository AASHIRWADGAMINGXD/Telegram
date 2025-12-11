import os
import re
import logging
import json
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from functools import wraps
from typing import Set, Dict, Any

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
AUTH_PASSWORD = "bala"  # CHANGE THIS!
ADMIN_USER_IDS: Set[int] = {7915800827,6920845760,1389356052} # Add your admin User IDs (integers)
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
                auth_list = data.get('authenticated_users', [])
                authenticated_users = set(map(int, auth_list))
                
                blocked_list = data.get('blocked_users', [])
                blocked_users = set(map(int, blocked_list))
                
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
        user_id = update.effective_user.id
        if user_id not in authenticated_users:
            await update.message.reply_text(
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
        is_admin = (
            user.id in ADMIN_USER_IDS or user.username in ADMIN_USERNAMES
        )
        if not is_admin:
            await update.message.reply_text(
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
            "Tu *fully loaded* hai. Commands maar, *System* hila de.",
            parse_mode="Markdown",
        )
    else:
        await update.message.reply_text(
            "👋 *Kya Haal, Bhai!* I'm your private Mod-Bot.\n"
            "Sabse pehle, *login* kar. Command: `/login <password>`",
            parse_mode="Markdown",
        )


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
    save_data() # Save state after successful login
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
        save_data() # Save state after successful logout
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
    except Exception:
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
    except Exception:
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
    except Exception:
        await update.message.reply_text("❌ *Mute nahi hua, Boss!*")

@check_auth
@check_admin
async def del_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Simple delete command for message replied to."""
    if update.message.reply_to_message:
        try:
            await update.message.reply_to_message.delete()
            await update.message.delete()
            await context.bot.send_message(
                update.effective_chat.id, 
                "🗑️ *Tabaah!*"
            )
        except Exception:
            await context.bot.send_message(
                update.effective_chat.id, 
                "❌ *Delete Failed.* Admin rights confirm kar."
            )

@check_auth
@check_admin
async def nuke_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Naruto Pain themed message deletion interface (symbolic)."""
    await update.message.reply_text(
        "🌀 *Shinra Tensei... Message Deletion Panel Activated!* \n"
        "Abhi *full-scale Nuke* chalu nahi hua. Filhaal, *reply* kar /del se.",
        parse_mode="Markdown",
    )

# --- 6. Shout Command (With Complex Restriction) ---

@check_auth
@check_admin
async def shout_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Broadcasts a message with specific content restrictions."""
    if not context.args:
        await update.message.reply_text("📢 *Bolo Kya Chhapaun?* Sahi tareeka: `/shout <tera_message>`")
        return

    message_text = " ".join(context.args)
    restricted_words = {"aashirwad ki", "sp ki", "anant ki", "jhaa ki"}
    
    for word in restricted_words:
        # Create a regex pattern to match the word with optional dots or spaces between characters
        # e.g., 'a.a.s.h.i.r.w.a.d .k i'
        pattern = re.escape(word.replace(' ', '')) # Base word without spaces
        
        # Insert optional non-letter/non-digit characters (including dot/space) between every character
        # Example: 'a' becomes 'a[.\s]*'
        pattern_with_noise = r'[.\s]*'.join(list(pattern)) 
        
        # Optionally allow spaces around the full word match
        final_pattern = r'\b' + pattern_with_noise + r'\b'
        
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


# --- 7. Auto-Reply Handlers ---

@check_auth
async def add_reply_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Adds a customizable auto-reply and saves state."""
    if len(context.args) < 2:
        await update.message.reply_text("⚙️ Sahi tareeka: `/addreply <trigger_word> <response_text>`")
        return

    trigger = context.args[0].lower()
    response = " ".join(context.args[1:])
    auto_replies[trigger] = response
    save_data() # Save state
    
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
        save_data() # Save state
        await update.message.reply_text(f"✅ *Reply Deleted!* *{trigger.upper()}* ab *chup* rahega.", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"🤔 *Yeh Trigger Mila Hi Nahi.*")


# --- 8. Block/Unblock Handlers ---

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
    save_data() # Save state
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
        save_data() # Save state
        await update.message.reply_text(
            f"🔓 *UNBLOCK!* **{update.message.reply_to_message.from_user.full_name}** *wapis aa gaya*.",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("🤷‍♂️ *Yeh Banda Blocked Nahi Tha.*")


# --- 9. AI and Custom Message Handler ---

async def ai_response_placeholder(text: str) -> str:
    """Simulates an AI-powered, bilingual, gangster-mixed response."""
    # Integrate your actual AI API here.
    
    if "kya haal" in text.lower() or "how are you" in text.lower():
        return "Bhai, *mast*! Tu bata, *system* kaisa hai? Sab *changa*?"
    
    return f"Aye, *sahi baat*! *Main* samajh gaya. **Chal Hata!**"


async def custom_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles blocked users, Thala logic, auto-replies, and AI responses."""
    if not update.message or not update.message.text:
        return

    user_id = update.effective_user.id
    message_text = update.message.text
    
    # 1. Blocked User Check
    if user_id in blocked_users:
        return # Silently ignore
    
    # 2. Thala Logic (Complex Rule)
    if re.search(r"Thala", message_text, re.IGNORECASE):
        # Check if dot or space is present
        dot_or_space_present = re.search(r"[.\s]", message_text)
        
        # Remove all spaces and dots to check for length 7
        text_cleaned_for_7 = re.sub(r'[\s.]', '', message_text) 
        
        if dot_or_space_present:
            if len(text_cleaned_for_7) == 7:
                await update.message.reply_text(
                    "👑 *THALA FOR A REASON!* \n"
                    "**Tere Upar Bala Send**\n"
                    "Aur Sun, *7 Detected*, Bhai! *Perfect*!"
                )
            else:
                await update.message.reply_text("👑 **Tere Upar Bala Send**")
            return

    # 3. Auto-Reply System
    for trigger, response in auto_replies.items():
        if trigger in message_text.lower():
            await update.message.reply_text(response)
            return

    # 4. AI-Powered Responses (Only for authenticated users, if replied to bot or mentions bot)
    if user_id in authenticated_users:
        bot_mention = context.bot.username in message_text if context.bot.username else False
        is_reply = (update.message.reply_to_message and update.message.reply_to_message.from_user.id == context.bot.id)

        if is_reply or bot_mention:
            response = await ai_response_placeholder(message_text)
            await update.message.reply_text(response, parse_mode="Markdown")
            return


# --- 10. Main Application ---

def main() -> None:
    """Start the bot."""
    
    load_data() # Load persistent data at startup

    application = Application.builder().token(BOT_TOKEN).build()

    # Handlers Setup
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("login", login_command))
    application.add_handler(CommandHandler("logout", logout_command))

    application.add_handler(CommandHandler("kick", kick_command))
    application.add_handler(CommandHandler("ban", ban_command))
    application.add_handler(CommandHandler("mute", mute_command))
    
    application.add_handler(CommandHandler("shout", shout_command))
    application.add_handler(CommandHandler("nuke", nuke_command))
    application.add_handler(CommandHandler("del", del_command)) 

    application.add_handler(CommandHandler("addreply", add_reply_command))
    application.add_handler(CommandHandler("delreply", delete_reply_command))

    application.add_handler(CommandHandler("block", block_command))
    application.add_handler(CommandHandler("unblock", unblock_command))
    
    # MUST BE LAST: Message Handler for Thala, Auto-Replies, and AI
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, custom_message_handler)
    )

    logger.info("Bot is starting polling...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
