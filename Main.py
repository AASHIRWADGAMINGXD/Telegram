import logging
import json
import os
import sys
import re
import asyncio
from dotenv import load_dotenv  # pip install python-dotenv

from telegram import Update, ChatPermissions
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ================= ⚙️ CONFIGURATION =================
# Load .env file
load_dotenv()

# Get Keys
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = os.getenv("OWNER_ID")

# Validation
if not BOT_TOKEN:
    print("❌ ERROR: BOT_TOKEN is missing in .env file.")
    sys.exit(1)

if OWNER_ID:
    try:
        OWNER_ID = int(OWNER_ID)
    except ValueError:
        print("⚠️ WARNING: OWNER_ID must be a number.")

# Database File
DATA_FILE = "bot_data.json"

# Logging
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# ================= 💾 DATABASE SYSTEM =================
class DataManager:
    def __init__(self):
        self.data = self._load()

    def _load(self):
        if not os.path.exists(DATA_FILE):
            return {
                "chats": {}, 
                "gban_list": []
            }
        try:
            with open(DATA_FILE, "r") as f:
                return json.load(f)
        except:
            return {"chats": {}, "gban_list": []}

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

# ================= 🔨 1. MODERATION =================
@admin_only
async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/ban - Bans user"""
    if not update.message.reply_to_message: return await update.message.reply_text("Reply to a user.")
    try:
        user = update.message.reply_to_message.from_user
        await update.effective_chat.ban_member(user.id)
        await update.message.reply_text(f"🔴 **Banned:** {user.first_name} [`{user.id}`]", parse_mode=ParseMode.MARKDOWN)
    except Exception as e: await update.message.reply_text(f"Error: {e}")

@admin_only
async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/unban <id>"""
    uid = context.args[0] if context.args else (update.message.reply_to_message.from_user.id if update.message.reply_to_message else None)
    if not uid: return await update.message.reply_text("Give ID or reply.")
    try:
        await update.effective_chat.unban_member(uid)
        await update.message.reply_text("🟢 User unbanned.")
    except: pass

@admin_only
async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/mute - Mute user"""
    if not update.message.reply_to_message: return
    user = update.message.reply_to_message.from_user
    await update.effective_chat.restrict_member(user.id, permissions=ChatPermissions(can_send_messages=False))
    await update.message.reply_text(f"🔇 **Muted** {user.first_name}.")

@admin_only
async def unmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message: return
    user = update.message.reply_to_message.from_user
    await update.effective_chat.restrict_member(user.id, permissions=ChatPermissions(can_send_messages=True, can_send_media_messages=True))
    await update.message.reply_text("🔊 **Unmuted.**", parse_mode=ParseMode.MARKDOWN)

@admin_only
async def purge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/purge - Delete messages"""
    if not update.message.reply_to_message: return await update.message.reply_text("Reply to start.")
    msg_id = update.message.reply_to_message.message_id
    curr_id = update.message.message_id
    tasks = [context.bot.delete_message(update.effective_chat.id, m) for m in range(msg_id, curr_id + 1)]
    await asyncio.gather(*tasks[:100], return_exceptions=True)
    tmp = await update.message.reply_text("🧹 **Purged.**", parse_mode=ParseMode.MARKDOWN)
    await asyncio.sleep(3)
    try: await tmp.delete()
    except: pass

@owner_only
async def gban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/gban - Global Ban (Owner Only)"""
    if not update.message.reply_to_message: return
    user = update.message.reply_to_message.from_user
    db.add_gban(user.id)
    await update.message.reply_text(f"🌍 **Globally Banned** {user.first_name}. They will be banned from all groups.")

# ================= 🔐 2. SECURITY & LOCKS =================
@admin_only
async def lock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/lock <all/text/media>"""
    if not context.args: return await update.message.reply_text("Usage: /lock <type>")
    chat_id = update.effective_chat.id
    arg = context.args[0].lower()
    c = db.get_chat(chat_id)
    
    if arg not in c["locked"]:
        c["locked"].append(arg)
        db.save()
        
    if arg == "all":
        await update.effective_chat.set_permissions(ChatPermissions(can_send_messages=False))
    elif arg == "media":
        await update.effective_chat.set_permissions(ChatPermissions(can_send_messages=True, can_send_media_messages=False))
        
    await update.message.reply_text(f"🔒 Locked: **{arg}**", parse_mode=ParseMode.MARKDOWN)

@admin_only
async def unlock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/unlock <type>"""
    if not context.args: return
    chat_id = update.effective_chat.id
    arg = context.args[0].lower()
    c = db.get_chat(chat_id)
    
    if arg in c["locked"]:
        c["locked"].remove(arg)
        db.save()
    
    if arg == "all" or arg == "media":
        await update.effective_chat.set_permissions(ChatPermissions(can_send_messages=True, can_send_media_messages=True, can_send_other_messages=True))

    await update.message.reply_text(f"🔓 Unlocked: **{arg}**", parse_mode=ParseMode.MARKDOWN)

@admin_only
async def antilink(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/antilink on/off"""
    if not context.args: return await update.message.reply_text("Usage: /antilink on/off")
    val = context.args[0].lower() == "on"
    db.update_setting(update.effective_chat.id, "antilink", val)
    await update.message.reply_text(f"🔗 Anti-Link is now: **{val}**", parse_mode=ParseMode.MARKDOWN)

# ================= 🤖 3. AUTOMATION & FILTERS =================
@admin_only
async def set_welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/setwelcome <text>"""
    text = " ".join(context.args)
    db.set_text(update.effective_chat.id, "welcome", text)
    await update.message.reply_text("✅ Welcome message saved.")

@admin_only
async def filter_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/filter <trigger> <reply>"""
    if len(context.args) < 2: return
    trigger = context.args[0].lower()
    reply = " ".join(context.args[1:])
    c = db.get_chat(update.effective_chat.id)
    c["filters"][trigger] = reply
    db.save()
    await update.message.reply_text(f"💾 Filter `{trigger}` saved.")

# ================= ℹ️ 4. INFO & UTILITIES =================
async def info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.reply_to_message.from_user if update.message.reply_to_message else update.effective_user
    chat = update.effective_chat
    txt = (
        f"👤 **User Info**\n"
        f"ID: `{user.id}`\n"
        f"Name: {user.full_name}\n\n"
        f"🏠 **Chat Info**\n"
        f"ID: `{chat.id}`"
    )
    await update.message.reply_text(txt, parse_mode=ParseMode.MARKDOWN)

async def staff(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admins = await update.effective_chat.get_administrators()
    txt = "👮‍♂️ **Staff List:**\n"
    for a in admins:
        if not a.user.is_bot:
            txt += f"- {a.user.full_name}\n"
    await update.message.reply_text(txt)

# ================= 👮 6. MESSAGE HANDLER =================
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    
    user = update.effective_user
    chat = update.effective_chat
    text = update.message.text
    chat_data = db.get_chat(chat.id)
    
    # 1. Global Ban Check
    if db.check_gban(user.id):
        try: await chat.ban_member(user.id)
        except: pass
        return

    # 2. Admin Check
    is_adm = await is_admin(update)

    # 3. Anti-Link
    if chat_data["settings"]["antilink"] and not is_adm:
        if re.search(r"http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+", text):
            await update.message.delete()
            return

    # 4. Locks
    if not is_adm:
        if "text" in chat_data["locked"]:
            await update.message.delete()
            return
        if "forward" in chat_data["locked"] and (update.message.forward_date or update.message.forward_from):
            await update.message.delete()
            return

    # 5. Filters
    text_lower = text.lower()
    if text_lower in chat_data["filters"]:
        await update.message.reply_text(chat_data["filters"][text_lower])

async def welcome_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_data = db.get_chat(update.effective_chat.id)
    if not chat_data["settings"]["welcome"]: return
    
    for member in update.message.new_chat_members:
        if db.check_gban(member.id):
            await update.effective_chat.ban_member(member.id)
            continue
            
        w_text = chat_data["text"]["welcome"].format(
            name=member.first_name, 
            chat=update.effective_chat.title
        )
        await update.message.reply_text(w_text)

# ================= 🚀 STARTUP =================
def main():
    print("🚀 Bot Starting...")
    
    app = Application.builder().token(BOT_TOKEN).build()

    # Admin
    app.add_handler(CommandHandler("ban", ban))
    app.add_handler(CommandHandler("unban", unban))
    app.add_handler(CommandHandler("mute", mute))
    app.add_handler(CommandHandler("unmute", unmute))
    app.add_handler(CommandHandler("purge", purge))
    app.add_handler(CommandHandler("gban", gban))
    
    # Settings
    app.add_handler(CommandHandler("lock", lock))
    app.add_handler(CommandHandler("unlock", unlock))
    app.add_handler(CommandHandler("antilink", antilink))
    app.add_handler(CommandHandler("setwelcome", set_welcome))
    app.add_handler(CommandHandler("filter", filter_cmd))
    
    # Info
    app.add_handler(CommandHandler("info", info))
    app.add_handler(CommandHandler("id", info))
    app.add_handler(CommandHandler("staff", staff))

    # Handlers
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    print("✅ Bot is Online! (Ensure only ONE instance is running)")
    app.run_polling()

if __name__ == "__main__":
    main()
