import os
from telegram import Update, ChatPermissions
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)
from flask import Flask
from threading import Thread

# ------------------------
# KEEP ALIVE SERVER (FOR RENDER)
# ------------------------
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot Running..."

def run_server():
    app.run(host="0.0.0.0", port=8080)

def keep_alive():
    t = Thread(target=run_server)
    t.start()

# ------------------------
# BOT CONFIG
# ------------------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
PASSWORD = os.getenv("BOT_PASSWORD", "12345")

logged_in_users = set()


# ------------------------
# START
# ------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Namaste bhai. Login ke liye /login <password> bhejo."
    )


# ------------------------
# LOGIN
# ------------------------
async def login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if len(context.args) == 0:
        return await update.message.reply_text(
            "Password daalna padta bhai. Example: /login 12345"
        )

    if context.args[0] == PASSWORD:
        logged_in_users.add(user_id)
        await update.message.reply_text("Sahi password bhai. Aap login ho gaye.")
    else:
        await update.message.reply_text("Galat password bhai.")


# ------------------------
# ADMIN CHECK
# ------------------------
async def is_admin(update: Update):
    admins = await update.effective_chat.get_administrators()
    admin_ids = [a.user.id for a in admins]
    return update.effective_user.id in admin_ids


def require_login(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id not in logged_in_users:
            return await update.message.reply_text("Pehle login karo bhai.")
        return await func(update, context)
    return wrapper


def require_admin(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await is_admin(update):
            return await update.message.reply_text("Ye command admin ke liye hai bhai.")
        return await func(update, context)
    return wrapper


# ------------------------
# KICK USER
# ------------------------
@require_login
@require_admin
async def kick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) == 0:
        return await update.message.reply_text("User ID do bhai. Example: /kick 12345")

    user_id = int(context.args[0])
    try:
        await update.effective_chat.ban_member(user_id)
        await update.message.reply_text("User ko group se nikal diya bhai.")
    except:
        await update.message.reply_text("User ko kick nahi kar paaya bhai.")


# ------------------------
# CLEAR MESSAGES
# ------------------------
@require_login
@require_admin
async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        count = int(context.args[0]) if context.args else 10
        chat = update.effective_chat

        async for msg in chat.get_history(limit=count):
            try:
                await chat.delete_message(msg.message_id)
            except:
                pass

        await update.message.reply_text("Messages saaf kar diye bhai.")
    except:
        await update.message.reply_text("Clear command me dikkat aa gayi.")


# ------------------------
# MUTE USER
# ------------------------
@require_login
@require_admin
async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        return await update.message.reply_text("Use: /mute <user_id> <minutes>")

    user_id = int(context.args[0])
    minutes = int(context.args[1])
    try:
        permissions = ChatPermissions(can_send_messages=False)
        await update.effective_chat.restrict_member(
            user_id,
            permissions,
            until_date=minutes * 60
        )
        await update.message.reply_text(
            f"User ko {minutes} minute ke liye mute kar diya bhai."
        )
    except:
        await update.message.reply_text("Mute karne me dikkat aa gayi.")


# ------------------------
# MAIN FUNCTION (PTB v20)
# ------------------------
async def main():
    keep_alive()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("login", login))
    app.add_handler(CommandHandler("kick", kick))
    app.add_handler(CommandHandler("clear", clear))
    app.add_handler(CommandHandler("mute", mute))

    print("Bot started on Render")
    await app.run_polling()


# ------------------------
# ENTRY POINT
# ------------------------
if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
