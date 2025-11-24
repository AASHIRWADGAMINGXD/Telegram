import os
import logging
import re
import datetime
from threading import Thread
from flask import Flask
from telegram import Update, ChatPermissions
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, filters
from telegram.constants import ParseMode

# ---------------- CONFIGURATION ---------------- #
# Replace with your Token or use Environment Variables (Recommended for Render)
TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")

# ---------------- KEEP ALIVE (FOR RENDER) ---------------- #
app = Flask('')

@app.route('/')
def home():
    return "I am alive and running!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

# ---------------- HELPER FUNCTIONS ---------------- #
def parse_time_str(time_str):
    """Converts strings like 10m, 1h, 1d into seconds."""
    regex = re.compile(r"(\d+)([smhd])")
    parts = regex.match(time_str)
    if not parts:
        return None
    
    amount, unit = parts.groups()
    amount = int(amount)
    
    if unit == 's': return amount
    if unit == 'm': return amount * 60
    if unit == 'h': return amount * 3600
    if unit == 'd': return amount * 86400
    return None

async def check_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Checks if the user issuing the command is an admin."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    member = await context.bot.get_chat_member(chat_id, user_id)
    if member.status not in ['administrator', 'creator']:
        await update.message.reply_text("❌ You do not have permission to use this command.")
        return False
    return True

# ---------------- BOT COMMANDS ---------------- #

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 **Moderator Bot Online**\n\n"
        "Commands:\n"
        "/kick - Kick a user (Reply)\n"
        "/mute <time> - Mute a user (Reply)\n"
        "/promote - Promote a user (Reply)\n"
        "/demote - Demote an admin (Reply)\n"
        "/permission <time|forever> <type> - Give specific rights",
        parse_mode=ParseMode.MARKDOWN
    )

# 1. KICK
async def kick_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_admin(update, context): return
    
    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Please reply to a user to kick them.")
        return

    user_to_kick = update.message.reply_to_message.from_user
    chat_id = update.effective_chat.id

    try:
        # Ban and then Unban to kick (allows rejoining)
        await context.bot.ban_chat_member(chat_id, user_to_kick.id)
        await context.bot.unban_chat_member(chat_id, user_to_kick.id)
        await update.message.reply_text(f"👢 {user_to_kick.first_name} has been kicked.")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

# 2. TEMP MUTE
async def mute_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_admin(update, context): return

    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Reply to a user to mute.")
        return

    if not context.args:
        await update.message.reply_text("❌ Usage: /mute 10m (or 1h, 1d)")
        return

    time_str = context.args[0]
    seconds = parse_time_str(time_str)
    
    if not seconds:
        await update.message.reply_text("❌ Invalid time format. Use 10m, 1h, etc.")
        return

    user_to_mute = update.message.reply_to_message.from_user
    chat_id = update.effective_chat.id
    
    # Permissions object for Muted user (cannot send anything)
    permissions = ChatPermissions(can_send_messages=False)
    until_date = datetime.datetime.now() + datetime.timedelta(seconds=seconds)

    try:
        await context.bot.restrict_chat_member(
            chat_id, user_to_mute.id, permissions=permissions, until_date=until_date
        )
        await update.message.reply_text(f"🔇 {user_to_mute.first_name} muted for {time_str}.")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

# 3. PROMOTE
async def promote_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_admin(update, context): return

    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Reply to a user to promote.")
        return

    user_to_promote = update.message.reply_to_message.from_user
    chat_id = update.effective_chat.id

    try:
        await context.bot.promote_chat_member(
            chat_id, 
            user_to_promote.id,
            can_manage_chat=True,
            can_delete_messages=True,
            can_invite_users=True,
            can_restrict_members=True,
            can_pin_messages=True,
            can_promote_members=False
        )
        await update.message.reply_text(f"🆙 {user_to_promote.first_name} is now an Admin.")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

# 4. DEMOTE (D. Promote)
async def demote_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_admin(update, context): return

    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Reply to an admin to demote.")
        return

    user_to_demote = update.message.reply_to_message.from_user
    chat_id = update.effective_chat.id

    try:
        # Promoting with all False values effectively demotes them
        await context.bot.promote_chat_member(
            chat_id,
            user_to_demote.id,
            can_manage_chat=False,
            can_delete_messages=False,
            can_invite_users=False,
            can_restrict_members=False,
            can_pin_messages=False,
            can_promote_members=False
        )
        await update.message.reply_text(f"⬇️ {user_to_demote.first_name} has been demoted.")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

# 5. PERMISSION (Complex)
async def set_permission(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Usage: /permission <time|forever> <permission_name> (Reply to User)
    Permission Names: messages, media, polls, info, invite
    """
    if not await check_admin(update, context): return

    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Reply to a user to change permissions.")
        return

    if len(context.args) < 2:
        await update.message.reply_text("❌ Usage: /permission <time|forever> <messages/media/invite>")
        return

    duration_arg = context.args[0].lower()
    perm_type = context.args[1].lower()
    user = update.message.reply_to_message.from_user
    chat_id = update.effective_chat.id

    # Determine Duration
    until_date = None # Default is None (Forever)
    if duration_arg != "forever":
        seconds = parse_time_str(duration_arg)
        if not seconds:
            await update.message.reply_text("❌ Invalid time. Use 'forever' or '10m', '2h'.")
            return
        until_date = datetime.datetime.now() + datetime.timedelta(seconds=seconds)

    # Map string input to ChatPermissions
    # Default: Restricted from everything, we add the specific one asked
    p = {
        'send_messages': False,
        'send_media_messages': False,
        'send_polls': False,
        'can_invite_users': False,
        'can_change_info': False,
        'can_pin_messages': False
    }

    # Logic: Use 'restrict' to GRANT specific permissions to non-admins
    if perm_type == 'messages':
        p['send_messages'] = True
    elif perm_type == 'media':
        p['send_messages'] = True # Usually need text to send media
        p['send_media_messages'] = True
    elif perm_type == 'invite':
        p['send_messages'] = True
        p['can_invite_users'] = True
    elif perm_type == 'info':
        p['send_messages'] = True
        p['can_change_info'] = True
    else:
        await update.message.reply_text("❌ Unknown permission. Use: messages, media, invite, info")
        return

    new_perms = ChatPermissions(**p)

    try:
        # Apply restriction (which is how you set permissions for members)
        if until_date:
            await context.bot.restrict_chat_member(chat_id, user.id, permissions=new_perms, until_date=until_date)
            msg = f"✅ {user.first_name} can now use **{perm_type}** for {duration_arg}."
        else:
            await context.bot.restrict_chat_member(chat_id, user.id, permissions=new_perms)
            msg = f"✅ {user.first_name} can now use **{perm_type}** forever."
            
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
        
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

# ---------------- MAIN EXECUTION ---------------- #

if __name__ == '__main__':
    # 1. Start the Web Server for Render/Replit
    keep_alive()

    # 2. Build the Bot
    application = ApplicationBuilder().token(TOKEN).build()

    # 3. Add Handlers
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('kick', kick_user))
    application.add_handler(CommandHandler('mute', mute_user))
    application.add_handler(CommandHandler('promote', promote_user))
    application.add_handler(CommandHandler('demote', demote_user))
    application.add_handler(CommandHandler('permission', set_permission))

    # 4. Run
    print("Bot is polling...")
    application.run_polling()
