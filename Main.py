import os
import logging
import re
import datetime
from threading import Thread
from flask import Flask
from telegram import Update, ChatPermissions
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, filters, Application
from telegram.constants import ParseMode

# ---------------- CONFIGURATION ---------------- #
TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")

# ---------------- KEEP ALIVE (FOR RENDER) ---------------- #
app = Flask('')

@app.route('/')
def home():
    return "I am alive and running!"

def run():
    # RENDER requires the app to listen on the specific PORT environment variable
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()

# ---------------- HELPER FUNCTIONS ---------------- #
def parse_time_str(time_str):
    regex = re.compile(r"(\d+)([smhd])")
    parts = regex.match(time_str)
    if not parts: return None
    amount, unit = parts.groups()
    amount = int(amount)
    if unit == 's': return amount
    if unit == 'm': return amount * 60
    if unit == 'h': return amount * 3600
    if unit == 'd': return amount * 86400
    return None

async def check_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    member = await context.bot.get_chat_member(chat_id, user_id)
    if member.status not in ['administrator', 'creator']:
        await update.message.reply_text("❌ You do not have permission.")
        return False
    return True

# ---------------- STARTUP HOOK ---------------- #
async def post_init(application: Application):
    """
    This runs before the bot starts polling.
    It deletes any existing webhook to prevent Conflict errors.
    """
    print("Checking for webhooks...")
    await application.bot.delete_webhook(drop_pending_updates=True)
    print("Webhook deleted. Starting polling...")

# ---------------- COMMANDS ---------------- #

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 Bot is Online!\n/kick, /mute, /promote, /permission")

async def kick_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_admin(update, context): return
    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Reply to a user.")
        return
    user = update.message.reply_to_message.from_user
    try:
        await context.bot.ban_chat_member(update.effective_chat.id, user.id)
        await context.bot.unban_chat_member(update.effective_chat.id, user.id)
        await update.message.reply_text(f"👢 {user.first_name} kicked.")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

async def mute_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_admin(update, context): return
    if not update.message.reply_to_message or not context.args:
        await update.message.reply_text("❌ Usage: /mute 10m (Reply to user)")
        return
    
    seconds = parse_time_str(context.args[0])
    if not seconds:
        await update.message.reply_text("❌ Invalid time.")
        return

    user = update.message.reply_to_message.from_user
    until = datetime.datetime.now() + datetime.timedelta(seconds=seconds)
    permissions = ChatPermissions(can_send_messages=False)

    try:
        await context.bot.restrict_chat_member(update.effective_chat.id, user.id, permissions, until_date=until)
        await update.message.reply_text(f"🔇 {user.first_name} muted for {context.args[0]}.")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

async def promote_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_admin(update, context): return
    if not update.message.reply_to_message: return
    try:
        await context.bot.promote_chat_member(
            update.effective_chat.id, 
            update.message.reply_to_message.from_user.id,
            can_manage_chat=True, can_delete_messages=True, can_invite_users=True, can_restrict_members=True
        )
        await update.message.reply_text("🆙 Promoted.")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

async def demote_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_admin(update, context): return
    if not update.message.reply_to_message: return
    try:
        await context.bot.promote_chat_member(
            update.effective_chat.id,
            update.message.reply_to_message.from_user.id,
            can_manage_chat=False, can_delete_messages=False, can_invite_users=False, can_restrict_members=False
        )
        await update.message.reply_text("⬇️ Demoted.")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

async def set_permission(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_admin(update, context): return
    if not update.message.reply_to_message or len(context.args) < 2:
        await update.message.reply_text("❌ Usage: /permission <time|forever> <messages/media/invite>")
        return

    duration, p_type = context.args[0].lower(), context.args[1].lower()
    until = None
    if duration != "forever":
        s = parse_time_str(duration)
        if s: until = datetime.datetime.now() + datetime.timedelta(seconds=s)

    p = {'send_messages': False, 'send_media_messages': False, 'can_invite_users': False}
    if p_type == 'messages': p['send_messages'] = True
    elif p_type == 'media': p['send_messages'] = True; p['send_media_messages'] = True
    elif p_type == 'invite': p['send_messages'] = True; p['can_invite_users'] = True

    try:
        await context.bot.restrict_chat_member(
            update.effective_chat.id, 
            update.message.reply_to_message.from_user.id, 
            permissions=ChatPermissions(**p), 
            until_date=until
        )
        await update.message.reply_text(f"✅ Permissions updated: {p_type} ({duration})")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

# ---------------- MAIN ---------------- #
if __name__ == '__main__':
    keep_alive()
    
    # Added post_init to automatically clear webhooks
    application = ApplicationBuilder().token(TOKEN).post_init(post_init).build()

    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('kick', kick_user))
    application.add_handler(CommandHandler('mute', mute_user))
    application.add_handler(CommandHandler('promote', promote_user))
    application.add_handler(CommandHandler('demote', demote_user))
    application.add_handler(CommandHandler('permission', set_permission))

    print("Bot is running...")
    application.run_polling()
