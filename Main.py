import os
import logging
import asyncio
import requests
from telegram import Update, ChatPermissions
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    filters
)
from telegram.constants import ParseMode
from dotenv import load_dotenv
from keep_alive import keep_alive

# 1. Load Environment & Validate
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = os.getenv("OWNER_ID")

if not BOT_TOKEN:
    raise ValueError("Error: BOT_TOKEN is missing in .env file. The world cannot exist without a core.")

# 2. Setup Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Temporary storage for broadcast (In production, use a Database)
active_chats = set()

# --- Helper Functions ---
def is_admin(user_id):
    """Check if user is the Owner (God)"""
    return str(user_id) == str(OWNER_ID)

async def check_bot_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Check if Pain has permission to judge."""
    chat = update.effective_chat
    bot_member = await chat.get_member(context.bot.id)
    if not bot_member.status == 'administrator':
        await update.message.reply_text("I lack the power (Admin Rights) to perform this judgement.")
        return False
    return True

# --- Commands ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    active_chats.add(chat_id)
    await update.message.reply_text(
        "**I am Pain.**\n\n"
        "We are but men, drawn to act in the name of revenge that we deem to be justice.\n\n"
        "Commands:\n"
        "/shout <msg> - Let the world hear you\n"
        "/ban, /kick, /mute - Deliver judgement\n"
        "/promote, /demote - Grant or strip power\n"
        "/permission - Control the flow of media\n"
        "/linkshort <url> - Shorten the path\n"
        "/broadcast - Speak to all (Owner only)",
        parse_mode=ParseMode.MARKDOWN
    )

async def shout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("You must speak words for them to be heard.")
        return
    text = ' '.join(context.args).upper()
    await update.message.reply_text(f"📢 **{text}**", parse_mode=ParseMode.MARKDOWN)

async def link_short(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Give me the link, and I shall shorten the distance.")
        return
    
    url = context.args[0]
    try:
        # Using TinyURL API (No auth required for basic use)
        api_url = f"http://tinyurl.com/api-create.php?url={url}"
        response = requests.get(api_url)
        if response.status_code == 200:
            await update.message.reply_text(f"The path is shortened:\n{response.text}")
        else:
            await update.message.reply_text("The connection was severed. Error shortening link.")
    except Exception as e:
        logger.error(e)
        await update.message.reply_text("Unknown pain occurred.")

# --- Moderation Tools ---

async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_bot_admin(update, context): return
    if not update.message.reply_to_message:
        await update.message.reply_text("Reply to a soul to banish them.")
        return

    user_to_ban = update.message.reply_to_message.from_user
    try:
        await context.bot.ban_chat_member(update.effective_chat.id, user_to_ban.id)
        await update.message.reply_text(f"Almighty Push. {user_to_ban.first_name} has been banished.")
    except Exception as e:
        await update.message.reply_text(f"I cannot banish them. {e}")

async def kick_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_bot_admin(update, context): return
    if not update.message.reply_to_message:
        await update.message.reply_text("Reply to a soul to kick them.")
        return

    user_to_kick = update.message.reply_to_message.from_user
    try:
        await context.bot.ban_chat_member(update.effective_chat.id, user_to_kick.id)
        await context.bot.unban_chat_member(update.effective_chat.id, user_to_kick.id) # Unban immediately allows rejoin
        await update.message.reply_text(f"Feel pain. {user_to_kick.first_name} was kicked.")
    except Exception as e:
        await update.message.reply_text(f"Resistance encountered. {e}")

async def mute_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_bot_admin(update, context): return
    if not update.message.reply_to_message:
        await update.message.reply_text("Reply to a soul to silence them.")
        return
    
    user_to_mute = update.message.reply_to_message.from_user
    permissions = ChatPermissions(can_send_messages=False)
    
    try:
        await context.bot.restrict_chat_member(update.effective_chat.id, user_to_mute.id, permissions=permissions)
        await update.message.reply_text(f"Silence. {user_to_mute.first_name} is now mute.")
    except Exception as e:
        await update.message.reply_text(f"Failed to silence. {e}")

# --- Administrative Tools ---

async def promote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_bot_admin(update, context): return
    if not update.message.reply_to_message:
        await update.message.reply_text("Reply to the one who seeks power.")
        return

    user = update.message.reply_to_message.from_user
    try:
        await context.bot.promote_chat_member(
            chat_id=update.effective_chat.id,
            user_id=user.id,
            can_manage_chat=True,
            can_delete_messages=True,
            can_invite_users=True,
            can_restrict_members=True,
            can_pin_messages=True
        )
        await update.message.reply_text(f"{user.first_name} has ascended.")
    except Exception as e:
        await update.message.reply_text(f"Cannot promote. {e}")

async def demote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_bot_admin(update, context): return
    if not update.message.reply_to_message:
        await update.message.reply_text("Reply to the one who must fall.")
        return

    user = update.message.reply_to_message.from_user
    try:
        await context.bot.promote_chat_member(
            chat_id=update.effective_chat.id,
            user_id=user.id,
            can_manage_chat=False,
            can_delete_messages=False,
            can_invite_users=False
        )
        await update.message.reply_text(f"{user.first_name} has returned to the earth.")
    except Exception as e:
        await update.message.reply_text(f"Cannot demote. {e}")

# --- Permission Management ---

async def permissions_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Usage: /permission gif off
    """
    if not await check_bot_admin(update, context): return
    
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /permission [media/gif/messages] [on/off]")
        return

    target = context.args[0].lower()
    state = context.args[1].lower() == 'on'
    
    chat_id = update.effective_chat.id
    
    # Base permissions
    p = ChatPermissions(
        can_send_messages=True,
        can_send_media_messages=True,
        can_send_other_messages=True, # Controls GIFs/Stickers
        can_add_web_page_previews=True
    )

    msg_text = ""
    
    if target == 'gif':
        # Telegram groups 'can_send_other_messages' controls GIFs and Stickers
        p.can_send_other_messages = state
        msg_text = f"GIFs and Stickers are now {'enabled' if state else 'disabled'}."
    elif target == 'media':
        p.can_send_media_messages = state
        msg_text = f"Media is now {'enabled' if state else 'disabled'}."
    elif target == 'messages':
        p.can_send_messages = state
        msg_text = f"Messages are now {'enabled' if state else 'disabled'}."
    else:
        await update.message.reply_text("Unknown target. Use: gif, media, or messages.")
        return

    try:
        await context.bot.set_chat_permissions(chat_id, p)
        await update.message.reply_text(f"Order restored. {msg_text}")
    except Exception as e:
        await update.message.reply_text(f"Failed to change permissions. {e}")

# --- Owner Tools ---

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("You are not God. You cannot command me.")
        return

    if not context.args:
        await update.message.reply_text("Give me the message to spread pain.")
        return

    message = ' '.join(context.args)
    count = 0
    for chat in active_chats:
        try:
            await context.bot.send_message(chat, f"**[Divine Broadcast]**\n\n{message}", parse_mode=ParseMode.MARKDOWN)
            count += 1
        except:
            pass # Ignore chats where bot was kicked
    
    await update.message.reply_text(f"Message delivered to {count} realms.")

async def login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fake login - just confirms identity based on ENV"""
    user_id = update.effective_user.id
    if is_admin(user_id):
        await update.message.reply_text("I know you. You are the one who pulls the strings.")
    else:
        await update.message.reply_text("Who are you? You are nothing.")

async def tracker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Silently tracks active chats for broadcast"""
    if update.effective_chat:
        active_chats.add(update.effective_chat.id)

# --- Main Execution ---

def main():
    # Start Keep Alive for Hostings like Render/Replit
    keep_alive()

    application = ApplicationBuilder().token(BOT_TOKEN).build()

    # Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("shout", shout))
    application.add_handler(CommandHandler("linkshort", link_short))
    
    # Moderation
    application.add_handler(CommandHandler("ban", ban_user))
    application.add_handler(CommandHandler("kick", kick_user))
    application.add_handler(CommandHandler("mute", mute_user))
    application.add_handler(CommandHandler("promote", promote))
    application.add_handler(CommandHandler("demote", demote))
    application.add_handler(CommandHandler("permission", permissions_handler))
    
    # Owner
    application.add_handler(CommandHandler("broadcast", broadcast))
    application.add_handler(CommandHandler("login", login))

    # Passive Tracker (Must be last to capture chat IDs)
    application.add_handler(MessageHandler(filters.ALL, tracker))

    print("Pain is awake. The world shall know pain...")
    application.run_polling()

if __name__ == '__main__':
    main()
