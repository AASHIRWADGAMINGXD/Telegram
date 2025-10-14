import os
import logging
import asyncio
from datetime import datetime, timedelta
from telegram import Update, ChatPermissions
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    filters, ContextTypes
)

# Config
TOKEN = os.getenv("TOKEN")
SPAM_LIMIT = 5
MUTE_TIME = 10 * 60
THALA_LIMIT = 3

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

user_messages = {}
user_thala_count = {}
last_reset_date = datetime.now().date()

def reset_daily_limits():
    global user_thala_count, last_reset_date
    today = datetime.now().date()
    if today != last_reset_date:
        user_thala_count = {}
        last_reset_date = today

async def mute_user(context, chat_id, user_id):
    await context.bot.restrict_chat_member(
        chat_id,
        user_id,
        ChatPermissions(can_send_messages=False),
        until_date=datetime.now() + timedelta(seconds=MUTE_TIME)
    )
    await context.bot.send_message(chat_id, "User muted for 10 minutes due to spam.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "**Help Menu**\n"
        "- Spam Detection → auto mute 10 min\n"
        "- 'Thala' limit → 3 times/day\n"
        "- !rules (admin only)\n"
        "- Made by Aashirwadgamerzz",
        parse_mode="Markdown"
    )

async def rules_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    member = await update.effective_chat.get_member(user.id)
    if member.status not in ("administrator", "creator"):
        await update.message.reply_text("Only admins can use this command.")
        return
    await update.message.reply_text("#1 Spam is not allowed")

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reset_daily_limits()
    msg = update.message
    user_id = msg.from_user.id
    chat_id = msg.chat_id
    text = msg.text.lower()

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
            await msg.delete()
            await msg.reply_text("You thala limit has reached!")
        else:
            await msg.reply_text(f"Thala count: {count}/3")

async def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.Regex(r"^!rules$"), rules_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
