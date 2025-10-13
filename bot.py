import os
import logging
import asyncio
from datetime import datetime, timedelta
from flask import Flask
from telegram import Update, ChatPermissions
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    filters, ContextTypes
)

TOKEN = os.getenv("TOKEN")  # token from environment
SPAM_LIMIT = 5
MUTE_TIME = 10 * 60
THALA_LIMIT = 3

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

user_messages = {}
user_thala_count = {}
last_reset_date = datetime.now().date()

app = Flask(__name__)

@app.route('/')
def home():
    return "Telegram Bot by Aashirwadgamerzz is running!"

def reset_daily_limits():
    global user_thala_count, last_reset_date
    today = datetime.now().date()
    if today != last_reset_date:
        user_thala_count = {}
        last_reset_date = today

async def mute_user(context: ContextTypes.DEFAULT_TYPE, chat_id, user_id):
    await context.bot.restrict_chat_member(
        chat_id,
        user_id,
        ChatPermissions(can_send_messages=False),
        until_date=datetime.now() + timedelta(seconds=MUTE_TIME)
    )
    await context.bot.send_message(chat_id, "User muted for 10 minutes due to spam.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "**Help Menu**\n"
        "- Spam Detection → auto mute 10 min\n"
        "- 'Thala' limit → max 3 times per day\n"
        "- !rules → shows group rules (admin only)\n"
        "- Made by Aashirwadgamerzz"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def rules_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    member = await update.effective_chat.get_member(user.id)

    if member.status not in ("administrator", "creator"):
        await update.message.reply_text("Only admins can use this command.")
        return

    await update.message.reply_text("#1 Spam is not allowed")

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reset_daily_limits()
    message = update.message
    user_id = message.from_user.id
    chat_id = message.chat_id
    text = message.text.lower()

    if user_id not in user_messages:
        user_messages[user_id] = []
    user_messages[user_id].append(datetime.now())
    user_messages[user_id] = [
        t for t in user_messages[user_id] if (datetime.now() - t).seconds < 10
    ]

    if len(user_messages[user_id]) > SPAM_LIMIT:
        await mute_user(context, chat_id, user_id)
        user_messages[user_id] = []

    if "thala" in text:
        count = user_thala_count.get(user_id, 0) + 1
        user_thala_count[user_id] = count
        if count > THALA_LIMIT:
            await message.delete()
            await message.reply_text("You thala limit has reached!")
        else:
            await message.reply_text(f"Thala count: {count}/3")

async def main():
    app_instance = ApplicationBuilder().token(TOKEN).build()
    app_instance.add_handler(CommandHandler("help", help_command))
    app_instance.add_handler(MessageHandler(filters.Regex(r"^!rules$"), rules_command))
    app_instance.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    await app_instance.run_polling()

if __name__ == "__main__":
    import threading
    threading.Thread(target=lambda: app.run(host="0.0.0.0", port=8080)).start()
    asyncio.run(main())
