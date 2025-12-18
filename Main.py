import os
import asyncio
from telegram import Update, ChatPermissions
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, JobQueue
from telegram.error import BadRequest

# Environment variables
BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD')

# Global data structures
blocked_users = set()  # Users blocked from bot
auto_replies = {}  # Dict of trigger: response
logged_in_users = set()  # Users who have logged in

async def is_admin(update: Update) -> bool:
    return update.effective_user.id in logged_in_users

async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        await update.message.reply_text("Access denied. Use /login [password] to authenticate.")
        return
    chat_id = update.effective_chat.id
    try:
        # Delete recent messages (Telegram limits to 100 per call, and only bot's own messages or in channels)
        messages = await context.bot.get_chat_history(chat_id, limit=100)
        for msg in messages:
            if msg.message_id != update.message.message_id:  # Don't delete the command itself
                await context.bot.delete_message(chat_id, msg.message_id)
        await update.message.reply_text("Chat cleared (recent messages deleted).")
    except BadRequest:
        await update.message.reply_text("Unable to clear chat (insufficient permissions).")

async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        await update.message.reply_text("Access denied.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /mute @username or user_id")
        return
    user = context.args[0]
    chat_id = update.effective_chat.id
    try:
        await context.bot.restrict_chat_member(chat_id, user, ChatPermissions(can_send_messages=False))
        await update.message.reply_text(f"User {user} muted.")
    except BadRequest:
        await update.message.reply_text("Failed to mute user.")

async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        await update.message.reply_text("Access denied.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /ban @username or user_id")
        return
    user = context.args[0]
    chat_id = update.effective_chat.id
    try:
        await context.bot.ban_chat_member(chat_id, user)
        await update.message.reply_text(f"User {user} banned.")
    except BadRequest:
        await update.message.reply_text("Failed to ban user.")

async def kick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        await update.message.reply_text("Access denied.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /kick @username or user_id")
        return
    user = context.args[0]
    chat_id = update.effective_chat.id
    try:
        await context.bot.ban_chat_member(chat_id, user)
        await context.bot.unban_chat_member(chat_id, user)  # Unban to allow rejoin
        await update.message.reply_text(f"User {user} kicked.")
    except BadRequest:
        await update.message.reply_text("Failed to kick user.")

async def block(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        await update.message.reply_text("Access denied.")
        return
    if not context.args:
        await update.message.reply_text("Usage: block @username or user_id")
        return
    user_id = int(context.args[0].lstrip('@')) if context.args[0].startswith('@') else int(context.args[0])
    blocked_users.add(user_id)
    await update.message.reply_text(f"User {user_id} blocked from bot.")

async def add_auto_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        await update.message.reply_text("Access denied.")
        return
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Usage: add auto reply [trigger] [response]")
        return
    trigger = args[0]
    response = ' '.join(args[1:])
    auto_replies[trigger.lower()] = response
    await update.message.reply_text(f"Auto-reply added for '{trigger}'.")

async def remove_auto_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        await update.message.reply_text("Access denied.")
        return
    if not context.args:
        await update.message.reply_text("Usage: remove auto reply [trigger]")
        return
    trigger = context.args[0].lower()
    if trigger in auto_replies:
        del auto_replies[trigger]
        await update.message.reply_text(f"Auto-reply removed for '{trigger}'.")
    else:
        await update.message.reply_text("No auto-reply found for that trigger.")

async def login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or context.args[0] != ADMIN_PASSWORD:
        await update.message.reply_text("Invalid password.")
        return
    user_id = update.effective_user.id
    logged_in_users.add(user_id)
    await update.message.reply_text("Logged in. You now have full access.")

async def removeuser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        await update.message.reply_text("Access denied.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /removeuser @username or user_id")
        return
    user_id = int(context.args[0].lstrip('@')) if context.args[0].startswith('@') else int(context.args[0])
    logged_in_users.discard(user_id)
    await update.message.reply_text(f"User {user_id} logged out.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in blocked_users:
        return  # Ignore blocked users
    text = update.message.text.lower()
    for trigger, response in auto_replies.items():
        if trigger in text:
            await update.message.reply_text(response)
            break

async def keep_alive_job(context: ContextTypes.DEFAULT_TYPE):
    print("Bot is alive.")

def main():
    application = Application.builder().token(BOT_TOKEN).build()

    # Handlers
    application.add_handler(CommandHandler("clear", clear))
    application.add_handler(CommandHandler("mute", mute))
    application.add_handler(CommandHandler("ban", ban))
    application.add_handler(CommandHandler("kick", kick))
    application.add_handler(CommandHandler("login", login))
    application.add_handler(CommandHandler("removeuser", removeuser))
    application.add_handler(MessageHandler(filters.Regex(r'^block'), block))
    application.add_handler(MessageHandler(filters.Regex(r'^add auto reply'), add_auto_reply))
    application.add_handler(MessageHandler(filters.Regex(r'^remove auto reply'), remove_auto_reply))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Add keep-alive job (runs every 300 seconds)
    job_queue = application.job_queue
    job_queue.run_repeating(keep_alive_job, interval=300, first=0)

    application.run_polling()

if __name__ == '__main__':
    main()
