import os
import logging
import re
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatMember
from telegram.ext import (
    ApplicationBuilder, 
    ContextTypes, 
    CommandHandler, 
    MessageHandler, 
    CallbackQueryHandler, 
    filters
)
from keep_alive import keep_alive

# --- LOGGING ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- CONFIG ---
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_PASSWORD = os.getenv("ADMIN_PASS", "BhaiKaSystem")
# The owner's Telegram ID to prevent them from being restricted/blocked
OWNER_ID = 5122557555 # Replace with the actual Telegram ID for @AashirwadGamerzz

# --- IN-MEMORY DATABASE ---
authorized_users = set()
warns = {}
afk_users = {}
auto_replies = {}
blocked_users = set() # NEW: Users blocked from using bot commands

# --- FORBIDDEN WORDS LISTS ---
# General abuse filter for chat
BAD_WORDS = {
    # Add your bad words here, e.g., "gaali1", "gaali2"
}

# Specific phrases the Bot will REFUSE to shout (Updated with new requests)
# Using regex to match with optional spaces/dots and case insensitivity
FORBIDDEN_SHOUTS_PATTERNS = [
    r"aashirwad\s*ki",
    r"anant\s*ki",
    r"jha\s*ki",
    r"levi\s*ki",
]

# --- HELPER: AUTH CHECK ---
async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    # 1. Check if logged in via password
    if user_id in authorized_users:
        return True
    
    # 2. Check actual Telegram Admin status
    try:
        member: ChatMember = await context.bot.get_chat_member(chat_id, user_id)
        if member.status in [ChatMember.ADMINISTRATOR, ChatMember.CREATOR]:
            return True
    except Exception as e:
        logger.error(f"Admin check error: {e}")
    return False

# NEW HELPER: Blocked User Check
async def is_user_blocked(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user_id = update.effective_user.id
    if user_id in blocked_users:
        # Optional: Send a silent message to the user that they are blocked
        # await update.message.reply_text("⛔ You are blocked from using bot commands.", ephemeral=True)
        return True
    return False

# --- CORE COMMANDS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await is_user_blocked(update, context): return
    txt = (
        "🙏 **Namaste Bhai!** System Update v2.5 Live.\n\n"
        "**Available Commands:**\n"
        "👮 `/warn` - Warning de (Reply to user)\n"
        "☢️ `/nuke` - **NEW:** Panel se message delete kar\n"
        "📢 `/shout [msg]` - Zor se bol (Mods Only)\n"
        "⬆️ `/promote` & ⬇️ `/demote` - Power control (Reply)\n"
        "💤 `/afk [reason]` - Offline chala ja\n"
        "📌 `/pin` & `/unpin` - Message chipkao\n"
        "🎲 `/roll` - Ludo khel le\n"
        "🤖 `/setautoreply [word] | [reply]` - Auto jawab\n"
        "❌ `/deleteautoreply [word]` - Auto jawab delete\n"
        "🔑 `/login [pass]` - Secret access\n"
        "❌ `/block` - **NEW:** User ko bot use karne se rok\n"
        "🟢 `/status` - Bot Zinda hai ya nahi?"
    )
    await update.message.reply_text(txt, parse_mode='Markdown')

async def login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await is_user_blocked(update, context): return
    if context.args and context.args[0] == ADMIN_PASSWORD:
        authorized_users.add(update.effective_user.id)
        await update.message.reply_text("😎 **System Set!** Ab tu Admin hai.")
    else:
        await update.message.reply_text("🤨 **Galat Password!**")

# --- MODERATION ---

async def warn_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await is_user_blocked(update, context): return
    if not await is_admin(update, context):
        return await update.message.reply_text("⛔ Power nahi hai tere paas!")
    
    if not update.message.reply_to_message:
        return await update.message.reply_text("Reply kar ke warn de!")

    target = update.message.reply_to_message.from_user
    chat_id = update.effective_chat.id

    if target.id == context.bot.id:
        return await update.message.reply_text("🤬 **Khud ko warn nahi dunga!**")
    
    if target.id == OWNER_ID: # NEW: Owner restriction
        return await update.message.reply_text("🚫 **AashirwadGamerzz** ko restrict karna allowed nahi hai!")

    current_warns = warns.get(target.id, 0) + 1
    warns[target.id] = current_warns

    msg = f"⚠️ **Warning!**\nUser: {target.first_name}\nCount: {current_warns}/3"
    
    if current_warns >= 3:
        try:
            # We use restrict_chat_member instead of ban_chat_member for a temporary mute/restriction
            await context.bot.restrict_chat_member(
                chat_id=chat_id,
                user_id=target.id,
                permissions=ChatMember.RESTRICTED # This is usually a temporary mute
            )
            warns[target.id] = 0
            msg = f"🚫 **Khatam!** {target.first_name} ko **Mute** kar diya (3 Warnings)."
        except Exception as e:
            msg += f"\n(Mute failed: {e})"

    await update.message.reply_text(msg)

async def shout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await is_user_blocked(update, context): return
    # 1. MODERATOR ONLY CHECK
    if not await is_admin(update, context):
        return await update.message.reply_text("⛔ Sirf Admins shout kar sakte hain!")

    msg = " ".join(context.args)
    if not msg:
        return await update.message.reply_text("Likhna kya hai?")

    # 2. CENSORSHIP CHECK (Updated to use regex patterns)
    msg_lower = msg.lower()
    for pattern in FORBIDDEN_SHOUTS_PATTERNS:
        # Use re.search for pattern matching
        if re.search(pattern, msg_lower):
            return await update.message.reply_text("❌ **Ye shabd allowed nahi hain!**")

    await update.message.reply_text(f"📢 **{msg.upper()}**", parse_mode='Markdown')

# --- NUKE SYSTEM (UPDATED PANEL) ---

async def nuke_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await is_user_blocked(update, context): return
    if not await is_admin(update, context): 
        return await update.message.reply_text("⛔ Power nahi hai.")
    
    keyboard = [
        [
            InlineKeyboardButton("🗑️ Clean 10", callback_data='clean_10'),
            InlineKeyboardButton("🗑️ Clean 100", callback_data='clean_100')
        ],
        [
            InlineKeyboardButton("☢️ Clean 200", callback_data='clean_200'),
            InlineKeyboardButton("🔥 Clean 500", callback_data='clean_500')
        ],
        [InlineKeyboardButton("❌ Cancel", callback_data='nuke_cancel')]
    ]
    
    # Send the initial GIF and the panel message
    chat_id = update.effective_chat.id
    
    # Send GIF (Naruto Pain)
    await context.bot.send_animation(
        chat_id=chat_id,
        animation='https://media.tenor.com/O_46hYpNdB4AAAAM/pain-naruto.gif',
        caption="🧹 **Cleaning Panel Active!**\nKitne message udane hain?"
    )
    
    # Wait 2 seconds and send SHINRA TENSEI
    await asyncio.sleep(2)
    
    # Send panel message with keyboard
    await context.bot.send_message(
        chat_id=chat_id,
        text="**SHINRA TENSEI!**\nChoose your delete count:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def nuke_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    
    # Check admin status on the query user
    user_id = query.from_user.id
    chat_id = query.message.chat_id
    
    try:
        # We need to re-check admin status based on the user who pressed the button
        member: ChatMember = await context.bot.get_chat_member(chat_id, user_id)
        if member.status not in [ChatMember.ADMINISTRATOR, ChatMember.CREATOR] and user_id not in authorized_users:
             return await query.answer("⛔ Admin only!", show_alert=True)
    except Exception:
        return await query.answer("⛔ Admin check failed!", show_alert=True)

    await query.answer()
    data = query.data

    if data == 'nuke_cancel':
        await query.edit_message_text("👍 **Operation Cancelled.**")
        return

    # Extract number from 'clean_500' -> 500
    try:
        count = int(data.split('_')[1])
    except:
        return

    await query.edit_message_text(f"☢️ **Deleting last {count} messages...**")
    
    # Start message ID is the message that contained the panel (query.message.message_id)
    msg_id = query.message.message_id
    
    deleted = 0
    # Loop to delete
    # Start from the panel message itself (msg_id), then go backward (msg_id - 1, msg_id - 2, ...)
    for i in range(count + 1): # +1 to delete the panel message too
        try:
            await context.bot.delete_message(chat_id, msg_id - i)
            deleted += 1
        except Exception:
            pass # Skip if message doesn't exist or too old
            
    # Send the final confirmation message
    final_msg = await context.bot.send_message(chat_id, f"💥 **Safai Abhiyan Complete!**\nDeleted approx {deleted} messages.")
    
    # Delete the confirmation after 5 seconds
    await asyncio.sleep(5)
    try:
        await final_msg.delete()
    except Exception:
        pass

# --- ADMIN TOOLS (FIXED & UPDATED) ---

async def promote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await is_user_blocked(update, context): return
    if not await is_admin(update, context): 
        return await update.message.reply_text("⛔ Power nahi hai.")
    
    if not update.message.reply_to_message:
        return await update.message.reply_text("Reply karke promote kar.")

    target_user = update.message.reply_to_message.from_user
    user_id = target_user.id
    chat_id = update.effective_chat.id

    if user_id == OWNER_ID: # NEW: Owner restriction
        return await update.message.reply_text("🚫 **AashirwadGamerzz** ko restrict karna allowed nahi hai!")

    try:
        # Full Admin Rights (Excluding can_promote_members for standard bots)
        await context.bot.promote_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            can_manage_chat=True,
            can_delete_messages=True,
            can_manage_video_chats=True,
            can_restrict_members=True,
            can_promote_members=False, # Bots often can't grant this
            can_change_info=True,
            can_invite_users=True,
            can_pin_messages=True,
            is_anonymous=False
        )
        # Updated Promotion Message
        msg = f"🌟 **Badhai ho!** {target_user.first_name} is now a **Soldier!**\n\nHope you kill Titans. Make peace."
        await update.message.reply_text(msg)
    except Exception as e:
        await update.message.reply_text(f"❌ **Error:** {e}\n(Shayad mere paas khud power nahi hai ya banda pehle se admin hai)")

async def demote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await is_user_blocked(update, context): return
    if not await is_admin(update, context): 
        return await update.message.reply_text("⛔ Power nahi hai.")
    
    if not update.message.reply_to_message:
        return await update.message.reply_text("Reply karke demote kar.")

    target_user = update.message.reply_to_message.from_user
    user_id = target_user.id
    chat_id = update.effective_chat.id

    if user_id == OWNER_ID: # NEW: Owner restriction
        return await update.message.reply_text("🚫 **AashirwadGamerzz** ko restrict karna allowed nahi hai!")
    
    if user_id == context.bot.id:
        return await update.message.reply_text("🤬 **Khud ko demote nahi karunga!**")


    try:
        # Remove all privileges
        await context.bot.promote_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            can_manage_chat=False,
            can_delete_messages=False,
            can_manage_video_chats=False,
            can_restrict_members=False,
            can_promote_members=False,
            can_change_info=False,
            can_invite_users=False,
            can_pin_messages=False,
            is_anonymous=False
        )
        # Updated Demotion Message
        msg = f"🤡 **Demoted!** {target_user.first_name}, you are not capable to kill Titans. You are not a soldier."
        await update.message.reply_text(msg)
    except Exception as e:
        await update.message.reply_text(f"❌ **Error:** {e}")

# The set_slow_mode command has been REMOVED as requested.

async def pin_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await is_user_blocked(update, context): return
    if await is_admin(update, context) and update.message.reply_to_message:
        try:
            await update.message.reply_to_message.pin()
            await update.message.reply_text("📌 Pinned.")
        except Exception as e:
            await update.message.reply_text(f"Error: {e}")

async def unpin_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await is_user_blocked(update, context): return
    if await is_admin(update, context) and update.message.reply_to_message:
        try:
            await update.message.reply_to_message.unpin()
            await update.message.reply_text("📌 Unpinned.")
        except:
            pass

# NEW COMMAND: Block a user from using bot commands
async def block_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await is_user_blocked(update, context): return
    if not await is_admin(update, context): 
        return await update.message.reply_text("⛔ Power nahi hai.")

    if not update.message.reply_to_message:
        return await update.message.reply_text("Reply karke user ko block kar.")

    target_user = update.message.reply_to_message.from_user
    user_id = target_user.id
    
    if user_id == OWNER_ID: # NEW: Owner restriction
        return await update.message.reply_text("🚫 **AashirwadGamerzz** ko block karna allowed nahi hai!")

    if user_id in blocked_users:
        blocked_users.remove(user_id)
        await update.message.reply_text(f"🔓 **Unblocked!** {target_user.first_name} ab commands use kar sakta hai.")
    else:
        blocked_users.add(user_id)
        await update.message.reply_text(f"🔒 **Blocked!** {target_user.first_name} ab bot commands use nahi kar sakta.")

# NEW COMMAND: Bot status
async def bot_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await is_user_blocked(update, context): return
    # Check if the bot is running (which it is, if this command is reached)
    await update.message.reply_text("🟢 **Bhai Zinda hoon!** (Main Mar Chuka hoon! - *Just Kidding*)")


# --- UTILS ---
async def afk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await is_user_blocked(update, context): return
    afk_users[update.effective_user.id] = " ".join(context.args) or "Busy"
    await update.message.reply_text(f"💤 **{update.effective_user.first_name}** is now AFK.")

async def roll(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await is_user_blocked(update, context): return
    await context.bot.send_dice(update.effective_chat.id)

async def set_auto_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await is_user_blocked(update, context): return
    if await is_admin(update, context):
        text = " ".join(context.args)
        if "|" in text:
            t, r = text.split("|", 1)
            auto_replies[t.strip().lower()] = r.strip()
            await update.message.reply_text("✅ Saved.")

async def delete_auto_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await is_user_blocked(update, context): return
    if await is_admin(update, context):
        trigger = " ".join(context.args).lower().strip()
        if trigger in auto_replies:
            del auto_replies[trigger]
            await update.message.reply_text("🗑️ Deleted.")

# --- MAIN MESSAGE HANDLER ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    
    user = update.effective_user
    text_raw = update.message.text
    text_lower = text_raw.lower()
    
    # Check if message contains a Link (http, https, www)
    is_link = re.search(r'(http|https|www\.)', text_lower)

    # 1. SPECIAL TRIGGER: "Tere Upar Bala"
    triggered_bala = False
    
    # We only check for 7/Seven/tupilepermeramut if there is NO link in the message
    if not is_link:
        clean_text = re.sub(r'[\s\.]', '', text_lower)
        
        if "7" in text_raw or "seven" in clean_text or "tupilepermeramut" in clean_text:
            triggered_bala = True
    
    if triggered_bala:
        await update.message.reply_text("Tere upar Bala")
        return # Stop processing (bypass abuse filter)
        
    # 2. ABUSE FILTER
    found_bad = False
    for bad in BAD_WORDS:
        if bad in text_lower:
            found_bad = True
            break
            
    if found_bad:
        await update.message.reply_text(f"⛔ **Oye {user.first_name}!** Gaali mat de, tameez se reh.")

    # 3. AFK Handler
    if user.id in afk_users:
        del afk_users[user.id]
        await update.message.reply_text(f"👋 **Welcome Back {user.first_name}!**")

    if update.message.reply_to_message:
        replied_id = update.message.reply_to_message.from_user.id
        if replied_id in afk_users:
            await update.message.reply_text(f"🤫 **Wo AFK hai.** Reason: {afk_users[replied_id]}")

    # 4. Auto Reply
    if text_lower in auto_replies:
        await update.message.reply_text(auto_replies[text_lower])

# --- RUN ---
if __name__ == '__main__':
    keep_alive()
    if not TOKEN:
        print("❌ Error: BOT_TOKEN environment variable is missing.")
        exit()
        
    app = ApplicationBuilder().token(TOKEN).build()
    
    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("login", login))
    app.add_handler(CommandHandler("warn", warn_user))
    app.add_handler(CommandHandler("shout", shout))
    app.add_handler(CommandHandler("nuke", nuke_panel))
    app.add_handler(CommandHandler("promote", promote))
    app.add_handler(CommandHandler("demote", demote))
    # app.add_handler(CommandHandler("setslowmode", set_slow_mode)) # REMOVED as requested
    app.add_handler(CommandHandler("pin", pin_msg))
    app.add_handler(CommandHandler("unpin", unpin_msg))
    app.add_handler(CommandHandler("afk", afk))
    app.add_handler(CommandHandler("roll", roll))
    app.add_handler(CommandHandler("setautoreply", set_auto_reply))
    app.add_handler(CommandHandler("deleteautoreply", delete_auto_reply))
    app.add_handler(CommandHandler("block", block_user)) # NEW
    app.add_handler(CommandHandler("status", bot_status)) # NEW

    # Handlers
    app.add_handler(CallbackQueryHandler(nuke_callback))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    
    print("🚀 Bot Started with System v2.5 Updates...")
    app.run_polling()
