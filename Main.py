import logging
import asyncio
import re
from datetime import datetime, timedelta
from telegram import ChatPermissions, Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler
from telegram.constants import ChatMemberStatus
from keep_alive import keep_alive

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# --- HELPER FUNCTIONS ---

async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Checks if the user issuing the command is an admin."""
    user = update.effective_user
    chat = update.effective_chat
    member = await chat.get_member(user.id)
    return member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]

def get_target_user(update: Update):
    """Extracts the target user from a reply or argument."""
    if update.message.reply_to_message:
        return update.message.reply_to_message.from_user
    return None

# --- MODERATION COMMANDS ---

async def kick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): return
    target = get_target_user(update)
    if target:
        await update.effective_chat.unban_member(target.id) # Kick = Unban (removes user but allows rejoin)
        await update.message.reply_text(f"👢 Kicked {target.first_name}.")
    else:
        await update.message.reply_text("Reply to a user to kick them.")

async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): return
    target = get_target_user(update)
    if target:
        await update.effective_chat.ban_member(target.id)
        await update.message.reply_text(f"🔨 Banned {target.first_name}.")
    else:
        await update.message.reply_text("Reply to a user to ban them.")

async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): return
    target = get_target_user(update)
    if target:
        # Restrict permissions to effectively mute
        mute_permissions = ChatPermissions(can_send_messages=False)
        await update.effective_chat.restrict_member(target.id, permissions=mute_permissions)
        await update.message.reply_text(f"cw Muted {target.first_name}.")
    else:
        await update.message.reply_text("Reply to a user to mute them.")

async def unmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): return
    target = get_target_user(update)
    if target:
        # Restore default permissions (adjust as needed for your group)
        unmute_permissions = ChatPermissions(
            can_send_messages=True,
            can_send_media_messages=True,
            can_send_other_messages=True,
            can_add_web_page_previews=True
        )
        await update.effective_chat.restrict_member(target.id, permissions=unmute_permissions)
        await update.message.reply_text(f"🔊 Unmuted {target.first_name}.")
    else:
        await update.message.reply_text("Reply to a user to unmute them.")

async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Deletes X messages.
    Usage: /clear 10
    """
    if not await is_admin(update, context): return
    
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /clear <number>")
        return

    try:
        amount = int(args[0])
    except ValueError:
        await update.message.reply_text("Please provide a valid number.")
        return

    # Telegram API constraint: Cannot delete messages older than 48h.
    # We delete the command message itself + 'amount' previous messages.
    message_id = update.message.message_id
    chat_id = update.effective_chat.id
    
    deleted_count = 0
    # Simple loop to delete messages going backwards
    # Note: Bulk delete is not fully supported in bots API for all messages, we iterate.
    for i in range(amount + 1): 
        try:
            await context.bot.delete_message(chat_id, message_id - i)
            deleted_count += 1
        except Exception:
            continue
    
    confirm_msg = await context.bot.send_message(chat_id, f"🗑 Cleared {deleted_count - 1} messages.")
    # Auto-delete confirmation after 3 seconds
    await asyncio.sleep(3)
    try:
        await context.bot.delete_message(chat_id, confirm_msg.message_id)
    except:
        pass

async def clear_undo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "❌ **Impossible**: Telegram API does not allow restoring deleted messages. Once deleted, they are gone forever."
    , parse_mode='Markdown')

async def promote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): return
    target = get_target_user(update)
    if target:
        await update.effective_chat.promote_member(
            target.id,
            can_manage_chat=True,
            can_delete_messages=True,
            can_invite_users=True,
            can_restrict_members=True,
            can_pin_messages=True,
            can_promote_members=False,
            can_manage_video_chats=True
        )
        await update.message.reply_text(f"⭐ Promoted {target.first_name} to Admin.")
    else:
        await update.message.reply_text("Reply to a user to promote them.")

async def demote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): return
    target = get_target_user(update)
    if target:
        await update.effective_chat.promote_member(
            target.id,
            can_manage_chat=False,
            can_delete_messages=False,
            can_invite_users=False,
            can_restrict_members=False,
            can_pin_messages=False,
            can_promote_members=False,
            can_manage_video_chats=False
        )
        await update.message.reply_text(f"📉 Demoted {target.first_name}.")
    else:
        await update.message.reply_text("Reply to a user to demote them.")

async def invite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Creates a custom invite link.
    Usage: /invite limit=1 time=30m
    """
    if not await is_admin(update, context): return

    limit = 0 # Unlimited by default
    expire_seconds = 0 # Never expires by default
    
    # Parse arguments
    for arg in context.args:
        if arg.startswith("limit="):
            limit = int(arg.split("=")[1])
        elif arg.startswith("time="):
            t_str = arg.split("=")[1]
            if 'm' in t_str:
                expire_seconds = int(t_str.replace('m', '')) * 60
            elif 'h' in t_str:
                expire_seconds = int(t_str.replace('h', '')) * 3600
            elif 'd' in t_str:
                expire_seconds = int(t_str.replace('d', '')) * 86400

    expire_date = datetime.now() + timedelta(seconds=expire_seconds) if expire_seconds > 0 else None
    
    try:
        link = await update.effective_chat.create_invite_link(
            member_limit=limit if limit > 0 else None,
            expire_date=expire_date
        )
        
        msg = f"🔗 **New Invite Link**\n\nLink: {link.invite_link}"
        if limit > 0: msg += f"\nUsers: {limit}"
        if expire_seconds > 0: msg += f"\nExpires: in {int(expire_seconds/60)} mins"
        
        await update.message.reply_text(msg, parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f"Error creating link: {e}")

# --- MAIN CONFIG ---

if __name__ == '__main__':
    # REPLACE 'YOUR_BOT_TOKEN' WITH YOUR ACTUAL TOKEN DIRECTLY OR USE OS.ENVIRON
    import os
    TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")

    keep_alive() # Start the web server to keep Render awake

    application = ApplicationBuilder().token(TOKEN).build()

    application.add_handler(CommandHandler("kick", kick))
    application.add_handler(CommandHandler("ban", ban))
    application.add_handler(CommandHandler("mute", mute))
    application.add_handler(CommandHandler("unmute", unmute))
    application.add_handler(CommandHandler("clear", clear))
    application.add_handler(CommandHandler("undo", clear_undo)) # Handler for 'clear undo' request
    application.add_handler(CommandHandler("promote", promote))
    application.add_handler(CommandHandler("demote", demote)) # Assuming 'deprompt' meant demote
    application.add_handler(CommandHandler("invite", invite))

    print("Bot is running...")
    application.run_polling()
