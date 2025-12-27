import os
import logging
import asyncio
from dotenv import load_dotenv
from telegram import Update, ChatPermissions
from telegram.ext import (
    ApplicationBuilder, 
    ContextTypes, 
    CommandHandler, 
    MessageHandler, 
    filters
)
from keep_alive import keep_alive

# 1. LOAD ENVIRONMENT
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    print("❌ Error: BOT_TOKEN not found in .env file.")
    exit(1)

# 2. LOGGING CONFIG
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# 3. MEMORY STORAGE
anti_raid_status = {} 

# --- 🧠 THE BOT BRAIN (Safety & Helper Functions) ---

async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    try:
        member = await context.bot.get_chat_member(update.effective_chat.id, user_id)
        return member.status in ['administrator', 'creator']
    except:
        return False

async def check_authority(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user_id = update.effective_user.id
    if not await is_admin(update, context, user_id):
        await update.message.reply_text("⛔ **Access Denied:** Administrators only.")
        return False
    return True

async def get_target(update: Update):
    if not update.message.reply_to_message:
        await update.message.reply_text("⚠️ Reply to a user's message to perform this action.")
        return None
    return update.message.reply_to_message.from_user

async def safety_check(update: Update, context: ContextTypes.DEFAULT_TYPE, target_user) -> bool:
    if target_user.id == context.bot.id:
        await update.message.reply_text("🤖 **System Protocol:** I cannot ban or mute myself.")
        return False
    
    if await is_admin(update, context, target_user.id):
        await update.message.reply_text(f"🛡️ **Security:** I cannot punish Admin {target_user.first_name}.")
        return False
        
    return True

# --- 🛠️ FEATURE COMMANDS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 **Professional Manager Bot Online**\n"
        "Commands:\n/antiraid, /shout, /clear, /pin, /kick, /ban, /mute"
    )

async def cmd_clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_authority(update, context): return
    if update.message.reply_to_message:
        try:
            await update.message.reply_to_message.delete()
            await update.message.delete()
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {e}")
    else:
        await update.message.reply_text("Usage: Reply to the message you want to /clear.")

async def cmd_shout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_authority(update, context): return
    args = context.args
    if not args:
        return await update.message.reply_text("Usage: `/shout <message>`", parse_mode='Markdown')
    
    text = " ".join(args).upper()
    try:
        msg = await update.message.reply_text(f"📢 **ANNOUNCEMENT**\n\n{text}", parse_mode='Markdown')
        await msg.pin(disable_notification=False)
    except:
        await update.message.reply_text("⚠️ Could not pin.")

async def cmd_pin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_authority(update, context): return
    if not update.message.reply_to_message: return
    try:
        await update.message.reply_to_message.pin()
    except:
        await update.message.reply_text("❌ Failed to pin.")

async def cmd_unpin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_authority(update, context): return
    if not update.message.reply_to_message: return
    try:
        await update.message.reply_to_message.unpin()
    except:
        await update.message.reply_text("❌ Failed to unpin.")

# --- ⚖️ MODERATION TOOLS ---

async def cmd_kick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_authority(update, context): return
    target = await get_target(update)
    if not target or not await safety_check(update, context, target): return

    try:
        await context.bot.ban_chat_member(update.effective_chat.id, target.id)
        await context.bot.unban_chat_member(update.effective_chat.id, target.id)
        await update.message.reply_text(f"👢 **{target.first_name}** was kicked.")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

async def cmd_ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_authority(update, context): return
    target = await get_target(update)
    if not target or not await safety_check(update, context, target): return

    try:
        await context.bot.ban_chat_member(update.effective_chat.id, target.id)
        await update.message.reply_text(f"⛔ **{target.first_name}** has been banned permanently.")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

async def cmd_mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_authority(update, context): return
    target = await get_target(update)
    if not target or not await safety_check(update, context, target): return

    try:
        permissions = ChatPermissions(can_send_messages=False)
        await context.bot.restrict_chat_member(update.effective_chat.id, target.id, permissions=permissions)
        await update.message.reply_text(f"🔇 **{target.first_name}** is now muted.")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

# --- 🛡️ WATCHERS ---

async def cmd_antiraid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_authority(update, context): return
    chat_id = update.effective_chat.id
    current_status = anti_raid_status.get(chat_id, False)
    anti_raid_status[chat_id] = not current_status
    status = "ENABLED" if not current_status else "DISABLED"
    await update.message.reply_text(f"🛡️ Anti-Raid {status}")

async def watcher_new_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if anti_raid_status.get(chat_id, False):
        for member in update.message.new_chat_members:
            if member.id == context.bot.id: continue
            try:
                await context.bot.ban_chat_member(chat_id, member.id)
                await context.bot.unban_chat_member(chat_id, member.id)
            except: pass

async def watcher_autoreply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    msg = update.message.text.lower()
    if "admin" in msg: await update.message.reply_text("👨‍💻 Admins are busy.")
    elif "rules" in msg: await update.message.reply_text("📜 Check pinned messages.")

# --- ⚠️ ERROR HANDLER ---

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Log the error and send a telegram message to notify the developer."""
    logger.error("Exception while handling an update:", exc_info=context.error)

# --- 🚀 RUNNER ---

if __name__ == '__main__':
    keep_alive()
    print("🔥 System Starting...")
    
    application = ApplicationBuilder().token(TOKEN).build()
    
    # Register Error Handler
    application.add_error_handler(error_handler)

    # Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("clear", cmd_clear))
    application.add_handler(CommandHandler("shout", cmd_shout))
    application.add_handler(CommandHandler("pin", cmd_pin))
    application.add_handler(CommandHandler("unpin", cmd_unpin))
    application.add_handler(CommandHandler("kick", cmd_kick))
    application.add_handler(CommandHandler("mute", cmd_mute))
    application.add_handler(CommandHandler("ban", cmd_ban))
    application.add_handler(CommandHandler("banchannel", cmd_ban))
    application.add_handler(CommandHandler("antiraid", cmd_antiraid))
    
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, watcher_new_members))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), watcher_autoreply))

    print("✅ Bot is Live.")
    application.run_polling()
