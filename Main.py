import logging
import json
import os
import sys
import re
import asyncio
import uuid
import requests
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

BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = os.getenv("OWNER_ID")

if not BOT_TOKEN:
    print("❌ ERROR: BOT_TOKEN is missing in .env file.")
    sys.exit(1)

if OWNER_ID:
    try:
        OWNER_ID = int(OWNER_ID)
    except ValueError:
        print("⚠️ WARNING: OWNER_ID must be a number.")

DATA_FILE = "bot_data.json"

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
                "gban_list": [],
                "special_links": {} # Store for /special_link
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

    # --- NEW: Special Links Storage ---
    def add_special_msg(self, text):
        uid = str(uuid.uuid4())[:8] # Short unique ID
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

# ================= 🆕 NEW COMMANDS =================

# 1. HELP COMMAND
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🤖 **Bot Command List**\n\n"
        "**👮 Admin & Mod:**\n"
        "/ban, /unban, /mute, /unmute, /purge\n"
        "/lock <text/media>, /unlock, /antilink\n"
        "/setwelcome, /filter\n\n"
        "**🔗 Links & Join Requests:**\n"
        "`/link <name> <limit>` - Create Approval Link\n"
        "`/genlink` - Create Standard Invite\n"
        "`/shortener <url>` - Shorten URL\n"
        "`/special_link <text>` - Store secret message\n\n"
        "**📢 Tools:**\n"
        "`/broadcast <msg>` - Send to all chats\n"
        "`/info`, `/id`, `/staff`"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

# 2. GENERATE STANDARD LINK
@admin_only
async def genlink(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/genlink - Create a standard invite link"""
    chat = update.effective_chat
    try:
        link = await chat.create_invite_link(member_limit=1)
        await update.message.reply_text(f"🔗 **New Invite Link:**\n{link.invite_link}")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

# 3. SHORTENER
async def shortener(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/shortener <url>"""
    if not context.args:
        return await update.message.reply_text("Usage: /shortener <https://google.com>")
    
    url = context.args[0]
    msg = await update.message.reply_text("🔄 Shortening...")
    try:
        # Using TinyURL API (Free, no key required)
        api_url = f"http://tinyurl.com/api-create.php?url={url}"
        res = requests.get(api_url)
        if res.status_code == 200:
            await msg.edit_text(f"✅ **Short Link:**\n{res.text}", parse_mode=ParseMode.MARKDOWN)
        else:
            await msg.edit_text("❌ Failed to shorten.")
    except Exception as e:
        await msg.edit_text(f"Error: {e}")

# 4. BROADCAST
@owner_only
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/broadcast <text> - Send to all known chats"""
    if not context.args: return await update.message.reply_text("Usage: /broadcast <message>")
    
    msg = " ".join(context.args)
    count = 0
    failed = 0
    
    status = await update.message.reply_text("📢 Sending broadcast...")
    
    # Iterate over all chats in DB
    chats = list(db.data["chats"].keys())
    
    for chat_id in chats:
        try:
            await context.bot.send_message(chat_id, f"📢 **Broadcast:**\n{msg}", parse_mode=ParseMode.MARKDOWN)
            count += 1
            await asyncio.sleep(0.5) # Anti-flood
        except:
            failed += 1
            
    await status.edit_text(f"✅ Broadcast Sent!\nSuccessful: {count}\nFailed: {failed}")

# 5. SPECIAL LINK (Store Multiple Messages)
async def special_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/special_link <content>"""
    if not context.args:
        return await update.message.reply_text("Usage: /special_link <hidden text>")
    
    text = " ".join(context.args)
    uid = db.add_special_msg(text)
    
    bot_username = context.bot.username
    deep_link = f"https://t.me/{bot_username}?start={uid}"
    
    await update.message.reply_text(f"🔐 **Secret Message Stored!**\n\nShare this link to read it:\n{deep_link}")

# 6. COMPLEX JOIN REQUEST LINK SYSTEM
@admin_only
async def create_approval_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/link Name <limit>"""
    # Syntax: /link MyEvent 10
    if len(context.args) < 1:
        return await update.message.reply_text("Usage: /link <LinkName> <Limit (optional)>")
    
    name = context.args[0]
    limit = int(context.args[1]) if len(context.args) > 1 and context.args[1].isdigit() else 0
    limit_arg = limit if limit > 0 else None

    try:
        # creates_join_request=True is the key feature here
        link = await update.effective_chat.create_invite_link(
            name=name,
            member_limit=limit_arg,
            creates_join_request=True 
        )
        limit_text = f"Limit: {limit}" if limit else "Limit: Unlimited"
        await update.message.reply_text(
            f"🛡 **Approval Link Created**\n"
            f"Name: {name}\n"
            f"{limit_text}\n\n"
            f"🔗 {link.invite_link}\n\n"
            f"Users clicking this will require Admin Approval."
        )
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

# ================= 🧠 HANDLERS FOR JOIN REQUESTS =================

async def join_request_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Triggered when a user clicks the /link (Approval Link)"""
    req = update.chat_join_request
    chat = req.chat
    user = req.from_user
    
    # Text: "Hey Username Is Requesting to Join"
    text = (
        f"Hey {user.first_name} (@{user.username}) Is Requesting to Join\n"
        f"Chat: {chat.title}"
    )
    
    # Buttons: Yes / No
    # We store user_id and chat_id in callback data
    keyboard = [
        [
            InlineKeyboardButton("Yes", callback_data=f"join_accept_{user.id}"),
            InlineKeyboardButton("No", callback_data=f"join_decline_{user.id}")
        ]
    ]
    
    await context.bot.send_message(
        chat_id=chat.id,
        text=text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles Yes/No buttons"""
    query = update.callback_query
    data = query.data
    chat = update.effective_chat
    
    # Check Admin
    if not await is_admin(update):
        return await query.answer("❌ Admin Only!", show_alert=True)

    user_id = int(data.split("_")[-1])
    
    if "join_accept" in data:
        # YES -> Approve
        try:
            await chat.approve_join_request(user_id)
            await query.edit_message_text(f"✅ Approved user ID {user_id}")
        except Exception as e:
            await query.edit_message_text(f"Error approving: {e}")
            
    elif "join_decline" in data:
        # NO -> Decline & DM
        try:
            await chat.decline_join_request(user_id)
            await query.edit_message_text(f"🚫 Rejected user ID {user_id}")
            
            # Send DM: "Sorry first name you can’t join you are Reject By Onwer / Admin"
            # Note: This only works if user has interacted with bot before.
            try:
                # Need to fetch user first name if possible, otherwise generic
                # We can try to get chat member info, but they aren't member yet.
                # We'll just say "You".
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"Sorry, you can't join. You are Rejected By Owner / Admin."
                )
            except:
                pass # Can't DM user (Blocked bot or Privacy settings)
                
        except Exception as e:
            await query.edit_message_text(f"Error declining: {e}")

# ================= 🦴 OLD CODE (Maintained) =================

@admin_only
async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message: return await update.message.reply_text("Reply to a user.")
    try:
        user = update.message.reply_to_message.from_user
        await update.effective_chat.ban_member(user.id)
        await update.message.reply_text(f"🔴 **Banned:** {user.first_name}")
    except Exception as e: await update.message.reply_text(f"Error: {e}")

@admin_only
async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = context.args[0] if context.args else (update.message.reply_to_message.from_user.id if update.message.reply_to_message else None)
    if not uid: return
    try:
        await update.effective_chat.unban_member(uid)
        await update.message.reply_text("🟢 User unbanned.")
    except: pass

@admin_only
async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message: return
    user = update.message.reply_to_message.from_user
    await update.effective_chat.restrict_member(user.id, permissions=ChatPermissions(can_send_messages=False))
    await update.message.reply_text(f"🔇 **Muted** {user.first_name}.")

@admin_only
async def unmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message: return
    user = update.message.reply_to_message.from_user
    await update.effective_chat.restrict_member(user.id, permissions=ChatPermissions(can_send_messages=True, can_send_media_messages=True))
    await update.message.reply_text("🔊 **Unmuted.**")

@admin_only
async def purge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message: return
    msg_id = update.message.reply_to_message.message_id
    curr_id = update.message.message_id
    tasks = [context.bot.delete_message(update.effective_chat.id, m) for m in range(msg_id, curr_id + 1)]
    await asyncio.gather(*tasks[:100], return_exceptions=True)
    tmp = await update.message.reply_text("🧹 **Purged.**")
    await asyncio.sleep(3)
    try: await tmp.delete() 
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
async def antilink(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args: return
    val = context.args[0].lower() == "on"
    db.update_setting(update.effective_chat.id, "antilink", val)
    await update.message.reply_text(f"🔗 Anti-Link: **{val}**")

@admin_only
async def set_welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = " ".join(context.args)
    db.set_text(update.effective_chat.id, "welcome", text)
    await update.message.reply_text("✅ Welcome saved.")

@admin_only
async def filter_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2: return
    trigger = context.args[0].lower()
    reply = " ".join(context.args[1:])
    c = db.get_chat(update.effective_chat.id)
    c["filters"][trigger] = reply
    db.save()
    await update.message.reply_text(f"💾 Filter `{trigger}` saved.")

async def info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.reply_to_message.from_user if update.message.reply_to_message else update.effective_user
    await update.message.reply_text(f"👤 **User Info**\nID: `{user.id}`\nName: {user.full_name}", parse_mode=ParseMode.MARKDOWN)

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    user = update.effective_user
    chat = update.effective_chat
    text = update.message.text
    chat_data = db.get_chat(chat.id)
    
    # Handle Start Command for Special Links
    if text.startswith("/start") and len(text.split()) > 1:
        arg = text.split()[1]
        special_text = db.get_special_msg(arg)
        if special_text:
            await update.message.reply_text(f"🔓 **Secret Message:**\n\n{special_text}")
        return

    is_adm = await is_admin(update)

    if chat_data["settings"]["antilink"] and not is_adm:
        if re.search(r"http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+", text):
            await update.message.delete()
            return

    if not is_adm and "text" in chat_data["locked"]:
        await update.message.delete()
        return

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
        w_text = chat_data["text"]["welcome"].format(name=member.first_name, chat=update.effective_chat.title)
        await update.message.reply_text(w_text)

# ================= 🚀 STARTUP =================
def main():
    print("🚀 Mega Bot Starting...")
    if not BOT_TOKEN:
        print("❌ CRITICAL ERROR: BOT_TOKEN is missing!")
        return

    app = Application.builder().token(BOT_TOKEN).build()

    # --- NEW HANDLERS ---
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("genlink", genlink))
    app.add_handler(CommandHandler("shortener", shortener))
    app.add_handler(CommandHandler("broadcast", broadcast)) # /brocast fixed to /broadcast
    app.add_handler(CommandHandler("special_link", special_link))
    app.add_handler(CommandHandler("link", create_approval_link))
    
    # Join Requests (The approval logic)
    app.add_handler(ChatJoinRequestHandler(join_request_handler))
    app.add_handler(CallbackQueryHandler(join_callback, pattern="^join_"))

    # --- OLD HANDLERS ---
    app.add_handler(CommandHandler("ban", ban))
    app.add_handler(CommandHandler("unban", unban))
    app.add_handler(CommandHandler("mute", mute))
    app.add_handler(CommandHandler("unmute", unmute))
    app.add_handler(CommandHandler("purge", purge))
    app.add_handler(CommandHandler("lock", lock))
    app.add_handler(CommandHandler("unlock", unlock))
    app.add_handler(CommandHandler("antilink", antilink))
    app.add_handler(CommandHandler("setwelcome", set_welcome))
    app.add_handler(CommandHandler("filter", filter_cmd))
    app.add_handler(CommandHandler("info", info))
    app.add_handler(CommandHandler("id", info))

    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_handler))
    app.add_handler(MessageHandler(filters.TEXT, message_handler)) # removed ~filters.COMMAND so /start works for deep linking

    print("✅ Bot is Online and polling...")
    app.run_polling()

if __name__ == "__main__":
    main()
