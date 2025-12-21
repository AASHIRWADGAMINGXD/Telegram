import os
import asyncio
from flask import Flask
from threading import Thread
from telegram import (
    Update,
    ChatPermissions,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)

# ================== ENV ==================
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN not set")

# ================= KEEP ALIVE =================
app_web = Flask(__name__)

@app_web.route("/")
def home():
    return "Bot alive 🔥"

def run_web():
    app_web.run(host="0.0.0.0", port=8080)

def keep_alive():
    Thread(target=run_web, daemon=True).start()

# ================= STORAGE =================
afk_users = {}          # user_id: message
blocked_users = set()   # user_id
auto_replies = {}       # trigger: reply

# ================= HELPERS =================
def gang(text: str) -> str:
    return f"😎 {text} bruh 🔥"

async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    member = await context.bot.get_chat_member(
        update.effective_chat.id,
        update.effective_user.id
    )
    return member.status in ("administrator", "creator")

# ================= COMMANDS =================
async def kick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return await update.message.reply_text(gang("no powers"))

    if not update.message.reply_to_message:
        return

    user = update.message.reply_to_message.from_user
    await context.bot.ban_chat_member(
        update.effective_chat.id,
        user.id,
        until_date=10
    )
    await update.message.reply_text(gang("user kicked"))

async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return
    if not update.message.reply_to_message:
        return

    user = update.message.reply_to_message.from_user
    await context.bot.ban_chat_member(update.effective_chat.id, user.id)
    await update.message.reply_text(gang("user banned"))

async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return
    if not update.message.reply_to_message:
        return

    user = update.message.reply_to_message.from_user
    await context.bot.restrict_chat_member(
        update.effective_chat.id,
        user.id,
        ChatPermissions(can_send_messages=False)
    )
    await update.message.reply_text(gang("muted hard"))

async def shout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = " ".join(context.args)
    if text:
        await update.message.reply_text(gang(text.upper()))

async def nuke(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return

    kb = [
        [InlineKeyboardButton("💣 10", callback_data="nuke_10")],
        [InlineKeyboardButton("💥 25", callback_data="nuke_25")],
        [InlineKeyboardButton("☢️ 50", callback_data="nuke_50")]
    ]
    await update.message.reply_text(
        gang("choose destruction"),
        reply_markup=InlineKeyboardMarkup(kb)
    )

async def nuke_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    amount = int(query.data.split("_")[1])
    chat_id = query.message.chat.id

    deleted = 0
    async for msg in context.bot.get_chat_history(chat_id, limit=amount):
        try:
            await context.bot.delete_message(chat_id, msg.message_id)
            deleted += 1
        except:
            pass

    await query.edit_message_text(gang(f"nuked {deleted} msgs"))

async def set_auto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        return
    key = context.args[0].lower()
    value = " ".join(context.args[1:])
    auto_replies[key] = value
    await update.message.reply_text(gang("auto reply added"))

async def remove_auto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return
    auto_replies.pop(context.args[0].lower(), None)
    await update.message.reply_text(gang("auto reply removed"))

async def block(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        return
    blocked_users.add(update.message.reply_to_message.from_user.id)
    await update.message.reply_text(gang("user blocked"))

async def unblock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        return
    blocked_users.discard(update.message.reply_to_message.from_user.id)
    await update.message.reply_text(gang("user unblocked"))

async def pin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await is_admin(update, context) and update.message.reply_to_message:
        await update.message.reply_to_message.pin()
        await update.message.reply_text(gang("pinned"))

async def unpin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await is_admin(update, context):
        await update.message.chat.unpin_all_messages()
        await update.message.reply_text(gang("unpinned all"))

async def afk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = " ".join(context.args) or "AFK"
    afk_users[update.effective_user.id] = msg
    await update.message.reply_text(gang("you AFK now"))

# ================= MESSAGE WATCHER =================
async def watch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.lower()

    if user_id in blocked_users:
        return

    if text in auto_replies:
        await update.message.reply_text(gang(auto_replies[text]))

    if update.message.entities:
        for uid, msg in afk_users.items():
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
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, watch))

    print("🔥 Bot running clean")
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
