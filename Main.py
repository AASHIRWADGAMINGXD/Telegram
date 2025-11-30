import os
from telegram import Update, ChatPermissions
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
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
PASSWORD = os.getenv("BOT_PASSWORD", "12345")  # default password

logged_in_users = set()  # store user_ids who logged in


# ------------------------
# HELP / START
# ------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Namaste bhai! Bot ready hai.\n"
        "Login ke liye: /login <password>"
    )


# ------------------------
# LOGIN SYSTEM
# ------------------------
async def login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args

    if len(args) == 0:
        return await update.message.reply_text("Password daalo bhai: /login <password>")

    if args[0] == PASSWORD:
        logged_in_users.add(user_id)
        return await update.message.reply_text("Sahi password! Aap login ho gaye ho bhai.")
    else:
        return await update.message.reply_text("Galat password hai dost.")


# ------------------------
# CHECK ADMIN + LOGIN
# ------------------------
async def is_admin(update: Update):
    chat_admins = await update.effective_chat.get_administrators()
    admin_ids = [admin.user.id for admin in chat_admins]
    return update.effective_user.id in admin_ids


def require_login(func):
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if user_id not in logged_in_users:
            return await update.message.reply_text("Bhai pehle login karo: /login <password>")
        return await func(update, context)
    return wrapped


def require_admin(func):
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await is_admin(update):
            return await update.message.reply_text("Ye command sirf admins ke liye hai bhai.")
        return await func(update, context)
    return wrapped


# ------------------------
# KICK USER
# ------------------------
@require_login
@require_admin
async def kick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await update.message.reply_text("User mention karo ya ID do bhai.")

    user_id = int(context.args[0])
    try:
        await update.effective_chat.ban_member(user_id)
        await update.message.reply_text("User ko nikal diya bhai.")
    except:
        await update.message.reply_text("Nikalne me problem aa rahi hai bhai.")


# ------------------------
# CLEAR (DELETE MESSAGES)
# ------------------------
@require_login
@require_admin
async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        count = int(context.args[0]) if context.args else 10

        chat = update.effective_chat
        messages = []
        async for msg in chat.get_history(limit=count):
            messages.append(msg.message_id)

        for m in messages:
            await chat.delete_message(m)

        await update.message.reply_text("Chat saaf kar diya bhai.")
    except:
        await update.message.reply_text("Clear command me kuch issue aa gaya bhai.")


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
            user_id, permissions, until_date=minutes * 60
        )
        await update.message.reply_text(f"User ko {minutes} minute ke liye mute kar diya bhai.")
    except:
        await update.message.reply_text("Mute karne me dikkat aa rahi hai bhai.")


# ------------------------
# MAIN
# ------------------------
def main():
    keep_alive()  # start keep-alive server

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("login", login))
    app.add_handler(CommandHandler("kick", kick))
    app.add_handler(CommandHandler("clear", clear))
    app.add_handler(CommandHandler("mute", mute))

    print("Bot running...")
    app.run_polling()


if __name__ == "__main__":
    main()
