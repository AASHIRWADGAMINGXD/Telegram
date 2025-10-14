#!/usr/bin/env python3
"""
Telegram moderation bot
- 20+ moderator commands (ban, kick, mute, unmute, tempmute, warn, warnings, purge, pin, unpin, promote, demote, lock, unlock, setrules, rules, clearcache, stats, config, etc.)
- "thala" limit: users can send "thala" (case-insensitive) up to 3 times per calendar day; after that their message is deleted and they are notified.
- Admins (chat admins) are exempt from the "thala" limit.
- Uses SQLite for persistence (warnings, thala counts, rules, muted users).
"""

import os
import asyncio
import logging
import sqlite3
from datetime import datetime, date, timedelta
from typing import Optional, List

from telegram import (
    Update,
    ChatPermissions,
    ChatMemberAdministrator,
    ChatMemberOwner,
    MessageEntity,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ------------ Config ------------
TOKEN = os.environ.get("TELEGRAM_TOKEN")
if not TOKEN:
    raise RuntimeError("Set TELEGRAM_TOKEN environment variable")

DB_PATH = os.environ.get("DB_PATH", "bot_data.db")  # on Render, attach persistent disk or use DB service
THALA_LIMIT_PER_DAY = 3
# -------------------------------

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
log = logging.getLogger(__name__)

# ---------- DB helpers ----------
def init_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    c = conn.cursor()
    c.execute(
        """CREATE TABLE IF NOT EXISTS warnings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            user_id INTEGER,
            by_user_id INTEGER,
            reason TEXT,
            ts TEXT
        )"""
    )
    c.execute(
        """CREATE TABLE IF NOT EXISTS thala_counts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            user_id INTEGER,
            date TEXT,
            count INTEGER
        )"""
    )
    c.execute(
        """CREATE TABLE IF NOT EXISTS rules (
            chat_id INTEGER PRIMARY KEY,
            text TEXT
        )"""
    )
    c.execute(
        """CREATE TABLE IF NOT EXISTS muted (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            user_id INTEGER,
            until_ts TEXT
        )"""
    )
    # recent messages cache for purge: store last N msg ids per chat
    c.execute(
        """CREATE TABLE IF NOT EXISTS recent_messages (
            chat_id INTEGER,
            message_id INTEGER,
            user_id INTEGER,
            ts TEXT
        )"""
    )
    conn.commit()
    return conn

DB = init_db()

# ---------- Utilities ----------
def is_user_admin(chat_member) -> bool:
    return isinstance(chat_member, (ChatMemberAdministrator, ChatMemberOwner))

async def user_is_admin(app: Application, chat_id: int, user_id: int) -> bool:
    try:
        member = await app.bot.get_chat_member(chat_id, user_id)
        return is_user_admin(member)
    except Exception:
        return False

def thala_get_count(chat_id: int, user_id: int) -> int:
    c = DB.cursor()
    today = date.today().isoformat()
    c.execute(
        "SELECT count FROM thala_counts WHERE chat_id=? AND user_id=? AND date=?",
        (chat_id, user_id, today),
    )
    r = c.fetchone()
    return r[0] if r else 0

def thala_inc(chat_id: int, user_id: int) -> int:
    c = DB.cursor()
    today = date.today().isoformat()
    cur = c.execute(
        "SELECT id, count FROM thala_counts WHERE chat_id=? AND user_id=? AND date=?",
        (chat_id, user_id, today),
    ).fetchone()
    if cur:
        new = cur[1] + 1
        c.execute("UPDATE thala_counts SET count=? WHERE id=?", (new, cur[0]))
    else:
        new = 1
        c.execute(
            "INSERT INTO thala_counts (chat_id, user_id, date, count) VALUES (?,?,?,?)",
            (chat_id, user_id, today, new),
        )
    DB.commit()
    return new

def add_warning(chat_id: int, user_id: int, by_user: int, reason: str):
    c = DB.cursor()
    c.execute(
        "INSERT INTO warnings (chat_id,user_id,by_user_id,reason,ts) VALUES (?,?,?,?,?)",
        (chat_id, user_id, by_user, reason, datetime.utcnow().isoformat()),
    )
    DB.commit()

def get_warnings(chat_id: int, user_id: int):
    c = DB.cursor()
    c.execute(
        "SELECT id,by_user_id,reason,ts FROM warnings WHERE chat_id=? AND user_id=? ORDER BY id DESC",
        (chat_id, user_id),
    )
    return c.fetchall()

def add_recent_message(chat_id: int, message_id: int, user_id: int):
    c = DB.cursor()
    c.execute(
        "INSERT INTO recent_messages (chat_id,message_id,user_id,ts) VALUES (?,?,?,?)",
        (chat_id, message_id, user_id, datetime.utcnow().isoformat()),
    )
    # keep last ~1000 rows per chat to limit growth
    c.execute(
        "DELETE FROM recent_messages WHERE rowid IN (SELECT rowid FROM recent_messages WHERE chat_id=? ORDER BY rowid DESC LIMIT -1 OFFSET 1000)",
        (chat_id,),
    )
    DB.commit()

def get_recent_message_ids(chat_id: int, limit: int) -> List[int]:
    c = DB.cursor()
    c.execute(
        "SELECT message_id FROM recent_messages WHERE chat_id=? ORDER BY rowid DESC LIMIT ?",
        (chat_id, limit),
    )
    return [r[0] for r in c.fetchall()]

def set_rules(chat_id: int, text: str):
    c = DB.cursor()
    c.execute(
        "INSERT INTO rules (chat_id,text) VALUES (?,?) ON CONFLICT(chat_id) DO UPDATE SET text=excluded.text",
        (chat_id, text),
    )
    DB.commit()

def get_rules(chat_id: int) -> Optional[str]:
    c = DB.cursor()
    c.execute("SELECT text FROM rules WHERE chat_id=?", (chat_id,))
    r = c.fetchone()
    return r[0] if r else None

# ---------- Moderation helpers ----------
async def restrict_user(app: Application, chat_id: int, user_id: int, can_send: bool, until_ts: Optional[int] = None):
    # Set permissions: allow or disallow sending messages
    perms = ChatPermissions(can_send_messages=can_send)
    try:
        await app.bot.restrict_chat_member(chat_id, user_id, permissions=perms, until_date=until_ts)
        return True
    except Exception as e:
        log.exception("restrict_user error: %s", e)
        return False

async def promote_user(app: Application, chat_id: int, user_id: int, can_change_info=False, can_delete_messages=False, can_invite_users=False, can_pin_messages=False):
    try:
        await app.bot.promote_chat_member(
            chat_id,
            user_id,
            can_change_info=can_change_info,
            can_delete_messages=can_delete_messages,
            can_invite_users=can_invite_users,
            can_pin_messages=can_pin_messages,
        )
        return True
    except Exception as e:
        log.exception("promote error: %s", e)
        return False

# ---------- Command handlers ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Moderation bot online. Use /help to see moderator commands."
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "Moderation commands (admins only):\n"
        "/ban @user [reason]\n"
        "/unban user_id\n"
        "/kick @user\n"
        "/mute @user [minutes]\n"
        "/unmute @user\n"
        "/tempmute @user <minutes>\n"
        "/warn @user [reason]\n"
        "/warnings @user\n"
        "/purge <n> - delete last n tracked messages\n"
        "/pin - reply to a message to pin\n"
        "/unpin\n"
        "/promote @user\n"
        "/demote @user\n"
        "/lock - prevents sending messages\n"
        "/unlock\n"
        "/setrules <text>\n"
        "/rules\n"
        "/stats\n"
        "/clearcache\n"
    )
    await update.message.reply_text(help_text)

async def require_admin(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        chat = update.effective_chat
        app = context.application
        if not chat or not user:
            return
        if await user_is_admin(app, chat.id, user.id):
            return await func(update, context)
        else:
            await update.message.reply_text("You must be an admin to use this.")
    return wrapper

@require_admin
async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    args = context.args
    if not args and not update.message.reply_to_message:
        return await update.message.reply_text("Usage: /ban @user [reason] or reply with /ban")
    target = None
    reason = " ".join(args[1:]) if len(args) > 1 else ""
    if update.message.reply_to_message:
        target = update.message.reply_to_message.from_user
    else:
        target_username = args[0]
        # try parse @username or id
        if target_username.startswith("@"):
            # find by username via get_chat? Skip; ask to reply for reliability
            return await update.message.reply_text("Please reply to user's message to ban or use user_id.")
        else:
            try:
                user_id = int(target_username)
                target = await context.application.bot.get_chat_member(chat.id, user_id)
                target = target.user
            except Exception:
                return await update.message.reply_text("Couldn't parse target.")
    try:
        await context.application.bot.ban_chat_member(chat.id, target.id)
        await update.message.reply_text(f"Banned {target.mention_html()}.\nReason: {reason}", parse_mode=ParseMode.HTML)
    except Exception as e:
        log.exception(e)
        await update.message.reply_text("Failed to ban. Make sure bot is admin with ban rights.")

@require_admin
async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        return await update.message.reply_text("Usage: /unban user_id")
    try:
        user_id = int(args[0])
        await context.application.bot.unban_chat_member(update.effective_chat.id, user_id)
        await update.message.reply_text(f"Unbanned {user_id}")
    except Exception as e:
        log.exception(e)
        await update.message.reply_text("Failed to unban.")

@require_admin
async def kick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # kick = ban then unban
    if update.message.reply_to_message:
        target = update.message.reply_to_message.from_user
    elif context.args:
        try:
            target = await context.application.bot.get_chat_member(update.effective_chat.id, int(context.args[0]))
            target = target.user
        except Exception:
            return await update.message.reply_text("Specify user id or reply to a user.")
    else:
        return await update.message.reply_text("Reply to user to kick.")
    try:
        await context.application.bot.ban_chat_member(update.effective_chat.id, target.id)
        await context.application.bot.unban_chat_member(update.effective_chat.id, target.id)
        await update.message.reply_text(f"Kicked {target.mention_html()}", parse_mode=ParseMode.HTML)
    except Exception as e:
        log.exception(e)
        await update.message.reply_text("Failed to kick.")

@require_admin
async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = None
    minutes = None
    if update.message.reply_to_message:
        target = update.message.reply_to_message.from_user
        if context.args:
            try:
                minutes = int(context.args[0])
            except:
                minutes = None
    else:
        return await update.message.reply_text("Reply to a user to mute.")
    until = None
    if minutes:
        until = datetime.utcnow() + timedelta(minutes=minutes)
    success = await restrict_user(context.application, update.effective_chat.id, target.id, can_send=False, until_ts=None if not until else int(until.timestamp()))
    if success:
        if minutes:
            await update.message.reply_text(f"Muted {target.mention_html()} for {minutes} minutes.", parse_mode=ParseMode.HTML)
            # store mute
            DB.cursor().execute("INSERT INTO muted (chat_id,user_id,until_ts) VALUES (?,?,?)", (update.effective_chat.id, target.id, until.isoformat()))
            DB.commit()
        else:
            await update.message.reply_text(f"Muted {target.mention_html()}", parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text("Failed to mute. Check bot permissions.")

@require_admin
async def unmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.reply_to_message:
        target = update.message.reply_to_message.from_user
    elif context.args:
        try:
            target_id = int(context.args[0])
            target = await context.application.bot.get_chat_member(update.effective_chat.id, target_id)
            target = target.user
        except:
            return await update.message.reply_text("Specify user id or reply to a user.")
    else:
        return await update.message.reply_text("Reply to a user to unmute.")
    success = await restrict_user(context.application, update.effective_chat.id, target.id, can_send=True)
    if success:
        await update.message.reply_text(f"Unmuted {target.mention_html()}", parse_mode=ParseMode.HTML)
        DB.cursor().execute("DELETE FROM muted WHERE chat_id=? AND user_id=?", (update.effective_chat.id, target.id))
        DB.commit()
    else:
        await update.message.reply_text("Failed to unmute.")

@require_admin
async def tempmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # usage: /tempmute <minutes> (reply to user)
    if not update.message.reply_to_message:
        return await update.message.reply_text("Reply to a user to tempmute and give minutes.")
    try:
        minutes = int(context.args[0])
    except:
        return await update.message.reply_text("Provide minutes as integer: /tempmute 10")
    target = update.message.reply_to_message.from_user
    until = datetime.utcnow() + timedelta(minutes=minutes)
    ok = await restrict_user(context.application, update.effective_chat.id, target.id, can_send=False, until_ts=int(until.timestamp()))
    if ok:
        DB.cursor().execute("INSERT INTO muted (chat_id,user_id,until_ts) VALUES (?,?,?)", (update.effective_chat.id, target.id, until.isoformat()))
        DB.commit()
        await update.message.reply_text(f"Tempmuted {target.mention_html()} for {minutes} minutes.", parse_mode=ParseMode.HTML)
        # schedule unmute in background (best-effort)
        async def _unmute_later():
            await asyncio.sleep(minutes * 60)
            try:
                await restrict_user(context.application, update.effective_chat.id, target.id, can_send=True)
                DB.cursor().execute("DELETE FROM muted WHERE chat_id=? AND user_id=?", (update.effective_chat.id, target.id))
                DB.commit()
            except Exception:
                pass
        asyncio.create_task(_unmute_later())
    else:
        await update.message.reply_text("Failed to tempmute.")

@require_admin
async def warn_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.reply_to_message:
        target = update.message.reply_to_message.from_user
    else:
        return await update.message.reply_text("Reply to a user to warn.")
    reason = " ".join(context.args) if context.args else "No reason"
    add_warning(update.effective_chat.id, target.id, update.effective_user.id, reason)
    await update.message.reply_text(f"{target.mention_html()} warned. Reason: {reason}", parse_mode=ParseMode.HTML)

@require_admin
async def warnings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = None
    if update.message.reply_to_message:
        target = update.message.reply_to_message.from_user
    elif context.args:
        try:
            target_id = int(context.args[0])
            target = await context.application.bot.get_chat_member(update.effective_chat.id, target_id)
            target = target.user
        except:
            return await update.message.reply_text("Reply to a user or give user_id.")
    else:
        return await update.message.reply_text("Reply to a user to show warnings.")
    rows = get_warnings(update.effective_chat.id, target.id)
    if not rows:
        return await update.message.reply_text("No warnings for that user.")
    text = f"Warnings for {target.mention_html()}:\n"
    for r in rows:
        text += f"- {r[2]} (by {r[1]} at {r[3]})\n"
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

@require_admin
async def purge_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # /purge n  -> deletes last n recent tracked messages (best-effort)
    if not context.args:
        return await update.message.reply_text("Usage: /purge <n>")
    try:
        n = int(context.args[0])
    except:
        return await update.message.reply_text("Provide an integer.")
    ids = get_recent_message_ids(update.effective_chat.id, n)
    deleted = 0
    for mid in ids:
        try:
            await context.application.bot.delete_message(update.effective_chat.id, mid)
            deleted += 1
        except:
            pass
    await update.message.reply_text(f"Attempted to delete {deleted} messages.")

@require_admin
async def pin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        return await update.message.reply_text("Reply to a message to pin.")
    try:
        await context.application.bot.pin_chat_message(update.effective_chat.id, update.message.reply_to_message.message_id)
        await update.message.reply_text("Pinned.")
    except Exception:
        await update.message.reply_text("Failed to pin. Check bot rights.")

@require_admin
async def unpin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await context.application.bot.unpin_all_chat_messages(update.effective_chat.id)
        await update.message.reply_text("Unpinned all messages.")
    except Exception:
        await update.message.reply_text("Failed to unpin.")

@require_admin
async def promote_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        return await update.message.reply_text("Reply to a user to promote.")
    target = update.message.reply_to_message.from_user
    ok = await promote_user(context.application, update.effective_chat.id, target.id, can_change_info=True, can_delete_messages=True, can_pin_messages=True, can_invite_users=True)
    if ok:
        await update.message.reply_text(f"Promoted {target.mention_html()}", parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text("Failed to promote.")

@require_admin
async def demote_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        return await update.message.reply_text("Reply to a user to demote.")
    target = update.message.reply_to_message.from_user
    try:
        await context.application.bot.promote_chat_member(
            update.effective_chat.id,
            target.id,
            can_change_info=False,
            can_delete_messages=False,
            can_invite_users=False,
            can_pin_messages=False,
            is_anonymous=False,
        )
        await update.message.reply_text(f"Demoted {target.mention_html()}", parse_mode=ParseMode.HTML)
    except Exception:
        await update.message.reply_text("Failed to demote.")

@require_admin
async def lock_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # disallow sending messages for all non-admins
    perms = ChatPermissions(can_send_messages=False)
    try:
        await context.application.bot.set_chat_permissions(update.effective_chat.id, perms)
        await update.message.reply_text("Chat locked: non-admins cannot send messages.")
    except Exception:
        await update.message.reply_text("Failed to lock chat.")

@require_admin
async def unlock_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    perms = ChatPermissions(can_send_messages=True, can_send_media_messages=True, can_send_other_messages=True, can_send_polls=True)
    try:
        await context.application.bot.set_chat_permissions(update.effective_chat.id, perms)
        await update.message.reply_text("Chat unlocked.")
    except Exception:
        await update.message.reply_text("Failed to unlock chat.")

@require_admin
async def setrules_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = " ".join(context.args)
    if not text and update.message.reply_to_message:
        text = update.message.reply_to_message.text or ""
    if not text:
        return await update.message.reply_text("Usage: /setrules <text> or reply to a message with /setrules")
    set_rules(update.effective_chat.id, text)
    await update.message.reply_text("Rules saved.")

async def rules_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = get_rules(update.effective_chat.id)
    if not text:
        return await update.message.reply_text("No rules set.")
    await update.message.reply_text(f"Rules:\n{text}")

async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    c = DB.cursor()
    c.execute("SELECT COUNT(*) FROM warnings")
    warnings_count = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM thala_counts")
    thala_rows = c.fetchone()[0]
    await update.message.reply_text(f"Warnings total: {warnings_count}\nThala rows: {thala_rows}")

@require_admin
async def clearcache_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # clear recent_messages
    DB.cursor().execute("DELETE FROM recent_messages WHERE chat_id=?", (update.effective_chat.id,))
    DB.commit()
    await update.message.reply_text("Recent message cache cleared.")

# ---------- Message handler ----------
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg:
        return
    chat = update.effective_chat
    user = update.effective_user

    # store recent messages for purge feature
    try:
        add_recent_message(chat.id, msg.message_id, user.id)
    except Exception:
        pass

    # check for "thala" occurrence (word match)
    text = (msg.text or "") + " " + " ".join([e.url for e in (msg.entities or []) if e.type == MessageEntity.URL])
    if "thala" in (text or "").lower():
        # exempt admins
        if await user_is_admin(context.application, chat.id, user.id):
            return
        new_count = thala_inc(chat.id, user.id)
        if new_count > THALA_LIMIT_PER_DAY:
            # delete the message and notify
            try:
                await context.application.bot.delete_message(chat.id, msg.message_id)
            except Exception:
                pass
            try:
                await msg.reply_text(f"You thala limit has reached! (limit {THALA_LIMIT_PER_DAY}/day)")
            except Exception:
                pass
            return

# ---------- Error handler ----------
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    log.exception("Exception while handling an update: %s", context.error)

# ---------- main ----------
def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("ban", ban))
    app.add_handler(CommandHandler("unban", unban))
    app.add_handler(CommandHandler("kick", kick))
    app.add_handler(CommandHandler("mute", mute))
    app.add_handler(CommandHandler("unmute", unmute))
    app.add_handler(CommandHandler("tempmute", tempmute))
    app.add_handler(CommandHandler("warn", warn_cmd))
    app.add_handler(CommandHandler("warnings", warnings_cmd))
    app.add_handler(CommandHandler("purge", purge_cmd))
    app.add_handler(CommandHandler("pin", pin_cmd))
    app.add_handler(CommandHandler("unpin", unpin_cmd))
    app.add_handler(CommandHandler("promote", promote_cmd))
    app.add_handler(CommandHandler("demote", demote_cmd))
    app.add_handler(CommandHandler("lock", lock_cmd))
    app.add_handler(CommandHandler("unlock", unlock_cmd))
    app.add_handler(CommandHandler("setrules", setrules_cmd))
    app.add_handler(CommandHandler("rules", rules_cmd))
    app.add_handler(CommandHandler("stats", stats_cmd))
    app.add_handler(CommandHandler("clearcache", clearcache_cmd))

    # message handler (track messages, enforce thala)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    app.add_error_handler(error_handler)

    log.info("Starting bot long-polling")
    app.run_polling(allowed_updates=None)  # long polling

if __name__ == "__main__":
    main()
