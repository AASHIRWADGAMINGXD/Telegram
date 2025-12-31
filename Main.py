import os
import logging
import asyncio
import requests
from datetime import datetime, timedelta
from collections import defaultdict, deque
from typing import Dict, List
import re

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatMember
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ChatJoinRequestHandler, filters, ContextTypes

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Environment variables
TOKEN = os.getenv('BOT_TOKEN')
if not TOKEN:
    raise ValueError("BOT_TOKEN environment variable is required.")

OWNER_ID = int(os.getenv('OWNER_ID', 0))  # Optional, for broadcast

# In-memory storage (for single file, no persistence)
chat_settings = defaultdict(lambda: {
    'welcome_msg': 'Welcome to the group, {username}!',
    'antilink': False,
    'autoreplies': {},  # trigger: response
    'special_links': {},  # url_pattern: [messages]
    'recent_msgs': deque(maxlen=100),  # message ids for clear
    'chat_ids': set(),  # for broadcast, but we'll use a global
    'join_counts': {},  # for anti-raid: timestamp: count
    'invite_links': {}  # name: {'link': str, 'max_uses': int, 'expire': datetime}
})
global_chat_ids = set()  # All chats for broadcast

# Anti-raid settings
RAID_THRESHOLD = 5
RAID_WINDOW = 60  # seconds

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    await update.message.reply_text('Hi! I am your Telegram bot. Use /help for commands.')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    help_text = """
Available commands:
/start - Start the bot
/help - Show this help
/add @user - Add user to broadcast list (admin only)
/broadcast <msg> - Broadcast message (owner only)
/shortener <url> - Shorten URL with TinyURL
/kick @user - Kick user
/ban @user - Ban user
/mute @user - Mute user
/umute @user - Unmute user
/clear <num> - Delete last <num> messages
/lock - Restrict new members
/setwelcome <msg> - Set welcome message
/shout <msg> - Shout message (bold)
/autoreply <trigger> <response> - Set auto reply
/special_link <url> <msg1>|<msg2> - Set special link replies
/antilink on/off - Toggle anti-link
/antiRaid on/off - Toggle anti-raid (placeholder)
/link <name> <max_uses> <expire_days> - Create invite link with approval
    """
    await update.message.reply_text(help_text)

async def add_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Add user to broadcast list (simple, add chat_id)."""
    if not update.effective_chat or not update.effective_chat.id in global_chat_ids:
        global_chat_ids.add(update.effective_chat.id)
    await update.message.reply_text('Chat added to broadcast list.')

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Broadcast message to all chats."""
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text('Not authorized.')
        return
    if not context.args:
        await update.message.reply_text('Usage: /broadcast <message>')
        return
    msg = ' '.join(context.args)
    for chat_id in list(global_chat_ids):
        try:
            await context.bot.send_message(chat_id=chat_id, text=msg)
        except Exception as e:
            logger.error(f"Failed to broadcast to {chat_id}: {e}")
    await update.message.reply_text('Broadcast sent.')

async def shortener(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Shorten URL using TinyURL."""
    if not context.args:
        await update.message.reply_text('Usage: /shortener <url>')
        return
    long_url = ' '.join(context.args)
    api_url = f'http://tinyurl.com/api-create.php?url={long_url}'
    try:
        response = requests.get(api_url)
        if response.status_code == 200:
            short_url = response.text.strip()
            await update.message.reply_text(f'Shortened: {short_url}')
        else:
            await update.message.reply_text('Failed to shorten URL.')
    except Exception as e:
        logger.error(e)
        await update.message.reply_text('Error shortening URL.')

async def kick_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Kick a user."""
    if not await is_admin(update, context):
        return
    if not context.args:
        await update.message.reply_text('Usage: /kick @username')
        return
    user = context.args[0].replace('@', '')
    try:
        # Find user by username or reply
        if update.message.reply_to_message:
            user_id = update.message.reply_to_message.from_user.id
        else:
            # Simple, assume mentioned
            members = await context.bot.get_chat_members(update.effective_chat.id)
            user_id = next((m.user.id for m in members if m.user.username == user), None)
            if not user_id:
                await update.message.reply_text('User not found.')
                return
        await context.bot.ban_chat_member(update.effective_chat.id, user_id)
        await context.bot.unban_chat_member(update.effective_chat.id, user_id)  # Kick
        await update.message.reply_text(f'User {user} kicked.')
    except Exception as e:
        logger.error(e)
        await update.message.reply_text('Failed to kick user.')

async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ban a user."""
    if not await is_admin(update, context):
        return
    # Similar to kick, but just ban
    if not context.args and not update.message.reply_to_message:
        await update.message.reply_text('Usage: /ban @username or reply to message')
        return
    if update.message.reply_to_message:
        user_id = update.message.reply_to_message.from_user.id
    else:
        user = context.args[0].replace('@', '') if context.args else None
        if not user:
            return
        # Find user_id similar...
        await update.message.reply_text('Reply or mention for simplicity.')
        return  # Placeholder
    try:
        await context.bot.ban_chat_member(update.effective_chat.id, user_id)
        await update.message.reply_text('User banned.')
    except Exception as e:
        logger.error(e)
        await update.message.reply_text('Failed to ban.')

async def mute_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mute a user (restrict)."""
    if not await is_admin(update, context):
        return
    # Similar
    if update.message.reply_to_message:
        user_id = update.message.reply_to_message.from_user.id
    else:
        return
    try:
        until_date = datetime.now() + timedelta(hours=1)  # 1 hour
        await context.bot.restrict_chat_member(update.effective_chat.id, user_id, until_date=until_date)
        await update.message.reply_text('User muted for 1 hour.')
    except Exception as e:
        logger.error(e)

async def umute_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Unmute a user."""
    if not await is_admin(update, context):
        return
    if update.message.reply_to_message:
        user_id = update.message.reply_to_message.from_user.id
    else:
        return
    try:
        await context.bot.restrict_chat_member(update.effective_chat.id, user_id, permissions=ChatMember().permissions)  # Full perms
        await update.message.reply_text('User unmuted.')
    except Exception as e:
        logger.error(e)

async def clear_messages(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Clear last N messages."""
    if not await is_admin(update, context):
        return
    try:
        num = int(context.args[0]) if context.args else 5
    except:
        await update.message.reply_text('Usage: /clear <num>')
        return
    chat_id = update.effective_chat.id
    settings = chat_settings[chat_id]
    deleted = 0
    for _ in range(num):
        if settings['recent_msgs']:
            msg_id = settings['recent_msgs'].pop()
            try:
                await context.bot.delete_message(chat_id, msg_id)
                deleted += 1
            except:
                pass
    await update.message.reply_text(f'Deleted {deleted} messages.')

async def lock_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Lock chat (restrict new members)."""
    if not await is_admin(update, context):
        return
    chat_id = update.effective_chat.id
    try:
        # Restrict all to only admins can send, but for lock new, perhaps set pending join
        # Or restrict new members
        await context.bot.set_chat_permissions(chat_id, permissions=...)  # Placeholder, need to define
        await update.message.reply_text('Chat locked.')
    except Exception as e:
        logger.error(e)

async def set_welcome(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Set welcome message."""
    if not await is_admin(update, context):
        return
    if not context.args:
        await update.message.reply_text('Usage: /setwelcome <message>')
        return
    msg = ' '.join(context.args)
    chat_id = update.effective_chat.id
    chat_settings[chat_id]['welcome_msg'] = msg
    await update.message.reply_text('Welcome message set.')

async def shout_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Shout message (bold)."""
    if not context.args:
        await update.message.reply_text('Usage: /shout <message>')
        return
    msg = ' '.join(context.args).upper()
    await update.message.reply_text(f'**{msg}**', parse_mode='Markdown')

async def set_autoreply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Set auto reply: /autoreply trigger response"""
    if not await is_admin(update, context):
        return
    if len(context.args) < 2:
        await update.message.reply_text('Usage: /autoreply <trigger> <response>')
        return
    trigger = context.args[0].lower()
    response = ' '.join(context.args[1:])
    chat_id = update.effective_chat.id
    chat_settings[chat_id]['autoreplies'][trigger] = response
    await update.message.reply_text('Auto reply set.')

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle messages for auto reply, anti link, special link, recent msgs, anti raid."""
    chat_id = update.effective_chat.id
    if update.message:
        # Store recent msg id
        chat_settings[chat_id]['recent_msgs'].append(update.message.message_id)
        
        text = update.message.text.lower() if update.message.text else ''
        
        # Auto reply
        for trigger, resp in chat_settings[chat_id]['autoreplies'].items():
            # Simple contains, ignore case
            if trigger in text.replace('.', ' ').replace(' ', ''):  # As per desc, dot or space don't matter
                await update.message.reply_text(resp)
                break
        
        # Special link - assume if url in special_links, reply with list
        if update.message.entities:
            for entity in update.message.entities:
                if entity.type == 'url' or entity.type == 'text_link':
                    url = update.message.text[entity.offset:entity.offset+entity.length].lower()
                    if url in chat_settings[chat_id]['special_links']:
                        for msg in chat_settings[chat_id]['special_links'][url]:
                            await update.message.reply_text(msg)
        
        # Anti link
        if chat_settings[chat_id]['antilink'] and re.search(r'http[s]?://', text) and not await is_admin(update, context):
            await update.message.delete()
            await context.bot.send_message(chat_id, 'Links are not allowed!')
        
        # Anti raid placeholder
        if update.message.new_chat_members:
            # Handle new members
            now = datetime.now()
            settings = chat_settings[chat_id]
            if 'last_raid_check' not in settings:
                settings['last_raid_check'] = now
            if (now - settings['last_raid_check']).seconds > RAID_WINDOW:
                settings['join_count'] = 0
            settings['join_count'] += len(update.message.new_chat_members)
            settings['last_raid_check'] = now
            if settings['join_count'] > RAID_THRESHOLD:
                # Restrict new members
                try:
                    await context.bot.set_chat_permissions(chat_id, permissions=None)  # Or restrict
                    await update.message.reply_text('Anti-raid activated!')
                except:
                    pass
            # Send welcome
            for member in update.message.new_chat_members:
                username = member.username or member.first_name
                welcome = chat_settings[chat_id]['welcome_msg'].format(username=username)
                await update.message.reply_text(welcome)

async def set_special_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Set special link: /special_link url msg1|msg2"""
    if not await is_admin(update, context):
        return
    if len(context.args) < 2:
        await update.message.reply_text('Usage: /special_link <url> <msg1>|<msg2>...')
        return
    url = context.args[0]
    msgs_str = ' '.join(context.args[1:])
    msgs = [m.strip() for m in msgs_str.split('|')]
    chat_id = update.effective_chat.id
    chat_settings[chat_id]['special_links'][url.lower()] = msgs
    await update.message.reply_text('Special link set.')

async def toggle_antilink(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Toggle anti-link."""
    if not await is_admin(update, context):
        return
    chat_id = update.effective_chat.id
    chat_settings[chat_id]['antilink'] = not chat_settings[chat_id]['antilink']
    status = 'on' if chat_settings[chat_id]['antilink'] else 'off'
    await update.message.reply_text(f'Anti-link {status}.')

# Placeholder for antiRaid toggle
async def toggle_antiraid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Toggle anti-raid."""
    if not await is_admin(update, context):
        return
    # Implement toggle if needed
    await update.message.reply_text('Anti-raid toggled (placeholder).')

async def create_invite_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Create invite link with approval: /link name max_uses expire_days"""
    if not await is_admin(update, context):
        return
    if len(context.args) < 3:
        await update.message.reply_text('Usage: /link <name> <max_uses> <expire_days>')
        return
    name = context.args[0]
    try:
        max_uses = int(context.args[1])
        expire_days = int(context.args[2])
    except:
        await update.message.reply_text('Max_uses and expire_days must be integers.')
        return
    chat_id = update.effective_chat.id
    expire_date = datetime.now() + timedelta(days=expire_days)
    try:
        link = await context.bot.create_chat_invite_link(
            chat_id,
            name=name,
            member_limit=max_uses,
            expiration_date=expire_date,
            creates_join_request=True
        )
        chat_settings[chat_id]['invite_links'][name] = {
            'link': link.invite_link,
            'max_uses': max_uses,
            'expire': expire_date
        }
        await update.message.reply_text(f'Invite link created: {link.invite_link}')
    except Exception as e:
        logger.error(e)
        await update.message.reply_text('Failed to create link.')

pending_approvals = {}  # join_request_id: {'user': user, 'msg_id': msg_id}

async def handle_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle join requests."""
    chat_id = update.effective_chat.id
    user = update.effective_chat_join_request.from_user
    join_request_id = update.effective_chat_join_request.join_request_id  # Actually, it's update.chat_join_request
    # Note: update.chat_join_request
    username = user.username or user.first_name
    
    # Create inline keyboard
    keyboard = [
        [
            InlineKeyboardButton("Yes", callback_data=f"approve_{user.id}"),
            InlineKeyboardButton("No", callback_data=f"decline_{user.id}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    msg = await context.bot.send_message(
        chat_id,
        f"Hey, {username} is requesting to join.\nYes or No?",
        reply_markup=reply_markup
    )
    
    pending_approvals[user.id] = {'request': update.chat_join_request, 'msg_id': msg.message_id, 'chat_id': chat_id}

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle callback for approvals."""
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = int(data.split('_')[1])
    if user_id not in pending_approvals:
        return
    
    pending = pending_approvals[user_id]
    chat_id = pending['chat_id']
    
    # Check if callback from admin
    if not await is_admin_for_callback(query, context, chat_id):
        await query.edit_message_text('Only admins can approve.')
        return
    
    if data.startswith('approve_'):
        try:
            await context.bot.approve_chat_join_request(pending['request'].chat.id, pending['request'].from_user.id)
            await query.edit_message_text(f'{pending["request"].from_user.first_name} approved and joined.')
            # DM welcome if needed
        except Exception as e:
            logger.error(e)
    else:  # decline
        try:
            await context.bot.decline_chat_join_request(pending['request'].chat.id, pending['request'].from_user.id)
            await query.edit_message_text(f'{pending["request"].from_user.first_name} rejected.')
            # DM sorry
            try:
                await context.bot.send_message(
                    pending['request'].from_user.id,
                    f"Sorry {pending['request'].from_user.first_name}, you can't join. You were rejected by owner/admin."
                )
            except:
                pass
        except Exception as e:
            logger.error(e)
    
    # Delete the message
    try:
        await context.bot.delete_message(chat_id, pending['msg_id'])
    except:
        pass
    del pending_approvals[user_id]

async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Check if user is admin."""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        return member.status in ['administrator', 'creator']
    except:
        return False

async def is_admin_for_callback(query, context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> bool:
    """Check admin for callback."""
    user_id = query.from_user.id
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        return member.status in ['administrator', 'creator']
    except:
        return False

def main() -> None:
    """Start the bot."""
    application = Application.builder().token(TOKEN).build()

    # Commands
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("add", add_user))
    application.add_handler(CommandHandler("broadcast", broadcast))
    application.add_handler(CommandHandler("shortener", shortener))
    application.add_handler(CommandHandler("kick", kick_user))
    application.add_handler(CommandHandler("ban", ban_user))
    application.add_handler(CommandHandler("mute", mute_user))
    application.add_handler(CommandHandler("umute", umute_user))
    application.add_handler(CommandHandler("clear", clear_messages))
    application.add_handler(CommandHandler("lock", lock_chat))
    application.add_handler(CommandHandler("setwelcome", set_welcome))
    application.add_handler(CommandHandler("shout", shout_message))
    application.add_handler(CommandHandler("autoreply", set_autoreply))
    application.add_handler(CommandHandler("special_link", set_special_link))
    application.add_handler(CommandHandler("antilink", toggle_antilink))
    application.add_handler(CommandHandler("antiraid", toggle_antiraid))
    application.add_handler(CommandHandler("link", create_invite_link))

    # Handlers
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_handler(ChatJoinRequestHandler(handle_join_request))

    # Run the bot until the user presses Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
