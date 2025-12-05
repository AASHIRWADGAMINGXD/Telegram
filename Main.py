import os
import logging
import re
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, 
    ContextTypes, 
    CommandHandler, 
    MessageHandler, 
    CallbackQueryHandler, 
    filters
)
from keep_alive import keep_alive

# --- LOGGING ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- CONFIG ---
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_PASSWORD = os.getenv("ADMIN_PASS", "BhaiKaSystem")

# --- IN-MEMORY DATABASE ---
authorized_users = set()
warns = {}
afk_users = {}
auto_replies = {}

# --- FORBIDDEN WORDS LISTS ---
# General abuse filter for chat
BAD_WORDS = {
  
}

# Specific phrases the Bot will REFUSE to shout
FORBIDDEN_SHOUTS = [
    "levi ki", 
    "aashirwad ki", 
    "shabd preet ki", 
    "anant ki"
     "Levi ki", 
    "Aashirwad ki", 
    "Shabd ki", 
    "Anant ki"
]

# --- HELPER: AUTH CHECK ---
async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    # Check if logged in via password
    if user_id in authorized_users:
        return True
    
    # Check actual Telegram Admin status
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        if member.status in ['administrator', 'creator']:
            return True
    except Exception as e:
        logger.error(f"Admin check error: {e}")
    return False

# --- CORE COMMANDS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = (
        "🙏 **Namaste Bhai!** System Update v2.0 Live.\n\n"
        "**Available Commands:**\n"
        "👮 `/warn` - Warning de (Reply to user)\n"
        "☢️ `/nuke` - **NEW:** Panel se message delete kar\n"
        "📢 `/shout [msg]` - Zor se bol (Mods Only)\n"
        "⬆️ `/promote` & ⬇️ `/demote` - Power control (Fixed)\n"
        "🐢 `/setslowmode [seconds]` - Chat speed (0, 10, 30...)\n"
        "💤 `/afk [reason]` - Offline chala ja\n"
        "📌 `/pin` & `/unpin` - Message chipkao\n"
        "🎲 `/roll` - Ludo khel le\n"
        "🤖 `/setautoreply [word] | [reply]` - Auto jawab\n"
        "❌ `/deleteautoreply [word]` - Auto jawab delete\n"
        "🔑 `/login [pass]` - Secret access"
    )
    await update.message.reply_text(txt, parse_mode='Markdown')

async def login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args and context.args[0] == ADMIN_PASSWORD:
        authorized_users.add(update.effective_user.id)
        await update.message.reply_text("😎 **System Set!** Ab tu Admin hai.")
    else:
        await update.message.reply_text("🤨 **Galat Password!**")

# --- MODERATION ---

async def warn_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return await update.message.reply_text("⛔ Power nahi hai tere paas!")
    
    if not update.message.reply_to_message:
        return await update.message.reply_text("Reply kar ke warn de!")

    target = update.message.reply_to_message.from_user
    chat_id = update.effective_chat.id

    if target.id == context.bot.id:
        return await update.message.reply_text("🤬 **Khud ko warn nahi dunga!**")

    current_warns = warns.get(target.id, 0) + 1
    warns[target.id] = current_warns

    msg = f"⚠️ **Warning!**\nUser: {target.first_name}\nCount: {current_warns}/3"
    
    if current_warns >= 3:
        try:
            await context.bot.ban_chat_member(chat_id, target.id)
            warns[target.id] = 0
            msg = f"🚫 **Khatam!** {target.first_name} ko uda diya (3 Warnings)."
        except Exception as e:
            msg += f"\n(Ban failed: {e})"

    await update.message.reply_text(msg)

async def shout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 1. MODERATOR ONLY CHECK
    if not await is_admin(update, context):
        return await update.message.reply_text("⛔ Sirf Admins shout kar sakte hain!")

    msg = " ".join(context.args)
    if not msg:
        return await update.message.reply_text("Likhna kya hai?")

    # 2. CENSORSHIP CHECK
    msg_lower = msg.lower()
    for forbidden in FORBIDDEN_SHOUTS:
        if forbidden in msg_lower:
            return await update.message.reply_text("❌ **Ye shabd allowed nahi hain!**")

    await update.message.reply_text(f"📢 **{msg.upper()}**", parse_mode='Markdown')

# --- NUKE SYSTEM (NEW PANEL) ---

async def nuke_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): 
        return await update.message.reply_text("⛔ Power nahi hai.")
    
    keyboard = [
        [
            InlineKeyboardButton("🗑️ Clean 10", callback_data='clean_10'),
            InlineKeyboardButton("🗑️ Clean 30", callback_data='clean_30')
        ],
        [
            InlineKeyboardButton("☢️ Clean 50", callback_data='clean_50'),
            InlineKeyboardButton("🔥 Clean 100", callback_data='clean_100')
        ],
        [InlineKeyboardButton("❌ Cancel", callback_data='nuke_cancel')]
    ]
    await update.message.reply_text("🧹 **Cleaning Panel**\nKitne message udane hain?", reply_markup=InlineKeyboardMarkup(keyboard))

async def nuke_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not await is_admin(update, context):
        return await query.answer("⛔ Admin only!", show_alert=True)

    await query.answer()
    data = query.data

    if data == 'nuke_cancel':
        await query.edit_message_text("👍 **Operation Cancelled.**")
        return

    # Extract number from 'clean_50' -> 50
    try:
        count = int(data.split('_')[1])
    except:
        return

    await query.edit_message_text(f"☢️ **Deleting last {count} messages...**")
    
    chat_id = query.message.chat_id
    msg_id = query.message.message_id
    
    deleted = 0
    # Loop to delete
    for i in range(count):
        try:
            # Delete message ID going backwards from the command
            await context.bot.delete_message(chat_id, msg_id - i)
            deleted += 1
        except Exception:
            pass # Skip if message doesn't exist or too old
        
    final_msg = await context.bot.send_message(chat_id, f"💥 **Safai Abhiyan Complete!**\nDeleted approx {deleted} messages.")
    # Delete the confirmation after 5 seconds
    await asyncio.sleep(5)
    try:
        await final_msg.delete()
    except:
        pass

# --- ADMIN TOOLS (FIXED) ---

async def promote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): 
        return await update.message.reply_text("⛔ Power nahi hai.")
    
    if not update.message.reply_to_message:
        return await update.message.reply_text("Reply karke promote kar.")

    user_id = update.message.reply_to_message.from_user.id
    chat_id = update.effective_chat.id

    try:
        # Full Admin Rights (Except adding new admins, restricted by Telegram API for bots usually)
        await context.bot.promote_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            can_manage_chat=True,
            can_delete_messages=True,
            can_manage_video_chats=True,
            can_restrict_members=True,
            can_promote_members=False, # Bots often can't grant this
            can_change_info=True,
            can_invite_users=True,
            can_pin_messages=True
        )
        await update.message.reply_text("🌟 **Badhai ho!** Banda promote ho gaya.")
    except Exception as e:
        await update.message.reply_text(f"❌ **Error:** {e}\n(Shayad mere paas khud power nahi hai ya banda pehle se admin hai)")

async def demote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): 
        return await update.message.reply_text("⛔ Power nahi hai.")
    
    if not update.message.reply_to_message:
        return await update.message.reply_text("Reply karke demote kar.")

    user_id = update.message.reply_to_message.from_user.id
    chat_id = update.effective_chat.id

    try:
        await context.bot.promote_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            can_manage_chat=False,
            can_delete_messages=False,
            can_manage_video_chats=False,
            can_restrict_members=False,
            can_promote_members=False,
            can_change_info=False,
            can_invite_users=False,
            can_pin_messages=False
        )
        await update.message.reply_text("🤡 **Demoted!** Power chhin li gayi.")
    except Exception as e:
        await update.message.reply_text(f"❌ **Error:** {e}")

async def set_slow_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): 
        return await update.message.reply_text("⛔ Power nahi hai.")
    
    if not context.args:
        return await update.message.reply_text("Usage: `/setslowmode 10`\nValid values: 0, 10, 30, 60, 300, 900, 3600")

    try:
        seconds = int(context.args[0])
        valid_values = [0, 10, 30, 60, 300, 900, 3600]
        
        if seconds not in valid_values:
            return await update.message.reply_text(f"❌ Invalid Number!\nUse only: {valid_values}")

        await context.bot.set_chat_slow_mode_delay(update.effective_chat.id, seconds)
        if seconds == 0:
            await update.message.reply_text("🏎️ **Slow Mode Off!**")
        else:
            await update.message.reply_text(f"🐢 **Slow Mode Set:** {seconds}s")
            
    except ValueError:
        await update.message.reply_text("❌ Number daal bhai.")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

async def pin_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await is_admin(update, context) and update.message.reply_to_message:
        try:
            await update.message.reply_to_message.pin()
            await update.message.reply_text("📌 Pinned.")
        except Exception as e:
            await update.message.reply_text(f"Error: {e}")

async def unpin_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await is_admin(update, context) and update.message.reply_to_message:
        try:
            await update.message.reply_to_message.unpin()
            await update.message.reply_text("📌 Unpinned.")
        except:
            pass

# --- UTILS ---
async def afk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    afk_users[update.effective_user.id] = " ".join(context.args) or "Busy"
    await update.message.reply_text(f"💤 **{update.effective_user.first_name}** is now AFK.")

async def roll(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_dice(update.effective_chat.id)

async def set_auto_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await is_admin(update, context):
        text = " ".join(context.args)
        if "|" in text:
            t, r = text.split("|", 1)
            auto_replies[t.strip().lower()] = r.strip()
            await update.message.reply_text("✅ Saved.")

async def delete_auto_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await is_admin(update, context):
        trigger = " ".join(context.args).lower().strip()
        if trigger in auto_replies:
            del auto_replies[trigger]
            await update.message.reply_text("🗑️ Deleted.")

# --- MAIN MESSAGE HANDLER ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    
    user = update.effective_user
    text_raw = update.message.text
    text_lower = text_raw.lower()
    
    # Check if message contains a Link (http, https, www)
    # If it contains a link, we DISABLE the Bala trigger to avoid false alarms
    is_link = re.search(r'(http|https|www\.)', text_lower)
    
    # 1. SPECIAL TRIGGER: "Tere Upar Bala" Logic (Bot command removed, but trigger kept)
    clean_text = re.sub(r'[\s\.]', '', text_lower) 
    
    triggered_bala = False
    if "7" in text_raw:
        triggered_bala = True
    elif "seven" in clean_text:
        triggered_bala = True
    elif "tupilepermeramut" in clean_text:
        triggered_bala = True
    
    if triggered_bala:
        await update.message.reply_text("Tere upar Bala")
        return # Stop processing abuse check for this fun trigger

    # 2. ABUSE FILTER
    found_bad = False
    for bad in BAD_WORDS:
        if bad in text_lower:
            found_bad = True
            break
            
    if found_bad:
        await update.message.reply_text(f"⛔ **Oye {user.first_name}!** Gaali mat de, tameez se reh.")

    # 3. AFK Handler
    if user.id in afk_users:
        del afk_users[user.id]
        await update.message.reply_text(f"👋 **Welcome Back {user.first_name}!**")

    if update.message.reply_to_message:
        replied_id = update.message.reply_to_message.from_user.id
        if replied_id in afk_users:
            await update.message.reply_text(f"🤫 **Wo AFK hai.** Reason: {afk_users[replied_id]}")

    # 4. Auto Reply
    if text_lower in auto_replies:
        await update.message.reply_text(auto_replies[text_lower])

# --- RUN ---
if __name__ == '__main__':
    keep_alive()
    if not TOKEN:
        print("❌ Error: TOKEN missing.")
        exit()
        
    app = ApplicationBuilder().token(TOKEN).build()
    
    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("login", login))
    app.add_handler(CommandHandler("warn", warn_user))
    app.add_handler(CommandHandler("shout", shout))
    app.add_handler(CommandHandler("nuke", nuke_panel)) # Updated to Panel
    app.add_handler(CommandHandler("promote", promote))
    app.add_handler(CommandHandler("demote", demote))
    app.add_handler(CommandHandler("setslowmode", set_slow_mode))
    app.add_handler(CommandHandler("pin", pin_msg))
    app.add_handler(CommandHandler("unpin", unpin_msg))
    app.add_handler(CommandHandler("afk", afk))
    app.add_handler(CommandHandler("roll", roll))
    app.add_handler(CommandHandler("setautoreply", set_auto_reply))
    app.add_handler(CommandHandler("deleteautoreply", delete_auto_reply))

    # Handlers
    app.add_handler(CallbackQueryHandler(nuke_callback))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    
    print("🚀 Bot Started with Updated Config...")
    app.run_polling()
