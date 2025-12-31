import logging
import json
import os
import sys
import re
import asyncio
import uuid
import requests
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from dotenv import load_dotenv

from telegram import Update, ChatPermissions, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
    CallbackQueryHandler,
    ChatJoinRequestHandler, 
)

# ================= ⚙️ CONFIGURATION =================
load_dotenv()

PORT = int(os.environ.get("PORT", 8080))
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = os.getenv("OWNER_ID")

if not BOT_TOKEN:
    print("❌ ERROR: BOT_TOKEN is missing. Check .env file.")
    sys.exit(1)

if OWNER_ID:
    try:
        OWNER_ID = int(OWNER_ID)
    except ValueError:
        pass

DATA_FILE = "bot_data.json"

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# ================= 🌐 1. WEB SERVER (Prevents Timeout) =================
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.wfile.write(b"Bot is active.")

def start_web_server():
    try:
        server = HTTPServer(("0.0.0.0", PORT), HealthCheckHandler)
        server.serve_forever()
    except:
        pass

# ================= 💾 2. DATABASE SYSTEM =================
class DataManager:
    def __init__(self):
        self.data = self._load()

    def _load(self):
        if not os.path.exists(DATA_FILE):
            return {
                "chats": {}, 
                "gban_list": [], 
                "stored_msgs": {}
            }
        try:
            with open(DATA_FILE, "r") as f:
                return json.load(f)
        except:
            return {"chats": {}, "gban_list": [], "stored_msgs": {}}

    def save(self):
        with open(DATA_FILE, "w") as f:
            json.dump(self.data, f, indent=4)

    def get_chat(self, chat_id):
        cid = str(chat_id)
        if cid not in self.data["chats"]:
            self.data["chats"][cid] = {
                "settings": {
                    "welcome": True, 
                    "antilink": False,
                    "antiraid": False # New Feature
                },
                "text": {"welcome": "Hello {name}!"},
                "filters": {},
                "locked": []
            }
            self.save()
        return self.data["chats"][cid]

    def update_setting(self, chat_id, setting, value):
        c = self.get_chat(chat_id)
        c["settings"][setting] = value
        self.save()

    def set_text(self, chat_id, key, text):
        c = self.get_chat(chat_id)
        c["text"][key] = text
        self.save()

    def add_gban(self, user_id):
        if user_id not in self.data["gban_list"]:
            self.data["gban_list"].append(user_id)
            self.save()

    def check_gban(self, user_id):
        return user_id in self.data["gban_list"]

    def store_msg(self, text):
        uid = str(uuid.uuid4())[:8]
        if "stored_msgs" not in self.data:
            self.data["stored_msgs"] = {}
        self.data["stored_msgs"][uid] = text
        self.save()
        return uid

    def get_msg(self, uid):
        return self.data.get("stored_msgs", {}).get(uid, None)

    def add_filter(self, chat_id, trigger, reply):
        c = self.get_chat(chat_id)
        c["filters"][trigger.lower()] = reply
        self.save()

db = DataManager()

# ================= 🛡️ HELPERS =================
async def is_admin(update: Update) -> bool:
    if update.effective_user.id == OWNER_ID: return True
    chat = update.effective_chat
    if chat.type == "private": return True
    member = await chat.get_member(update.effective_user.id)
    return member.status in ["administrator", "creator"]

def admin_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if await is_admin(update):
            return await func(update, context)
        else:
            msg = await update.message.reply_text("⛔ **Admin Only**", parse_mode=ParseMode.MARKDOWN)
            await asyncio.sleep(2)
            try: await msg.delete()
            except: pass
    return wrapper

# ================= 🆕 COMMANDS =================

async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /start and Special Links"""
    args = context.args
    if args:
        token = args[0]
        content = db.get_msg(token)
        if content:
            await update.message.reply_text(f"📩 **Stored Message:**\n\n{content}")
        else:
            await update.message.reply_text("❌ Link expired or invalid.")
    else:
        await update.message.reply_text("🤖 **Bot Online!** Type /help for commands.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📚 **Command List**\n\n"
        "**👮 Moderation:**\n"
        "`/ban`, `/kick`, `/mute`, `/unmute`\n"
        "`/clear <num>` - Delete messages\n"
        "`/lock <text/media/all>`, `/unlock`\n"
        "`/antiraid <on/off>` - Ban new joins\n"
        "`/antilink <on/off>`\n\n"
        "**🔗 Tools:**\n"
        "`/genlink` - Create Invite + TinyURL\n"
        "`/shortener <url>` - Shorten URL\n"
        "`/special_link <text>` - Store text\n"
        "`/link <name> <limit>` - **Approval Link**\n\n"
        "**⚙️ Utils:**\n"
        "`/shout <text>` - 📢 **LOUD**\n"
        "`/broadcast <msg>` - Send to all chats\n"
        "`/setwelcome <text>`\n"
        "`/info`, `/id`"
    )
    await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)

@admin_only
async def genlink(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/genlink - Generate TinyURL Invite"""
    chat = update.effective_chat
    try:
        link = await chat.create_invite_link(member_limit=1)
        # TinyURL
        api = f"http://tinyurl.com/api-create.php?url={link.invite_link}"
        short = requests.get(api).text
        await update.message.reply_text(f"🔗 **Invite Generated:**\n{short}")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

async def shortener_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/shortener <url> - Shorten external URL"""
    if not context.args:
        return await update.message.reply_text("Usage: /shortener <https://example.com>")
    
    url = context.args[0]
    try:
        api = f"http://tinyurl.com/api-create.php?url={url}"
        short = requests.get(api).text
        await update.message.reply_text(f"✅ **Short Link:**\n{short}")
    except:
        await update.message.reply_text("❌ Failed to shorten.")

async def special_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/special_link - Store multi-line text"""
    text = ""
    if update.message.reply_to_message:
        text += update.message.reply_to_message.text or ""
        text += "\n\n"
    
    if context.args:
        user_input = update.message.text.split(" ", 1)[1]
        text += user_input
    
    if not text:
        return await update.message.reply_text("Usage: /special_link <text> (or reply)")

    uid = db.store_msg(text)
    bot_url = f"https://t.me/{context.bot.username}?start={uid}"
    await update.message.reply_text(f"🔐 **Stored!**\n\n🔗 Link:\n{bot_url}")

async def shout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/shout <text> - BOLD CAPS"""
    if not context.args: return
    msg = " ".join(context.args).upper()
    await update.message.reply_text(f"📢 **{msg}**", parse_mode=ParseMode.MARKDOWN)

@admin_only
async def antiraid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/antiraid on/off"""
    if not context.args: return await update.message.reply_text("Usage: /antiraid on/off")
    val = context.args[0].lower() == "on"
    db.update_setting(update.effective_chat.id, "antiraid", val)
    status = "🔴 ENABLED (New members will be Banned)" if val else "🟢 DISABLED"
    await update.message.reply_text(f"🛡 **Anti-Raid:** {status}")

# ================= 🔗 ADVANCED APPROVAL SYSTEM =================
@admin_only
async def create_approval_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/link Name Limit"""
    if len(context.args) < 1: return await update.message.reply_text("Usage: /link <Name> <Limit>")
    name = context.args[0]
    limit = int(context.args[1]) if len(context.args) > 1 and context.args[1].isdigit() else None
    
    try:
        link = await update.effective_chat.create_invite_link(
            name=name, 
            member_limit=limit, 
            creates_join_request=True 
        )
        await update.message.reply_text(
            f"🛡 **Approval Link Created**\n"
            f"🔗 {link.invite_link}\n\n"
            f"Users clicking this must be approved by Admin."
        )
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

async def join_request_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Triggered when user clicks /link"""
    req = update.chat_join_request
    user = req.from_user
    chat = req.chat
    
    # Message to Group
    text = (
        f"Hey {user.full_name} (@{user.username or 'NoUser'}) Is Requesting to Join\n"
        f"Chat: {chat.title}"
    )
    
    # Buttons
    kb = [
        [
            InlineKeyboardButton("Yes", callback_data=f"join_yes_{user.id}"),
            InlineKeyboardButton("No", callback_data=f"join_no_{user.id}")
        ]
    ]
    
    await context.bot.send_message(
        chat_id=chat.id, 
        text=text, 
        reply_markup=InlineKeyboardMarkup(kb)
    )

async def join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not await is_admin(update):
        return await query.answer("❌ Admins Only!", show_alert=True)

    data = query.data.split("_")
    action = data[1] # yes or no
    user_id = int(data[2])
    chat = update.effective_chat
    
    if action == "yes":
        try:
            await chat.approve_join_request(user_id)
            await query.edit_message_text(f"✅ **Yes.** User {user_id} Approved.", parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            await query.edit_message_text(f"Error: {e}")
            
    elif action == "no":
        try:
            await chat.decline_join_request(user_id)
            await query.edit_message_text(f"🚫 **No.** User {user_id} Rejected.", parse_mode=ParseMode.MARKDOWN)
            
            # DM The User
            try:
                # Fetching user info is hard if not in chat, but we try standard send
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"Sorry, you can't join. You are Rejected By Owner / Admin."
                )
            except:
                pass # User privacy settings
        except Exception as e:
            await query.edit_message_text(f"Error: {e}")

# ================= 👮 MODERATION COMMANDS =================
@admin_only
async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message: return await update.message.reply_text("Reply to user.")
    try:
        await update.effective_chat.ban_member(update.message.reply_to_message.from_user.id)
        await update.message.reply_text("🔨 **Banned.**", parse_mode=ParseMode.MARKDOWN)
    except Exception as e: await update.message.reply_text(str(e))

@admin_only
async def kick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message: return await update.message.reply_text("Reply to user.")
    try:
        await update.effective_chat.unban_member(update.message.reply_to_message.from_user.id)
        await update.message.reply_text("👞 **Kicked.**", parse_mode=ParseMode.MARKDOWN)
    except: pass

@admin_only
async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message: return
    try:
        await update.effective_chat.restrict_member(update.message.reply_to_message.from_user.id, permissions=ChatPermissions(can_send_messages=False))
        await update.message.reply_text("🔇 **Muted.**", parse_mode=ParseMode.MARKDOWN)
    except: pass

@admin_only
async def unmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message: return
    try:
        await update.effective_chat.restrict_member(update.message.reply_to_message.from_user.id, permissions=ChatPermissions(can_send_messages=True, can_send_media_messages=True))
        await update.message.reply_text("🔊 **Unmuted.**", parse_mode=ParseMode.MARKDOWN)
    except: pass

@admin_only
async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/clear <num> or reply"""
    if update.message.reply_to_message:
        # Purge from reply
        msg_id = update.message.reply_to_message.message_id
        current_id = update.message.message_id
        ids = list(range(msg_id, current_id + 1))
    elif context.args and context.args[0].isdigit():
        # Purge last N
        num = int(context.args[0])
        current_id = update.message.message_id
        ids = list(range(current_id - num, current_id + 1))
    else:
        return await update.message.reply_text("Reply to a message OR use: /clear 10")

    # Batch delete
    chunk_size = 100
    deleted = 0
    for i in range(0, len(ids), chunk_size):
        chunk = ids[i:i + chunk_size]
        try:
            await update.effective_chat.delete_messages(chunk)
            deleted += len(chunk)
        except: pass
    
    msg = await update.message.reply_text(f"🗑 **Cleared {deleted} messages.**", parse_mode=ParseMode.MARKDOWN)
    await asyncio.sleep(3)
    try: await msg.delete()
    except: pass

@admin_only
async def lock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args: return
    arg = context.args[0].lower()
    c = db.get_chat(update.effective_chat.id)
    if arg not in c["locked"]:
        c["locked"].append(arg)
        db.save()
    if arg == "all":
        await update.effective_chat.set_permissions(ChatPermissions(can_send_messages=False))
    await update.message.reply_text(f"🔒 Locked: **{arg}**", parse_mode=ParseMode.MARKDOWN)

@admin_only
async def unlock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args: return
    arg = context.args[0].lower()
    c = db.get_chat(update.effective_chat.id)
    if arg in c["locked"]:
        c["locked"].remove(arg)
        db.save()
    if arg == "all":
        await update.effective_chat.set_permissions(ChatPermissions(can_send_messages=True, can_send_media_messages=True, can_send_other_messages=True))
    await update.message.reply_text(f"🔓 Unlocked: **{arg}**", parse_mode=ParseMode.MARKDOWN)

@admin_only
async def set_welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args: return
    db.set_text(update.effective_chat.id, "welcome", " ".join(context.args))
    await update.message.reply_text("✅ Welcome saved.")

@admin_only
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args: return
    msg = " ".join(context.args)
    count = 0
    for cid in db.data["chats"]:
        try:
            await context.bot.send_message(cid, f"📢 **Broadcast:**\n{msg}", parse_mode=ParseMode.MARKDOWN)
            count += 1
        except: pass
    await update.message.reply_text(f"Sent to {count} chats.")

# ================= 🚀 MAIN HANDLER =================
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    chat_id = update.effective_chat.id
    text = update.message.text
    chat_data = db.get_chat(chat_id)
    is_adm = await is_admin(update)

    # 1. Antilink
    if chat_data["settings"]["antilink"] and not is_adm:
        if re.search(r"(https?://|www\.|t\.me|telegram\.me)[a-zA-Z0-9_./-]+", text, re.IGNORECASE):
            try: await update.message.delete()
            except: pass
            return

    # 2. Text Lock
    if not is_adm and "text" in chat_data["locked"]:
        await update.message.delete()
        return

    # 3. Filters
    text_lower = text.lower()
    if text_lower in chat_data["filters"]:
        await update.message.reply_text(chat_data["filters"][text_lower])

async def welcome_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_data = db.get_chat(update.effective_chat.id)
    
    # 1. Anti-Raid (Ban new users if ON)
    if chat_data["settings"]["antiraid"]:
        for m in update.message.new_chat_members:
            try:
                await update.effective_chat.ban_member(m.id)
                await update.message.reply_text(f"🛡 **AntiRaid:** Banned {m.first_name}")
            except: pass
        return

    # 2. Welcome
    if chat_data["settings"]["welcome"]:
        for m in update.message.new_chat_members:
            if db.check_gban(m.id): 
                await update.effective_chat.ban_member(m.id)
            else: 
                await update.message.reply_text(chat_data["text"]["welcome"].format(name=m.first_name, chat=update.effective_chat.title))

# ================= 🚀 START =================
def main():
    print("🚀 Bot Starting...")
    threading.Thread(target=start_web_server, daemon=True).start()
    
    app = Application.builder().token(BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("help", help_command))
    
    # Tools
    app.add_handler(CommandHandler("genlink", genlink))
    app.add_handler(CommandHandler("shortener", shortener_cmd)) 
    app.add_handler(CommandHandler("special_link", special_link))
    app.add_handler(CommandHandler("link", create_approval_link))
    app.add_handler(CommandHandler("shout", shout))
    
    # Moderation
    app.add_handler(CommandHandler("ban", ban))
    app.add_handler(CommandHandler("kick", kick))
    app.add_handler(CommandHandler("mute", mute))
    app.add_handler(CommandHandler("unmute", unmute))
    app.add_handler(CommandHandler("clear", clear)) # Alias for purge
    app.add_handler(CommandHandler("purge", clear)) # Keep purge as alias
    
    # Settings
    app.add_handler(CommandHandler("lock", lock))
    app.add_handler(CommandHandler("unlock", unlock))
    app.add_handler(CommandHandler("setwelcome", set_welcome))
    app.add_handler(CommandHandler("antiraid", antiraid))
    app.add_handler(CommandHandler("broadcast", broadcast))

    # Handlers
    app.add_handler(ChatJoinRequestHandler(join_request_handler))
    app.add_handler(CallbackQueryHandler(join_callback, pattern="^join_"))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    print("✅ Bot is Online!")
    app.run_polling()

if __name__ == "__main__":
    main()
