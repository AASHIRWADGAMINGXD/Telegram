# Telegram Bot with /kick, /clean, /mute, and password authentication
# Full Deployable Code for Render

import os
import time
import asyncio
import sqlite3
from datetime import datetime, timedelta
from telegram import Update, ChatPermissions
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

BOT_TOKEN = os.getenv("BOT_TOKEN")
AUTH_PASSWORD = os.getenv("AUTH_PASSWORD", "indianpower123")
DB = "bot.db"

# ---------------------- DATABASE SETUP ----------------------
def init_db():
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS auth (
        user_id INTEGER PRIMARY KEY,
        is_verified INTEGER
    )""")
    con.commit(); con.close()

def is_verified(user_id: int):
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.execute("SELECT is_verified FROM auth WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    con.close()
    return row and row[0] == 1

def verify_user(user_id: int):
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.execute("REPLACE INTO auth VALUES (?, 1)", (user_id,))
    con.commit(); con.close()

# ---------------------- COMMANDS ----------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Namaste! 🙏\n" \
        "Aapka swagat hai Indian Security Bot me!\n" \
        "Aage badhne ke liye password type karein: /auth <password>"
    )

async def auth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Bhai password daalna padega! Format: /auth <password>")
        return

    if context.args[0] == AUTH_PASSWORD:
        verify_user(update.effective_user.id)
        await update.message.reply_text("Sahi pakde hain! ✔️ Authentication Successful 💪🇮🇳")
    else:
        await update.message.reply_text("Galat password bhai! Thoda dhyaan se likho 😭")

async def clean(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat

    if not is_verified(user.id):
        await update.message.reply_text("Pehle authentication karo bhai! /auth <password>")
        return

    n = int(context.args[0]) if context.args else 20
    deleted = 0

    for msg_id in range(update.message.message_id - 1, update.message.message_id - n - 1, -1):
        try:
            await context.bot.delete_message(chat.id, msg_id)
            deleted += 1
        except:
            pass

    await update.message.reply_text(f"Khatam! 🚮 {deleted} messages uda diye boss 😎")

async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if not is_verified(user.id):
        await update.message.reply_text("Pehle authentication karo bhai! /auth <password>")
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("Kisko mute karna hai? Reply karke /mute karo bhai.")
        return

    target = update.message.reply_to_message.from_user

    perms = ChatPermissions(can_send_messages=False)

    try:
        await context.bot.restrict_chat_member(
            update.effective_chat.id, target.id, permissions=perms, until_date=datetime.utcnow() + timedelta(hours=1)
        )
        await update.message.reply_text(
            f"{target.full_name} ko 1 ghanta ke liye chup kara diya! 🤐\n"
            "Thoda shanti rakho bhai log. 🙏"
        )
    except:
        await update.message.reply_text("Arre yeh banda nahi mute hota! Admin ya owner hoga 😭")

async def kick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if not is_verified(user.id):
        await update.message.reply_text("Pehle authentication karo bhai! /auth <password>")
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("Kisko kick karna hai? Reply karke bolo. /kick")
        return

    target = update.message.reply_to_message.from_user

    try:
        await context.bot.ban_chat_member(update.effective_chat.id, target.id)
        await context.bot.unban_chat_member(update.effective_chat.id, target.id)

        await update.message.reply_text(
            f"{target.full_name} ko group se nikal diya bhai! 🚪👋\n"
            "Baat khatam, paisa hazam 😎"
        )
    except:
        await update.message.reply_text("Bhai ye banda strong hai… admin lagta hai, nahi nikal sakta 😭")

# ---------------------- MAIN ----------------------
async def main():
    init_db()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("auth", auth))
    app.add_handler(CommandHandler("clean", clean))
    app.add_handler(CommandHandler("kick", kick))
    app.add_handler(CommandHandler("mute", mute))

    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
