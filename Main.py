import asyncio
from datetime import datetime, timedelta
from telegram import Update, ChatPermissions
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
import os

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "letmein")  # set in Render dashboard

# ---- In-memory storage ----
admins = set()
thala_count = {}
daily_reset_time = datetime.now().day
warns = {}

# ---------- BASIC ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Bot is online! Type /help to see commands.\n\n"
        "If you're an admin, type /login <password> to access moderation."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("""
🤖 Bot Commands:
/login <password> - Grant admin access
/help - Show help menu
/rules - Show chat rules

Admin Commands:
/mute (reply) - Mute a user
/unmute (reply) - Unmute a user
/ban (reply) - Ban a user
/unban (user_id) - Unban user by ID
/kick (reply) - Kick a user
/warn (reply) - Warn a user
/warnings (reply) - Show warning count
/slowmode <seconds> - Enable slowmode
/lock - Lock chat (no messages)
/unlock - Unlock chat
/status - Show bot uptime
""")

async def rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("#1 No spam. #2 Respect others. #3 Follow group rules.")

# ---------- ADMIN LOGIN ----------
async def login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if len(context.args) == 0:
        return await update.message.reply_text("Usage: /login <password>")
    password = context.args[0]
    if password == ADMIN_PASSWORD:
        admins.add(user_id)
        await update.message.reply_text("✅ Access granted! You are now an admin.")
    else:
        await update.message.reply_text("❌ Wrong password.")

def is_admin(user_id):
    return user_id in admins

# ---------- MODERATION ----------
async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("🚫 You are not authorized.")
    if not update.message.reply_to_message:
        return await update.message.reply_text("Reply to a user to mute them.")
    member = update.message.reply_to_message.from_user
    await update.effective_chat.restrict_member(member.id, ChatPermissions(can_send_messages=False))
    await update.message.reply_text(f"🔇 {member.first_name} has been muted.")

async def unmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("🚫 You are not authorized.")
    if not update.message.reply_to_message:
        return await update.message.reply_text("Reply to a user to unmute them.")
    member = update.message.reply_to_message.from_user
    await update.effective_chat.restrict_member(member.id, ChatPermissions(can_send_messages=True))
    await update.message.reply_text(f"🔊 {member.first_name} has been unmuted.")

async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("🚫 You are not authorized.")
    if not update.message.reply_to_message:
        return await update.message.reply_text("Reply to a user to ban them.")
    member = update.message.reply_to_message.from_user
    await update.effective_chat.ban_member(member.id)
    await update.message.reply_text(f"⛔ {member.first_name} has been banned.")

async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("🚫 You are not authorized.")
    if not context.args:
        return await update.message.reply_text("Usage: /unban <user_id>")
    user_id = int(context.args[0])
    await update.effective_chat.unban_member(user_id)
    await update.message.reply_text("✅ User unbanned successfully.")

async def kick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("🚫 You are not authorized.")
    if not update.message.reply_to_message:
        return await update.message.reply_text("Reply to a user to kick them.")
    member = update.message.reply_to_message.from_user
    await update.effective_chat.ban_member(member.id)
    await update.effective_chat.unban_member(member.id)
    await update.message.reply_text(f"👢 {member.first_name} has been kicked.")

# ---------- WARN SYSTEM ----------
async def warn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("🚫 You are not authorized.")
    if not update.message.reply_to_message:
        return await update.message.reply_text("Reply to a user to warn them.")
    user = update.message.reply_to_message.from_user
    warns[user.id] = warns.get(user.id, 0) + 1
    await update.message.reply_text(f"⚠️ {user.first_name} has been warned ({warns[user.id]} warnings).")

async def warnings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        return await update.message.reply_text("Reply to a user to check their warnings.")
    user = update.message.reply_to_message.from_user
    count = warns.get(user.id, 0)
    await update.message.reply_text(f"⚠️ {user.first_name} has {count} warnings.")

# ---------- CHAT CONTROL ----------
async def lock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("🚫 You are not authorized.")
    await update.effective_chat.set_permissions(ChatPermissions(can_send_messages=False))
    await update.message.reply_text("🔒 Chat locked.")

async def unlock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("🚫 You are not authorized.")
    await update.effective_chat.set_permissions(ChatPermissions(can_send_messages=True))
    await update.message.reply_text("🔓 Chat unlocked.")

async def slowmode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("🚫 You are not authorized.")
    if not context.args:
        return await update.message.reply_text("Usage: /slowmode <seconds>")
    try:
        seconds = int(context.args[0])
        await update.effective_chat.set_slow_mode_delay(seconds)
        await update.message.reply_text(f"🐢 Slowmode set to {seconds} seconds.")
    except ValueError:
        await update.message.reply_text("Please enter a valid number.")

# ---------- THALA LIMIT ----------
async def handle_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global daily_reset_time
    user_id = update.effective_user.id
    text = update.message.text.lower()

    if datetime.now().day != daily_reset_time:
        thala_count.clear()
        daily_reset_time = datetime.now().day

    if "thala" in text:
        count = thala_count.get(user_id, 0) + 1
        thala_count[user_id] = count
        if count > 3:
            await update.message.delete()
            await update.message.reply_text("⚠️ You reached your Thala limit for today!")

# ---------- STATUS ----------
start_time = datetime.now()

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uptime = datetime.now() - start_time
    await update.message.reply_text(f"✅ Bot running for {str(uptime).split('.')[0]} (24/7).")

# ---------- MAIN ----------
async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

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
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_messages))

    print("✅ Bot is online 24/7.")
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
