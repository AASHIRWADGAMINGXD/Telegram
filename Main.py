# Main.py
"""
Telegram Moderation Bot with password-protected admin access.
Compatible with Python 3.13 and python-telegram-bot==21.6.

Environment variables required:
- BOT_TOKEN   : Telegram bot token
- OWNER_ID    : your Telegram numeric user id
- ADMIN_PASSWORD : (optional but recommended) initial admin password (plaintext).
                   On first run the bot will hash+store it.
Optional:
- DB_PATH     : path to sqlite file (default: moderator_bot.db)
"""
import asyncio
import hashlib
import hmac
import os
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from telegram import ChatPermissions, Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# ----------------- CONFIG -----------------
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_PASSWORD_ENV = os.environ.get("ADMIN_PASSWORD")  # plaintext on first-run (optional)
DB_PATH = os.environ.get("DB_PATH", "moderator_bot.db")

# Limits & behavior
DAILY_THALA_LIMIT = 3
SPAM_LIMIT = 5         # messages
SPAM_WINDOW = 10       # seconds
SPAM_MUTE_SECONDS = 60 # mute duration for spam
SLOWMODE_DEFAULT = 0   # seconds (0 = off)
AUTH_SESSION_DAYS = 7  # login validity

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable required")

if not OWNER_ID or OWNER_ID == 0:
    raise RuntimeError("OWNER_ID environment variable required and must be your numeric Telegram ID")

# ----------------- DB -----------------
_conn = sqlite3.connect(DB_PATH, check_same_thread=False)
_conn.row_factory = sqlite3.Row
_cur = _conn.cursor()

_cur.executescript(
    """
CREATE TABLE IF NOT EXISTS moderators (chat_id INTEGER, user_id INTEGER, PRIMARY KEY(chat_id,user_id));
CREATE TABLE IF NOT EXISTS allowed_users (user_id INTEGER PRIMARY KEY); -- optional friends by owner
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS thala_counts (chat_id INTEGER, user_id INTEGER, date TEXT, count INTEGER DEFAULT 0, PRIMARY KEY(chat_id,user_id,date));
CREATE TABLE IF NOT EXISTS warnings (chat_id INTEGER, user_id INTEGER, warns INTEGER DEFAULT 0, PRIMARY KEY(chat_id,user_id));
CREATE TABLE IF NOT EXISTS mutes (chat_id INTEGER, user_id INTEGER, until_ts INTEGER, PRIMARY KEY(chat_id,user_id));
CREATE TABLE IF NOT EXISTS auth_sessions (user_id INTEGER PRIMARY KEY, expires_ts INTEGER);
CREATE TABLE IF NOT EXISTS slowmode (chat_id INTEGER PRIMARY KEY, seconds INTEGER DEFAULT 0);
"""
)
_conn.commit()


# ----------------- SECURITY: password hashing -----------------
# Use PBKDF2-HMAC-SHA256 from stdlib
def _hash_password(password: str, salt: bytes, iterations: int = 150_000) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)


def set_password_from_env():
    """
    If ADMIN_PASSWORD provided in env and no password stored in settings,
    create salt and hashed password and store in settings table.
    """
    if not ADMIN_PASSWORD_ENV:
        return
    _cur.execute("SELECT value FROM settings WHERE key='pw_salt'")
    if _cur.fetchone():
        return  # already set
    salt = os.urandom(16)
    hashed = _hash_password(ADMIN_PASSWORD_ENV, salt).hex()
    _cur.execute("INSERT OR REPLACE INTO settings(key,value) VALUES (?,?)", ("pw_salt", salt.hex()))
    _cur.execute("INSERT OR REPLACE INTO settings(key,value) VALUES (?,?)", ("pw_hash", hashed))
    _conn.commit()


def verify_password(candidate: str) -> bool:
    _cur.execute("SELECT value FROM settings WHERE key='pw_salt'")
    row = _cur.fetchone()
    if not row:
        return False
    salt = bytes.fromhex(row["value"])
    _cur.execute("SELECT value FROM settings WHERE key='pw_hash'")
    row2 = _cur.fetchone()
    if not row2:
        return False
    stored = row2["value"]
    cand_hash = _hash_password(candidate, salt).hex()
    # use hmac.compare_digest for timing-attack resistance
    return hmac.compare_digest(cand_hash, stored)


def set_new_password(new_pw: str):
    salt = os.urandom(16)
    hashed = _hash_password(new_pw, salt).hex()
    _cur.execute("INSERT OR REPLACE INTO settings(key,value) VALUES (?,?)", ("pw_salt", salt.hex()))
    _cur.execute("INSERT OR REPLACE INTO settings(key,value) VALUES (?,?)", ("pw_hash", hashed))
    _conn.commit()


# initialize password from env if provided
set_password_from_env()


# ----------------- AUTH & PERMISSIONS -----------------
def is_owner(user_id: int) -> bool:
    return user_id == OWNER_ID


def is_allowed_user(user_id: int) -> bool:
    """Owner, explicit allowed_users, or active auth session"""
    if is_owner(user_id):
        return True
    _cur.execute("SELECT 1 FROM allowed_users WHERE user_id=?", (user_id,))
    if _cur.fetchone():
        return True
    # check session
    _cur.execute("SELECT expires_ts FROM auth_sessions WHERE user_id=?", (user_id,))
    r = _cur.fetchone()
    if r and r["expires_ts"] >= int(time.time()):
        return True
    return False


def require_admin(func):
    """Decorator for handler functions to allow only authenticated admins/friends/owner"""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user = update.effective_user
        if not user:
            return
        if not is_allowed_user(user.id):
            await update.message.reply_text("❌ You are not authorized to use this command. Use /login <password>.")
            return
        return await func(update, context, *args, **kwargs)
    return wrapper


# ----------------- UTILITIES -----------------
def parse_target_user_id(update: Update) -> Optional[int]:
    # prefer reply
    if update.message.reply_to_message:
        return update.message.reply_to_message.from_user.id
    parts = update.message.text.split()
    if len(parts) >= 2:
        try:
            return int(parts[1])
        except ValueError:
            return None
    return None


def now_ts() -> int:
    return int(time.time())


# ----------------- CORE FEATURES -----------------
# spam tracker: map (chat_id, user_id) -> list[timestamps]
from collections import defaultdict, deque
_spam_tracker = defaultdict(deque)


def record_message_for_spam(chat_id: int, user_id: int):
    key = (chat_id, user_id)
    dq = _spam_tracker[key]
    ts = time.time()
    dq.append(ts)
    # purge older than SPAM_WINDOW
    while dq and ts - dq[0] > SPAM_WINDOW:
        dq.popleft()
    _spam_tracker[key] = dq
    return len(dq)


def increment_thala(chat_id: int, user_id: int) -> int:
    today = datetime.now(timezone.utc).date().isoformat()
    _cur.execute(
        "INSERT OR IGNORE INTO thala_counts(chat_id,user_id,date,count) VALUES (?,?,?,0)",
        (chat_id, user_id, today),
    )
    _cur.execute(
        "UPDATE thala_counts SET count = count + 1 WHERE chat_id=? AND user_id=? AND date=?",
        (chat_id, user_id, today),
    )
    _conn.commit()
    _cur.execute("SELECT count FROM thala_counts WHERE chat_id=? AND user_id=? AND date=?",
                 (chat_id, user_id, today))
    r = _cur.fetchone()
    return r["count"] if r else 0


def get_thala_count(chat_id: int, user_id: int) -> int:
    today = datetime.now(timezone.utc).date().isoformat()
    _cur.execute("SELECT count FROM thala_counts WHERE chat_id=? AND user_id=? AND date=?",
                 (chat_id, user_id, today))
    r = _cur.fetchone()
    return r["count"] if r else 0


def reset_daily_limits():
    today = datetime.now(timezone.utc).date().isoformat()
    # delete old thala counts
    _cur.execute("DELETE FROM thala_counts WHERE date != ?", (today,))
    # reset warnings
    _cur.execute("DELETE FROM warnings")
    _conn.commit()


def get_slowmode_seconds(chat_id: int) -> int:
    _cur.execute("SELECT seconds FROM slowmode WHERE chat_id=?", (chat_id,))
    r = _cur.fetchone()
    return int(r["seconds"]) if r else SLOWMODE_DEFAULT


def set_slowmode_seconds(chat_id: int, seconds: int):
    _cur.execute("INSERT OR REPLACE INTO slowmode(chat_id,seconds) VALUES (?,?)", (chat_id, seconds))
    _conn.commit()


# ----------------- COMMAND HANDLERS -----------------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hello — moderation bot online. Use /help to see commands.")


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "Moderation commands (admin-only use /login first):\n"
        "/login <password> — authenticate for admin commands (valid 7 days)\n"
        "/logout — clear your session\n"
        "/addfriend <user_id> — owner only (adds allowed friend)\n"
        "/removefriend <user_id> — owner only\n"
        "/ban <reply|user_id>\n"
        "/unban <user_id>\n"
        "/kick <reply|user_id>\n"
        "/mute <reply|user_id> <10m|1h|1d>\n"
        "/unmute <reply|user_id>\n"
        "/warn <reply|user_id>\n"
        "/warnings <reply|user_id>\n"
        "/addmod <reply|user_id> — add chat moderator\n"
        "/removemod <reply|user_id>\n"
        "/listmods — list moderators in this chat\n"
        "/setslow <seconds> — set slowmode for this chat (0 to disable)\n"
        "/purge <n> — delete last n messages (chat admin permissions required for bot)\n"
        "/rules <text> — set rules\n"
        "/rules — show rules\n"
        "Thala limit: users can only say 'thala' 3 times per UTC day."
    )
    await update.message.reply_text(text)


# -------- AUTH ----------
async def login_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    parts = update.message.text.split(maxsplit=1)
    if len(parts) < 2:
        return await update.message.reply_text("Usage: /login <password>")
    pw = parts[1].strip()
    if verify_password(pw):
        expires = now_ts() + AUTH_SESSION_DAYS * 24 * 3600
        _cur.execute("INSERT OR REPLACE INTO auth_sessions(user_id,expires_ts) VALUES (?,?)",
                     (update.effective_user.id, expires))
        _conn.commit()
        await update.message.reply_text(f"✅ Authenticated for {AUTH_SESSION_DAYS} days.")
    else:
        await update.message.reply_text("❌ Wrong password.")


async def logout_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _cur.execute("DELETE FROM auth_sessions WHERE user_id=?", (update.effective_user.id,))
    _conn.commit()
    await update.message.reply_text("You have been logged out.")


# -------- FRIEND MANAGEMENT (owner) ----------
async def addfriend_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        return await update.message.reply_text("Owner only.")
    parts = update.message.text.split()
    if len(parts) < 2:
        return await update.message.reply_text("Usage: /addfriend <user_id>")
    try:
        uid = int(parts[1])
        _cur.execute("INSERT OR IGNORE INTO allowed_users(user_id) VALUES (?)", (uid,))
        _conn.commit()
        await update.message.reply_text("Friend added.")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")


async def removefriend_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        return await update.message.reply_text("Owner only.")
    parts = update.message.text.split()
    if len(parts) < 2:
        return await update.message.reply_text("Usage: /removefriend <user_id>")
    try:
        uid = int(parts[1])
        _cur.execute("DELETE FROM allowed_users WHERE user_id=?", (uid,))
        _conn.commit()
        await update.message.reply_text("Friend removed.")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")


# -------- MODERATOR MANAGEMENT (per chat) ----------
@require_admin
async def addmod_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = parse_target_user_id(update)
    if not target:
        return await update.message.reply_text("Reply to user or /addmod <user_id>")
    _cur.execute("INSERT OR IGNORE INTO moderators(chat_id,user_id) VALUES (?,?)", (update.effective_chat.id, target))
    _conn.commit()
    await update.message.reply_text("Moderator added for this chat.")


@require_admin
async def removemod_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = parse_target_user_id(update)
    if not target:
        return await update.message.reply_text("Reply to user or /removemod <user_id>")
    _cur.execute("DELETE FROM moderators WHERE chat_id=? AND user_id=?", (update.effective_chat.id, target))
    _conn.commit()
    await update.message.reply_text("Moderator removed from this chat.")


async def listmods_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _cur.execute("SELECT user_id FROM moderators WHERE chat_id=?", (update.effective_chat.id,))
    rows = _cur.fetchall()
    if not rows:
        return await update.message.reply_text("No moderators set for this chat.")
    text = "Moderators in this chat:\n" + "\n".join(str(r["user_id"]) for r in rows)
    await update.message.reply_text(text)


# -------- ACTIONS (ban/unban/kick/mute/unmute/warn) ----------
@require_admin
async def ban_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = parse_target_user_id(update)
    if not target:
        return await update.message.reply_text("Reply to user or /ban <user_id>")
    try:
        await context.bot.ban_chat_member(update.effective_chat.id, target)
        await update.message.reply_text("User banned.")
    except Exception as e:
        await update.message.reply_text(f"Failed to ban: {e}")


@require_admin
async def unban_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    parts = update.message.text.split()
    if len(parts) < 2:
        return await update.message.reply_text("Usage: /unban <user_id>")
    try:
        uid = int(parts[1])
        await context.bot.unban_chat_member(update.effective_chat.id, uid)
        await update.message.reply_text("User unbanned.")
    except Exception as e:
        await update.message.reply_text(f"Failed to unban: {e}")


@require_admin
async def kick_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = parse_target_user_id(update)
    if not target:
        return await update.message.reply_text("Reply to user or /kick <user_id>")
    try:
        await context.bot.ban_chat_member(update.effective_chat.id, target)
        await context.bot.unban_chat_member(update.effective_chat.id, target)
        await update.message.reply_text("User kicked.")
    except Exception as e:
        await update.message.reply_text(f"Failed to kick: {e}")


@require_admin
async def mute_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = parse_target_user_id(update)
    if not target:
        return await update.message.reply_text("Reply to user or /mute <user_id> <10m|1h|1d>")
    parts = update.message.text.split()
    if len(parts) < 3:
        return await update.message.reply_text("Usage: /mute <reply|user_id> <10m|1h|1d>")
    dur = parts[2]
    try:
        val, unit = int(dur[:-1]), dur[-1]
        seconds = val * (60 if unit == "m" else 3600 if unit == "h" else 86400)
    except Exception:
        return await update.message.reply_text("Invalid duration. Use 10m, 1h, 1d")
    until = datetime.now(timezone.utc) + timedelta(seconds=seconds)
    try:
        await context.bot.restrict_chat_member(
            update.effective_chat.id, target,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=until
        )
        _cur.execute("INSERT OR REPLACE INTO mutes(chat_id,user_id,until_ts) VALUES (?,?,?)",
                     (update.effective_chat.id, target, int(until.timestamp())))
        _conn.commit()
        await update.message.reply_text(f"User muted for {dur}.")
    except Exception as e:
        await update.message.reply_text(f"Failed to mute: {e}")


@require_admin
async def unmute_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = parse_target_user_id(update)
    if not target:
        return await update.message.reply_text("Reply to user or /unmute <user_id>")
    try:
        await context.bot.restrict_chat_member(
            update.effective_chat.id, target,
            permissions=ChatPermissions(
                can_send_messages=True,
                can_send_media_messages=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True
            )
        )
        _cur.execute("DELETE FROM mutes WHERE chat_id=? AND user_id=?", (update.effective_chat.id, target))
        _conn.commit()
        await update.message.reply_text("User unmuted.")
    except Exception as e:
        await update.message.reply_text(f"Failed to unmute: {e}")


@require_admin
async def warn_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = parse_target_user_id(update)
    if not target:
        return await update.message.reply_text("Reply to user or /warn <user_id>")
    _cur.execute("INSERT OR IGNORE INTO warnings(chat_id,user_id,warns) VALUES (?,?,0)",
                 (update.effective_chat.id, target))
    _cur.execute("UPDATE warnings SET warns = warns + 1 WHERE chat_id=? AND user_id=?",
                 (update.effective_chat.id, target))
    _conn.commit()
    _cur.execute("SELECT warns FROM warnings WHERE chat_id=? AND user_id=?", (update.effective_chat.id, target))
    r = _cur.fetchone()
    await update.message.reply_text(f"Warned user. Total warns: {r['warns']}")


async def warnings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = parse_target_user_id(update) or update.effective_user.id
    _cur.execute("SELECT warns FROM warnings WHERE chat_id=? AND user_id=?", (update.effective_chat.id, target))
    r = _cur.fetchone()
    await update.message.reply_text(f"Warnings: {r['warns'] if r else 0}")


# -------- MISC: rules, pin, purge, slowmode ----------
@require_admin
async def setrules_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.partition(" ")[2].strip()
    if not text:
        return await update.message.reply_text("Use: /rules <text>")
    key = f"rules_{update.effective_chat.id}"
    _cur.execute("INSERT OR REPLACE INTO settings(key,value) VALUES (?,?)", (key, text))
    _conn.commit()
    await update.message.reply_text("Rules set.")


async def rules_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = f"rules_{update.effective_chat.id}"
    _cur.execute("SELECT value FROM settings WHERE key=?", (key,))
    r = _cur.fetchone()
    if not r:
        await update.message.reply_text("No rules set.")
    else:
        await update.message.reply_text(r["value"])


@require_admin
async def pin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        return await update.message.reply_text("Reply to a message to pin it.")
    try:
        await context.bot.pin_chat_message(update.effective_chat.id, update.message.reply_to_message.message_id)
        await update.message.reply_text("Pinned.")
    except Exception as e:
        await update.message.reply_text(f"Failed to pin: {e}")


@require_admin
async def unpin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await context.bot.unpin_all_chat_messages(update.effective_chat.id)
        await update.message.reply_text("All pins cleared.")
    except Exception as e:
        await update.message.reply_text(f"Failed to unpin: {e}")


@require_admin
async def purge_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    parts = update.message.text.split()
    if len(parts) < 2:
        return await update.message.reply_text("Usage: /purge <n>")
    try:
        n = int(parts[1])
        if n <= 0 or n > 100:
            return await update.message.reply_text("n must be between 1 and 100")
        # attempt to delete last n messages by fetching recent messages (bot needs permission)
        messages = await context.bot.get_chat_history(update.effective_chat.id, limit=n + 1)
        deleted = 0
        for m in messages:
            try:
                await context.bot.delete_message(update.effective_chat.id, m.message_id)
                deleted += 1
            except Exception:
                continue
        await update.message.reply_text(f"Attempted to delete {deleted} messages.")
    except Exception as e:
        await update.message.reply_text(f"Failed purge: {e}")


@require_admin
async def setslow_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    parts = update.message.text.split()
    if len(parts) < 2:
        return await update.message.reply_text("Usage: /setslow <seconds>")
    try:
        secs = int(parts[1])
        set_slowmode_seconds(update.effective_chat.id, max(0, secs))
        await update.message.reply_text(f"Slowmode set to {secs}s.")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")


# -------- MESSAGE HANDLER: anti-link, spam, thala, slowmode ----------
import re
LINK_RE = re.compile(r"(https?://\S+|t\.me/\S+|telegram\.me/\S+|\S+\.\w{2,4})", re.IGNORECASE)


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    chat = update.effective_chat
    user = update.effective_user
    text = update.message.text.strip()

    # 1) Slowmode: check when user last message in this chat
    slow_secs = get_slowmode_seconds(chat.id)
    if slow_secs > 0 and not is_owner(user.id) and not is_allowed_user(user.id):
        # use context.chat_data to store last_message_ts per user
        last_map = context.chat_data.setdefault("last_msg_ts", {})
        last = last_map.get(user.id, 0)
        now = time.time()
        if now - last < slow_secs:
            try:
                await update.message.delete()
            except Exception:
                pass
            await update.message.reply_text(f"Slowmode is enabled. Please wait {int(slow_secs - (now - last))}s.")
            return
        last_map[user.id] = now
        context.chat_data["last_msg_ts"] = last_map

    # 2) Anti-link
    if LINK_RE.search(text) and not is_allowed_user(user.id) and not is_owner(user.id):
        try:
            await update.message.delete()
            await update.message.reply_text(f"Links are not allowed, {user.first_name}.")
            return
        except Exception:
            pass

    # 3) Spam detection
    cnt = record_message_for_spam(chat.id, user.id)
    if cnt >= SPAM_LIMIT and not is_allowed_user(user.id) and not is_owner(user.id):
        # mute briefly
        until = datetime.now(timezone.utc) + timedelta(seconds=SPAM_MUTE_SECONDS)
        try:
            await context.bot.restrict_chat_member(chat.id, user.id, permissions=ChatPermissions(can_send_messages=False), until_date=until)
            _cur.execute("INSERT OR REPLACE INTO mutes(chat_id,user_id,until_ts) VALUES (?,?,?)",
                         (chat.id, user.id, int(until.timestamp())))
            _conn.commit()
            await update.message.reply_text(f"Muted {user.first_name} for spam.")
            _spam_tracker[(chat.id, user.id)].clear()
        except Exception:
            pass
        return

    # 4) Thala limiter (exact match)
    if text.lower() == "thala" and not is_allowed_user(user.id) and not is_owner(user.id):
        count = increment_thala(chat.id, user.id)
        if count > DAILY_THALA_LIMIT:
            try:
                await update.message.delete()
            except Exception:
                pass
            await update.message.reply_text(f"You reached your daily 'thala' limit ({DAILY_THALA_LIMIT}).")
            return
        else:
            remaining = DAILY_THALA_LIMIT - count
            await update.message.reply_text(f"'thala': {count}/{DAILY_THALA_LIMIT} (remaining {remaining})")
            return


# ----------------- BACKGROUND JOBS -----------------
async def cleanup_mutes_job(app: Application):
    now = int(time.time())
    _cur.execute("SELECT chat_id,user_id FROM mutes WHERE until_ts <= ?", (now,))
    rows = _cur.fetchall()
    for r in rows:
        try:
            await app.bot.restrict_chat_member(
                r["chat_id"],
                r["user_id"],
                permissions=ChatPermissions(
                    can_send_messages=True,
                    can_send_media_messages=True,
                    can_send_other_messages=True,
                    can_add_web_page_previews=True,
                ),
            )
        except Exception:
            pass
        _cur.execute("DELETE FROM mutes WHERE chat_id=? AND user_id=?", (r["chat_id"], r["user_id"]))
    _conn.commit()


async def expire_sessions_job(app: Application):
    now = int(time.time())
    _cur.execute("DELETE FROM auth_sessions WHERE expires_ts < ?", (now,))
    _conn.commit()


async def daily_reset_job(app: Application):
    reset_daily_limits()


# ----------------- STARTUP & RUN -----------------
async def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # basic
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))

    # auth/friends
    app.add_handler(CommandHandler("login", login_cmd))
    app.add_handler(CommandHandler("logout", logout_cmd))
    app.add_handler(CommandHandler("addfriend", addfriend_cmd))
    app.add_handler(CommandHandler("removefriend", removefriend_cmd))

    # moderator management
    app.add_handler(CommandHandler("addmod", addmod_cmd))
    app.add_handler(CommandHandler("removemod", removemod_cmd))
    app.add_handler(CommandHandler("listmods", listmods_cmd))

    # actions
    app.add_handler(CommandHandler("ban", ban_cmd))
    app.add_handler(CommandHandler("unban", unban_cmd))
    app.add_handler(CommandHandler("kick", kick_cmd))
    app.add_handler(CommandHandler("mute", mute_cmd))
    app.add_handler(CommandHandler("unmute", unmute_cmd))
    app.add_handler(CommandHandler("warn", warn_cmd))
    app.add_handler(CommandHandler("warnings", warnings_cmd))

    # misc
    app.add_handler(CommandHandler("rules", rules_cmd))
    app.add_handler(CommandHandler("setrules", setrules_cmd))
    app.add_handler(CommandHandler("pin", pin_cmd))
    app.add_handler(CommandHandler("unpin", unpin_cmd))
    app.add_handler(CommandHandler("purge", purge_cmd))
    app.add_handler(CommandHandler("setslow", setslow_cmd))
    app.add_handler(CommandHandler("start", start_cmd))

    # owner-only password change
    async def setpw_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not is_owner(update.effective_user.id):
            return await update.message.reply_text("Owner only.")
        parts = update.message.text.split(maxsplit=1)
        if len(parts) < 2:
            return await update.message.reply_text("Usage: /setpassword <newpassword>")
        set_new_password(parts[1].strip())
        await update.message.reply_text("Password updated.")
    app.add_handler(CommandHandler("setpassword", setpw_cmd))

    # message handler
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    # jobs
    app.job_queue.run_repeating(lambda ctx: asyncio.create_task(cleanup_mutes_job(app)), interval=60, first=10)
    app.job_queue.run_repeating(lambda ctx: asyncio.create_task(expire_sessions_job(app)), interval=3600, first=30)
    # daily reset at midnight UTC
    from datetime import time as dtime
    app.job_queue.run_daily(lambda ctx: asyncio.create_task(daily_reset_job(app)), time=dtime(0, 0, tzinfo=timezone.utc))

    print("✅ Bot starting (admin suite + password auth).")
    await app.run_polling()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Bot stopped")
