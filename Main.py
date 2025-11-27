#!/usr/bin/env python3
"""
Telegram Moderator Bot (single-file)
- Uses python-telegram-bot v20+ (async)
- Persistent JSON store for: authorized users, warnings, mutes, bans, rules
- Password-based authorization (env var PASSWORD or /auth <password>)
- aiohttp keep-alive endpoint (for Render / uptime checks)
- Designed for group moderation; many commands require admin/owner authorization
"""

import os
import json
import asyncio
from pathlib import Path
from typing import Dict, Any, Set

from aiohttp import web

from telegram import Update, ChatPermissions, Message, ChatMember
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackContext,
)

# ---------- CONFIG ----------
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "<PUT_YOUR_TOKEN_HERE>")
PASSWORD = os.environ.get("BOT_PASSWORD", "Pain1")  # change before deploy!
DATA_FILE = Path("bot_data.json")
PORT = int(os.environ.get("PORT", "8443"))  # Render provides PORT env var
OWNER_ID = int(os.environ.get("OWNER_ID", "0"))  # optional owner override (int id)
# ----------------------------

# Default structure for persistent storage
DEFAULT_DATA = {
    "authorized": [],   # list of user ids allowed to run moderation commands
    "warnings": {},     # {chat_id: {user_id: [reason1, reason2, ...]}}
    "mutes": {},        # {chat_id: {user_id: unmute_timestamp_or_0_for_indefinite}}
    "bans": {},         # {chat_id: [user_id1, user_id2...]}
    "rules": {},        # {chat_id: "rules text"}
}

# ---------------- persistence helpers ----------------
def load_data() -> Dict[str, Any]:
    if DATA_FILE.exists():
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return DEFAULT_DATA.copy()
    else:
        return DEFAULT_DATA.copy()


def save_data(data: Dict[str, Any]):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


DATA = load_data()

def ensure_chat_structures(chat_id: str):
    chat_id = str(chat_id)
    if chat_id not in DATA.get("warnings", {}):
        DATA.setdefault("warnings", {})[chat_id] = {}
    if chat_id not in DATA.get("mutes", {}):
        DATA.setdefault("mutes", {})[chat_id] = {}
    if chat_id not in DATA.get("bans", {}):
        DATA.setdefault("bans", {})[chat_id] = []
    if chat_id not in DATA.get("rules", {}):
        DATA.setdefault("rules", {})[chat_id] = ""


# --------------- auth decorators ----------------
def is_authorized(user_id: int) -> bool:
    if OWNER_ID and user_id == OWNER_ID:
        return True
    return int(user_id) in [int(x) for x in DATA.get("authorized", [])]


def require_auth(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user = update.effective_user
        if user and is_authorized(user.id):
            return await func(update, context, *args, **kwargs)
        else:
            await update.message.reply_text("Unauthorized. Use /auth <password> to authenticate.")
    return wrapper


# ----------------- command handlers -----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = (
        "Moderator Bot online.\n"
        "This is a private moderation bot. To authenticate: /auth <password>\n"
        "Use /help_mod to see moderator commands (auth required)."
    )
    await update.message.reply_text(txt)


async def auth_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # /auth <password>
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /auth <password>")
        return
    provided = args[0]
    user_id = update.effective_user.id
    if provided == PASSWORD:
        if user_id not in DATA.get("authorized", []):
            DATA.setdefault("authorized", []).append(user_id)
            save_data(DATA)
        await update.message.reply_text("Authenticated ✅ — you can use moderation commands now.")
    else:
        await update.message.reply_text("Wrong password ❌")


async def unauth_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # /unauth - remove yourself
    user_id = update.effective_user.id
    if user_id in DATA.get("authorized", []):
        DATA["authorized"].remove(user_id)
        save_data(DATA)
        await update.message.reply_text("You have been deauthorized.")
    else:
        await update.message.reply_text("You were not authorized.")


# Show help for moderation commands
@require_auth
async def help_mod(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "Moderator commands:\n"
        "/ban <reply/user_id> [reason]\n"
        "/unban <user_id>\n"
        "/kick <reply>\n"
        "/mute <reply_or_id> [minutes]\n"
        "/unmute <reply_or_id>\n"
        "/warn <reply_or_id> [reason]\n"
        "/warnings <user_id or reply>\n"
        "/clear <n> - delete last n messages (admin only)\n"
        "/purge <user_id> - delete last 100 messages from a user\n"
        "/pin [reply]\n"
        "/unpin [message_id]\n"
        "/lock - restrict sending messages in group\n"
        "/unlock\n"
        "/setrules <text>\n"
        "/getrules\n"
        "/promote <reply>\n"
        "/demote <reply>\n"
        "/stats\n"
        "/setpassword <newpassword> (owner only if OWNER_ID set)\n"
        "/auth /unauth\n"
    )
    await update.message.reply_text(help_text)


# Helper: extract target user id from reply or args
def extract_target_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if msg.reply_to_message:
        return msg.reply_to_message.from_user.id
    if context.args:
        try:
            return int(context.args[0])
        except:
            return None
    return None


@require_auth
async def ban_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    target = extract_target_user(update, context)
    reason = " ".join(context.args[1:]) if len(context.args) > 1 else "No reason"
    if not target:
        await update.message.reply_text("Reply to a user or provide user_id to ban.")
        return
    try:
        await context.bot.ban_chat_member(chat.id, target)
        DATA.setdefault("bans", {}).setdefault(str(chat.id), [])
        if target not in DATA["bans"][str(chat.id)]:
            DATA["bans"][str(chat.id)].append(target)
            save_data(DATA)
        await update.message.reply_text(f"Banned {target}\nReason: {reason}")
    except Exception as e:
        await update.message.reply_text(f"Failed to ban: {e}")


@require_auth
async def unban_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /unban <user_id>")
        return
    try:
        user_id = int(context.args[0])
    except:
        await update.message.reply_text("Invalid user_id.")
        return
    chat = update.effective_chat
    try:
        await context.bot.unban_chat_member(chat.id, user_id)
        DATA.setdefault("bans", {}).setdefault(str(chat.id), [])
        if user_id in DATA["bans"][str(chat.id)]:
            DATA["bans"][str(chat.id)].remove(user_id)
            save_data(DATA)
        await update.message.reply_text(f"Unbanned {user_id}")
    except Exception as e:
        await update.message.reply_text(f"Failed to unban: {e}")


@require_auth
async def kick_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = extract_target_user(update, context)
    if not target:
        await update.message.reply_text("Reply to a user to kick.")
        return
    chat = update.effective_chat
    try:
        await context.bot.ban_chat_member(chat.id, target)
        await context.bot.unban_chat_member(chat.id, target)  # kick -> ban + unban
        await update.message.reply_text(f"Kicked {target}")
    except Exception as e:
        await update.message.reply_text(f"Failed to kick: {e}")


@require_auth
async def mute_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = extract_target_user(update, context)
    if not target:
        await update.message.reply_text("Reply to a user to mute.")
        return
    minutes = 0
    if context.args:
        try:
            minutes = int(context.args[-1])
        except:
            minutes = 0
    until_date = None
    if minutes > 0:
        until_date = int((asyncio.get_event_loop().time() + minutes * 60))
    chat = update.effective_chat
    try:
        await context.bot.restrict_chat_member(
            chat_id=chat.id,
            user_id=target,
            permissions=ChatPermissions(can_send_messages=False),
        )
        ensure_chat_structures(chat.id)
        DATA.setdefault("mutes", {}).setdefault(str(chat.id), {})[str(target)] = int(until_date or 0)
        save_data(DATA)
        msg = f"Muted {target}" + (f" for {minutes} minutes." if minutes else " indefinitely.")
        await update.message.reply_text(msg)
    except Exception as e:
        await update.message.reply_text(f"Failed to mute: {e}")


@require_auth
async def unmute_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = extract_target_user(update, context)
    if not target:
        await update.message.reply_text("Reply to a user to unmute.")
        return
    chat = update.effective_chat
    try:
        await context.bot.restrict_chat_member(
            chat_id=chat.id,
            user_id=target,
            permissions=ChatPermissions(
                can_send_messages=True, can_send_media_messages=True, can_send_other_messages=True
            ),
        )
        DATA.setdefault("mutes", {}).setdefault(str(chat.id), {})
        if str(target) in DATA["mutes"][str(chat.id)]:
            DATA["mutes"][str(chat.id)].pop(str(target), None)
            save_data(DATA)
        await update.message.reply_text(f"Unmuted {target}")
    except Exception as e:
        await update.message.reply_text(f"Failed to unmute: {e}")


@require_auth
async def warn_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = extract_target_user(update, context)
    if not target:
        await update.message.reply_text("Reply to a user to warn.")
        return
    reason = " ".join(context.args[1:]) if len(context.args) > 1 else "No reason"
    chat_id = str(update.effective_chat.id)
    ensure_chat_structures(chat_id)
    DATA.setdefault("warnings", {}).setdefault(chat_id, {}).setdefault(str(target), [])
    DATA["warnings"][chat_id][str(target)].append(reason)
    save_data(DATA)
    await update.message.reply_text(f"Warned {target}. Reason: {reason}")


@require_auth
async def warnings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = extract_target_user(update, context)
    if not target and context.args:
        try:
            target = int(context.args[0])
        except:
            await update.message.reply_text("Invalid user id.")
            return
    if not target:
        await update.message.reply_text("Reply to a user or provide user_id to list warnings.")
        return
    chat_id = str(update.effective_chat.id)
    ensure_chat_structures(chat_id)
    user_warns = DATA.get("warnings", {}).get(chat_id, {}).get(str(target), [])
    await update.message.reply_text(f"Warnings for {target}: {len(user_warns)}\n" + "\n".join(f"- {w}" for w in user_warns))


@require_auth
async def clear_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # /clear n  - delete last n messages (bot must be admin + can_delete_messages)
    if not context.args:
        await update.message.reply_text("Usage: /clear <n>")
        return
    try:
        n = int(context.args[0])
    except:
        await update.message.reply_text("Provide a number.")
        return
    chat = update.effective_chat
    msgs = []
    async for m in context.bot.get_chat(chat.id).iter_history(limit=n+1):  # +1 includes the command message
        msgs.append(m.message_id)
    for mid in msgs:
        try:
            await context.bot.delete_message(chat.id, mid)
        except:
            pass
    await update.message.reply_text(f"Attempted to delete {n} messages.")


@require_auth
async def purge_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Purge last 100 messages from a user_id
    target = extract_target_user(update, context)
    if not target:
        await update.message.reply_text("Reply to target user or provide user_id: /purge <user_id>")
        return
    chat = update.effective_chat
    count = 0
    async for m in context.bot.get_chat(chat.id).iter_history(limit=500):
        if m.from_user and m.from_user.id == target:
            try:
                await context.bot.delete_message(chat.id, m.message_id)
                count += 1
            except:
                pass
    await update.message.reply_text(f"Purged {count} messages from {target}.")


@require_auth
async def pin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if msg.reply_to_message:
        await context.bot.pin_chat_message(chat_id=msg.chat_id, message_id=msg.reply_to_message.message_id)
        await msg.reply_text("Pinned the message.")
    else:
        await msg.reply_text("Reply to a message to pin it.")


@require_auth
async def unpin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.unpin_all_chat_messages(chat_id=update.effective_chat.id)
    await update.message.reply_text("Unpinned all messages.")


@require_auth
async def lock_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    try:
        await context.bot.set_chat_permissions(chat.id, ChatPermissions(can_send_messages=False))
        await update.message.reply_text("Group locked: users cannot send messages.")
    except Exception as e:
        await update.message.reply_text(f"Failed to lock: {e}")


@require_auth
async def unlock_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    try:
        await context.bot.set_chat_permissions(chat.id, ChatPermissions(
            can_send_messages=True, can_send_media_messages=True, can_send_other_messages=True
        ))
        await update.message.reply_text("Group unlocked.")
    except Exception as e:
        await update.message.reply_text(f"Failed to unlock: {e}")


@require_auth
async def setrules_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /setrules <rules text>")
        return
    chat_id = str(update.effective_chat.id)
    DATA.setdefault("rules", {})[chat_id] = " ".join(context.args)
    save_data(DATA)
    await update.message.reply_text("Rules saved.")


async def getrules_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    text = DATA.get("rules", {}).get(chat_id) or "No rules set for this chat."
    await update.message.reply_text(text)


@require_auth
async def promote_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = extract_target_user(update, context)
    if not target:
        await update.message.reply_text("Reply to user to promote.")
        return
    try:
        await context.bot.promote_chat_member(
            chat_id=update.effective_chat.id,
            user_id=target,
            can_change_info=True,
            can_delete_messages=True,
            can_invite_users=True,
            can_manage_topics=True,
            can_restrict_members=True,
            can_pin_messages=True,
            can_promote_members=False,
        )
        await update.message.reply_text(f"Promoted {target}")
    except Exception as e:
        await update.message.reply_text(f"Failed to promote: {e}")


@require_auth
async def demote_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = extract_target_user(update, context)
    if not target:
        await update.message.reply_text("Reply to user to demote.")
        return
    try:
        await context.bot.promote_chat_member(
            chat_id=update.effective_chat.id,
            user_id=target,
            can_change_info=False,
            can_delete_messages=False,
            can_invite_users=False,
            can_manage_topics=False,
            can_restrict_members=False,
            can_pin_messages=False,
            can_promote_members=False,
        )
        await update.message.reply_text(f"Demoted {target}")
    except Exception as e:
        await update.message.reply_text(f"Failed to demote: {e}")


@require_auth
async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    warn_data = DATA.get("warnings", {}).get(chat_id, {})
    mute_data = DATA.get("mutes", {}).get(chat_id, {})
    ban_data = DATA.get("bans", {}).get(chat_id, [])
    txt = (
        f"Stats for chat {chat_id}:\n"
        f"Warned users: {len(warn_data)}\n"
        f"Muted users: {len(mute_data)}\n"
        f"Banned users: {len(ban_data)}"
    )
    await update.message.reply_text(txt)


@require_auth
async def setpassword_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Only owner can change password if OWNER_ID set
    user = update.effective_user
    if OWNER_ID and user.id != OWNER_ID:
        await update.message.reply_text("Only the owner can change the bot password.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /setpassword <newpassword>")
        return
    new = context.args[0]
    # Persisting password to environment is not possible from inside app; we save to DATA file (note: less secure)
    DATA.setdefault("meta", {})["password"] = new
    save_data(DATA)
    await update.message.reply_text("Password changed in persistent store. (Also set BOT_PASSWORD env var on your host.)")


# Simple echo-ignore handler to enforce mutes
async def message_monitor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # check mutes expired
    chat_id = str(update.effective_chat.id)
    ensure_chat_structures(chat_id)
    mute_map = DATA.get("mutes", {}).get(chat_id, {})
    to_unmute = []
    now = int(asyncio.get_event_loop().time())
    for uid_str, until in list(mute_map.items()):
        if until and now >= int(until):
            to_unmute.append(int(uid_str))
            mute_map.pop(uid_str, None)
    if to_unmute:
        save_data(DATA)
        for uid in to_unmute:
            try:
                await context.bot.restrict_chat_member(
                    chat_id=int(chat_id),
                    user_id=uid,
                    permissions=ChatPermissions(
                        can_send_messages=True,
                        can_send_media_messages=True,
                        can_send_other_messages=True
                    )
                )
            except:
                pass

    # auto-delete messages from muted users (best-effort)
    if update.message and update.message.from_user:
        user_id = update.message.from_user.id
        if str(user_id) in DATA.get("mutes", {}).get(chat_id, {}):
            try:
                await update.message.delete()
            except:
                pass


# --------------- keep-alive (aiohttp) ----------------
async def run_keep_alive(app):
    async def index(request):
        return web.Response(text="OK - bot alive")

    web_app = web.Application()
    web_app.router.add_get("/", index)
    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    print(f"Keep-alive server running on port {PORT}")


# --------------- main ---------------
def main():
    if TOKEN.startswith("<PUT") or not TOKEN:
        print("Set TELEGRAM_BOT_TOKEN environment variable.")
        return

    application = ApplicationBuilder().token(TOKEN).build()

    # Basic commands
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("auth", auth_cmd))
    application.add_handler(CommandHandler("unauth", unauth_cmd))
    application.add_handler(CommandHandler("help_mod", help_mod))
    application.add_handler(CommandHandler("getrules", getrules_cmd))

    # mod commands (require auth)
    application.add_handler(CommandHandler("ban", ban_cmd))
    application.add_handler(CommandHandler("unban", unban_cmd))
    application.add_handler(CommandHandler("kick", kick_cmd))
    application.add_handler(CommandHandler("mute", mute_cmd))
    application.add_handler(CommandHandler("unmute", unmute_cmd))
    application.add_handler(CommandHandler("warn", warn_cmd))
    application.add_handler(CommandHandler("warnings", warnings_cmd))
    application.add_handler(CommandHandler("clear", clear_cmd))
    application.add_handler(CommandHandler("purge", purge_cmd))
    application.add_handler(CommandHandler("pin", pin_cmd))
    application.add_handler(CommandHandler("unpin", unpin_cmd))
    application.add_handler(CommandHandler("lock", lock_cmd))
    application.add_handler(CommandHandler("unlock", unlock_cmd))
    application.add_handler(CommandHandler("setrules", setrules_cmd))
    application.add_handler(CommandHandler("promote", promote_cmd))
    application.add_handler(CommandHandler("demote", demote_cmd))
    application.add_handler(CommandHandler("stats", stats_cmd))
    application.add_handler(CommandHandler("setpassword", setpassword_cmd))
    application.add_handler(CommandHandler("help", help_mod))

    # message monitor to auto-delete messages from muted users and manage time-based unmute
    application.add_handler(MessageHandler(filters.ALL & (~filters.COMMAND), message_monitor))

    # Start both bot and keep-alive web server
    async def runner():
        # start keep-alive server (aiohttp) in background
        await run_keep_alive(application)
        # start the bot (polling)
        print("Starting bot polling...")
        await application.initialize()
        await application.start()
        await application.updater.start_polling()  # high-level start for PTB v20
        # Keep running until stopped
        while True:
            await asyncio.sleep(10)

    try:
        asyncio.run(runner())
    except (KeyboardInterrupt, SystemExit):
        print("Shutting down...")
        save_data(DATA)


if __name__ == "__main__":
    main()
