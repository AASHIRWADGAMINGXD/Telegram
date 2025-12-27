import os
import logging
import asyncio
from dotenv import load_dotenv
from telegram import Update, ChatPermissions
from telegram.ext import (
    ApplicationBuilder, 
    ContextTypes, 
    CommandHandler, 
    MessageHandler, 
    filters
)
from keep_alive import keep_alive

# 1. LOAD ENVIRONMENT
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    print("❌ Error: BOT_TOKEN not found in .env file.")
    exit(1)

# 2. LOGGING CONFIG
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# 3. MEMORY STORAGE
# Stores Anti-Raid status per chat: { chat_id: True/False }
anti_raid_status = {} 

# --- 🧠 THE BOT BRAIN (Safety & Helper Functions) ---

async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    """Checks if a specific user ID is an admin in the chat."""
    try:
        member = await context.bot.get_chat_member(update.effective_chat.id, user_id)
        return member.status in ['administrator', 'creator']
    except:
        return False

async def check_authority(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    1. Checks if the command sender is Admin.
    2. Sends a rejection message if not.
    """
    user_id = update.effective_user.id
    if not await is_admin(update, context, user_id):
        await update.message.reply_text("⛔ **Access Denied:** Administrators only.")
        return False
    return True

async def get_target(update: Update):
    """Safely gets the user replying to."""
    if not update.message.reply_to_message:
        await update.message.reply_text("⚠️ Reply to a user's message to perform this action.")
        return None
    return update.message.reply_to_message.from_user

async def safety_check(update: Update, context: ContextTypes.DEFAULT_TYPE, target_user) -> bool:
    """
    THE BRAIN: 
    - Prevents bot from targeting itself.
    - Prevents bot from targeting other admins.
    """
    # 1. Don't attack self
    if target_user.id == context.bot.id:
        await update.message.reply_text("🤖 **System Protocol:** I cannot ban or mute myself.")
        return False
    
    # 2. Don't attack admins
    if await is_admin(update, context, target_user.id):
        await update.message.reply_text(f"🛡️ **Security:** I cannot punish Admin {target_user.first_name}.")
        return False
        
    return True

# --- 🛠️ FEATURE COMMANDS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 **Professional Manager Bot Online**\n\n"
        "**Commands:**\n"
        "• /antiraid - Toggle Raid Protection\n"
        "• /shout <msg> - Pin & Notify\n"
        "• /clear - Delete replied message\n"
        "• /pin & /unpin\n"
        "• /kick, /mute, /ban\n"
        "• /banchannel - Permaban from channel"
    )

async def cmd_clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_authority(update, context): return
    
    # If replied to a message, delete that message and the command
    if update.message.reply_to_message:
        try:
            await update.message.reply_to_message.delete()
            await update.message.delete()
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {e}")
    else:
        await update.message.reply_text("Usage: Reply to the message you want to /clear.")

async def cmd_shout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_authority(update, context): return
    
    args = context.args
    if not args:
        return await update.message.reply_text("Usage: `/shout <message>`", parse_mode='Markdown')
    
    text = " ".join(args).upper()
    try:
        # Send message
        msg = await update.message.reply_text(f"📢 **ANNOUNCEMENT**\n\n{text}", parse_mode='Markdown')
        # Pin with notification
        await msg.pin(disable_notification=False)
    except Exception as e:
        await update.message.reply_text("⚠️ Could not pin. Check my admin permissions.")

async def cmd_pin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_authority(update, context): return
    if not update.message.reply_to_message: return await update.message.reply_text("Reply to a message to pin.")
    
    try:
        await update.message.reply_to_message.pin()
        await update.message.reply_text("📌 **Pinned.**")
    except:
        await update.message.reply_text("❌ Failed to pin.")

async def cmd_unpin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_authority(update, context): return
    if not update.message.reply_to_message: return await update.message.reply_text("Reply to a message to unpin.")
    
    try:
        await update.message.reply_to_message.unpin()
        await update.message.reply_text("Message unpinned.")
    except:
        await update.message.reply_text("❌ Failed to unpin.")

# --- ⚖️ MODERATION TOOLS ---

async def cmd_kick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_authority(update, context): return
    target = await get_target(update)
    if not target: return
    
    # Run Safety Checks (Brain)
    if not await safety_check(update, context, target): return

    try:
        await context.bot.ban_chat_member(update.effective_chat.id, target.id)
        await context.bot.unban_chat_member(update.effective_chat.id, target.id) # Unban immediately allows rejoin
        await update.message.reply_text(f"👢 **{target.first_name}** was kicked.")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

async def cmd_ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Logic for /ban and /banchannel (Same function in Telegram API)"""
    if not await check_authority(update, context): return
    target = await get_target(update)
    if not target: return
    
    if not await safety_check(update, context, target): return

    try:
        # Ban permanently (User cannot open channel/group via link)
        await context.bot.ban_chat_member(update.effective_chat.id, target.id)
        await update.message.reply_text(f"⛔ **{target.first_name}** has been banned permanently.")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

async def cmd_mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_authority(update, context): return
    target = await get_target(update)
    if not target: return
    
    if not await safety_check(update, context, target): return

    try:
        # Restrict permissions to False
        permissions = ChatPermissions(can_send_messages=False)
        await context.bot.restrict_chat_member(update.effective_chat.id, target.id, permissions=permissions)
        await update.message.reply_text(f"🔇 **{target.first_name}** is now muted.")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

# --- 🛡️ ANTI RAID & AUTO REPLY ---

async def cmd_antiraid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_authority(update, context): return
    
    chat_id = update.effective_chat.id
    current_status = anti_raid_status.get(chat_id, False)
    
    # Toggle Status
    anti_raid_status[chat_id] = not current_status
    
    if not current_status:
        await update.message.reply_text(f"🚨 **ANTI-RAID ENABLED**\nBot is now watching `{update.effective_chat.title}`. Any new user joining will be kicked immediately.")
    else:
        await update.message.reply_text(f"✅ **Anti-Raid Disabled**\nNormal entry allowed.")

async def watcher_new_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Passive watcher.
    1. Checks if Anti-Raid is ON for this specific chat.
    2. If ON, kicks new members.
    """
    chat_id = update.effective_chat.id
    
    # Check if Anti-Raid is active in this specific group
    if anti_raid_status.get(chat_id, False):
        for member in update.message.new_chat_members:
            # Don't kick the bot
            if member.id == context.bot.id: continue
            
            try:
                await context.bot.ban_chat_member(chat_id, member.id)
                await context.bot.unban_chat_member(chat_id, member.id)
                await update.message.reply_text(f"🛡️ **Raid Protection:** Removed {member.first_name}")
            except:
                pass

async def watcher_autoreply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Passive text listener for auto-replies."""
    if not update.message or not update.message.text: return
    
    msg_text = update.message.text.lower()
    
    # Dictionary of triggers
    triggers = {
        "price": "💰 Check pinned message for prices!",
        "admin": "👨‍💻 Admins are currently busy, please wait.",
        "support": "📩 Contact @Owner for support.",
        "rules": "📜 Read the rules before chatting."
    }
    
    for word, response in triggers.items():
        if word in msg_text:
            await update.message.reply_text(response)
            break

# --- 🚀 RUNNER ---

if __name__ == '__main__':
    # 1. Start Web Server
    keep_alive()
    
    # 2. Build Bot
    print("🔥 System Starting...")
    application = ApplicationBuilder().token(TOKEN).build()
    
    # 3. Add Command Handlers
    application.add_handler(CommandHandler("start", start))
    
    # Feature Handlers
    application.add_handler(CommandHandler("clear", cmd_clear))
    application.add_handler(CommandHandler("shout", cmd_shout))
    application.add_handler(CommandHandler("pin", cmd_pin))
    application.add_handler(CommandHandler("unpin", cmd_unpin))
    
    # Moderation Handlers
    application.add_handler(CommandHandler("kick", cmd_kick))
    application.add_handler(CommandHandler("mute", cmd_mute))
    application.add_handler(CommandHandler("ban", cmd_ban))
    application.add_handler(CommandHandler("banchannel", cmd_ban)) # Alias
    
    # Security Handlers
    application.add_handler(CommandHandler("antiraid", cmd_antiraid))
    
    # Passive Watchers (Grouped to run alongside commands if needed)
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, watcher_new_members))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), watcher_autoreply))

    print("✅ Bot is Live and Polling.")
    application.run_polling()
