import logging
import asyncio
import google.generativeai as genai
from telegram import Update, ChatPermissions
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
from keep_alive import keep_alive

# --- CONFIGURATION ---
TOKEN = "8578532543:AAE-r1vXUkNPVmIIDuMRz1oFhAg9GY0UQH4"  # ⚠️ REPLACE THIS
GEMINI_API_KEY = "AIzaSyAjUI-SgoHBIiXH8TasuA8dTq4F7A_6LuI"

# --- SETUP ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Configure Google Gemini AI
genai.configure(api_key=GEMINI_API_KEY)
# Using the specific version to avoid 404s
try:
    model = genai.GenerativeModel('gemini-1.5-flash-001')
except:
    model = genai.GenerativeModel('gemini-pro')

# --- DATA STORAGE (In-Memory) ---
thala_counts = {}  # {user_id: count}
afk_data = {}      # {user_id: {"reason": str, "name": str}}

# --- PERMISSION CHECK ---
async def is_user_admin(update: Update):
    if not update.effective_chat or not update.effective_user:
        return False
    member = await update.effective_chat.get_member(update.effective_user.id)
    return member.status in ['administrator', 'creator']

# --- AFK COMMANDS ---

async def set_afk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sets the user as AFK. Usage: /setafk <reason>"""
    user = update.effective_user
    
    # Get reason (default if empty)
    if context.args:
        reason = ' '.join(context.args)
    else:
        reason = "I am away"

    # Store AFK data
    afk_data[user.id] = {
        "reason": reason,
        "name": user.first_name
    }

    await update.message.reply_text(
        f"💤 <b>{user.first_name}</b> is now AFK.\nReason: {reason}", 
        parse_mode=ParseMode.HTML
    )

async def afk_clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manually removes AFK status."""
    user = update.effective_user
    if user.id in afk_data:
        del afk_data[user.id]
        await update.message.reply_text(f"👋 Welcome back, <b>{user.first_name}</b>! AFK removed.", parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text("You are not AFK.")

# --- MODERATOR COMMANDS ---

async def mute_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_user_admin(update):
        await update.message.reply_text("❌ You don't have permission.")
        return
    reply = update.message.reply_to_message
    if not reply:
        await update.message.reply_text("⚠️ Reply to the user to mute.")
        return
    try:
        await update.effective_chat.restrict_member(reply.from_user.id, permissions=ChatPermissions(can_send_messages=False))
        await update.message.reply_text(f"🔇 <b>{reply.from_user.first_name}</b> has been muted.", parse_mode=ParseMode.HTML)
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

async def unmute_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_user_admin(update): return
    reply = update.message.reply_to_message
    if not reply:
        await update.message.reply_text("⚠️ Reply to the user to unmute.")
        return
    try:
        await update.effective_chat.restrict_member(
            reply.from_user.id, 
            permissions=ChatPermissions(can_send_messages=True, can_send_media_messages=True, can_send_other_messages=True)
        )
        await update.message.reply_text(f"🔊 <b>{reply.from_user.first_name}</b> has been unmuted.", parse_mode=ParseMode.HTML)
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

async def promote_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_user_admin(update): return
    reply = update.message.reply_to_message
    if not reply:
        await update.message.reply_text("⚠️ Reply to a user to promote.")
        return
    try:
        await update.effective_chat.promote_member(
            user_id=reply.from_user.id,
            can_manage_chat=True, can_delete_messages=True, can_restrict_members=True, can_invite_users=True
        )
        await update.message.reply_text(f"👮‍♂️ <b>{reply.from_user.first_name}</b> is now an Admin!", parse_mode=ParseMode.HTML)
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

async def demote_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_user_admin(update): return
    reply = update.message.reply_to_message
    if not reply:
        await update.message.reply_text("⚠️ Reply to an admin to demote.")
        return
    try:
        await update.effective_chat.promote_member(
            user_id=reply.from_user.id,
            can_manage_chat=False, can_delete_messages=False, can_restrict_members=False
        )
        await update.message.reply_text(f"📉 <b>{reply.from_user.first_name}</b> has been demoted.", parse_mode=ParseMode.HTML)
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

async def clear_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_user_admin(update): return
    if not context.args:
        await update.message.reply_text("⚠️ Usage: /clear <number>")
        return
    try:
        amount = int(context.args[0])
        msg_id = update.message.message_id
        chat_id = update.message.chat_id
        await update.message.delete()
        deleted = 0
        for i in range(1, amount + 1):
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=msg_id - i)
                deleted += 1
            except Exception: continue
        status = await context.bot.send_message(chat_id, f"🧹 Cleared {deleted} messages.")
        await asyncio.sleep(3)
        await status.delete()
    except ValueError:
        await update.message.reply_text("⚠️ Please provide a valid number.")

# --- AI FEATURE ---

async def ask_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❓ Usage: `/ask What is Python?`", parse_mode=ParseMode.MARKDOWN)
        return

    user_query = ' '.join(context.args)
    status_msg = await update.message.reply_text("🤔 Thinking...")

    try:
        response = await asyncio.to_thread(model.generate_content, user_query)
        ai_text = response.text
        if len(ai_text) > 4000: ai_text = ai_text[:4000] + "..."
        await context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=status_msg.message_id, text=ai_text, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        await context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=status_msg.message_id, text=f"❌ Error: {e}")

# --- GLOBAL MESSAGE MONITOR (AFK + THALA) ---

async def global_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles Text messages to check for AFK status and Thala counting."""
    if not update.message or not update.message.text:
        return

    user = update.effective_user
    text = update.message.text.lower()
    
    # 1. AUTO-REMOVE AFK: If an AFK user speaks, remove AFK status
    if user.id in afk_data:
        del afk_data[user.id]
        welcome_msg = await update.message.reply_text(f"👋 Welcome back <b>{user.first_name}</b>! I removed your AFK.", parse_mode=ParseMode.HTML)
        # Optional: Delete welcome message after 5 seconds to keep chat clean
        await asyncio.sleep(5)
        try: await welcome_msg.delete()
        except: pass

    # 2. CHECK REPLIES: If someone replies to an AFK user
    if update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user
        if target_user.id in afk_data:
            info = afk_data[target_user.id]
            await update.message.reply_text(
                f"💤 <b>{info['name']}</b> is currently AFK.\nReason: {info['reason']}",
                parse_mode=ParseMode.HTML
            )
    
    # 3. CHECK MENTIONS: If someone mentions an AFK user (basic text check)
    # This checks if any AFK user's first name is in the message
    # (Optional: removed for simplicity, Reply check is usually sufficient)

    # 4. ANTI-THALA CHECKER
    if "thala" in text:
        current_count = thala_counts.get(user.id, 0) + 1
        thala_counts[user.id] = current_count
        if current_count == 3:
            await update.message.reply_text("🛑 You thala limit reached")


# --- MAIN ---

if __name__ == '__main__':
    keep_alive()
    app = ApplicationBuilder().token(TOKEN).build()

    # Admin/Mod
    app.add_handler(CommandHandler("mute", mute_user))
    app.add_handler(CommandHandler("unmute", unmute_user))
    app.add_handler(CommandHandler("admin", promote_user))
    app.add_handler(CommandHandler("demote", demote_user))
    app.add_handler(CommandHandler("clear", clear_messages))
    
    # AFK
    app.add_handler(CommandHandler("setafk", set_afk))
    app.add_handler(CommandHandler("afkclear", afk_clear_command))

    # AI
    app.add_handler(CommandHandler("ask", ask_command))
    
    # Global Handler (Must be last to capture text)
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), global_message_handler))

    print("Bot is running...")
    app.run_polling()
