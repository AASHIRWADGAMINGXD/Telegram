import os
import logging
import asyncio
from telegram import Update, ChatPermissions
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from keep_alive import keep_alive

# --- CONFIGURATION ---
TOKEN = os.environ.get("TOKEN")  # Get from Render Env Vars
PASSWORD = os.environ.get("PASSWORD", "admin123")  # Default password
OWNER_ID = int(os.environ.get("OWNER_ID", "6920845760")) # Optional: Your Telegram ID

# In-memory storage (Note: Resets on Render deploy/restart)
# For production, use a database like MongoDB.
AUTHORIZED_USERS = set()
if OWNER_ID != 0:
    AUTHORIZED_USERS.add(OWNER_ID)

WARNINGS = {}  # {user_id: count}

# --- LOGGING ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

# --- DECORATORS & CHECKS ---
async def is_authorized(update: Update) -> bool:
    user = update.effective_user
    # Allow if user is in authorized list OR is a Chat Admin
    if user.id in AUTHORIZED_USERS:
        return True
    
    # Check if user is admin in the group
    if update.effective_chat.type in ["group", "supergroup"]:
        member = await update.effective_chat.get_member(user.id)
        return member.status in ["administrator", "creator"]
    
    return False

# --- AUTH COMMANDS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Entry point. Check password."""
    args = context.args
    user_id = update.effective_user.id
    
    if user_id in AUTHORIZED_USERS:
        await update.message.reply_text("✅ You are already authorized. Use /help for commands.")
        return

    # Check if password provided: /start mypassword
    if args and args[0] == PASSWORD:
        AUTHORIZED_USERS.add(user_id)
        await update.message.reply_text("🔓 **Access Granted.** You are now an authorized admin.", parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text("🔒 **Access Denied.**\nUsage: `/start <password>`", parse_mode=ParseMode.MARKDOWN)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_authorized(update): return
    help_text = """
**🛡 Moderation Bot Commands**

**User Actions:**
/ban - Ban user
/unban - Unban user
/kick - Kick user
/mute - Mute user (read only)
/unmute - Unmute user
/tmute <m> - Temp mute (e.g., /tmute 10)
/promote - Promote to Admin
/demote - Demote Admin

**Chat Actions:**
/lock - Lock chat (no messages)
/unlock - Unlock chat
/purge <n> - Delete n messages
/pin - Pin message
/unpin - Unpin message
/unpinall - Unpin everything
/settitle <text> - Change Group Title
/setdesc <text> - Change Group Description

**Warnings:**
/warn - Warn user
/unwarn - Remove warn
/resetwarns - Clear all warns
/warns - Check user warns

**Utils:**
/id - Get Chat/User ID
/info - User info
/staff - List admins
/echo <text> - Bot speaks
    """
    await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)

# --- MODERATION FUNCTIONS ---

async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_authorized(update): return
    if not update.message.reply_to_message:
        await update.message.reply_text("Reply to a user to ban them.")
        return
    try:
        user_id = update.message.reply_to_message.from_user.id
        await update.effective_chat.ban_member(user_id)
        await update.message.reply_text("🔨 User Banned.")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_authorized(update): return
    if not update.message.reply_to_message: return
    try:
        user_id = update.message.reply_to_message.from_user.id
        await update.effective_chat.unban_member(user_id)
        await update.message.reply_text("🕊 User Unbanned.")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

async def kick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_authorized(update): return
    if not update.message.reply_to_message: return
    try:
        user_id = update.message.reply_to_message.from_user.id
        await update.effective_chat.unban_member(user_id) # Unbanning a member usually kicks them if they aren't banned
        await update.message.reply_text("👢 User Kicked.")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_authorized(update): return
    if not update.message.reply_to_message: return
    try:
        user_id = update.message.reply_to_message.from_user.id
        permissions = ChatPermissions(can_send_messages=False)
        await update.effective_chat.restrict_member(user_id, permissions)
        await update.message.reply_text("😶 User Muted.")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

async def unmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_authorized(update): return
    if not update.message.reply_to_message: return
    try:
        user_id = update.message.reply_to_message.from_user.id
        permissions = ChatPermissions(
            can_send_messages=True, can_send_media_messages=True, can_send_other_messages=True
        )
        await update.effective_chat.restrict_member(user_id, permissions)
        await update.message.reply_text("🗣 User Unmuted.")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

async def purge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_authorized(update): return
    try:
        count = int(context.args[0]) if context.args else 5
        message_id = update.message.message_id
        # Delete the command itself
        await update.message.delete()
        
        # This is a basic purge (Telegram API limits bulk delete, so we loop)
        # Note: Bots can't delete messages older than 48 hours
        tasks = []
        for i in range(count):
            tasks.append(context.bot.delete_message(chat_id=update.effective_chat.id, message_id=message_id - 1 - i))
        
        await asyncio.gather(*tasks, return_exceptions=True)
        msg = await update.effective_chat.send_message(f"🗑 Purged {count} messages.")
        # Auto delete notification
        await asyncio.sleep(3)
        await msg.delete()
    except Exception as e:
        pass

async def pin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_authorized(update): return
    if not update.message.reply_to_message: return
    await update.message.reply_to_message.pin()
    await update.message.reply_text("📌 Pinned.")

async def unpin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_authorized(update): return
    if not update.message.reply_to_message: return
    await update.message.reply_to_message.unpin()
    await update.message.reply_text("📍 Unpinned.")

async def lock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_authorized(update): return
    permissions = ChatPermissions(can_send_messages=False)
    await update.effective_chat.set_permissions(permissions)
    await update.message.reply_text("🔒 Chat Locked.")

async def unlock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_authorized(update): return
    permissions = ChatPermissions(
        can_send_messages=True, can_send_media_messages=True, can_send_other_messages=True,
        can_invite_users=True
    )
    await update.effective_chat.set_permissions(permissions)
    await update.message.reply_text("🔓 Chat Unlocked.")

async def set_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_authorized(update): return
    title = ' '.join(context.args)
    if not title: return
    await update.effective_chat.set_title(title)
    await update.message.reply_text(f"📝 Title set to: {title}")

# --- WARNING SYSTEM ---

async def warn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_authorized(update): return
    if not update.message.reply_to_message: return
    user_id = update.message.reply_to_message.from_user.id
    name = update.message.reply_to_message.from_user.first_name
    
    WARNINGS[user_id] = WARNINGS.get(user_id, 0) + 1
    count = WARNINGS[user_id]
    
    await update.message.reply_text(f"⚠️ Warned {name}. (Total: {count}/3)")
    
    if count >= 3:
        await update.effective_chat.ban_member(user_id)
        await update.message.reply_text(f"🚫 {name} has been banned for reaching 3 warns.")
        WARNINGS[user_id] = 0

async def unwarn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_authorized(update): return
    if not update.message.reply_to_message: return
    user_id = update.message.reply_to_message.from_user.id
    if user_id in WARNINGS and WARNINGS[user_id] > 0:
        WARNINGS[user_id] -= 1
        await update.message.reply_text(f"📉 Warn removed. Current: {WARNINGS[user_id]}")
    else:
        await update.message.reply_text("User has no warnings.")

async def get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    reply_id = update.message.reply_to_message.from_user.id if update.message.reply_to_message else None
    
    msg = f"Chat ID: `{chat_id}`\nYour ID: `{user_id}`"
    if reply_id:
        msg += f"\nReplied User ID: `{reply_id}`"
    
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

# --- MAIN EXECUTION ---

def main():
    # 1. Create Application
    application = Application.builder().token(TOKEN).build()

    # 2. Add Handlers
    # Core
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    
    # Moderation
    application.add_handler(CommandHandler("ban", ban))
    application.add_handler(CommandHandler("unban", unban))
    application.add_handler(CommandHandler("kick", kick))
    application.add_handler(CommandHandler("mute", mute))
    application.add_handler(CommandHandler("unmute", unmute))
    application.add_handler(CommandHandler("purge", purge))
    application.add_handler(CommandHandler("pin", pin))
    application.add_handler(CommandHandler("unpin", unpin))
    application.add_handler(CommandHandler("lock", lock))
    application.add_handler(CommandHandler("unlock", unlock))
    application.add_handler(CommandHandler("settitle", set_title))
    
    # Warnings
    application.add_handler(CommandHandler("warn", warn))
    application.add_handler(CommandHandler("unwarn", unwarn))
    
    # Utils
    application.add_handler(CommandHandler("id", get_id))

    # 3. Start Keep Alive (For Render)
    keep_alive()

    # 4. Run Bot
    print("Bot is running...")
    application.run_polling()

if __name__ == "__main__":
    main()
