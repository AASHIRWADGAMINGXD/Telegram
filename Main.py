import os
import asyncio
from telegram import Update, ChatPermissions
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)
from flask import Flask
from threading import Thread

# ----------------------------------------------------------------------
# KEEP ALIVE SERVER FOR RENDER
# ----------------------------------------------------------------------
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot Running"

def run_server():
    app.run(host="0.0.0.0", port=8080)

def keep_alive():
    t = Thread(target=run_server)
    t.daemon = True
    t.start()

# ----------------------------------------------------------------------
# CONFIG
# ----------------------------------------------------------------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
PASSWORD = os.getenv("BOT_PASSWORD", "12345")

logged_in_users = set()

# ----------------------------------------------------------------------
# COMMANDS
# ----------------------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Namaste bhai. Login ke liye /login <password> bhejo."
    )

async def login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if len(context.args) == 0:
        return await update.message.reply_text("Password bhejo bhai. /login 12345")

    if context.args[0] == PASSWORD:
        logged_in_users.add(user_id)
        await update.message.reply_text("Sahi password bhai. Login done.")
    else:
        await update.message.reply_text("Galat password bhai.")


# ADMIN CHECK
async def is_admin(update: Update):
    admins = await update.effective_chat.get_administrators()
    return update.effective_user.id in [a.user.id for a in admins]


def require_login(func):
    async def w(update, context):
        if update.effective_user.id not in logged_in_users:
            return await update.message.reply_text("Pehle login karo bhai.")
        return await func(update, context)
    return w

def require_admin(func):
    async def w(update, context):
        if not await is_admin(update):
            return await update.message.reply_text("Ye command admin ke liye hai bhai.")
        return await func(update, context)
    return w


# ----------------------------------------------------------------------
# KICK
# ----------------------------------------------------------------------
@require_login
@require_admin
async def kick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await update.message.reply_text("User ID do bhai. /kick 12345")

    try:
        user_id = int(context.args[0])
        await update.effective_chat.ban_member(user_id)
        await update.message.reply_text("User ko group se nikal diya bhai.")
    except:
        await update.message.reply_text("Kick nahi ho paaya bhai.")


# ----------------------------------------------------------------------
# CLEAR
# ----------------------------------------------------------------------
@require_login
@require_admin
async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        limit = int(context.args[0]) if context.args else 10
        chat = update.effective_chat

        async for msg in chat.get_history(limit=limit):
            try:
                await chat.delete_message(msg.message_id)
            except:
                pass

        await update.message.reply_text("Messages saaf ho gaye bhai.")
    except:
        await update.message.reply_text("Clear command fail ho gaya bhai.")


# ----------------------------------------------------------------------
# MUTE
# ----------------------------------------------------------------------
@require_login
@require_admin
async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        return await update.message.reply_text("Use: /mute <user_id> <minutes>")

    try:
        user_id = int(context.args[0])
        minutes = int(context.args[1])

        permissions = ChatPermissions(can_send_messages=False)
        await update.effective_chat.restrict_member(
            user_id,
            permissions,
            until_date=minutes * 60
        )

        await update.message.reply_text(f"User {minutes} minute ke liye mute ho gaya bhai.")
    except:
        await update.message.reply_text("Mute nahi ho paaya bhai.")


# ----------------------------------------------------------------------
# MAIN FUNCTION (100% COMPATIBLE)
# ----------------------------------------------------------------------
async def run_bot():
    keep_alive()

    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("login", login))
    application.add_handler(CommandHandler("kick", kick))
    application.add_handler(CommandHandler("clear", clear))
    application.add_handler(CommandHandler("mute", mute))

    print("Bot starting on Render...")
    await application.run_polling(close_loop=False)

# ----------------------------------------------------------------------
# ENTRY POINT
# ----------------------------------------------------------------------
if __name__ == "__main__":
    asyncio.run(run_bot())
