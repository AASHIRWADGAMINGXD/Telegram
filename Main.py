import os
import asyncio
from telegram import Update, ChatPermissions, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)
from flask import Flask
from threading import Thread
from datetime import timedelta

# ================= CONFIG =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))

# ================= KEEP ALIVE =================
app = Flask("")

@app.route("/")
def home():
    return "Bot alive 🔥"

def run():
    app.run(host="0.0.0.0", port=8080)

def keep_alive():
    Thread(target=run).start()

# ================= DATA =================
afk_users = {}
blocked_users = set()
auto_replies = {}

# ================= UTILS =================
def gang(text):
    return f"😎 {text} bruh 🔥"

async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.id
    chat = update.effective_chat.id
    member = await context.bot.get_chat_member(chat, user)
    return member.status in ["administrator", "creator"]

# ================= COMMANDS =================

async def kick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return await update.message.reply_text(gang("no power, stay in yo lane"))

    user = update.message.reply_to_message.from_user
    await context.bot.ban_chat_member(update.effective_chat.id, user.id, until_date=timedelta(seconds=30))
    await update.message.reply_text(gang(f"{user.first_name} got kicked out"))

async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return
    user = update.message.reply_to_message.from_user
    await context.bot.ban_chat_member(update.effective_chat.id, user.id)
    await update.message.reply_text(gang("user banned forever"))

async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return
    user = update.message.reply_to_message.from_user
    await context.bot.restrict_chat_member(
        update.effective_chat.id,
        user.id,
        ChatPermissions(can_send_messages=False)
    )
    await update.message.reply_text(gang("mouth zipped 🤐"))

async def shout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = " ".join(context.args).upper()
    await update.message.reply_text(gang(text))

async def nuke(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("💣 10", callback_data="nuke_10")],
        [InlineKeyboardButton("💥 50", callback_data="nuke_50")],
        [InlineKeyboardButton("☢️ 100", callback_data="nuke_100")]
    ]
    await update.message.reply_text(
        gang("how hard we nukin?"),
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def nuke_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    amount = int(query.data.split("_")[1])

    chat_id = query.message.chat.id
    messages = await context.bot.get_chat_history(chat_id, limit=amount)

    for msg in messages:
        try:
            await context.bot.delete_message(chat_id, msg.message_id)
        except:
            pass

    await query.edit_message_text(gang(f"nuked {amount} messages 💀"))

async def set_auto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = context.args[0]
    value = " ".join(context.args[1:])
    auto_replies[key] = value
    await update.message.reply_text(gang("auto reply locked in"))

async def remove_auto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = context.args[0]
    auto_replies.pop(key, None)
    await update.message.reply_text(gang("auto reply removed"))

async def block(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.reply_to_message.from_user.id
    blocked_users.add(user)
    await update.message.reply_text(gang("user muted from existence"))

async def unblock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.reply_to_message.from_user.id
    blocked_users.discard(user)
    await update.message.reply_text(gang("user free now"))

async def pin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await is_admin(update, context):
        await update.message.reply_to_message.pin()
        await update.message.reply_text(gang("pinned that"))

async def unpin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await is_admin(update, context):
        await update.message.chat.unpin_all_messages()
        await update.message.reply_text(gang("all unpinned"))

async def afk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = " ".join(context.args)
    afk_users[update.effective_user.id] = msg
    await update.message.reply_text(gang("you AFK now"))

# ================= MESSAGE HANDLER =================
async def messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.id
    text = update.message.text.lower()

    if user in blocked_users:
        return

    if text in auto_replies:
        await update.message.reply_text(gang(auto_replies[text]))

    for uid, msg in afk_users.items():
        if update.message.entities:
            await update.message.reply_text(gang(f"user AFK: {msg}"))

# ================= MAIN =================
async def main():
    keep_alive()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("kick", kick))
    app.add_handler(CommandHandler("ban", ban))
    app.add_handler(CommandHandler("mute", mute))
    app.add_handler(CommandHandler("shout", shout))
    app.add_handler(CommandHandler("nuke", nuke))
    app.add_handler(CallbackQueryHandler(nuke_action))
    app.add_handler(CommandHandler("setauto", set_auto))
    app.add_handler(CommandHandler("removeauto", remove_auto))
    app.add_handler(CommandHandler("block", block))
    app.add_handler(CommandHandler("unblock", unblock))
    app.add_handler(CommandHandler("pin", pin))
    app.add_handler(CommandHandler("unpin", unpin))
    app.add_handler(CommandHandler("afk", afk))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, messages))

    print("🔥 Gang bot running")
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
