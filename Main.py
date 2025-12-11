import os
import re
import logging
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from functools import wraps

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
AUTH_PASSWORD = "bala"  # Change this to a secure password
ADMIN_USER_IDS = {
    123456789,
}  # Add the Telegram User IDs of your admins (integers)
ADMIN_USERNAMES = {
    "@uchihaitachidesu"
    "@Anantgamingxd"
    "@AashirwadGamerzz"
}  # Optional: Add admin usernames (strings)

# Global State
authenticated_users = set()  # Stores user IDs of authenticated users
auto_replies = {}  # Stores trigger: response pairs

# --- 2. Decorators & Access Control ---

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


# --- 3. Authentication and Session Management Handlers ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a bilingual greeting and prompts for login."""
    await update.message.reply_text(
        "👋 *Kya Haal, Bhai!*\n"
        "I'm your private Mod-Bot. Sabse pehle, *login* kar.\n"
        "Command: `/login <password>`",
        parse_mode="Markdown",
    )


async def login_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles user login with password authentication."""
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text(
            "🤦‍♂️ *Bhai, Password Kidhar?*\n"
            "Sahi tareeka: `/login <tera_password>`",
            parse_mode="Markdown",
        )
        return

    input_password = context.args[0]
    if input_password == AUTH_PASSWORD:
        authenticated_users.add(user_id)
        await update.message.reply_text(
            "✅ *Welcome back, Boss!* *Aaya Tu!*\n"
            "Ab tu *fully loaded* hai. Commands maar, *System* hila de.",
            parse_mode="Markdown",
        )
    else:
        await update.message.reply_text(
            "❌ *Galat Password, Chhote.* \n"
            "Chal, nikal. Phir aana jab *akal* aa jaaye."
        )


async def logout_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Logs out an authenticated user."""
    user_id = update.effective_user.id
    if user_id in authenticated_users:
        authenticated_users.remove(user_id)
        await update.message.reply_text(
            "👋 *Theek Hai, Ja.* \n"
            "Tera *session* khatam. Agli baar *password* laana."
        )
    else:
        await update.message.reply_text("🤔 *Tu Pehle Se Hi Bahar Hai.* \n" "Kya *mazak* kar raha hai?")


# --- 4. Moderation Handlers (Admin/Authenticated) ---

@check_auth
@check_admin
async def kick_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Kicks a user from the group."""
    if not update.message.reply_to_message:
        await update.message.reply_text(
            "👆 *Arey, kisko nikalna hai?* \n"
            "Command ko *reply* kar uss bande ke message par."
        )
        return
    
    target_user = update.message.reply_to_message.from_user
    chat_id = update.effective_chat.id
    
    try:
        await context.bot.ban_chat_member(chat_id, target_user.id)
        await context.bot.unban_chat_member(chat_id, target_user.id) # Unban immediately to allow re-joining
        await update.message.reply_text(
            f"💥 *BAHAR!* \n"
            f"**{target_user.full_name}** ko *dhakka* de diya. Ja simran, *jee* le apni zindagi... but not here.",
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error(f"Error kicking user: {e}")
        await update.message.reply_text("❌ *Kuchh Gadbad Hai!* \n" "Ya toh main admin nahi, ya yeh banda *bada aadmi* hai.")


@check_auth
@check_admin
async def ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Bans a user from the group."""
    if not update.message.reply_to_message:
        await update.message.reply_text(
            "👆 *Kisko hamesha ke liye bhagana hai?* \n"
            "Command ko *reply* kar uss bande ke message par."
        )
        return
    
    target_user = update.message.reply_to_message.from_user
    chat_id = update.effective_chat.id
    
    try:
        await context.bot.ban_chat_member(chat_id, target_user.id)
        await update.message.reply_text(
            f"🔨 *PAKKA BAN!* \n"
            f"**{target_user.full_name}** *sada* ke liye gaya. Ab *bhool* ja yeh group.",
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error(f"Error banning user: {e}")
        await update.message.reply_text("❌ *Kuchh Gadbad Hai!* \n" "Ya toh main admin nahi, ya *system* mein error hai.")


@check_auth
@check_admin
async def mute_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mutes a user for a short period (simulated for simplicity)."""
    # Real mute requires calculating permissions and time. We'll use a simple ban for 1 min as a quick example of temporary restriction.
    if not update.message.reply_to_message:
        await update.message.reply_text(
            "👆 *Kiska muh band karna hai?* \n"
            "Command ko *reply* kar uss bande ke message par."
        )
        return

    target_user = update.message.reply_to_message.from_user
    chat_id = update.effective_chat.id

    try:
        # Mute for 5 minutes (300 seconds)
        until_date = int(update.message.date.timestamp()) + 300 
        await context.bot.restrict_chat_member(
            chat_id,
            target_user.id,
            can_send_messages=False,
            until_date=until_date,
        )
        await update.message.reply_text(
            f"🤫 *SHHH!* \n"
            f"**{target_user.full_name}** ko *chuppi* de di. 5 minute *baad* aana.",
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error(f"Error muting user: {e}")
        await update.message.reply_text("❌ *Mute nahi hua, Boss!* \n" "Permission check kar le.")


# --- 5. Broadcast and Nuke Handlers (Advanced Admin) ---

@check_auth
@check_admin
async def shout_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Broadcasts a message to the group with restrictions."""
    if not context.args:
        await update.message.reply_text(
            "📢 *Bolo Kya Chhapaun?* \n"
            "Sahi tareeka: `/shout <tera_message>`"
        )
        return

    message_text = " ".join(context.args)
    # Shout Restriction Logic
    restricted_words = {"aashirwad ki", "sp ki", "anant ki", "jhaa ki"}
    
    # Restriction: If any restricted word (with or without dot/space) is found, DON'T send.
    for word in restricted_words:
        # Regex to match the restricted word with optional dots/spaces in between characters
        # Example: 'a.a.s.h.i.r.w.a.d. .k.i'
        pattern = re.escape(word)
        pattern = re.sub(r'(\s+)', r'[.\s]*', pattern) # Replace spaces in the word with optional dot/space
        pattern = re.sub(r'(.)', r'\1[.\s]*', pattern) # Add optional dot/space after every character

        if re.search(pattern, message_text, re.IGNORECASE):
            await update.message.reply_text(
                "🛑 *Shout Blocked.* \n"
                "Yeh *maal* **ban** hai. *Doosra* message bhej."
            )
            return

    # Broadcast the message
    await update.message.reply_text(
        f"📣 *BIGG NEWS FROM THE TOP!* \n\n"
        f"**{message_text}**",
        parse_mode="Markdown"
    )
    # Delete the original command message for cleanliness
    try:
        await update.message.delete()
    except Exception:
        pass # Ignore if bot can't delete the admin's message


@check_auth
@check_admin
async def nuke_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Provides a themed interface for message deletion (simulated)."""
    # This is a symbolic command. Real Nuke involves complex database logging and batch deletion,
    # often requiring a separate service or advanced permissions.
    await update.message.reply_text(
        "🌀 *Shinra Tensei... Message Deletion Panel Activated!* \n\n"
        "Bhai, abhi *full-scale Nuke* chalu nahi hua hai. \n"
        "Filhaal, *reply* kar /del se. *Aage* ka intezaam ho raha hai.",
        parse_mode="Markdown",
    )
    # A simple deletion helper for the replied message
    # Usage: Admin replies to a message with /del
    if update.message.reply_to_message:
        try:
            await update.message.reply_to_message.delete()
            await update.message.delete()
            await context.bot.send_message(
                update.effective_chat.id, 
                "🗑️ *Tabaah!* Ek message *raakh* ho gaya."
            )
        except Exception:
            await context.bot.send_message(
                update.effective_chat.id, 
                "❌ *Message Delete Nahi Hua.* Admin rights confirm kar."
            )

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
                "❌ *Delete Failed.*"
            )


# --- 6. Auto-Reply System Handlers ---

@check_auth
async def add_reply_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Adds a customizable auto-reply."""
    if len(context.args) < 2:
        await update.message.reply_text(
            "⚙️ *Adhoora Command, Yaar.* \n"
            "Sahi tareeka: `/addreply <trigger_word> <response_text>`"
        )
        return

    trigger = context.args[0].lower()
    response = " ".join(context.args[1:])
    auto_replies[trigger] = response
    
    await update.message.reply_text(
        f"🎯 *Auto-Reply Set!* \n"
        f"Trigger: *{trigger.upper()}*\n"
        f"Response: *{response[:30]}...*",
        parse_mode="Markdown"
    )


@check_auth
async def delete_reply_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Removes a configured auto-reply."""
    if not context.args:
        await update.message.reply_text(
            "🗑️ *Kaunsa Delete Karun?* \n"
            "Sahi tareeka: `/delreply <trigger_word>`"
        )
        return

    trigger = context.args[0].lower()
    if trigger in auto_replies:
        del auto_replies[trigger]
        await update.message.reply_text(f"✅ *Reply Deleted!* *{trigger.upper()}* ab *chup* rahega.", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"🤔 *Yeh Trigger Mila Hi Nahi.* *{trigger.upper()}* hai hi nahi.")


# --- 7. Block/Unblock User Interaction ---

blocked_users = set()

@check_auth
@check_admin
async def block_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Blocks a user from interacting with the bot."""
    if not update.message.reply_to_message:
        await update.message.reply_text("👆 *Kisko Block Karna Hai?* Reply kar uske message par.")
        return

    target_id = update.message.reply_to_message.from_user.id
    if target_id == update.effective_user.id:
        await update.message.reply_text("✋ *Khud Ko Nahi!* Kisi aur ko block kar.")
        return
    
    blocked_users.add(target_id)
    await update.message.reply_text(
        f"🚫 *BLOCK!* **{update.message.reply_to_message.from_user.full_name}** ab *bot* se baat nahi kar sakta.",
        parse_mode="Markdown"
    )

@check_auth
@check_admin
async def unblock_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Unblocks a user from interacting with the bot."""
    if not update.message.reply_to_message:
        await update.message.reply_text("👆 *Kisko Unblock Karna Hai?* Reply kar uske message par.")
        return

    target_id = update.message.reply_to_message.from_user.id
    
    if target_id in blocked_users:
        blocked_users.remove(target_id)
        await update.message.reply_text(
            f"🔓 *UNBLOCK!* **{update.message.reply_to_message.from_user.full_name}** *wapis aa gaya*.",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("🤷‍♂️ *Yeh Banda Blocked Nahi Tha.*")


# --- 8. AI and Custom Message Handler ---

async def ai_response_placeholder(text: str) -> str:
    """Simulates an AI-powered, bilingual, gangster-mixed response."""
    # This is where you would integrate your actual AI API call (e.g., Gemini, OpenAI)
    
    # Simple placeholder logic
    if "kya haal" in text.lower() or "how are you" in text.lower():
        return "Bhai, *mast*! Tu bata, *system* kaisa hai? Sab *changa*?"
    if "help" in text.lower():
        return "Tujhe *help* chahiyye? Apne *baap* se puch. Jokes apart, command list ke liye /start kar."
    
    return f"Aye, *sahi baat*! Tune bola: '{text[:20]}...'. Main bolta: *Chal Hata*, but main *samajh* gaya."


async def custom_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handles:
    1. Blocked users
    2. Auto-replies
    3. Thala-specific logic
    4. AI-powered conversational responses
    """
    if not update.message or not update.message.text:
        return

    user_id = update.effective_user.id
    message_text = update.message.text
    
    # 1. Blocked User Check
    if user_id in blocked_users:
        logger.info(f"Blocked user {user_id} tried to interact.")
        return # Silently ignore
    
    # 2. Thala Logic (High-priority and specific logic)
    # The condition is: 
    # - Message contains 'Thala' (case-insensitive)
    # - Message contains a dot or a space
    # - If the message's overall text (excluding dots/spaces) has a length of 7

    # Remove all spaces and dots for the specific '7 detected' rule
    text_cleaned_for_7 = re.sub(r'[\s.]', '', message_text) 

    if (
        re.search(r"Thala", message_text, re.IGNORECASE) and 
        re.search(r"[.\s]", message_text)
    ):
        if len(text_cleaned_for_7) == 7:
            await update.message.reply_text(
                "👑 *THALA FOR A REASON!* \n"
                "**Tere Upar Bala Send**\n"
                "Aur Sun, *7 Detected*, Bhai! *Perfect*!"
            )
            return
        else:
            await update.message.reply_text("👑 **Tere Upar Bala Send**")
            return

    # 3. Auto-Reply System
    for trigger, response in auto_replies.items():
        if trigger in message_text.lower():
            await update.message.reply_text(response)
            return

    # 4. AI-Powered Responses (Only for authenticated users)
    if user_id in authenticated_users:
        # Check if the message is a direct reply to the bot
        if (
            update.message.reply_to_message
            and update.message.reply_to_message.from_user.id == context.bot.id
        ):
            response = await ai_response_placeholder(message_text)
            await update.message.reply_text(response, parse_mode="Markdown")
            return
        
        # Simple non-command direct address (optional)
        if context.bot.username in message_text:
            response = await ai_response_placeholder(message_text)
            await update.message.reply_text(response, parse_mode="Markdown")
            return


# --- 9. Main Application and Keep Alive ---

def main() -> None:
    """Start the bot."""
    # Create the Application and pass it your bot's token.
    application = Application.builder().token(BOT_TOKEN).build()

    # Handlers for general commands
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("login", login_command))
    application.add_handler(CommandHandler("logout", logout_command))

    # Handlers for Moderation Commands
    application.add_handler(CommandHandler("kick", kick_command))
    application.add_handler(CommandHandler("ban", ban_command))
    application.add_handler(CommandHandler("mute", mute_command))
    
    # Handlers for Advanced Commands
    application.add_handler(CommandHandler("shout", shout_command))
    application.add_handler(CommandHandler("nuke", nuke_command))
    application.add_handler(CommandHandler("del", del_command)) # Simple delete helper

    # Handlers for Auto-Reply System
    application.add_handler(CommandHandler("addreply", add_reply_command))
    application.add_handler(CommandHandler("delreply", delete_reply_command))

    # Handlers for Block/Unblock
    application.add_handler(CommandHandler("block", block_command))
    application.add_handler(CommandHandler("unblock", unblock_command))
    
    # Message Handler (Must be last to avoid catching commands)
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, custom_message_handler)
    )

    # Note on Keep Alive: The `python-telegram-bot` long polling mechanism automatically handles the "keep alive"
    # aspect on most modern hosting platforms (like Render, which the user mentioned). You typically do not need
    # external "ping" logic for the bot itself to stay connected, just ensure the hosting service doesn't kill
    # the process due to inactivity. The code below keeps the Python process running.

    logger.info("Bot is starting polling...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
