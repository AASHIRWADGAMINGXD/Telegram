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

# Render/Heroku provide the PORT variable automatically
PORT = int(os.environ.get("PORT", 8080))

BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = os.getenv("OWNER_ID")

if not BOT_TOKEN:
    print("❌ ERROR: BOT_TOKEN is missing. Check your environment variables.")
    sys.exit(1)

if OWNER_ID:
    try:
        OWNER_ID = int(OWNER_ID)
    except ValueError:
        print("⚠️ WARNING: OWNER_ID must be a number.")

DATA_FILE = "bot_data.json"

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# ================= 🌐 1. WEB SERVER (FIXES PORT TIMEOUT) =================
# This dummy server tricks Render/Heroku into thinking we are a web app
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Bot is alive and running!")

def start_web_server():
    try:
        server = HTTPServer(("0.0.0.0", PORT), HealthCheckHandler)
        print(f"🌍 Web server started on port {PORT}")
        server.serve_forever()
    except Exception as e:
        print(f"❌ Web server error: {e}")

# ================= 💾 2. DATABASE SYSTEM =================
class DataManager:
    def __init__(self):
        self.data = self._load()

    def _load(self):
        if not os.path.exists(DATA_FILE):
            return {
                "chats": {}, 
                "gban_list": [],
                "special_links": {} 
            }
        try:
            with open(DATA_FILE, "r") as f:
                return json.load(f)
        except:
            return {"chats": {}, "gban_list": [], "special_links": {}}

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
                },
                "text": {
                    "welcome": "Hello {name}, welcome to {chat}!",
                },
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

    def add_special_msg(self, text):
        uid = str(uuid.uuid4())[:8]
        if "special_links" not in self.data:
            self.data["special_links"] = {}
        self.data["special_links"][uid] = text
        self.save()
        return uid

    def get_special_msg(self, uid):
        return self.data.get("special_links", {}).get(uid, None)

db = DataManager()

# ================= 🛡️ PERMISSIONS =================
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
            msg = await update.message.reply_text("⛔ **Admin access only.**", parse_mode=ParseMode.MARKDOWN)
            await asyncio.sleep(3)
            try: await msg.delete() 
            except: pass
    return wrapper

def owner_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id == OWNER_ID:
            return await func(update, context)
        else:
            await update.message.reply_text("⛔ **Bot Owner only.**")
    return wrapper

# ================= 🆕 COMMANDS =================

async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /start and /start <token> for special links"""
    args = context.args
    
    # Check if it's a deep link (Special Link Access)
    if args:
        token = args[0]
        secret_msg = db.get_special_msg(token)
        if secret_msg:
            await update.message.reply_text(f"🔓 **Secret Message:**\n\n{secret_msg}")
        else:
            await update.message.reply_text("❌ Invalid or expired link.")
    else:
        # Normal Start
        await update.message.reply_text(
            "🤖 **Bot Online!**\n\n"
            "I manage groups, handle join requests, and more.\n"
            "Use /help to see commands."
        )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🤖 **Bot Command List**\n\n"
        "**👮 Admin:**\n"
        "/ban, /unban, /mute, /unmute, /purge\n"
        "/lock <text/media/all>, /unlock, /antilink <on/off>\n\n"
        "**🔗 Invite System:**\n"
        "`/link <name> <limit>` - Create approval link (Admin Only)\n"
        "`/genlink` - Create standard invite\n"
        "`/shortener <url>` - Shorten URLs\n"
        "`/special_link <text>` - Create secret message link\n\n"
        "**📢 Tools:**\n"
        "`/broadcast <msg>` - Send to all chats\n"
        "`/info` - User Info"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

@admin_only
async def genlink(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    try:
        link = await chat.create_invite_link(member_limit=1)
        await update.message.reply_text(f"🔗 **New Standard Invite:**\n{link.invite_link}")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

async def shortener(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args: return await update.message.reply_text("Usage: /shortener <url>")
    url = context.args[0]
    msg = await update.message.reply_text("🔄 Shortening...")
    try:
        api_url = f"http://tinyurl.com/api-create.php?url={url}"
        res = requests.get(api_url)
        if res.status_code == 200:
            await msg.edit_text(f"✅ **Link:** {res.text}")
        else:
            await msg.edit_text("❌ Failed.")
    except Exception as e:
        await msg.edit_text(f"Error: {e}")

@owner_only
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args: return await update.message.reply_text("Usage: /broadcast <message>")
    msg = " ".join(context.args)
    count = 0
    status = await update.message.reply_text("📢 Broadcasting...")
    
    chats = list(db.data["chats"].keys())
    for chat_id in chats:
        try:
            await context.bot.send_message(chat_id, f"📢 **Broadcast:**\n{msg}", parse_mode=ParseMode.MARKDOWN)
            count += 1
            await asyncio.sleep(0.5) 
        except:
            pass 
    await status.edit_text(f"✅ Broadcast Sent to {count} chats.")

async def special_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args: return await update.message.reply_text("Usage: /special_link <text>")
    text = " ".join(context.args)
    uid = db.add_special_msg(text)
    bot_username = context.bot.username
    await update.message.reply_text(f"🔐 **Secret Link:**\nhttps://t.me/{bot_username}?start={uid}")

# ================= 🔗 JOIN REQUEST LOGIC (FIXED) =================
@admin_only
async def create_approval_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/link Name <limit>"""
    if len(context.args) < 1: return await update.message.reply_text("Usage: /link <Name> <Limit>")
    name = context.args[0]
    limit = int(context.args[1]) if len(context.args) > 1 and context.args[1].isdigit() else None

    try:
        # create_invite_link with creates_join_request=True
        link = await update.effective_chat.create_invite_link(
            name=name,
            member_limit=limit,
            creates_join_request=True 
        )
        await update.message.reply_text(
            f"🛡 **Approval Link Created**\n"
            f"Link: {link.invite_link}\n\n"
            f"Users will wait for Admin Approval."
        )
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

async def join_request_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Triggered when user clicks Approval Link"""
    req = update.chat_join_request
    chat = req.chat
    user = req.from_user
    
    text = f"👤 **Join Request**\nUser: {user.full_name} (@{user.username})\nChat: {chat.title}"
    
    keyboard = [
        [
            InlineKeyboardButton("✅ Yes", callback_data=f"join_accept_{user.id}"),
            InlineKeyboardButton("❌ No", callback_data=f"join_decline_{user.id}")
        ]
    ]
    
    # Send message to the group so admins can approve
    await context.bot.send_message(chat_id=chat.id, text=text, reply_markup=InlineKeyboardMarkup(keyboard))

async def join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    chat = update.effective_chat
    
    if not await is_admin(update):
        return await query.answer("❌ Admins Only!", show_alert=True)

    user_id = int(data.split("_")[-1])
    
    if "join_accept" in data:
        try:
            await chat.approve_join_request(user_id)
            await query.edit_message_text(f"✅ User ID {user_id} Approved.")
        except Exception as e:
            await query.edit_message_text(f"Error: {e}")
            
    elif "join_decline" in data:
        try:
            await chat.decline_join_request(user_id)
            await query.edit_message_text(f"🚫 User ID {user_id} Rejected.")
            
            # Try to DM the user
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"Sorry {query.from_user.first_name}, you can’t join. You were Rejected by Owner/Admin."
                )
            except:
                pass 
        except Exception as e:
            await query.edit_message_text(f"Error: {e}")

# ================= 🛡️ MODERATION & TOOLS =================
@admin_only
async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message: return
    try:
        await update.effective_chat.ban_member(update.message.reply_to_message.from_user.id)
        await update.message.reply_text("🔨 Banned.")
    except: pass

@admin_only
async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = context.args[0] if context.args else (update.message.reply_to_message.from_user.id if update.message.reply_to_message else None)
    if not uid: return
    try:
        await update.effective_chat.unban_member(uid)
        await update.message.reply_text("✅ Unbanned.")
    except: pass

@admin_only
async def purge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message: return
    msg_id = update.message.reply_to_message.message_id
    tasks = [context.bot.delete_message(update.effective_chat.id, m) for m in range(msg_id, update.message.message_id + 1)]
    await asyncio.gather(*tasks[:100], return_exceptions=True)
    await update.message.reply_text("🗑 Purged.")

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
async def antilink(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args: return
    val = context.args[0].lower() == "on"
    db.update_setting(update.effective_chat.id, "antilink", val)
    await update.message.reply_text(f"🔗 Antilink: {val}")

@admin_only
async def filter_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2: return
    trig = context.args[0].lower()
    resp = " ".join(context.args[1:])
    c = db.get_chat(update.effective_chat.id)
    c["filters"][trig] = resp
    db.save()
    await update.message.reply_text(f"✅ Filter `{trig}` saved.")

async def info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.message.reply_to_message.from_user if update.message.reply_to_message else update.effective_user
    await update.message.reply_text(f"👤 ID: `{u.id}`\nName: {u.full_name}", parse_mode=ParseMode.MARKDOWN)

# ================= 🚀 MAIN HANDLER =================
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    chat = update.effective_chat
    text = update.message.text
    chat_data = db.get_chat(chat.id)
    is_adm = await is_admin(update)

    # Antilink
    if chat_data["settings"]["antilink"] and not is_adm:
        if re.search(r"http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+", text):
            await update.message.delete()
            return

    # Text Lock
    if not is_adm and "text" in chat_data["locked"]:
        await update.message.delete()
        return

    # Filters
    if text.lower() in chat_data["filters"]:
        await update.message.reply_text(chat_data["filters"][text.lower()])

async def welcome_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_data = db.get_chat(update.effective_chat.id)
    if not chat_data["settings"]["welcome"]: return
    for m in update.message.new_chat_members:
        await update.message.reply_text(chat_data["text"]["welcome"].format(name=m.first_name, chat=update.effective_chat.title))

def main():
    print("🚀 Bot Starting...")
    if not BOT_TOKEN: return

    # --- 1. START WEB SERVER IN BACKGROUND ---
    threading.Thread(target=start_web_server, daemon=True).start()

    # --- 2. START BOT ---
    app = Application.builder().token(BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("genlink", genlink))
    app.add_handler(CommandHandler("shortener", shortener))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CommandHandler("special_link", special_link))
    app.add_handler(CommandHandler("link", create_approval_link))
    
    # Old Commands
    app.add_handler(CommandHandler("ban", ban))
    app.add_handler(CommandHandler("unban", unban))
    app.add_handler(CommandHandler("purge", purge))
    app.add_handler(CommandHandler("lock", lock))
    app.add_handler(CommandHandler("unlock", unlock))
    app.add_handler(CommandHandler("antilink", antilink))
    app.add_handler(CommandHandler("filter", filter_cmd))
    app.add_handler(CommandHandler("info", info))

    # Handlers
    app.add_handler(ChatJoinRequestHandler(join_request_handler))
    app.add_handler(CallbackQueryHandler(join_callback, pattern="^join_"))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    print("✅ Bot is Online & Web Server is Running!")
    app.run_polling()

if __name__ == "__main__":
    main()
