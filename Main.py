import logging
import json
import os
import asyncio
import datetime
from collections import deque, defaultdict
from flask import Flask
from threading import Thread
from telegram import (
    Update, 
    InlineKeyboardButton, 
    InlineKeyboardMarkup, 
    ChatPermissions, 
    constants
)
from telegram.ext import (
    ApplicationBuilder, 
    ContextTypes, 
    CommandHandler, 
    MessageHandler, 
    CallbackQueryHandler, 
    filters
)

# ==========================================
# 1. CONFIGURATION
# ==========================================

# 🔴 PUT YOUR TOKEN HERE
TOKEN = os.getenv("TELEGRAM_TOKEN", "YOUR_BOT_TOKEN_GOES_HERE")

# Data File
DATA_FILE = "bot_data.json"

# Slowmode Configuration
SLOWMODE_TRIGGER = 5      # Messages count
SLOWMODE_WINDOW = 5       # Seconds window
SLOWMODE_DURATION = 10    # Slowmode duration in seconds
SLOWMODE_COOLDOWN = 2     # Turn off if msgs < this

# Logging Setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# In-memory Data (Loaded from JSON)
bot_data = {
    "blocked_words": [],
    "auto_replies": {}
}

# Traffic Monitor: {chat_id: deque([timestamps])}
chat_traffic = defaultdict(lambda: deque(maxlen=20))

# ==========================================
# 2. KEEP ALIVE SERVER (Flask)
# ==========================================
app = Flask('')

@app.route('/')
def home():
    return "Telegram Bot is Running!"

def run_flask():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run_flask)
    t.start()

# ==========================================
# 3. DATA PERSISTENCE
# ==========================================
def load_data():
    global bot_data
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            bot_data = json.load(f)

def save_data():
    with open(DATA_FILE, 'w') as f:
        json.dump(bot_data, f, indent=4)

# ==========================================
# 4. HELP COMMAND (NEW)
# ==========================================

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays the help menu."""
    txt = (
        "🤖 **BOT COMMANDS**\n\n"
        "🛡️ **Admin & Moderation**\n"
        "`/kick` - Reply to user to kick\n"
        "`/ban` - Reply to user to ban\n"
        "`/mute` - Reply to user to mute\n"
        "`/lock` - Lock the chat\n"
        "`/unlock` - Unlock the chat\n"
        "`/blockword add <word>` - Block a word\n"
        "`/blockword remove <word>` - Unblock a word\n"
        "`/shout <msg>` - Pin an announcement\n"
        "`/admin` - Promote user\n"
        "`/depromote` - Demote user\n\n"
        
        "⚙️ **Configuration**\n"
        "`/autoreply <trigger> <msg>` - Set auto-reply\n"
        "`/setup_ticket <Title>|<Desc>` - Create Ticket Panel\n\n"
        
        "ℹ️ **General**\n"
        "`/serverinfo` - Chat stats\n"
        "`/userinfo` - User stats\n"
        "`/avatar` - Get user profile pic\n"
        "`/help` - Show this menu"
    )
    await update.message.reply_text(txt, parse_mode=constants.ParseMode.MARKDOWN)

# ==========================================
# 5. MODERATION COMMANDS
# ==========================================

async def kick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_admin(update): return
    target_id = await get_target_id(update, context)
    if not target_id: return
    try:
        await update.effective_chat.ban_member(target_id)
        await update.effective_chat.unban_member(target_id)
        await update.message.reply_text("👢 User has been kicked.")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_admin(update): return
    target_id = await get_target_id(update, context)
    if not target_id: return
    try:
        await update.effective_chat.ban_member(target_id)
        await update.message.reply_text("🔨 User has been banned.")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_admin(update): return
    target_id = await get_target_id(update, context)
    if not target_id: return
    perms = ChatPermissions(can_send_messages=False)
    try:
        await update.effective_chat.restrict_member(target_id, permissions=perms)
        await update.message.reply_text("🤐 User has been muted.")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

async def lock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_admin(update): return
    perms = ChatPermissions(can_send_messages=False)
    try:
        await update.effective_chat.set_permissions(perms)
        await update.message.reply_text("🔒 Chat is now LOCKED.")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

async def unlock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_admin(update): return
    perms = ChatPermissions(
        can_send_messages=True, can_send_media_messages=True,
        can_send_other_messages=True, can_add_web_page_previews=True,
        can_invite_users=True
    )
    try:
        await update.effective_chat.set_permissions(perms)
        await update.message.reply_text("🔓 Chat is now UNLOCKED.")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

# --- BLOCK WORD COMMAND ---
async def blockword(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Usage: /blockword add badword"""
    if not await check_admin(update): return
    
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /blockword <add/remove> <word>")
        return

    action = context.args[0].lower()
    word = context.args[1].lower()

    if action == "add":
        if word not in bot_data["blocked_words"]:
            bot_data["blocked_words"].append(word)
            save_data()
            await update.message.reply_text(f"🚫 Added ||{word}|| to blocklist.", parse_mode=constants.ParseMode.MARKDOWN_V2)
        else:
            await update.message.reply_text("Word already blocked.")
    elif action == "remove":
        if word in bot_data["blocked_words"]:
            bot_data["blocked_words"].remove(word)
            save_data()
            await update.message.reply_text(f"✅ Removed ||{word}|| from blocklist.", parse_mode=constants.ParseMode.MARKDOWN_V2)
        else:
            await update.message.reply_text("Word not found in blocklist.")

# ==========================================
# 6. ADMIN UTILITY COMMANDS
# ==========================================

async def promote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_admin(update): return
    target_id = await get_target_id(update, context)
    if not target_id: return
    try:
        await update.effective_chat.promote_member(
            target_id, can_manage_chat=True, can_delete_messages=True, 
            can_invite_users=True, can_pin_messages=True
        )
        await update.message.reply_text("👮 User promoted.")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

async def depromote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_admin(update): return
    target_id = await get_target_id(update, context)
    if not target_id: return
    try:
        await update.effective_chat.promote_member(
            target_id, can_manage_chat=False, can_delete_messages=False, 
            can_invite_users=False
        )
        await update.message.reply_text("📉 User demoted.")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

async def shout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_admin(update): return
    text = " ".join(context.args)
    if not text:
        await update.message.reply_text("Usage: /shout <message>")
        return
    msg = await update.message.reply_text(f"📢 **ANNOUNCEMENT**\n\n{text}", parse_mode=constants.ParseMode.MARKDOWN)
    try: await msg.pin()
    except: pass

async def autoreply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_admin(update): return
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /autoreply <trigger> <response>")
        return
    trigger = context.args[0]
    response = " ".join(context.args[1:])
    bot_data["auto_replies"][trigger] = response
    save_data()
    await update.message.reply_text(f"🤖 Autoreply set: {trigger} -> {response}")

# ==========================================
# 7. INFO COMMANDS
# ==========================================

async def chatinfo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    count = await chat.get_member_count()
    msg = f"📊 **Server Info**\nName: {chat.title}\nID: `{chat.id}`\nMembers: {count}\nType: {chat.type}"
    await update.message.reply_text(msg, parse_mode=constants.ParseMode.MARKDOWN)

async def userinfo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.reply_to_message.from_user if update.message.reply_to_message else update.message.from_user
    msg = f"👤 **User Info**\nName: {user.full_name}\nID: `{user.id}`\nUsername: @{user.username}"
    await update.message.reply_text(msg, parse_mode=constants.ParseMode.MARKDOWN)

async def avatar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.reply_to_message.from_user if update.message.reply_to_message else update.message.from_user
    pics = await user.get_profile_photos(limit=1)
    if pics.total_count > 0:
        await update.message.reply_photo(pics.photos[0][-1].file_id)
    else:
        await update.message.reply_text("No avatar found.")

# ==========================================
# 8. TICKET SYSTEM
# ==========================================

async def setup_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_admin(update): return
    if not context.args:
        await update.message.reply_text("Usage: /setup_ticket Title | Desc | [ImageURL]")
        return

    raw = " ".join(context.args)
    parts = [p.strip() for p in raw.split('|')]
    title = parts[0]
    desc = parts[1] if len(parts) > 1 else "Click below to contact support."
    img = parts[2] if len(parts) > 2 else None

    keyboard = [[InlineKeyboardButton("📩 Open Ticket", callback_data="create_ticket")]]
    markup = InlineKeyboardMarkup(keyboard)

    txt = f"🎫 *{title}*\n\n{desc}"
    if img:
        await update.message.reply_photo(img, caption=txt, parse_mode=constants.ParseMode.MARKDOWN, reply_markup=markup)
    else:
        await update.message.reply_text(txt, parse_mode=constants.ParseMode.MARKDOWN, reply_markup=markup)
    await update.message.delete()

async def ticket_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "create_ticket":
        chat = query.message.chat
        user = query.from_user
        if chat.is_forum:
            try:
                topic = await chat.create_forum_topic(name=f"Ticket - {user.first_name}")
                control_kb = [[InlineKeyboardButton("🔒 Close Ticket", callback_data=f"close_ticket_{topic.message_thread_id}")]]
                msg_txt = f"👋 Hello {user.mention_markdown()}!\n\n✅ **Ticket Created**"
                await context.bot.send_message(
                    chat_id=chat.id, message_thread_id=topic.message_thread_id,
                    text=msg_txt, parse_mode=constants.ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(control_kb)
                )
                link = f"https://t.me/c/{str(chat.id)[4:]}/{topic.message_thread_id}"
                await query.message.reply_text(f"✅ Ticket opened! [Click Here]({link})", parse_mode=constants.ParseMode.MARKDOWN, disable_web_page_preview=True)
            except Exception as e:
                await query.message.reply_text(f"❌ Error: {e}\n(Ensure Topics are enabled and I am Admin)")
        else:
            await query.message.reply_text("❌ Tickets require 'Topics' enabled in group settings.")
    elif query.data.startswith("close_ticket_"):
        topic_id = int(query.data.split("_")[2])
        try:
            await context.bot.close_forum_topic(chat_id=query.message.chat.id, message_thread_id=topic_id)
            await query.message.reply_text("🔒 Ticket closed.")
        except: pass

# ==========================================
# 9. MESSAGE MONITOR (BLOCKS & SLOWMODE)
# ==========================================

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    
    msg = update.message
    text = msg.text.lower()
    chat = update.effective_chat

    # --- 1. BLOCKED WORDS LOGIC ---
    if any(w in text for w in bot_data["blocked_words"]):
        try:
            await msg.delete()
            await chat.send_message(f"🚫 {msg.from_user.mention_markdown()}, that word is blocked!", parse_mode=constants.ParseMode.MARKDOWN)
        except: pass
        return

    # --- 2. AUTO REPLY ---
    if msg.text in bot_data["auto_replies"]:
        await msg.reply_text(bot_data["auto_replies"][msg.text])

    # --- 3. DYNAMIC SLOWMODE ---
    if chat.type in [constants.ChatType.SUPERGROUP, constants.ChatType.GROUP]:
        cid = chat.id
        now = datetime.datetime.now().timestamp()
        chat_traffic[cid].append(now)
        while len(chat_traffic[cid]) > 0 and chat_traffic[cid][0] < now - SLOWMODE_WINDOW:
            chat_traffic[cid].popleft()
        count = len(chat_traffic[cid])
        if count >= SLOWMODE_TRIGGER:
            try: await chat.set_slow_mode_delay(SLOWMODE_DURATION)
            except: pass
        elif count <= SLOWMODE_COOLDOWN:
            try: await chat.set_slow_mode_delay(0)
            except: pass

# ==========================================
# 10. HELPERS & MAIN
# ==========================================

async def check_admin(update: Update) -> bool:
    chat = update.effective_chat
    if chat.type == "private": return True
    member = await chat.get_member(update.effective_user.id)
    if member.status in ['administrator', 'creator']: return True
    await update.message.reply_text("⛔ You are not an admin.")
    return False

async def get_target_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.reply_to_message: return update.message.reply_to_message.from_user.id
    if context.args:
        try: return int(context.args[0])
        except: await update.message.reply_text("⚠ Invalid ID.")
    else: await update.message.reply_text("⚠ Reply to a user or use ID.")
    return None

if __name__ == '__main__':
    load_data()
    keep_alive()

    app_bot = ApplicationBuilder().token(TOKEN).build()

    # Handlers
    app_bot.add_handler(CommandHandler("start", lambda u,c: u.message.reply_text("Bot is Online!")))
    app_bot.add_handler(CommandHandler("help", help_command)) # ADDED
    app_bot.add_handler(CommandHandler(["kick"], kick))
    app_bot.add_handler(CommandHandler(["ban"], ban))
    app_bot.add_handler(CommandHandler(["mute"], mute))
    app_bot.add_handler(CommandHandler(["lock"], lock))
    app_bot.add_handler(CommandHandler(["unlock"], unlock))
    app_bot.add_handler(CommandHandler("blockword", blockword)) # VERIFIED
    app_bot.add_handler(CommandHandler(["admin", "promote"], promote))
    app_bot.add_handler(CommandHandler(["depromote"], depromote))
    app_bot.add_handler(CommandHandler(["shout"], shout))
    app_bot.add_handler(CommandHandler("autoreply", autoreply))
    app_bot.add_handler(CommandHandler(["serverinfo", "chatinfo"], chatinfo))
    app_bot.add_handler(CommandHandler(["userinfo"], userinfo))
    app_bot.add_handler(CommandHandler(["avatar"], avatar))
    app_bot.add_handler(CommandHandler("setup_ticket", setup_ticket))
    app_bot.add_handler(CallbackQueryHandler(ticket_callback))
    
    # Message Handler (Must be last)
    app_bot.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), message_handler))

    print("Bot is running...")
    app_bot.run_polling()
