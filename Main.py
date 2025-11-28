import os
import json
import threading
import asyncio
from flask import Flask, request
from telegram import Update, ChatPermissions
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

app = Flask(__name__)

TOKEN = os.environ.get('TELEGRAM_TOKEN')
if not TOKEN:
    raise ValueError('TELEGRAM_TOKEN environment variable is required.')

PORT = int(os.environ.get('PORT', 5000))
DATA_FILE = 'data.json'

# Load persistent data
def load_data():
    try:
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {'settings': {}, 'warns': {}}

data = load_data()

def save_data():
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=4)

# Settings helpers (per chat)
def get_setting(chat_id: int, key: str):
    data['settings'].setdefault(chat_id, {})
    return data['settings'][chat_id].get(key, '')

def set_setting(chat_id: int, key: str, value: str):
    data['settings'].setdefault(chat_id, {})
    data['settings'][chat_id][key] = value
    save_data()

# Warns helpers (per chat/user)
def get_warns(user_id: int, chat_id: int):
    data['warns'].setdefault(chat_id, {})
    return data['warns'][chat_id].get(user_id, 0)

def set_warns(user_id: int, chat_id: int, count: int):
    data['warns'].setdefault(chat_id, {})
    data['warns'][chat_id][user_id] = count
    save_data()

# Bot application
application = Application.builder().token(TOKEN).build()

# Command: /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('Hello! I am a moderator bot with 30+ features. Use /help for commands.')

application.add_handler(CommandHandler("start", start))

# Command: /help
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
/ping - Check bot status
/id - Your user ID
/info [user_id] - User info
/ban - Ban replied user
/unban - Unban replied user
/kick - Kick replied user
/mute [seconds] - Mute replied user
/unmute - Unmute replied user
/warn [reason] - Warn replied user
/unwarn - Remove warn from replied user
/warns - Show warns for replied/self user
/del - Delete replied message
/purge [count] - Purge last N messages (default 5)
/rules - Show group rules
/setrules <rules> - Set group rules
/welcome - Show welcome message
/setwelcome <msg> - Set welcome (use {name})
/goodbye - Show goodbye message
/setgoodbye <msg> - Set goodbye (use {name})
/pin - Pin replied message
/unpin - Unpin message
/promote - Promote replied user to admin
/demote - Demote replied user
/lock - Lock chat (restrict non-admins from sending messages)
/unlock - Unlock chat
/slowmode [seconds] - Set slow mode delay
/stats - Group member count
/broadcast <msg> - Send message to group
    """
    await update.message.reply_text(help_text)

application.add_handler(CommandHandler("help", help_command))

# Command: /ping
async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('Pong! Bot is alive.')

application.add_handler(CommandHandler("ping", ping))

# Command: /id
async def id_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(f'Your ID: {user.id}')

application.add_handler(CommandHandler("id", id_command))

# Command: /info
async def info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if context.args:
        try:
            user_id = int(context.args[0])
            user = await context.bot.get_chat(user_id)
        except:
            await update.message.reply_text('Invalid user ID.')
            return
    else:
        user = update.effective_user
    text = f"Name: {user.first_name or ''}\nID: {user.id}\nUsername: @{user.username or 'None'}"
    await update.message.reply_text(text)

application.add_handler(CommandHandler("info", info))

# Command: /ban
async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text('Reply to a user message to ban.')
        return
    user = update.message.reply_to_message.from_user
    chat = update.effective_chat
    if not await context.bot.get_chat_member(chat.id, context.bot.id).can_restrict_members:
        await update.message.reply_text('Bot lacks ban permission.')
        return
    await context.bot.ban_chat_member(chat_id=chat.id, user_id=user.id)
    await update.message.reply_text(f'Banned {user.first_name}.')

application.add_handler(CommandHandler("ban", ban))

# Command: /unban
async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text('Reply to a user message to unban.')
        return
    user = update.message.reply_to_message.from_user
    chat = update.effective_chat
    if not await context.bot.get_chat_member(chat.id, context.bot.id).can_restrict_members:
        await update.message.reply_text('Bot lacks unban permission.')
        return
    await context.bot.unban_chat_member(chat_id=chat.id, user_id=user.id)
    await update.message.reply_text(f'Unbanned {user.first_name}.')

application.add_handler(CommandHandler("unban", unban))

# Command: /kick
async def kick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text('Reply to a user message to kick.')
        return
    user = update.message.reply_to_message.from_user
    chat = update.effective_chat
    if not await context.bot.get_chat_member(chat.id, context.bot.id).can_restrict_members:
        await update.message.reply_text('Bot lacks kick permission.')
        return
    await context.bot.ban_chat_member(chat_id=chat.id, user_id=user.id)
    await context.bot.unban_chat_member(chat_id=chat.id, user_id=user.id)
    await update.message.reply_text(f'Kicked {user.first_name}.')

application.add_handler(CommandHandler("kick", kick))

# Command: /mute
async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text('Reply to a user message to mute.')
        return
    user = update.message.reply_to_message.from_user
    chat = update.effective_chat
    if not await context.bot.get_chat_member(chat.id, context.bot.id).can_restrict_members:
        await update.message.reply_text('Bot lacks mute permission.')
        return
    until_date = None
    if context.args:
        try:
            until_date = int(context.args[0])
        except ValueError:
            await update.message.reply_text('Invalid time (use seconds).')
            return
    permissions = ChatPermissions(can_send_messages=False)
    await context.bot.restrict_chat_member(chat_id=chat.id, user_id=user.id, permissions=permissions, until_date=until_date)
    await update.message.reply_text(f'Muted {user.first_name}.')

application.add_handler(CommandHandler("mute", mute))

# Command: /unmute
async def unmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text('Reply to a user message to unmute.')
        return
    user = update.message.reply_to_message.from_user
    chat = update.effective_chat
    if not await context.bot.get_chat_member(chat.id, context.bot.id).can_restrict_members:
        await update.message.reply_text('Bot lacks unmute permission.')
        return
    permissions = ChatPermissions.all()
    await context.bot.restrict_chat_member(chat_id=chat.id, user_id=user.id, permissions=permissions)
    await update.message.reply_text(f'Unmuted {user.first_name}.')

application.add_handler(CommandHandler("unmute", unmute))

# Command: /warn
async def warn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text('Reply to a user message to warn.')
        return
    user = update.message.reply_to_message.from_user
    chat_id = update.effective_chat.id
    user_id = user.id
    count = get_warns(user_id, chat_id) + 1
    set_warns(user_id, chat_id, count)
    reason = ' '.join(context.args) if context.args else 'No reason'
    await update.message.reply_text(f'Warned {user.first_name}. Warns: {count}. Reason: {reason}')
    if count >= 3:
        await context.bot.ban_chat_member(chat_id=chat_id, user_id=user_id)
        await update.message.reply_text(f'Auto-banned {user.first_name} (3 warns reached).')

application.add_handler(CommandHandler("warn", warn))

# Command: /unwarn
async def unwarn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text('Reply to a user message to unwarn.')
        return
    user = update.message.reply_to_message.from_user
    chat_id = update.effective_chat.id
    count = get_warns(user.id, chat_id) - 1
    if count < 0:
        count = 0
    set_warns(user.id, chat_id, count)
    await update.message.reply_text(f'Unwarned {user.first_name}. Remaining: {count}')

application.add_handler(CommandHandler("unwarn", unwarn))

# Command: /warns
async def show_warns(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.reply_to_message:
        user = update.message.reply_to_message.from_user
    else:
        user = update.effective_user
    chat_id = update.effective_chat.id
    count = get_warns(user.id, chat_id)
    await update.message.reply_text(f'{user.first_name} has {count} warns.')

application.add_handler(CommandHandler("warns", show_warns))

# Command: /del
async def delete_last(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.reply_to_message:
        await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=update.message.reply_to_message.message_id)
    await update.message.delete()

application.add_handler(CommandHandler("del", delete_last))

# Command: /purge
async def purge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    count = int(context.args[0]) if context.args else 5
    chat_id = update.effective_chat.id
    message_id = update.message.message_id
    for i in range(count + 1):  # +1 to include command
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=message_id - i)
        except:
            pass

application.add_handler(CommandHandler("purge", purge))

# Command: /rules
async def rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    rules_text = get_setting(chat_id, 'rules')
    if not rules_text:
        await update.message.reply_text('No rules set.')
    else:
        await update.message.reply_text(rules_text)

application.add_handler(CommandHandler("rules", rules))

# Command: /setrules
async def set_rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text('Provide rules text.')
        return
    chat_id = update.effective_chat.id
    rules_text = ' '.join(context.args)
    set_setting(chat_id, 'rules', rules_text)
    await update.message.reply_text('Rules updated.')

application.add_handler(CommandHandler("setrules", set_rules))

# Handler: Welcome new members
async def welcome_new(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    welcome_msg = get_setting(chat_id, 'welcome')
    if welcome_msg:
        for member in update.message.new_chat_members:
            name = member.first_name or member.username or 'User'
            formatted = welcome_msg.format(name=name)
            await update.message.reply_text(formatted)

application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new))

# Command: /welcome
async def show_welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    welcome_msg = get_setting(chat_id, 'welcome')
    if not welcome_msg:
        await update.message.reply_text('No welcome message set.')
    else:
        await update.message.reply_text(welcome_msg)

application.add_handler(CommandHandler("welcome", show_welcome))

# Command: /setwelcome
async def set_welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text('Provide welcome text (use {name} for user name).')
        return
    chat_id = update.effective_chat.id
    msg = ' '.join(context.args)
    set_setting(chat_id, 'welcome', msg)
    await update.message.reply_text('Welcome message updated.')

application.add_handler(CommandHandler("setwelcome", set_welcome))

# Handler: Goodbye leaving members
async def goodbye(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.left_chat_member:
        user = update.message.left_chat_member
        chat_id = update.effective_chat.id
        goodbye_msg = get_setting(chat_id, 'goodbye')
        if goodbye_msg:
            name = user.first_name or user.username or 'User'
            formatted = goodbye_msg.format(name=name)
            await update.message.reply_text(formatted)

application.add_handler(MessageHandler(filters.StatusUpdate.LEFT_CHAT_MEMBER, goodbye))

# Command: /goodbye
async def show_goodbye(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    goodbye_msg = get_setting(chat_id, 'goodbye')
    if not goodbye_msg:
        await update.message.reply_text('No goodbye message set.')
    else:
        await update.message.reply_text(goodbye_msg)

application.add_handler(CommandHandler("goodbye", show_goodbye))

# Command: /setgoodbye
async def set_goodbye(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text('Provide goodbye text (use {name} for user name).')
        return
    chat_id = update.effective_chat.id
    msg = ' '.join(context.args)
    set_setting(chat_id, 'goodbye', msg)
    await update.message.reply_text('Goodbye message updated.')

application.add_handler(CommandHandler("setgoodbye", set_goodbye))

# Command: /pin
async def pin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text('Reply to a message to pin.')
        return
    if not await context.bot.get_chat_member(update.effective_chat.id, context.bot.id).can_pin_messages:
        await update.message.reply_text('Bot lacks pin permission.')
        return
    await context.bot.pin_chat_message(chat_id=update.effective_chat.id, message_id=update.message.reply_to_message.message_id)
    await update.message.reply_text('Message pinned.')

application.add_handler(CommandHandler("pin", pin))

# Command: /unpin
async def unpin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await context.bot.get_chat_member(update.effective_chat.id, context.bot.id).can_pin_messages:
        await update.message.reply_text('Bot lacks unpin permission.')
        return
    await context.bot.unpin_chat_message(chat_id=update.effective_chat.id)
    await update.message.reply_text('Message unpinned.')

application.add_handler(CommandHandler("unpin", unpin))

# Command: /promote
async def promote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text('Reply to a user message to promote.')
        return
    user = update.message.reply_to_message.from_user
    chat = update.effective_chat
    if not await context.bot.get_chat_member(chat.id, context.bot.id).can_promote_members:
        await update.message.reply_text('Bot lacks promote permission.')
        return
    await context.bot.promote_chat_member(chat_id=chat.id, user_id=user.id, can_change_info=False, can_delete_messages=True, can_restrict_members=True, can_invite_users=True, can_pin_messages=True, can_manage_video_chats=False, can_manage_chat=False)
    await update.message.reply_text(f'Promoted {user.first_name}.')

application.add_handler(CommandHandler("promote", promote))

# Command: /demote
async def demote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text('Reply to a user message to demote.')
        return
    user = update.message.reply_to_message.from_user
    chat = update.effective_chat
    if not await context.bot.get_chat_member(chat.id, context.bot.id).can_promote_members:
        await update.message.reply_text('Bot lacks demote permission.')
        return
    await context.bot.promote_chat_member(chat_id=chat.id, user_id=user.id, can_change_info=False, can_delete_messages=False, can_restrict_members=False, can_invite_users=False, can_pin_messages=False, can_manage_video_chats=False, can_manage_chat=False)
    await update.message.reply_text(f'Demoted {user.first_name}.')

application.add_handler(CommandHandler("demote", demote))

# Command: /lock
async def lock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if not await context.bot.get_chat_member(chat.id, context.bot.id).can_restrict_members:
        await update.message.reply_text('Bot lacks lock permission.')
        return
    permissions = ChatPermissions(
        can_send_messages=False,
        can_send_media_messages=False,
        can_send_polls=False,
        can_send_other_messages=False,
        can_add_web_page_previews=False
    )
    await context.bot.set_chat_permissions(chat_id=chat.id, permissions=permissions)
    await update.message.reply_text('Chat locked (non-admins cannot send messages).')

application.add_handler(CommandHandler("lock", lock))

# Command: /unlock
async def unlock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if not await context.bot.get_chat_member(chat.id, context.bot.id).can_restrict_members:
        await update.message.reply_text('Bot lacks unlock permission.')
        return
    permissions = ChatPermissions.all()
    await context.bot.set_chat_permissions(chat_id=chat.id, permissions=permissions)
    await update.message.reply_text('Chat unlocked.')

application.add_handler(CommandHandler("unlock", unlock))

# Command: /slowmode
async def slowmode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text('Provide seconds (0 to disable).')
        return
    try:
        seconds = int(context.args[0])
        if seconds < 0 or seconds > 600:
            raise ValueError
    except ValueError:
        await update.message.reply_text('Invalid: 0-600 seconds.')
        return
    chat = update.effective_chat
    if not await context.bot.get_chat_member(chat.id, context.bot.id).can_restrict_members:
        await update.message.reply_text('Bot lacks slowmode permission.')
        return
    await context.bot.set_chat_slow_mode_delay(chat_id=chat.id, slow_mode_delay=seconds)
    status = 'disabled' if seconds == 0 else f'set to {seconds}s'
    await update.message.reply_text(f'Slow mode {status}.')

application.add_handler(CommandHandler("slowmode", slowmode))

# Command: /stats
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    member_count = await context.bot.get_chat_member_count(chat.id)
    await update.message.reply_text(f'Group stats:\nMembers: {member_count}')

application.add_handler(CommandHandler("stats", stats))

# Command: /broadcast
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text('Provide message to broadcast.')
        return
    msg = ' '.join(context.args)
    await context.bot.send_message(chat_id=update.effective_chat.id, text=msg)
    await update.message.reply_text('Message broadcasted.')

application.add_handler(CommandHandler("broadcast", broadcast))

# Flask routes for Render keep-alive
@app.route('/')
def health():
    return 'Bot is running and healthy!'

@app.route('/keepalive', methods=['GET'])
def keepalive():
    return 'Keep-alive ping received.'

# Run bot in background thread (polling)
def run_bot():
    application.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    app.run(host='0.0.0.0', port=PORT, debug=False)
