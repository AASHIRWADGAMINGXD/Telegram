import asyncio
from datetime import datetime
from telegram import Update, ChatPermissions
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
import os
from google.cloud import firestore
import requests
result = requests.post("https://my-cloudrun-app.a.run.app/api", json={"data": "test"})

db = firestore.Client()

def save_user(user_id, name):
    db.collection("users").document(str(user_id)).set({"name": name})
    
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "letmein")

admins = set()
thala_count = {}
daily_reset_time = datetime.now().day
warns = {}
start_time = datetime.now()

# ---------- BASIC ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Bot is online!\n\nUse /login <password> to access admin commands."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("""
🤖 Commands:
/login <password> - Become admin
/help - Show this menu
/rules - Show rules
/status - Bot uptime

Admin:
/mute (reply)
/unmute (reply)
/ban (reply)
/unban <user_id>
/kick (reply)
/warn (reply)
/warnings (reply)
/slowmode <sec>
/lock
/unlock
""")

async def rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📜 Rules: No spam, respect others, stay chill.")

# ---------- LOGIN ----------
async def login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await update.message.reply_text("Usage: /login <password>")
    if context.args[0] == ADMIN_PASSWORD:
        admins.add(update.effective_user.id)
        await update.message.reply_text("✅ Access granted! You’re now an admin.")
    else:
        await update.message.reply_text("❌ Wrong password.")

def is_admin(user_id):
    return user_id in admins

# ---------- MODERATION ----------
async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    if not update.message.reply_to_message: return
    member = update.message.reply_to_message.from_user
    await update.effective_chat.restrict_member(member.id, ChatPermissions(can_send_messages=False))
    await update.message.reply_text(f"🔇 {member.first_name} muted.")

async def unmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    if not update.message.reply_to_message: return
    member = update.message.reply_to_message.from_user
    await update.effective_chat.restrict_member(member.id, ChatPermissions(can_send_messages=True))
    await update.message.reply_text(f"🔊 {member.first_name} unmuted.")

async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    if not update.message.reply_to_message: return
    member = update.message.reply_to_message.from_user
    await update.effective_chat.ban_member(member.id)
    await update.message.reply_text(f"⛔ {member.first_name} banned.")

async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    if not context.args: return
    user_id = int(context.args[0])
    await update.effective_chat.unban_member(user_id)
    await update.message.reply_text("✅ User unbanned.")

async def kick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    if not update.message.reply_to_message: return
    member = update.message.reply_to_message.from_user
    await update.effective_chat.ban_member(member.id)
    await update.effective_chat.unban_member(member.id)
    await update.message.reply_text(f"👢 {member.first_name} kicked.")

# ---------- WARN ----------
async def warn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    if not update.message.reply_to_message: return
    user = update.message.reply_to_message.from_user
    warns[user.id] = warns.get(user.id, 0) + 1
    await update.message.reply_text(f"⚠️ {user.first_name} warned ({warns[user.id]}×).")

async def warnings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message: return
    user = update.message.reply_to_message.from_user
    await update.message.reply_text(f"{user.first_name} has {warns.get(user.id, 0)} warnings.")

# ---------- CHAT CONTROL ----------
async def lock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    await update.effective_chat.set_permissions(ChatPermissions(can_send_messages=False))
    await update.message.reply_text("🔒 Chat locked.")

async def unlock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    await update.effective_chat.set_permissions(ChatPermissions(can_send_messages=True))
    await update.message.reply_text("🔓 Chat unlocked.")

async def slowmode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    if not context.args: return
    try:
        sec = int(context.args[0])
        await update.effective_chat.set_slow_mode_delay(sec)
        await update.message.reply_text(f"🐢 Slowmode set to {sec}s.")
    except:
        await update.message.reply_text("Please enter a number.")

# ---------- THALA ----------
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global daily_reset_time
    text = update.message.text.lower()
    user_id = update.effective_user.id
    if datetime.now().day != daily_reset_time:
        thala_count.clear()
        daily_reset_time = datetime.now().day
    if "thala" in text:
        thala_count[user_id] = thala_count.get(user_id, 0) + 1
        if thala_count[user_id] > 3:
            await update.message.delete()
            await update.message.reply_text("⚠️ Thala limit reached (3/day)!")

# ---------- STATUS ----------
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uptime = datetime.now() - start_time
    await update.message.reply_text(f"✅ Uptime: {str(uptime).split('.')[0]}")

# ---------- MAIN ----------
async def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("rules", rules))
    app.add_handler(CommandHandler("login", login))
    app.add_handler(CommandHandler("mute", mute))
    app.add_handler(CommandHandler("unmute", unmute))
    app.add_handler(CommandHandler("ban", ban))
    app.add_handler(CommandHandler("unban", unban))
    app.add_handler(CommandHandler("kick", kick))
    app.add_handler(CommandHandler("warn", warn))
    app.add_handler(CommandHandler("warnings", warnings))
    app.add_handler(CommandHandler("lock", lock))
    app.add_handler(CommandHandler("unlock", unlock))
    app.add_handler(CommandHandler("slowmode", slowmode))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    print("✅ Bot is live (24/7).")
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
