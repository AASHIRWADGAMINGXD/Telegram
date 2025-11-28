# file: bot.py
import asyncio
import sqlite3
import time
from datetime import datetime, timedelta
import re
from aiohttp import web  # lightweight async web server for status page
from telegram import ChatPermissions, Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, filters

API_TOKEN = "YOUR_BOT_TOKEN"
DB = "bot.db"
WARN_THRESHOLD = 3

# --- DB helpers ---
def init_db():
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS warns (
        chat_id INTEGER, user_id INTEGER, username TEXT, reason TEXT, ts INTEGER
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS mutes (
        chat_id INTEGER, user_id INTEGER, until_ts INTEGER
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS invites (
        chat_id INTEGER, link TEXT, expires_at INTEGER
    )""")
    con.commit()
    con.close()

def add_warn(chat_id, user_id, username, reason):
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.execute("INSERT INTO warns VALUES (?,?,?,?,?)",
                (chat_id, user_id, username, reason, int(time.time())))
    con.commit()
    con.close()

def get_warns(chat_id, user_id):
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.execute("SELECT COUNT(*) FROM warns WHERE chat_id=? AND user_id=?",
                (chat_id, user_id))
    (count,) = cur.fetchone()
    con.close()
    return count

def clear_warns(chat_id, user_id, count=None):
    con = sqlite3.connect(DB)
    cur = con.cursor()
    if count is None:
        cur.execute("DELETE FROM warns WHERE chat_id=? AND user_id=?",
                    (chat_id, user_id))
    else:
        # remove N oldest warnings
        cur.execute("""DELETE FROM warns WHERE rowid IN (
            SELECT rowid FROM warns WHERE chat_id=? AND user_id=? ORDER BY ts ASC LIMIT ?
        )""", (chat_id, user_id, count))
    con.commit()
    con.close()

def add_mute(chat_id, user_id, until_ts):
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.execute("REPLACE INTO mutes VALUES (?,?,?)", (chat_id, user_id, until_ts))
    con.commit(); con.close()

def remove_mute(chat_id, user_id):
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.execute("DELETE FROM mutes WHERE chat_id=? AND user_id=?", (chat_id, user_id))
    con.commit(); con.close()

def list_mutes_expired():
    now = int(time.time())
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.execute("SELECT chat_id, user_id FROM mutes WHERE until_ts <= ?", (now,))
    rows = cur.fetchall()
    con.close()
    return rows

# --- utils ---
def is_admin(update: Update, user_id: int):
    chat = update.effective_chat
    if chat is None: return False
    member = chat.get_member(user_id)
    return member.status in ("administrator", "creator")

def parse_duration(s: str) -> int:
    """Parse duration like '10m','2h','1d' -> seconds"""
    if not s:
        return None
    m = re.match(r"^(\d+)([smhd])$", s)
    if not m: return None
    val, unit = int(m.group(1)), m.group(2)
    if unit == "s": return val
    if unit == "m": return val*60
    if unit == "h": return val*3600
    if unit == "d": return val*86400

# --- command handlers ---
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hello — bot ready.")

async def clean_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # admin-only
    if not is_admin(update, update.effective_user.id):
        await update.message.reply_text("Only admins can use /clean.")
        return
    try:
        n = int(context.args[0]) if context.args else 50
    except ValueError:
        n = 50
    chat = update.effective_chat
    # fetch recent messages via get_chat_history not available — rely on message ids
    # We'll try deleting messages in a window: last n messages before command message
    msg_id = update.message.message_id
    deleted = 0
    for mid in range(msg_id-1, max(msg_id-n-1, msg_id-200), -1):
        try:
            await context.bot.delete_message(chat.id, mid)
            deleted += 1
        except Exception:
            pass
    await update.message.reply_text(f"Attempted to delete up to {n} messages. Deleted: {deleted}")

async def mute_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update, update.effective_user.id):
        await update.message.reply_text("Only admins can mute.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /mute @username 10m")
        return
    # target
    if update.message.reply_to_message:
        target = update.message.reply_to_message.from_user
    else:
        # try parse @username or id
        target = None
        if context.args:
            try:
                user_mention = context.args[0]
                if user_mention.startswith("@"):
                    members = await context.bot.get_chat_administrators(update.effective_chat.id)  # fallback
                # For brevity: require reply to message for reliable target
            except Exception:
                pass
    if not update.message.reply_to_message:
        await update.message.reply_text("Please reply to a user's message to mute them.")
        return
    target = update.message.reply_to_message.from_user
    dur = parse_duration(context.args[0]) if len(context.args) > 0 else None
    until = None
    if dur:
        until_ts = int(time.time()) + dur
        until = datetime.utcfromtimestamp(until_ts)
        add_mute(update.effective_chat.id, target.id, until_ts)
    else:
        until = None
        add_mute(update.effective_chat.id, target.id, 2147483647)
    perms = ChatPermissions(can_send_messages=False, can_send_media_messages=False,
                            can_send_polls=False, can_send_other_messages=False,
                            can_add_web_page_previews=False, can_change_info=False,
                            can_invite_users=False, can_pin_messages=False)
    try:
        await context.bot.restrict_chat_member(update.effective_chat.id, target.id, permissions=perms, until_date=until)
        await update.message.reply_text(f"Muted {target.mention_html()} for {context.args[0] if dur else 'indefinitely' }", parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text("Failed to mute: " + str(e))

async def unmute_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update, update.effective_user.id):
        await update.message.reply_text("Only admins can unmute.")
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("Reply to the user's message to unmute.")
        return
    target = update.message.reply_to_message.from_user
    perms = ChatPermissions(can_send_messages=True, can_send_media_messages=True,
                            can_send_polls=True, can_send_other_messages=True,
                            can_add_web_page_previews=True, can_change_info=False,
                            can_invite_users=True, can_pin_messages=False)
    try:
        remove_mute(update.effective_chat.id, target.id)
        await context.bot.restrict_chat_member(update.effective_chat.id, target.id, permissions=perms, until_date=None)
        await update.message.reply_text(f"Unmuted {target.mention_html()}", parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text("Failed to unmute: " + str(e))

async def warn_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update, update.effective_user.id):
        await update.message.reply_text("Only admins can warn.")
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("Reply to the user you want to warn.")
        return
    target = update.message.reply_to_message.from_user
    reason = " ".join(context.args) if context.args else "No reason provided"
    add_warn(update.effective_chat.id, target.id, target.username or target.full_name, reason)
    count = get_warns(update.effective_chat.id, target.id)
    await update.message.reply_text(f"{target.mention_html()} has been warned. Total warns: {count}", parse_mode="HTML")
    if count >= WARN_THRESHOLD:
        # auto-action: mute for 1 hour
        until_ts = int(time.time()) + 3600
        add_mute(update.effective_chat.id, target.id, until_ts)
        perms = ChatPermissions(can_send_messages=False, can_send_media_messages=False,
                                can_send_polls=False, can_send_other_messages=False,
                                can_add_web_page_previews=False)
        try:
            await context.bot.restrict_chat_member(update.effective_chat.id, target.id, permissions=perms, until_date=datetime.utcfromtimestamp(until_ts))
            await update.message.reply_text(f"{target.mention_html()} reached {WARN_THRESHOLD} warns — auto-muted 1h", parse_mode="HTML")
        except Exception:
            pass

async def unwarn_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update, update.effective_user.id):
        await update.message.reply_text("Only admins can unwarn.")
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("Reply to the user to unwarn.")
        return
    target = update.message.reply_to_message.from_user
    count = None
    if context.args and context.args[0].isdigit():
        count = int(context.args[0])
    clear_warns(update.effective_chat.id, target.id, count)
    await update.message.reply_text(f"Removed warns for {target.mention_html()}", parse_mode="HTML")

async def invite_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update, update.effective_user.id):
        await update.message.reply_text("Only admins can create invite links.")
        return
    # Usage: /invite 1h  or reply to user to invite them via link
    if not context.args:
        await update.message.reply_text("Usage: /invite <duration> e.g. /invite 2h")
        return
    dur = parse_duration(context.args[0])
    if dur is None:
        await update.message.reply_text("Invalid duration. Use s/m/h/d like '30m', '2h'.")
        return
    expire_dt = datetime.utcnow() + timedelta(seconds=dur)
    chat = update.effective_chat
    try:
        res = await context.bot.create_chat_invite_link(chat.id, expire_date=expire_dt, member_limit=1)
        link = res.invite_link
        con = sqlite3.connect(DB)
        cur = con.cursor()
        cur.execute("INSERT INTO invites VALUES (?,?,?)", (chat.id, link, int(expire_dt.timestamp())))
        con.commit(); con.close()
        await update.message.reply_text(f"Invite link (expires at {expire_dt.isoformat()} UTC):\n{link}")
    except Exception as e:
        await update.message.reply_text("Failed to create invite link: " + str(e))

# --- periodic task to lift expired mutes ---
async def expire_checker(app):
    while True:
        # check mutes that expired and unrestrict them
        rows = list_mutes_expired()
        for chat_id, user_id in rows:
            try:
                perms = ChatPermissions(can_send_messages=True, can_send_media_messages=True,
                                        can_send_polls=True, can_send_other_messages=True,
                                        can_add_web_page_previews=True)
                await app.bot.restrict_chat_member(chat_id, user_id, permissions=perms, until_date=None)
            except Exception:
                pass
            remove_mute(chat_id, user_id)
        await asyncio.sleep(30)

# --- small aiohttp webserver for keepalive render ---
async def status_handler(request):
    # basic status page: uptime, active chats, pending warns count
    # For demo: compute uptime from start_ts
    start_ts = request.app["start_ts"]
    uptime = int(time.time()) - start_ts
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.execute("SELECT COUNT(DISTINCT chat_id) FROM warns")
    (active_chats_warns,) = cur.fetchone()
    cur.execute("SELECT COUNT(*) FROM warns")
    (total_warns,) = cur.fetchone()
    cur.close(); con.close()
    html = f"""
    <html><body>
      <h2>Bot Status</h2>
      <p>Uptime: {uptime} seconds</p>
      <p>Chats with warns: {active_chats_warns}</p>
      <p>Total warns: {total_warns}</p>
      <p>Time: {datetime.utcnow().isoformat()} UTC</p>
    </body></html>
    """
    return web.Response(text=html, content_type="text/html")

async def run_webapp(app):
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8080)
    await site.start()

# --- main startup ---
async def main():
    init_db()
    app = ApplicationBuilder().token(API_TOKEN).build()

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("clean", clean_cmd))
    app.add_handler(CommandHandler("mute", mute_cmd))
    app.add_handler(CommandHandler("unmute", unmute_cmd))
    app.add_handler(CommandHandler("warn", warn_cmd))
    app.add_handler(CommandHandler("unwarn", unwarn_cmd))
    app.add_handler(CommandHandler("invite", invite_cmd))

    # start expire task
    app.create_task(expire_checker(app))

    # start tiny web server for status page (aiohttp)
    aio_app = web.Application()
    aio_app["start_ts"] = int(time.time())
    aio_app.router.add_get("/status", status_handler)
    app.create_task(run_webapp(aio_app))

    await app.run_polling()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
