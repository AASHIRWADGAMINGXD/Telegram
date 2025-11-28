# main.py
import os
import logging
import sqlite3
import threading
import time
from datetime import datetime, timedelta

from flask import Flask, jsonify
from telegram import Bot, Update, ChatPermissions, ParseMode
from telegram.ext import (
    Updater, CommandHandler, MessageHandler, Filters, CallbackContext, Dispatcher,
)

# ---------- Configuration ----------
TOKEN = os.getenv("BOT_TOKEN")  # set on Render as an env var
OWNER_ID = int(os.getenv("OWNER_ID", "0"))  # optional owner id
DATABASE = os.getenv("DB_PATH", "bot.db")
PORT = int(os.getenv("PORT", "8000"))

# ---------- Logging ----------
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ---------- Database ----------
def init_db():
    conn = sqlite3.connect(DATABASE, check_same_thread=False)
    cur = conn.cursor()
    cur.execute('''
    CREATE TABLE IF NOT EXISTS settings(
        chat_id INTEGER PRIMARY KEY,
        welcome TEXT,
        rules TEXT,
        log_chat TEXT
    )''')
    cur.execute('''
    CREATE TABLE IF NOT EXISTS warns(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER,
        user_id INTEGER,
        username TEXT,
        reason TEXT,
        ts INTEGER
    )''')
    cur.execute('''
    CREATE TABLE IF NOT EXISTS logs(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER,
        actor_id INTEGER,
        action TEXT,
        target_id INTEGER,
        reason TEXT,
        ts INTEGER
    )''')
    conn.commit()
    return conn

db = init_db()
db_lock = threading.Lock()

# ---------- Helper DB functions ----------
def set_setting(chat_id, key, value):
    with db_lock:
        cur = db.cursor()
        cur.execute("INSERT OR IGNORE INTO settings(chat_id, welcome, rules, log_chat) VALUES(?,?,?,?)", (chat_id, None, None, None))
        if key == "welcome":
            cur.execute("UPDATE settings SET welcome=? WHERE chat_id=?", (value, chat_id))
        elif key == "rules":
            cur.execute("UPDATE settings SET rules=? WHERE chat_id=?", (value, chat_id))
        elif key == "log_chat":
            cur.execute("UPDATE settings SET log_chat=? WHERE chat_id=?", (value, chat_id))
        db.commit()

def get_setting(chat_id):
    with db_lock:
        cur = db.cursor()
        cur.execute("SELECT welcome, rules, log_chat FROM settings WHERE chat_id=?", (chat_id,))
        row = cur.fetchone()
        return row if row else (None, None, None)

def add_warn(chat_id, user_id, username, reason):
    with db_lock:
        cur = db.cursor()
        cur.execute("INSERT INTO warns(chat_id, user_id, username, reason, ts) VALUES(?,?,?,?,?)",
                    (chat_id, user_id, username or "", reason or "", int(time.time())))
        db.commit()

def get_warns(chat_id, user_id):
    with db_lock:
        cur = db.cursor()
        cur.execute("SELECT id, reason, ts FROM warns WHERE chat_id=? AND user_id=?", (chat_id, user_id))
        return cur.fetchall()

def clear_warns(chat_id, user_id):
    with db_lock:
        cur = db.cursor()
        cur.execute("DELETE FROM warns WHERE chat_id=? AND user_id=?", (chat_id, user_id))
        db.commit()

def add_log(chat_id, actor_id, action, target_id=None, reason=None):
    with db_lock:
        cur = db.cursor()
        cur.execute("INSERT INTO logs(chat_id, actor_id, action, target_id, reason, ts) VALUES(?,?,?,?,?,?)",
                    (chat_id, actor_id, action, target_id or 0, reason or "", int(time.time())))
        db.commit()

def get_logs(chat_id, limit=10):
    with db_lock:
        cur = db.cursor()
        cur.execute("SELECT actor_id, action, target_id, reason, ts FROM logs WHERE chat_id=? ORDER BY id DESC LIMIT ?",
                    (chat_id, limit))
        return cur.fetchall()

# ---------- Permissions helpers ----------
def is_user_admin(bot: Bot, chat_id: int, user_id: int):
    try:
        member = bot.get_chat_member(chat_id, user_id)
        return member.status in ("administrator", "creator")
    except Exception:
        return False

def require_admin(fn):
    def wrapper(update: Update, context: CallbackContext):
        chat = update.effective_chat
        user = update.effective_user
        if chat.type == "private":
            # allow in private only owner
            if OWNER_ID and user.id != OWNER_ID:
                update.message.reply_text("You must be the owner to use this in private.")
                return
        else:
            if not is_user_admin(context.bot, chat.id, user.id):
                update.message.reply_text("You must be an admin to use this command.")
                return
        return fn(update, context)
    wrapper.__name__ = fn.__name__
    return wrapper

# ---------- Telegram handlers ----------
def start(update: Update, context: CallbackContext):
    update.message.reply_text("Hello! I'm ModerationBot. Use /help to see commands.")

def help_cmd(update: Update, context: CallbackContext):
    txt = (
        "Moderation commands:\n"
        "/help - this message\n"
        "/ping - bot latency\n"
        "/setwelcome <text> - set welcome message (admin)\n"
        "/delwelcome - delete welcome\n"
        "/setrules <text> - set group rules\n"
        "/showrules - show rules\n"
        "/warn @user [reason] - add a warning (admin)\n"
        "/warnings @user - list warnings\n"
        "/clearwarns @user - clear warnings (admin)\n"
        "/mute @user [reason] - mute user (admin)\n"
        "/unmute @user - unmute (admin)\n"
        "/tempmute @user <minutes> - temp mute\n"
        "/ban @user [reason] - ban user (admin)\n"
        "/unban user_id - unban (admin)\n"
        "/tempban @user <minutes> - temporary ban\n"
        "/kick @user - kick user\n"
        "/promote @user - promote to admin (bot must be admin)\n"
        "/demote @user - demote admin\n"
        "/pin - pin replied message (admin)\n"
        "/unpin - unpin\n"
        "/purge <N> - delete last N messages (admin)\n"
        "/setlog <chat_id|@channel> - set log chat (admin)\n"
        "/logs [n] - show last logs\n"
        "/restrict @user - restrict user (admin)\n"
        "/allow @user - restore permissions (admin)\n"
        "/report @user [reason] - report a user\n"
        "/clean - delete bot messages in reply range\n    "
    )
    update.message.reply_text(txt)

def ping(update: Update, context: CallbackContext):
    start = time.time()
    msg = update.message.reply_text("Pinging...")
    latency = (time.time() - start) * 1000
    msg.edit_text(f"Pong! {int(latency)} ms")

def save_welcome(update: Update, context: CallbackContext):
    if update.effective_chat.type == "private":
        update.message.reply_text("Welcome messages only make sense in groups.")
        return
    if not context.args:
        update.message.reply_text("Usage: /setwelcome Welcome text with {first} or {name}")
        return
    text = ' '.join(context.args)
    set_setting(update.effective_chat.id, "welcome", text)
    update.message.reply_text("Welcome message saved.")
    add_log(update.effective_chat.id, update.effective_user.id, "set_welcome", None, text)

def del_welcome(update: Update, context: CallbackContext):
    set_setting(update.effective_chat.id, "welcome", None)
    update.message.reply_text("Welcome message deleted.")
    add_log(update.effective_chat.id, update.effective_user.id, "del_welcome")

def set_rules(update: Update, context: CallbackContext):
    if not context.args:
        update.message.reply_text("Usage: /setrules <text>")
        return
    text = ' '.join(context.args)
    set_setting(update.effective_chat.id, "rules", text)
    update.message.reply_text("Rules saved.")
    add_log(update.effective_chat.id, update.effective_user.id, "set_rules", None, text)

def show_rules(update: Update, context: CallbackContext):
    welcome, rules, log_chat = get_setting(update.effective_chat.id)
    if rules:
        update.message.reply_text(rules)
    else:
        update.message.reply_text("No rules set. Use /setrules <text>")

def new_member_welcome(update: Update, context: CallbackContext):
    welcome, rules, log_chat = get_setting(update.effective_chat.id)
    for m in update.message.new_chat_members:
        name = m.full_name
        text = welcome or f"Welcome, {name}!"
        text = text.replace("{first}", m.first_name or "").replace("{name}", name)
        update.message.reply_text(text)
        add_log(update.effective_chat.id, context.bot.id, "welcome", m.id, text)

# ---------- warnings & report ----------
@require_admin
def warn_user(update: Update, context: CallbackContext):
    if not update.message.reply_to_message and not context.args:
        update.message.reply_text("Reply to a user or use /warn @user [reason]")
        return
    target = None
    reason = None
    if update.message.reply_to_message:
        target = update.message.reply_to_message.from_user
        reason = ' '.join(context.args) if context.args else ""
    else:
        # parse args for username
        if len(context.args) >= 1:
            username = context.args[0]
            reason = ' '.join(context.args[1:]) if len(context.args) > 1 else ""
            try:
                target = context.bot.get_chat_member(update.effective_chat.id, username).user
            except Exception:
                update.message.reply_text("Couldn't find that user. Reply to them instead or pass their id.")
                return
    add_warn(update.effective_chat.id, target.id, target.username, reason)
    update.message.reply_text(f"{target.full_name} has been warned. Reason: {reason}")
    add_log(update.effective_chat.id, update.effective_user.id, "warn", target.id, reason)

def warnings_cmd(update: Update, context: CallbackContext):
    target = None
    if update.message.reply_to_message:
        target = update.message.reply_to_message.from_user
    elif context.args:
        try:
            target = context.bot.get_chat(context.args[0])
        except Exception:
            update.message.reply_text("Usage: reply to user or /warnings <user_id>")
            return
    else:
        update.message.reply_text("Reply to a user to see warnings.")
        return
    rows = get_warns(update.effective_chat.id, target.id)
    if not rows:
        update.message.reply_text("No warnings.")
        return
    msg = f"Warnings for {target.full_name}:\n"
    for r in rows:
        ts = datetime.fromtimestamp(r[2]).strftime("%Y-%m-%d %H:%M")
        msg += f"- {r[1]} (at {ts})\n"
    update.message.reply_text(msg)

@require_admin
def clear_warnings_cmd(update: Update, context: CallbackContext):
    target = None
    if update.message.reply_to_message:
        target = update.message.reply_to_message.from_user
    elif context.args:
        target_id = int(context.args[0])
        target = context.bot.get_chat_member(update.effective_chat.id, target_id).user
    else:
        update.message.reply_text("Reply to a user to clear warnings.")
        return
    clear_warns(update.effective_chat.id, target.id)
    update.message.reply_text(f"Warnings cleared for {target.full_name}.")
    add_log(update.effective_chat.id, update.effective_user.id, "clear_warns", target.id)

# ---------- mute/unmute/tempmute ----------
@require_admin
def mute_cmd(update: Update, context: CallbackContext):
    if not update.message.reply_to_message:
        update.message.reply_text("Reply to the user you want to mute.")
        return
    target = update.message.reply_to_message.from_user
    try:
        perms = ChatPermissions(can_send_messages=False)
        context.bot.restrict_chat_member(update.effective_chat.id, target.id, perms)
        update.message.reply_text(f"{target.full_name} muted.")
        add_log(update.effective_chat.id, update.effective_user.id, "mute", target.id)
    except Exception as e:
        update.message.reply_text("Failed to mute: " + str(e))

@require_admin
def unmute_cmd(update: Update, context: CallbackContext):
    if not update.message.reply_to_message:
        update.message.reply_text("Reply to the user you want to unmute.")
        return
    target = update.message.reply_to_message.from_user
    try:
        perms = ChatPermissions(
            can_send_messages=True, can_send_media_messages=True,
            can_send_other_messages=True, can_add_web_page_previews=True
        )
        context.bot.restrict_chat_member(update.effective_chat.id, target.id, perms)
        update.message.reply_text(f"{target.full_name} unmuted.")
        add_log(update.effective_chat.id, update.effective_user.id, "unmute", target.id)
    except Exception as e:
        update.message.reply_text("Failed to unmute: " + str(e))

@require_admin
def tempmute_cmd(update: Update, context: CallbackContext):
    if not update.message.reply_to_message or len(context.args) < 1:
        update.message.reply_text("Usage: reply to user and /tempmute <minutes>")
        return
    minutes = int(context.args[0])
    target = update.message.reply_to_message.from_user
    until = datetime.utcnow() + timedelta(minutes=minutes)
    perms = ChatPermissions(can_send_messages=False)
    try:
        context.bot.restrict_chat_member(update.effective_chat.id, target.id, perms, until_date=until)
        update.message.reply_text(f"{target.full_name} muted for {minutes} minutes.")
        add_log(update.effective_chat.id, update.effective_user.id, "tempmute", target.id, f"{minutes}m")
    except Exception as e:
        update.message.reply_text("Failed to tempmute: " + str(e))

# ---------- ban/unban/tempban/kick ----------
@require_admin
def ban_cmd(update: Update, context: CallbackContext):
    if not update.message.reply_to_message:
        update.message.reply_text("Reply to the user you want to ban.")
        return
    target = update.message.reply_to_message.from_user
    reason = ' '.join(context.args) if context.args else None
    try:
        context.bot.kick_chat_member(update.effective_chat.id, target.id)
        update.message.reply_text(f"{target.full_name} banned.")
        add_log(update.effective_chat.id, update.effective_user.id, "ban", target.id, reason)
    except Exception as e:
        update.message.reply_text("Failed to ban: " + str(e))

@require_admin
def unban_cmd(update: Update, context: CallbackContext):
    if not context.args:
        update.message.reply_text("Usage: /unban <user_id>")
        return
    uid = int(context.args[0])
    try:
        context.bot.unban_chat_member(update.effective_chat.id, uid)
        update.message.reply_text(f"User {uid} unbanned.")
        add_log(update.effective_chat.id, update.effective_user.id, "unban", uid)
    except Exception as e:
        update.message.reply_text("Failed to unban: " + str(e))

@require_admin
def tempban_cmd(update: Update, context: CallbackContext):
    if not update.message.reply_to_message or len(context.args) < 1:
        update.message.reply_text("Usage: reply + /tempban <minutes>")
        return
    minutes = int(context.args[0])
    target = update.message.reply_to_message.from_user
    until = datetime.utcnow() + timedelta(minutes=minutes)
    try:
        context.bot.kick_chat_member(update.effective_chat.id, target.id, until_date=until)
        update.message.reply_text(f"{target.full_name} banned for {minutes} minutes.")
        add_log(update.effective_chat.id, update.effective_user.id, "tempban", target.id, f"{minutes}m")
    except Exception as e:
        update.message.reply_text("Failed to tempban: " + str(e))

@require_admin
def kick_cmd(update: Update, context: CallbackContext):
    if not update.message.reply_to_message:
        update.message.reply_text("Reply to the user to kick.")
        return
    target = update.message.reply_to_message.from_user
    try:
        context.bot.kick_chat_member(update.effective_chat.id, target.id)
        context.bot.unban_chat_member(update.effective_chat.id, target.id)  # so it's a kick not ban
        update.message.reply_text(f"{target.full_name} kicked.")
        add_log(update.effective_chat.id, update.effective_user.id, "kick", target.id)
    except Exception as e:
        update.message.reply_text("Failed to kick: " + str(e))

# ---------- promote/demote ----------
@require_admin
def promote_cmd(update: Update, context: CallbackContext):
    if not update.message.reply_to_message:
        update.message.reply_text("Reply to the user you want to promote.")
        return
    target = update.message.reply_to_message.from_user
    try:
        context.bot.promote_chat_member(update.effective_chat.id, target.id,
                                       can_change_info=True, can_delete_messages=True,
                                       can_invite_users=True, can_restrict_members=True,
                                       can_pin_messages=True, can_promote_members=False)
        update.message.reply_text(f"{target.full_name} promoted to admin (limited).")
        add_log(update.effective_chat.id, update.effective_user.id, "promote", target.id)
    except Exception as e:
        update.message.reply_text("Failed to promote: " + str(e))

@require_admin
def demote_cmd(update: Update, context: CallbackContext):
    if not update.message.reply_to_message:
        update.message.reply_text("Reply to the admin you want to demote.")
        return
    target = update.message.reply_to_message.from_user
    try:
        context.bot.promote_chat_member(update.effective_chat.id, target.id,
                                       can_change_info=False, can_delete_messages=False,
                                       can_invite_users=False, can_restrict_members=False,
                                       can_pin_messages=False, can_promote_members=False,
                                       is_anonymous=False)
        update.message.reply_text(f"{target.full_name} demoted.")
        add_log(update.effective_chat.id, update.effective_user.id, "demote", target.id)
    except Exception as e:
        update.message.reply_text("Failed to demote: " + str(e))

# ---------- pin/unpin/purge ----------
@require_admin
def pin_cmd(update: Update, context: CallbackContext):
    if not update.message.reply_to_message:
        update.message.reply_text("Reply to a message to pin it.")
        return
    try:
        context.bot.pin_chat_message(update.effective_chat.id, update.message.reply_to_message.message_id)
        update.message.reply_text("Message pinned.")
        add_log(update.effective_chat.id, update.effective_user.id, "pin", update.message.reply_to_message.from_user.id)
    except Exception as e:
        update.message.reply_text("Failed to pin: " + str(e))

@require_admin
def unpin_cmd(update: Update, context: CallbackContext):
    try:
        context.bot.unpin_chat_message(update.effective_chat.id)
        update.message.reply_text("Unpinned.")
        add_log(update.effective_chat.id, update.effective_user.id, "unpin")
    except Exception as e:
        update.message.reply_text("Failed to unpin: " + str(e))

@require_admin
def purge_cmd(update: Update, context: CallbackContext):
    if not context.args:
        update.message.reply_text("Usage: /purge <N>")
        return
    n = int(context.args[0])
    msgs = []
    for m in context.bot.get_chat(update.effective_chat.id).get_history(limit=n+1):
        try:
            context.bot.delete_message(update.effective_chat.id, m.message_id)
        except Exception:
            pass
    update.message.reply_text(f"Attempted to delete last {n} messages.")
    add_log(update.effective_chat.id, update.effective_user.id, "purge", None, f"{n} messages")

# ---------- logs / setlog ----------
@require_admin
def setlog_cmd(update: Update, context: CallbackContext):
    if not context.args:
        update.message.reply_text("Usage: /setlog <chat_id or @channel>")
        return
    target = context.args[0]
    set_setting(update.effective_chat.id, "log_chat", target)
    update.message.reply_text(f"Log channel set to {target}")
    add_log(update.effective_chat.id, update.effective_user.id, "set_log", None, target)

def logs_cmd(update: Update, context: CallbackContext):
    n = int(context.args[0]) if context.args else 10
    rows = get_logs(update.effective_chat.id, n)
    if not rows:
        update.message.reply_text("No logs.")
        return
    txt = "Last logs:\n"
    for r in rows:
        ts = datetime.fromtimestamp(r[4]).strftime("%Y-%m-%d %H:%M")
        txt += f"{r[1]} by {r[0]} -> target {r[2]} ({r[3]}) at {ts}\n"
    update.message.reply_text(txt)

# ---------- restrict / allow ----------
@require_admin
def restrict_cmd(update: Update, context: CallbackContext):
    if not update.message.reply_to_message:
        update.message.reply_text("Reply to user to restrict.")
        return
    target = update.message.reply_to_message.from_user
    perms = ChatPermissions(can_send_messages=False, can_send_media_messages=False, can_add_web_page_previews=False)
    try:
        context.bot.restrict_chat_member(update.effective_chat.id, target.id, perms)
        update.message.reply_text(f"{target.full_name} restricted.")
        add_log(update.effective_chat.id, update.effective_user.id, "restrict", target.id)
    except Exception as e:
        update.message.reply_text("Failed to restrict: " + str(e))

@require_admin
def allow_cmd(update: Update, context: CallbackContext):
    if not update.message.reply_to_message:
        update.message.reply_text("Reply to user to allow.")
        return
    target = update.message.reply_to_message.from_user
    perms = ChatPermissions(can_send_messages=True, can_send_media_messages=True, can_add_web_page_previews=True)
    try:
        context.bot.restrict_chat_member(update.effective_chat.id, target.id, perms)
        update.message.reply_text(f"{target.full_name} allowed.")
        add_log(update.effective_chat.id, update.effective_user.id, "allow", target.id)
    except Exception as e:
        update.message.reply_text("Failed to allow: " + str(e))

# ---------- report ----------
def report_cmd(update: Update, context: CallbackContext):
    if not update.message.reply_to_message:
        update.message.reply_text("Reply to the message of the user you want to report, or use /report @user reason")
        return
    target = update.message.reply_to_message.from_user
    reason = ' '.join(context.args) if context.args else "Reported via reply"
    add_log(update.effective_chat.id, update.effective_user.id, "report", target.id, reason)
    update.message.reply_text("Report submitted to admins.")
    # Optionally notify log chat
    welcome, rules, log_chat = get_setting(update.effective_chat.id)
    if log_chat:
        try:
            context.bot.send_message(log_chat, f"Report in {update.effective_chat.title}: {update.effective_user.full_name} reported {target.full_name}: {reason}")
        except Exception:
            pass

# ---------- clean bot messages ----------
@require_admin
def clean_cmd(update: Update, context: CallbackContext):
    if not update.message.reply_to_message:
        update.message.reply_text("Reply to a bot message or the start of range to clean.")
        return
    start_id = update.message.reply_to_message.message_id
    cur_id = update.message.message_id
    deleted = 0
    for mid in range(start_id, cur_id + 1):
        try:
            context.bot.delete_message(update.effective_chat.id, mid)
            deleted += 1
        except Exception:
            pass
    update.message.reply_text(f"Deleted up to {deleted} messages (some may be protected).")
    add_log(update.effective_chat.id, update.effective_user.id, "clean", None, f"deleted {deleted}")

# ---------- Handlers registration ----------
def run_bot():
    updater = Updater(TOKEN, use_context=True)
    dp: Dispatcher = updater.dispatcher

    # basic
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("help", help_cmd))
    dp.add_handler(CommandHandler("ping", ping))

    # settings
    dp.add_handler(CommandHandler("setwelcome", save_welcome))
    dp.add_handler(CommandHandler("delwelcome", del_welcome))
    dp.add_handler(CommandHandler("setrules", set_rules))
    dp.add_handler(CommandHandler("showrules", show_rules))
    dp.add_handler(MessageHandler(Filters.status_update.new_chat_members, new_member_welcome))

    # warnings
    dp.add_handler(CommandHandler("warn", warn_user))
    dp.add_handler(CommandHandler("warnings", warnings_cmd))
    dp.add_handler(CommandHandler("clearwarns", clear_warnings_cmd))

    # mute/ban/etc
    dp.add_handler(CommandHandler("mute", mute_cmd))
    dp.add_handler(CommandHandler("unmute", unmute_cmd))
    dp.add_handler(CommandHandler("tempmute", tempmute_cmd))
    dp.add_handler(CommandHandler("ban", ban_cmd))
    dp.add_handler(CommandHandler("unban", unban_cmd))
    dp.add_handler(CommandHandler("tempban", tempban_cmd))
    dp.add_handler(CommandHandler("kick", kick_cmd))

    # admin management
    dp.add_handler(CommandHandler("promote", promote_cmd))
    dp.add_handler(CommandHandler("demote", demote_cmd))

    # pin/purge
    dp.add_handler(CommandHandler("pin", pin_cmd))
    dp.add_handler(CommandHandler("unpin", unpin_cmd))
    dp.add_handler(CommandHandler("purge", purge_cmd))

    # logs
    dp.add_handler(CommandHandler("setlog", setlog_cmd))
    dp.add_handler(CommandHandler("logs", logs_cmd))

    # restrict
    dp.add_handler(CommandHandler("restrict", restrict_cmd))
    dp.add_handler(CommandHandler("allow", allow_cmd))

    # report
    dp.add_handler(CommandHandler("report", report_cmd))

    # cleaning
    dp.add_handler(CommandHandler("clean", clean_cmd))

    # start polling
    logger.info("Starting bot polling thread...")
    updater.start_polling()
    updater.idle()

# ---------- Flask keep-alive ----------
app = Flask(__name__)

@app.route("/")
def index():
    return jsonify({"status": "ok", "time": datetime.utcnow().isoformat()})

@app.route("/health")
def health():
    return jsonify({"status": "healthy"})

# start bot in background thread when module starts
def start_background():
    t = threading.Thread(target=run_bot, daemon=True)
    t.start()

if __name__ == "__main__":
    if not TOKEN:
        raise RuntimeError("BOT_TOKEN environment variable missing.")
    start_background()
    # run flask
    app.run(host="0.0.0.0", port=PORT)
