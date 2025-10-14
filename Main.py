# bot.py
import asyncio
import logging
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Optional

from telegram import ChatPermissions, Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ChatMemberHandler,
)

# ---------- Configuration ----------
BOT_TOKEN = os.environ.get("BOT_TOKEN")
OWNER_ID = int(os.environ.get("OWNER_ID", "0"))  # your Telegram user id
DAILY_THALA_LIMIT = 3

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable required")

# ---------- Logging ----------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# ---------- Database ----------
DB_PATH = os.environ.get("DB_PATH", "moderator_bot.db")


def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


db = get_db()


def init_db():
    cur = db.cursor()
    cur.executescript(
        """
    CREATE TABLE IF NOT EXISTS moderators (
      chat_id INTEGER,
      user_id INTEGER,
      PRIMARY KEY(chat_id, user_id)
    );

    CREATE TABLE IF NOT EXISTS warnings (
      chat_id INTEGER,
      user_id INTEGER,
      warns INTEGER DEFAULT 0,
      PRIMARY KEY(chat_id, user_id)
    );

    CREATE TABLE IF NOT EXISTS thala_counts (
      chat_id INTEGER,
      user_id INTEGER,
      date TEXT,
      count INTEGER DEFAULT 0,
      PRIMARY KEY(chat_id, user_id, date)
    );

    CREATE TABLE IF NOT EXISTS mutes (
      chat_id INTEGER,
      user_id INTEGER,
      until_ts INTEGER,
      PRIMARY KEY(chat_id, user_id)
    );

    CREATE TABLE IF NOT EXISTS settings (
      chat_id INTEGER PRIMARY KEY,
      anti_link INTEGER DEFAULT 0,
      anti_spam INTEGER DEFAULT 0
    );
    """
    )
    db.commit()


init_db()

# ---------- Helpers ----------
def is_owner(user_id: int) -> bool:
    return user_id == OWNER_ID


def is_admin_or_mod(chat_id: int, user_id: int) -> bool:
    # owner always allowed
    if is_owner(user_id):
        return True
    # check moderators table
    cur = db.cursor()
    cur.execute(
        "SELECT 1 FROM moderators WHERE chat_id = ? AND user_id = ? LIMIT 1",
        (chat_id, user_id),
    )
    if cur.fetchone():
        return True
    return False


def add_mod(chat_id: int, user_id: int):
    cur = db.cursor()
    cur.execute(
        "INSERT OR IGNORE INTO moderators (chat_id, user_id) VALUES (?, ?)",
        (chat_id, user_id),
    )
    db.commit()


def remove_mod(chat_id: int, user_id: int):
    cur = db.cursor()
    cur.execute(
        "DELETE FROM moderators WHERE chat_id = ? AND user_id = ?", (chat_id, user_id)
    )
    db.commit()


def get_setting(chat_id: int, key: str) -> int:
    cur = db.cursor()
    cur.execute("SELECT {} FROM settings WHERE chat_id = ?".format(key), (chat_id,))
    r = cur.fetchone()
    if r:
        return int(r[0])
    # default 0; ensure row present
    cur.execute("INSERT OR IGNORE INTO settings (chat_id) VALUES (?)", (chat_id,))
    db.commit()
    return 0


def set_setting(chat_id: int, key: str, val: int):
    cur = db.cursor()
    cur.execute("INSERT OR REPLACE INTO settings (chat_id, {}) VALUES (?, ?)".format(key), (chat_id, val))
    # Note: SQLite trick: above won't work as intended when other columns are NULL. We do simpler:
    cur.execute("UPDATE settings SET {} = ? WHERE chat_id = ?".format(key), (val, chat_id))
    db.commit()


def increment_thala(chat_id: int, user_id: int) -> int:
    today = datetime.now(timezone.utc).date().isoformat()
    cur = db.cursor()
    cur.execute(
        "INSERT OR IGNORE INTO thala_counts (chat_id, user_id, date, count) VALUES (?, ?, ?, 0)",
        (chat_id, user_id, today),
    )
    cur.execute(
        "UPDATE thala_counts SET count = count + 1 WHERE chat_id = ? AND user_id = ? AND date = ?",
        (chat_id, user_id, today),
    )
    db.commit()
    cur.execute(
        "SELECT count FROM thala_counts WHERE chat_id = ? AND user_id = ? AND date = ?",
        (chat_id, user_id, today),
    )
    r = cur.fetchone()
    return r["count"] if r else 0


def get_thala_count(chat_id: int, user_id: int) -> int:
    today = datetime.now(timezone.utc).date().isoformat()
    cur = db.cursor()
    cur.execute(
        "SELECT count FROM thala_counts WHERE chat_id = ? AND user_id = ? AND date = ?",
        (chat_id, user_id, today),
    )
    r = cur.fetchone()
    return r["count"] if r else 0


def warn_user(chat_id: int, user_id: int, add: int = 1) -> int:
    cur = db.cursor()
    cur.execute(
        "INSERT OR IGNORE INTO warnings (chat_id, user_id, warns) VALUES (?, ?, 0)",
        (chat_id, user_id),
    )
    cur.execute(
        "UPDATE warnings SET warns = warns + ? WHERE chat_id = ? AND user_id = ?",
        (add, chat_id, user_id),
    )
    db.commit()
    cur.execute("SELECT warns FROM warnings WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
    r = cur.fetchone()
    return r["warns"] if r else 0


def get_warnings(chat_id: int, user_id: int) -> int:
    cur = db.cursor()
    cur.execute("SELECT warns FROM warnings WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
    r = cur.fetchone()
    return r["warns"] if r else 0


# ---------- Commands ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hi! I'm a moderation bot. Use /help to see moderation commands."
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "/ban @user - ban user\n"
        "/unban user_id - unban\n"
        "/kick @user - kick user\n"
        "/mute @user 10m - mute for 10 minutes (supports m/h/d)\n"
        "/unmute @user - unmute\n"
        "/warn @user - add warning\n"
        "/warnings @user - show warnings\n"
        "/addmod @user - add chat moderator (owner only)\n"
        "/removemod @user - remove chat moderator (owner only)\n"
        "/set_antlink on|off - toggle anti-link\n"
        "/set_antispam on|off - toggle anti-spam\n"
        "/rules - show rules (set by /setrules)\n"
        "/setrules <text> - set rules (mods+)\n"
        "The bot enforces a per-user daily limit of 3 messages equal to 'thala'."
    )
    await update.message.reply_text(text)


# utility: parse target user and reason
def parse_target_user(update: Update) -> Optional[int]:
    # prefer reply
    if update.message.reply_to_message:
        return update.message.reply_to_message.from_user.id
    # try entities
    entities = update.message.parse_entities()
    for ent, val in entities.items():
        if ent.type == "mention":  # @username
            # can't easily map mention to id without API call; so skip
            pass
        if ent.type == "text_mention":  # user without username
            return val.user.id
    # try args as id
    args = update.message.text.split()
    if len(args) >= 2:
        try:
            return int(args[1])
        except Exception:
            return None
    return None


async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    if not is_admin_or_mod(chat.id, user.id):
        await update.message.reply_text("You don't have permission.")
        return
    target_id = parse_target_user(update)
    if not target_id:
        await update.message.reply_text("Reply to the user or provide user id.")
        return
    try:
        await context.bot.ban_chat_member(chat.id, target_id)
        await update.message.reply_text("User banned.")
    except Exception as e:
        await update.message.reply_text(f"Failed to ban: {e}")


async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    if not is_admin_or_mod(chat.id, user.id):
        await update.message.reply_text("You don't have permission.")
        return
    args = update.message.text.split()
    if len(args) < 2:
        await update.message.reply_text("Provide user id to unban.")
        return
    try:
        target = int(args[1])
        await context.bot.unban_chat_member(chat.id, target)
        await update.message.reply_text("User unbanned.")
    except Exception as e:
        await update.message.reply_text(f"Failed to unban: {e}")


async def kick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    if not is_admin_or_mod(chat.id, user.id):
        await update.message.reply_text("You don't have permission.")
        return
    target_id = parse_target_user(update)
    if not target_id:
        await update.message.reply_text("Reply to the user or provide user id.")
        return
    try:
        await context.bot.ban_chat_member(chat.id, target_id)
        # immediately unban to kick
        await context.bot.unban_chat_member(chat.id, target_id)
        await update.message.reply_text("User kicked.")
    except Exception as e:
        await update.message.reply_text(f"Failed to kick: {e}")


async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    if not is_admin_or_mod(chat.id, user.id):
        await update.message.reply_text("You don't have permission.")
        return
    target_id = parse_target_user(update)
    if not target_id:
        await update.message.reply_text("Reply to the user or provide user id.")
        return
    args = update.message.text.split()
    if len(args) < 2:
        await update.message.reply_text("Specify duration like 10m, 1h, 1d")
        return
    # parse duration
    dur = args[2] if len(args) >= 3 else args[1]
    try:
        unit = dur[-1]
        val = int(dur[:-1])
        seconds = val * (60 if unit == "m" else 3600 if unit == "h" else 86400)
    except Exception:
        await update.message.reply_text("Bad duration. Use 10m, 1h, 1d.")
        return
    until = datetime.now(timezone.utc) + timedelta(seconds=seconds)
    try:
        await context.bot.restrict_chat_member(
            chat.id,
            target_id,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=until,
        )
        # store in DB
        cur = db.cursor()
        cur.execute(
            "INSERT OR REPLACE INTO mutes (chat_id, user_id, until_ts) VALUES (?, ?, ?)",
            (chat.id, target_id, int(until.timestamp())),
        )
        db.commit()
        await update.message.reply_text(f"User muted until {until.isoformat()}.")
    except Exception as e:
        await update.message.reply_text(f"Failed to mute: {e}")


async def unmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    if not is_admin_or_mod(chat.id, user.id):
        await update.message.reply_text("You don't have permission.")
        return
    target_id = parse_target_user(update)
    if not target_id:
        await update.message.reply_text("Reply to the user or provide user id.")
        return
    try:
        await context.bot.restrict_chat_member(
            chat.id,
            target_id,
            permissions=ChatPermissions(
                can_send_messages=True,
                can_send_media_messages=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True,
            ),
        )
        cur = db.cursor()
        cur.execute("DELETE FROM mutes WHERE chat_id = ? AND user_id = ?", (chat.id, target_id))
        db.commit()
        await update.message.reply_text("User unmuted.")
    except Exception as e:
        await update.message.reply_text(f"Failed to unmute: {e}")


async def warn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    if not is_admin_or_mod(chat.id, user.id):
        await update.message.reply_text("You don't have permission.")
        return
    target_id = parse_target_user(update)
    if not target_id:
        await update.message.reply_text("Reply to the user or provide user id.")
        return
    warns = warn_user(chat.id, target_id)
    await update.message.reply_text(f"User warned. Total warns: {warns}")


async def warnings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target_id = parse_target_user(update) or update.effective_user.id
    warns = get_warnings(update.effective_chat.id, target_id)
    await update.message.reply_text(f"Warnings: {warns}")


async def addmod_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_owner(user.id):
        await update.message.reply_text("Only bot owner can add moderators.")
        return
    target_id = parse_target_user(update)
    if not target_id:
        await update.message.reply_text("Reply to the user or provide user id.")
        return
    add_mod(update.effective_chat.id, target_id)
    await update.message.reply_text("Moderator added to this chat.")


async def removemod_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_owner(user.id):
        await update.message.reply_text("Only bot owner can remove moderators.")
        return
    target_id = parse_target_user(update)
    if not target_id:
        await update.message.reply_text("Reply to the user or provide user id.")
        return
    remove_mod(update.effective_chat.id, target_id)
    await update.message.reply_text("Moderator removed.")


async def setrules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin_or_mod(update.effective_chat.id, user.id):
        await update.message.reply_text("You don't have permission.")
        return
    text = update.message.text.partition(" ")[2]
    if not text:
        await update.message.reply_text("Usage: /setrules your rules here")
        return
    # store rules in a simple file per chat
    path = f"rules_{update.effective_chat.id}.txt"
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    await update.message.reply_text("Rules saved.")


async def rules_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    path = f"rules_{update.effective_chat.id}.txt"
    if not os.path.exists(path):
        await update.message.reply_text("No rules set.")
        return
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    await update.message.reply_text(text)


async def set_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin_or_mod(update.effective_chat.id, user.id):
        await update.message.reply_text("You don't have permission.")
        return
    parts = update.message.text.split()
    if len(parts) < 3:
        await update.message.reply_text("Usage: /set_antlink on|off or /set_antispam on|off")
        return
    cmd = parts[0].lower()
    val = 1 if parts[2].lower() in ("on", "1", "yes") else 0
    if cmd.startswith("/set_antlink"):
        set_setting(update.effective_chat.id, "anti_link", val)
        await update.message.reply_text(f"anti_link set to {val}")
    elif cmd.startswith("/set_antispam"):
        set_setting(update.effective_chat.id, "anti_spam", val)
        await update.message.reply_text(f"anti_spam set to {val}")
    else:
        await update.message.reply_text("Unknown toggle.")


# ---------- Message handlers ----------
# Simple anti-link check
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    text = update.message.text.strip()
    chat = update.effective_chat
    user = update.effective_user

    # 1) thala rule exact match (case-insensitive). You can change matching logic as needed.
    if text.lower() == "thala":
        # admins/mods bypass
        if is_admin_or_mod(chat.id, user.id):
            return
        count = increment_thala(chat.id, user.id)
        if count > DAILY_THALA_LIMIT:
            try:
                await update.message.delete()
            except Exception:
                pass
            await update.message.reply_text(
                f"You reached the daily 'thala' limit ({DAILY_THALA_LIMIT}). Your message was removed."
            )
            return
        else:
            # ok
            remaining = DAILY_THALA_LIMIT - count
            if remaining == 0:
                await update.message.reply_text("This was your last allowed 'thala' today.")
            else:
                await update.message.reply_text(f"'thala' count: {count}. Remaining today: {remaining}")
            return

    # 2) anti-link
    anti_link = get_setting(chat.id, "anti_link")
    if anti_link:
        if "http://" in text.lower() or "https://" in text.lower() or ".com" in text.lower():
            # simple heuristic
            if not is_admin_or_mod(chat.id, user.id):
                try:
                    await update.message.delete()
                except Exception:
                    pass
                await update.message.reply_text("Links are not allowed in this chat.")
                return

    # 3) anti-spam (simple: > X messages in Y sec)
    anti_spam = get_setting(chat.id, "anti_spam")
    if anti_spam:
        # very simple rate-limiter stored in context.user_data
        ud = context.chat_data.setdefault("recent_msgs", {})
        now_ts = datetime.now(timezone.utc).timestamp()
        lst = ud.get(user.id, [])
        # purge older than 10s
        lst = [ts for ts in lst if now_ts - ts < 10]
        lst.append(now_ts)
        ud[user.id] = lst
        if len(lst) > 5 and not is_admin_or_mod(chat.id, user.id):
            # considered spam
            try:
                await update.message.delete()
            except Exception:
                pass
            await update.message.reply_text("Please avoid spamming.")
            warn_user(chat.id, user.id)
            return


# ---------- Background jobs ----------
async def job_cleanup_mutes(app):
    # remove expired mutes in DB and try to unmute users
    cur = db.cursor()
    now_ts = int(datetime.now(timezone.utc).timestamp())
    cur.execute("SELECT chat_id, user_id FROM mutes WHERE until_ts <= ?", (now_ts,))
    rows = cur.fetchall()
    for r in rows:
        chat_id = r["chat_id"]
        user_id = r["user_id"]
        try:
            await app.bot.restrict_chat_member(
                chat_id,
                user_id,
                permissions=ChatPermissions(
                    can_send_messages=True,
                    can_send_media_messages=True,
                    can_send_other_messages=True,
                    can_add_web_page_previews=True,
                ),
            )
        except Exception:
            pass
        cur.execute("DELETE FROM mutes WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
    db.commit()


async def chat_member_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # optional: welcome new members or handle leave messages, etc.
    pass


# ---------- Main ----------
async def main():
    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .build()
    )

    # commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("ban", ban))
    app.add_handler(CommandHandler("unban", unban))
    app.add_handler(CommandHandler("kick", kick))
    app.add_handler(CommandHandler("mute", mute))
    app.add_handler(CommandHandler("unmute", unmute))
    app.add_handler(CommandHandler("warn", warn))
    app.add_handler(CommandHandler("warnings", warnings_cmd))
    app.add_handler(CommandHandler("addmod", addmod_cmd))
    app.add_handler(CommandHandler("removemod", removemod_cmd))
    app.add_handler(CommandHandler("setrules", setrules))
    app.add_handler(CommandHandler("rules", rules_cmd))
    app.add_handler(CommandHandler("set_antlink", set_toggle))
    app.add_handler(CommandHandler("set_antispam", set_toggle))

    # message handler
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    app.add_handler(ChatMemberHandler(chat_member_update, ChatMemberHandler.CHAT_MEMBER))

    # schedule periodic job for mutes cleanup
    job_queue = app.job_queue
    job_queue.run_repeating(lambda ctx: asyncio.create_task(job_cleanup_mutes(app)), interval=60, first=10)

    # start
    await app.run_polling()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped")
