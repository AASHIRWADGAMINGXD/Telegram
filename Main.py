import os
import json
import logging
import asyncio
from telegram import Update, ChatPermissions
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from keep_alive import keep_alive

# --- CONFIGURATION ---
# Load Token from Environment Variable for Security
TOKEN = os.environ.get("BOT_TOKEN")

# Setup Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- PERSISTENCE (JSON) ---
DB_FILE = "storage.json"

def load_data():
    if not os.path.exists(DB_FILE):
        return {"autoreply": {}, "blocked": []}
    try:
        with open(DB_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {"autoreply": {}, "blocked": []}

def save_data(data):
    with open(DB_FILE, "w") as f:
        json.dump(data, f, indent=4)

# --- HELPER: CHECK ADMIN ---
async def is_admin(update: Update) -> bool:
    """Checks if the user triggering the command is an admin."""
    if not update.effective_chat or not update.effective_user:
        return False
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    try:
        member = await update.effective_chat.get_member(user_id)
        return member.status in ['administrator', 'creator']
    except Exception as e:
        logger.error(f"Error checking admin: {e}")
        return False

# --- COMMANDS: PAIN THEME (Admin/Punishment) ---

async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        await update.message.reply_text("❌ You lack the visual prowess (Admin rights) for this.")
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("Please reply to a shinobi to execute **Shinra Tensei** (Ban).", parse_mode=ParseMode.MARKDOWN)
        return

    user_to_ban = update.message.reply_to_message.from_user
    try:
        await update.effective_chat.ban_member(user_to_ban.id)
        await update.message.reply_text(f"🛑 **SHINRA TENSEI!**\n{user_to_ban.first_name} has been purged from this world.", parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        await update.message.reply_text(f"Failed to ban: {e}")

async def kick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        await update.message.reply_text("❌ You are too weak to use this jutsu.")
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("Reply to a user to kick them.")
        return

    user_to_kick = update.message.reply_to_message.from_user
    try:
        await update.effective_chat.unban_member(user_to_kick.id) # Unban effectively kicks if not already banned
        await update.message.reply_text(f"🦶 **Begone!**\n{user_to_kick.first_name} was kicked. Know Pain.", parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        await update.message.reply_text(f"Failed to kick: {e}")

async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        await update.message.reply_text("❌ You do not possess the Rinnegan.")
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("Reply to a user to seal their voice.")
        return

    user_to_mute = update.message.reply_to_message.from_user
    permissions = ChatPermissions(can_send_messages=False)
    
    try:
        await update.effective_chat.restrict_member(user_to_mute.id, permissions=permissions)
        await update.message.reply_text(f"🔇 **Chibaku Tensei!**\n{user_to_mute.first_name} has been silenced.", parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        await update.message.reply_text(f"Failed to mute: {e}")

async def nuke(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Deletes X messages."""
    if not await is_admin(update):
        await update.message.reply_text("❌ You cannot destroy this village.")
        return

    args = context.args
    if not args:
        await update.message.reply_text("Usage: /nuke <number>")
        return

    try:
        count = int(args[0])
        message_id = update.message.message_id
        chat_id = update.message.chat_id
        
        # Delete the command message itself first
        await update.message.delete()
        
        # Batch delete is not directly supported by all clients easily, we iterate.
        # Note: Bots cannot delete messages older than 48 hours.
        deleted_count = 0
        current_id = message_id - 1
        
        status_msg = await context.bot.send_message(chat_id, f"☢️ **Almighty Push!** Destroying {count} messages...", parse_mode=ParseMode.MARKDOWN)
        
        # Attempt to delete previous messages
        for _ in range(count):
            try:
                await context.bot.delete_message(chat_id, current_id)
                deleted_count += 1
            except Exception:
                pass # Skip if message doesn't exist or can't be deleted
            current_id -= 1

        await context.bot.edit_message_text(chat_id=chat_id, message_id=status_msg.message_id, text=f"💥 **Art is an Explosion!**\nDeleted {deleted_count} messages.")
        
    except ValueError:
        await update.message.reply_text("Please provide a valid number.")

# --- COMMANDS: GENERAL / NARUTO THEME ---

async def shout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = ' '.join(context.args)
    if not msg:
        await update.message.reply_text("Usage: /shout <message>")
        return
    # Shout in bold and uppercase
    response = f"📢 **{msg.upper()}! DATTEBAYO!**"
    await update.message.reply_text(response, parse_mode=ParseMode.MARKDOWN)

async def block_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Blocks a user from using the bot (Soft Ban)."""
    if not await is_admin(update):
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("Reply to a user to block them from bot interaction.")
        return

    user_id = update.message.reply_to_message.from_user.id
    data = load_data()
    
    if user_id not in data["blocked"]:
        data["blocked"].append(user_id)
        save_data(data)
        await update.message.reply_text(f"🚫 User {user_id} has been blocked from using my jutsu.")
    else:
        await update.message.reply_text("User is already blocked.")

# --- AUTO REPLY SYSTEM ---

async def add_autoreply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Syntax: /autoreply trigger | response
    if not await is_admin(update):
        await update.message.reply_text("❌ Only the Kage can teach me new words.")
        return
        
    text = ' '.join(context.args)
    if "|" not in text:
        await update.message.reply_text("Usage: /autoreply trigger word | response message")
        return

    trigger, response = text.split("|", 1)
    trigger = trigger.strip().lower()
    response = response.strip()

    data = load_data()
    data["autoreply"][trigger] = response
    save_data(data)

    await update.message.reply_text(f"✅ **Jutsu Learned!**\nTrigger: `{trigger}`\nResponse: `{response}`", parse_mode=ParseMode.MARKDOWN)

async def delete_autoreply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return
        
    trigger = ' '.join(context.args).strip().lower()
    data = load_data()
    
    if trigger in data["autoreply"]:
        del data["autoreply"][trigger]
        save_data(data)
        await update.message.reply_text(f"🗑️ Forgot jutsu: `{trigger}`", parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text("❌ I don't know that jutsu.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    user_id = update.effective_user.id
    data = load_data()

    # Check Block
    if user_id in data["blocked"]:
        return # Ignore blocked users

    # Auto Reply Logic
    text = update.message.text.lower()
    if text in data["autoreply"]:
        await update.message.reply_text(data["autoreply"][text])

# --- MAIN EXECUTION ---
def main():
    if not TOKEN:
        print("Error: BOT_TOKEN is missing in .env")
        return

    # Start the Keep Alive server (Flask)
    keep_alive()

    # Build the Application
    app = Application.builder().token(TOKEN).build()

    # Admin Handlers
    app.add_handler(CommandHandler("ban", ban))
    app.add_handler(CommandHandler("kick", kick))
    app.add_handler(CommandHandler("mute", mute))
    app.add_handler(CommandHandler("nuke", nuke))
    app.add_handler(CommandHandler("block", block_user))
    
    # Auto Reply Handlers
    app.add_handler(CommandHandler("autoreply", add_autoreply))
    app.add_handler(CommandHandler("deleteautoreply", delete_autoreply))
    
    # General Handlers
    app.add_handler(CommandHandler("shout", shout))
    
    # Message Handler (Must be last)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Shinobi Bot is running... Dattebayo!")
    app.run_polling()

if __name__ == "__main__":
    main()
