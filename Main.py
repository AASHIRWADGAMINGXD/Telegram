import os
import json
import logging
import asyncio
from telegram import Update, ChatPermissions
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from keep_alive import keep_alive

# --- CONFIGURATION ---
TOKEN = os.environ.get("BOT_TOKEN")

# Setup Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- PERSISTENCE LAYER ---
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

# --- ADMIN HELPER ---
async def is_admin(update: Update) -> bool:
    """Checks if the user is an admin or creator."""
    if not update.effective_chat:
        return False
    if update.effective_chat.type == "private":
        return True # Owner is admin in DM
        
    try:
        user_id = update.effective_user.id
        member = await update.effective_chat.get_member(user_id)
        return member.status in ['administrator', 'creator']
    except Exception as e:
        logger.error(f"Admin Check Error: {e}")
        return False

# --- COMMANDS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👁️ **The cycle of hatred begins...**\n\n"
        "I am online. My commands:\n"
        "⚡ /ban (Reply) - Shinra Tensei\n"
        "⚡ /kick (Reply) - Begone\n"
        "⚡ /mute (Reply) - Chibaku Tensei\n"
        "⚡ /nuke <num> - Almighty Push\n"
        "⚡ /block (Reply) - Block user from bot\n"
        "⚡ /shout <msg> - Yell\n"
        "⚡ /autoreply <trigger> | <response>\n"
        "⚡ /deleteautorelpy <trigger>\n\n"
        "Dattebayo!",
        parse_mode=ParseMode.MARKDOWN
    )

async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        await update.message.reply_text("❌ You lack the visual prowess.")
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("Reply to a ninja to ban them.")
        return

    user = update.message.reply_to_message.from_user
    try:
        await update.effective_chat.ban_member(user.id)
        await update.message.reply_text(f"🛑 **SHINRA TENSEI!**\n{user.first_name} has been purged.")
    except Exception as e:
        await update.message.reply_text(f"Failed to ban: {e}")

async def kick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update): return
    if not update.message.reply_to_message:
        await update.message.reply_text("Reply to a ninja to kick them.")
        return

    user = update.message.reply_to_message.from_user
    try:
        await update.effective_chat.unban_member(user.id)
        await update.message.reply_text(f"🦶 **Begone!**\n{user.first_name} was kicked.")
    except Exception as e:
        await update.message.reply_text(f"Failed to kick: {e}")

async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update): return
    if not update.message.reply_to_message:
        await update.message.reply_text("Reply to a ninja to silence them.")
        return

    user = update.message.reply_to_message.from_user
    permissions = ChatPermissions(can_send_messages=False)
    try:
        await update.effective_chat.restrict_member(user.id, permissions=permissions)
        await update.message.reply_text(f"🔇 **Chibaku Tensei!**\n{user.first_name} is silenced.")
    except Exception as e:
        await update.message.reply_text(f"Failed to mute: {e}")

async def nuke(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Deletes X messages safely."""
    if not await is_admin(update): return
    
    # Validation
    if not context.args:
        await update.message.reply_text("Usage: /nuke <number>")
        return
    try:
        limit = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Enter a number.")
        return

    # Delete command message
    try:
        await update.message.delete()
    except:
        pass

    chat_id = update.effective_chat.id
    current_msg_id = update.message.message_id
    deleted_count = 0

    status_msg = await context.bot.send_message(chat_id, f"☢️ **Almighty Push!** Targeting {limit} messages...", parse_mode=ParseMode.MARKDOWN)

    # Loop backwards
    for i in range(1, limit + 1):
        target_id = current_msg_id - i
        if target_id == status_msg.message_id: continue # Don't delete status msg

        try:
            await context.bot.delete_message(chat_id, target_id)
            deleted_count += 1
            await asyncio.sleep(0.05) # Anti-flood
        except BadRequest:
            continue # Skip msg if too old or missing
        except Exception as e:
            logger.error(f"Nuke error: {e}")

    # Success & Cleanup
    final_text = f"💥 **Destruction Complete.**\nDeleted {deleted_count} messages."
    await context.bot.edit_message_text(chat_id, status_msg.message_id, final_text, parse_mode=ParseMode.MARKDOWN)
    
    await asyncio.sleep(3)
    try:
        await context.bot.delete_message(chat_id, status_msg.message_id)
    except:
        pass

async def shout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = ' '.join(context.args)
    if not msg:
        await update.message.reply_text("Usage: /shout <message>")
        return
    await update.message.reply_text(f"📢 **{msg.upper()}! DATTEBAYO!**", parse_mode=ParseMode.MARKDOWN)

async def block_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Soft Ban: Ignores user messages."""
    if not await is_admin(update): return
    if not update.message.reply_to_message:
        await update.message.reply_text("Reply to block user.")
        return
    
    uid = update.message.reply_to_message.from_user.id
    data = load_data()
    if uid not in data["blocked"]:
        data["blocked"].append(uid)
        save_data(data)
        await update.message.reply_text(f"🚫 User {uid} is now ignored by the Akatsuki.")
    else:
        await update.message.reply_text("User is already blocked.")

# --- AUTO REPLY SYSTEM ---

async def autoreply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update): return
    text = ' '.join(context.args)
    if "|" not in text:
        await update.message.reply_text("Usage: /autoreply trigger | response")
        return
    
    trigger, response = text.split("|", 1)
    trigger = trigger.strip().lower()
    
    data = load_data()
    data["autoreply"][trigger] = response.strip()
    save_data(data)
    await update.message.reply_text(f"✅ Learned Jutsu: `{trigger}`", parse_mode=ParseMode.MARKDOWN)

async def delete_autoreply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update): return
    trigger = ' '.join(context.args).strip().lower()
    data = load_data()
    
    if trigger in data["autoreply"]:
        del data["autoreply"][trigger]
        save_data(data)
        await update.message.reply_text(f"🗑️ Forgot Jutsu: `{trigger}`", parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text("❌ Jutsu not found.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    
    # 1. Check if user is blocked
    uid = update.effective_user.id
    data = load_data()
    if uid in data["blocked"]:
        return

    # 2. Check for Auto Reply
    text = update.message.text.lower()
    if text in data["autoreply"]:
        await update.message.reply_text(data["autoreply"][text])

# --- MAIN ENTRY ---

def main():
    if not TOKEN:
        print("❌ CRITICAL ERROR: BOT_TOKEN is missing in Environment Variables.")
        return

    # Start Flask Server
    keep_alive()

    # Init Bot
    app = Application.builder().token(TOKEN).build()

    # Add Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ban", ban))
    app.add_handler(CommandHandler("kick", kick))
    app.add_handler(CommandHandler("mute"
