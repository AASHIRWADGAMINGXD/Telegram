# Main.py
import asyncio
import logging
import os
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from collections import defaultdict

from telegram import ChatPermissions, Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ChatMemberHandler,
    filters,
    ContextTypes,
)

# =============== CONFIG ===============
BOT_TOKEN = os.environ.get("BOT_TOKEN")
OWNER_ID = int(os.environ.get("OWNER_ID", "0"))
DB_PATH = os.environ.get("DB_PATH", "moderator_bot.db")

DAILY_THALA_LIMIT = 3
SPAM_LIMIT = 5  # messages
SPAM_WINDOW = 10  # seconds
MUTE_DURATION = 60  # seconds for spam
LINK_PATTERN = re.compile(r"(https?://\S+|t\.me/\S+|telegram\.me/\S+)", re.IGNORECASE)

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is missing")

# =============== LOGGING ===============
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# =============== DATABASE ===============
db = sqlite3.connect(DB_PATH, check_same_thread=False)
db.row_factory = sqlite3.Row
cur = db.cursor()
cur.executescript("""
CREATE TABLE IF NOT EXISTS moderators (
    chat_id INTEGER,
    user_id INTEGER,
    PRIMARY KEY (chat_id, user_id)
);
CREATE TABLE IF NOT EXISTS thala_counts (
    chat_id INTEGER,
    user_id INTEGER,
    date TEXT,
    count INTEGER DEFAULT 0,
    PRIMARY KEY (chat_id, user_id, date)
);
CREATE TABLE IF NOT EXISTS warnings (
    chat_id INTEGER,
    user_id INTEGER,
    warns INTEGER DEFAULT 0,
    PRIMARY KEY (chat_id, user_id)
);
""")
db.commit()

# =============== HELPERS ===============
def is_owner(uid: int) -> bool:
    return uid == OWNER_ID

def is_admin_or_mod(chat_id: int, user_id: int) -> bool:
    if is_owner(user_id):
        return True
    cur = db.cursor()
    cur.execute("SELECT 1 FROM moderators WHERE chat_id=? AND user_id=?", (chat_id, user_id))
    return cur.fetchone() is not None

def increment_thala(chat_id: int, user_id: int) -> int:
    today = datetime.now(timezone.utc).date().isoformat()
    cur = db.cursor()
    cur.execute("INSERT OR IGNORE INTO thala_counts VALUES (?,?,?,0)", (chat_id, user_id, today))
    cur.execute("UPDATE thala_counts SET count=count+1 WHERE chat_id=? AND user_id=? AND date=?",
                (chat_id, user_id, today))
    db.commit()
    cur.execute("SELECT count FROM thala_counts WHERE chat_id=? AND user_id=? AND date=?",
                (chat_id, user_id, today))
    return cur.fetchone()["count"]

def reset_daily_limits():
    today = datetime.now(timezone.utc).date().isoformat()
    db.execute("DELETE FROM thala_counts WHERE date != ?", (today,))
    db.execute("DELETE FROM warnings")
    db.commit()

# track message timestamps for spam
spam_tracker = defaultdict(list)

# =============== COMMANDS ===============
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Hello! I'm your 24/7 moderation bot.\nUse /help for all commands.")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🛡️ Commands:\n"
        "/ban @user\n/unban <id>\n/mute @user <10m|1h|1d>\n/unmute @user\n"
        "/warn @user\n/warnings @user\n"
        "/addmod @user (owner only)\n/removemod @user (owner only)\n"
        "\nExtras:\n"
        "- 'thala' allowed only 3 times per day per user\n"
        "- Anti-Link protection\n"
        "- Spam auto-mute\n"
        "- Daily reset of warnings and thala"
    )

def get_target_id(update: Update):
    if update.message.reply_to_message:
        return update.message.reply_to_message.from_user.id
    parts = update.message.text.split()
    if len(parts) > 1 and parts[1].isdigit():
        return int(parts[1])
    return None

async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_or_mod(update.effective_chat.id, update.effective_user.id):
        return await update.message.reply_text("No permission.")
    uid = get_target_id(update)
    if not uid:
        return await update.message.reply_text("Reply or give user ID.")
    await context.bot.ban_chat_member(update.effective_chat.id, uid)
    await update.message.reply_text("🚫 User banned.")

async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_or_mod(update.effective_chat.id, update.effective_user.id):
        return await update.message.reply_text("No permission.")
    parts = update.message.text.split()
    if len(parts) < 2:
        return await update.message.reply_text("Usage: /unban <id>")
    await context.bot.unban_chat_member(update.effective_chat.id, int(parts[1]))
    await update.message.reply_text("✅ User unbanned.")

async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_or_mod(update.effective_chat.id, update.effective_user.id):
        return await update.message.reply_text("No permission.")
    uid = get_target_id(update)
    if not uid:
        return await update.message.reply_text("Reply or give user ID.")
    args = update.message.text.split()
    if len(args) < 3:
        return await update.message.reply_text("Usage: /mute @user 10m|1h|1d")
    val, unit = int(args[2][:-1]), args[2][-1]
    seconds = val * (60 if unit == "m" else 3600 if unit == "h" else 86400)
    until = datetime.now(timezone.utc) + timedelta(seconds=seconds)
    await context.bot.restrict_chat_member(
        update.effective_chat.id, uid,
        permissions=ChatPermissions(can_send_messages=False),
        until_date=until
    )
    await update.message.reply_text(f"🤐 Muted for {args[2]}.")

async def unmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_or_mod(update.effective_chat.id, update.effective_user.id):
        return await update.message.reply_text("No permission.")
    uid = get_target_id(update)
    if not uid:
        return await update.message.reply_text("Reply or give user ID.")
    await context.bot.restrict_chat_member(
        update.effective_chat.id, uid,
        permissions=ChatPermissions(
            can_send_messages=True,
            can_send_media_messages=True,
            can_send_other_messages=True
        )
    )
    await update.message.reply_text("✅ User unmuted.")

async def warn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_or_mod(update.effective_chat.id, update.effective_user.id):
        return await update.message.reply_text("No permission.")
    uid = get_target_id(update)
    if not uid:
        return await update.message.reply_text("Reply or give user ID.")
    cur = db.cursor()
    cur.execute("INSERT OR IGNORE INTO warnings VALUES (?,?,0)", (update.effective_chat.id, uid))
    cur.execute("UPDATE warnings SET warns=warns+1 WHERE chat_id=? AND user_id=?",
                (update.effective_chat.id, uid))
    db.commit()
    cur.execute("SELECT warns FROM warnings WHERE chat_id=? AND user_id=?",
                (update.effective_chat.id, uid))
    warns = cur.fetchone()["warns"]
    await update.message.reply_text(f"⚠️ Warned user. Total warns: {warns}")

async def warnings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = get_target_id(update) or update.effective_user.id
    cur = db.cursor()
    cur.execute("SELECT warns FROM warnings WHERE chat_id=? AND user_id=?",
                (update.effective_chat.id, uid))
    row = cur.fetchone()
    warns = row["warns"] if row else 0
    await update.message.reply_text(f"User has {warns} warnings.")

async def addmod(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        return await update.message.reply_text("Owner only.")
    uid = get_target_id(update)
    if not uid:
        return await update.message.reply_text("Reply or give user ID.")
    db.execute("INSERT OR IGNORE INTO moderators VALUES (?,?)", (update.effective_chat.id, uid))
    db.commit()
    await update.message.reply_text("✅ Moderator added.")

async def removemod(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        return await update.message.reply_text("Owner only.")
    uid = get_target_id(update)
    if not uid:
        return await update.message.reply_text("Reply or give user ID.")
    db.execute("DELETE FROM moderators WHERE chat_id=? AND user_id=?",
               (update.effective_chat.id, uid))
    db.commit()
    await update.message.reply_text("❌ Moderator removed.")

# =============== MESSAGE HANDLER ===============
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    chat = update.effective_chat
    user = update.effective_user
    text = update.message.text.strip()

    # 1. Anti-link
    if LINK_PATTERN.search(text) and not is_admin_or_mod(chat.id, user.id):
        try:
            await update.message.delete()
            await update.message.reply_text(f"🚫 Links not allowed, {user.first_name}.")
            return
        except Exception:
            pass

    # 2. Spam detection
    now = datetime.now().timestamp()
    user_msgs = spam_tracker[(chat.id, user.id)]
    user_msgs.append(now)
    spam_tracker[(chat.id, user.id)] = [t for t in user_msgs if now - t < SPAM_WINDOW]
    if len(spam_tracker[(chat.id, user.id)]) >= SPAM_LIMIT and not is_admin_or_mod(chat.id, user.id):
        await context.bot.restrict_chat_member(
            chat.id, user.id,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=datetime.now(timezone.utc) + timedelta(seconds=MUTE_DURATION)
        )
        spam_tracker[(chat.id, user.id)] = []
        await update.message.reply_text(f"🤐 {user.first_name} muted for spam ({SPAM_LIMIT} msgs in {SPAM_WINDOW}s).")
        return

    # 3. Thala limiter
    if text.lower() == "thala":
        if is_admin_or_mod(chat.id, user.id):
            return
        count = increment_thala(chat.id, user.id)
        if count > DAILY_THALA_LIMIT:
            try:
                await update.message.delete()
            except Exception:
                pass
            await update.message.reply_text("⚠️ You reached your daily 'thala' limit (3).")
        else:
            await update.message.reply_text(f"✅ 'thala' count: {count}/3")

# =============== JOBS ===============
async def daily_reset_job(context: ContextTypes.DEFAULT_TYPE):
    reset_daily_limits()
    logger.info("Daily reset of warnings and thala limits done.")

# =============== MAIN ===============
async def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("ban", ban))
    app.add_handler(CommandHandler("unban", unban))
    app.add_handler(CommandHandler("mute", mute))
    app.add_handler(CommandHandler("unmute", unmute))
    app.add_handler(CommandHandler("warn", warn))
    app.add_handler(CommandHandler("warnings", warnings))
    app.add_handler(CommandHandler("addmod", addmod))
    app.add_handler(CommandHandler("removemod", removemod))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    app.add_handler(ChatMemberHandler(lambda u, c: None, ChatMemberHandler.CHAT_MEMBER))

    # Daily reset at midnight UTC
    app.job_queue.run_daily(daily_reset_job, time=datetime.time(0, 0, tzinfo=timezone.utc))

    print("✅ Bot is online 24/7 with moderation, anti-link, spam control, and daily reset.")
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
