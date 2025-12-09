import os
import logging
import re
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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
OWNER_USERNAME = "AashirwadGamerzz"

# --- IN-MEMORY DATABASE ---
authorized_users = set()
warns = {}
afk_users = {}
auto_replies = {}
blocked_users = set()

# --- FORBIDDEN WORDS LISTS ---
# General abuse filter for chat
BAD_WORDS = {
  
}

# Specific phrases the Bot will REFUSE to shout
FORBIDDEN_SHOUTS = [
    "aashirwad ki", 
    "anant ki", 
    "jha ki", 
    "levi ki"
]

# --- HELPER: AUTH CHECK ---
async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    # Check if logged in via password
    if user_id in authorized_users:
        return True
    
    # Check actual Telegram Admin status
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        if member.status in ['administrator', 'creator']:
            return True
    except Exception as e:
        logger.error(f"Admin check error: {e}")
    return False

async def is_owner(user) -> bool:
    try:
        return user.username and user.username.lower() == OWNER_USERNAME.lower()
    except:
        return False

# --- CORE COMMANDS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = (
        "Tch. **Namaste, brat.** System Update v2.0. Clean it up.\n\n"
        "**Commands, listen up:**\n"
        "👮 `/warn` - Give a warning (reply to filth)\n"
        "☢️ `/nuke` - **Updated:** Panel to wipe messages\n"
        "📢 `/shout [msg]` - Yell it loud (Mods only)\n"
        "⬆️ `/promote` & ⬇️ `/demote` - Power shift (Fixed)\n"
        "💤 `/afk [reason]` - Go dark\n"
        "📌 `/pin` & `/unpin` - Pin the crap\n"
        "🎲 `/roll` - Roll the dice, soldier\n"
        "🤖 `/setautoreply [word] | [reply]` - Auto response\n"
        "❌ `/deleteautoreply [word]` - Scrap the auto\n"
        "🔑 `/login [pass]` - Access granted\n"
        "🚫 `/block` - Mute the weak (reply to user)\n"
        "📊 `/status` - Check if I'm still kicking"
    )
    await update.message.reply_text(txt, parse_mode='Markdown')

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Tch. **Bhai Zinda hoon!** Still cleaning up this mess.")

async def login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args and context.args[0] == ADMIN_PASSWORD:
        authorized_users.add(update.effective_user.id)
        await update.message.reply_text("Tch. **System set.** You're in, barely.")
    else:
        await update.message.reply_text("Filthy password. Try again, or get lost.")

# --- MODERATION ---

async def warn_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return await update.message.reply_text("Tch. No power for you, brat.")

    if not update.message.reply_to_message:
        return await update.message.reply_text("Reply to the mess to warn it.")

    target = update.message.reply_to_message.from_user
    if await is_owner(target):
        return await update.message.reply_text("Tch. Can't touch the captain. Owner protected.")

    chat_id = update.effective_chat.id

    if target.id == context.bot.id:
        return await update.message.reply_text("Tch. I won't warn myself, idiot.")

    current_warns = warns.get(target.id, 0) + 1
    warns[target.id] = current_warns

    msg = f"⚠️ **Warning, filth.**\nUser: {target.first_name}\nCount: {current_warns}/3"
    
    if current_warns >= 3:
        try:
            await context.bot.ban_chat_member(chat_id, target.id)
            warns[target.id] = 0
            msg = f"🚫 **Banned.** {target.first_name} is Titan food now (3 Warnings)."
        except Exception as e:
            msg += f"\n(Ban failed: {e})"

    await update.message.reply_text(msg)

async def shout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 1. MODERATOR ONLY CHECK
    if not await is_admin(update, context):
        return await update.message.reply_text("Tch. Shout? You? Dream on, brat.")

    msg = " ".join(context.args)
    if not msg:
        return await update.message.reply_text("What filth are you yelling? Speak.")

    # 2. CENSORSHIP CHECK - Normalize: lower, remove punctuation except spaces
    msg_normalized = re.sub(r'[^\w\s]', ' ', msg.lower())
    msg_normalized = ' '.join(msg_normalized.split())  # Clean multiple spaces

    for forbidden in FORBIDDEN_SHOUTS:
        if forbidden in msg_normalized:
            return await update.message.reply_text("Tch. **That word's dirtier than the stables. Blocked.**")

    await update.message.reply_text(f"📢 **{msg.upper()}**", parse_mode='Markdown')

# --- NUKE SYSTEM (UPDATED PANEL) ---

async def nuke_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): 
        return await update.message.reply_text("Tch. Nuke? With what authority?")
    
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
    await update.message.reply_text("🧹 **Nuke Panel**\nHow much filth to erase, soldier?", reply_markup=InlineKeyboardMarkup(keyboard))

async def nuke_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not await is_admin(update, context):
        return await query.answer("Tch. Admin only, brat!", show_alert=True)

    await query.answer()
    data = query.data

    if data == 'nuke_cancel':
        await query.edit_message_text("Tch. **Cancelled.** Waste of time.")
        return

    # Extract number from 'clean_50' -> 50
    try:
        count = int(data.split('_')[1])
    except:
        return

    await query.edit_message_text(f"☢️ **Erasing last {count} messages...**")
    
    chat_id = query.message.chat_id
    msg_id = query.message.message_id
    
    # Send GIF immediately
    gif_url = "https://media.tenor.com/O_46hYpNdB4AAAAM/pain-naruto.gif"
    await context.bot.send_animation(chat_id, gif_url)
    
    # Wait 2 seconds
    await asyncio.sleep(2)
    
    # Send SHINRA TENSEI
    await context.bot.send_message(chat_id, "SHINRA TENSEI!")
    
    deleted = 0
    # Loop to delete
    for i in range(count):
        try:
            # Delete message ID going backwards from the command
            await context.bot.delete_message(chat_id, msg_id - i)
            deleted += 1
        except Exception:
            pass # Skip if message doesn't exist or too old
        
    final_msg = await context.bot.send_message(chat_id, f"💥 **Cleanup done.**\nErased approx {deleted} messages, brats.")
    # Delete the confirmation after 5 seconds
    await asyncio.sleep(5)
    try:
        await final_msg.delete()
    except:
        pass

# --- ADMIN TOOLS (UPDATED) ---

async def promote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): 
        return await update.message.reply_text("Tch. Promote? You can't even clean your own mess.")

    if not update.message.reply_to_message:
        return await update.message.reply_text("Reply to the soldier to promote.")

    target = update.message.reply_to_message.from_user
    if await is_owner(target):
        return await update.message.reply_text("Tch. Owner doesn't need your scraps.")

    user_id = target.id
    chat_id = update.effective_chat.id

    try:
        # Full Admin Rights (Except adding new admins, restricted by Telegram API for bots usually)
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
            can_pin_messages=True
        )
        await update.message.reply_text("🌟 **You're now a soldier. Hope you kill Titans. Make peace.**")
    except Exception as e:
        await update.message.reply_text(f"Tch. **Error:** {e}\n(Maybe I lack the gear, or he's already geared up.)")

async def demote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): 
        return await update.message.reply_text("Tch. Demote? Earn it first.")

    if not update.message.reply_to_message:
        return await update.message.reply_text("Reply to the failure to demote.")

    target = update.message.reply_to_message.from_user
    if await is_owner(target):
        return await update.message.reply_text("Tch. Owner stays geared. No touch.")

    user_id = target.id
    chat_id = update.effective_chat.id

    try:
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
            can_pin_messages=False
        )
        await update.message.reply_text("🤡 **You are not capable to kill Titans. You not soldiers.**")
    except Exception as e:
        await update.message.reply_text(f"Tch. **Error:** {e}")

async def block_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): 
        return await update.message.reply_text("Tch. Block? With what blade?")

    if not update.message.reply_to_message:
        return await update.message.reply_text("Reply to the Titan to block it.")

    target = update.message.reply_to_message.from_user
    if await is_owner(target):
        return await update.message.reply_text("Tch. Can't block the captain.")

    user_id = target.id
    chat_id = update.effective_chat.id

    try:
        # Mute the user (restrict to no messages)
        await context.bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            permissions=telegram.ChatPermissions(can_send_messages=False)
        )
        blocked_users.add(user_id)
        await update.message.reply_text(f"Tch. **{target.first_name} muted. Can't filth the chat anymore.**")
    except Exception as e:
        await update.message.reply_text(f"Tch. **Error:** {e}")

async def pin_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await is_admin(update, context) and update.message.reply_to_message:
        try:
            await update.message.reply_to_message.pin()
            await update.message.reply_text("Tch. Pinned. Stay clean.")
        except Exception as e:
            await update.message.reply_text(f"Tch. Error: {e}")

async def unpin_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await is_admin(update, context) and update.message.reply_to_message:
        try:
            await update.message.reply_to_message.unpin()
            await update.message.reply_text("Tch. Unpinned. Messy.")
        except:
            pass

# --- UTILS ---
async def afk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    afk_users[update.effective_user.id] = " ".join(context.args) or "Busy"
    await update.message.reply_text(f"Tch. **{update.effective_user.first_name}** AFK. Don't disturb the cleaning.")

async def roll(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_dice(update.effective_chat.id)

async def set_auto_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await is_admin(update, context):
        text = " ".join(context.args)
        if "|" in text:
            t, r = text.split("|", 1)
            auto_replies[t.strip().lower()] = r.strip()
            await update.message.reply_text("Tch. Auto set. Efficient.")

async def delete_auto_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await is_admin(update, context):
        trigger = " ".join(context.args).lower().strip()
        if trigger in auto_replies:
            del auto_replies[trigger]
            await update.message.reply_text("Tch. Auto scrapped. Clean.")

# --- MAIN MESSAGE HANDLER ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    
    user = update.effective_user
    if user.id in blocked_users:
        try:
            await update.message.delete()
            return
        except:
            pass
    
    text_raw = update.message.text
    text_lower = text_raw.lower()
    
    # Check if message contains a Link (http, https, www)
    # If it contains a link, we DISABLE the Bala trigger to avoid false alarms
    is_link = re.search(r'(http|https|www\.)', text_lower)

    # 1. SPECIAL TRIGGER: "Tere Upar Bala"
    triggered_bala = False
    
    # We only check for 7/Seven if there is NO link in the message
    if not is_link:
        clean_text = re.sub(r'[\s\.]', '', text_lower)
        
        if "7" in text_raw:
            triggered_bala = True
        elif "seven" in clean_text:
            triggered_bala = True
        elif "tupilepermeramut" in clean_text:
            triggered_bala = True
    
    if triggered_bala:
        await update.message.reply_text("Tch. Tere upar Bala.")
        return # Stop processing (bypass abuse filter)
    # 2. ABUSE FILTER
    found_bad = False
    for bad in BAD_WORDS:
        if bad in text_lower:
            found_bad = True
            break
            
    if found_bad:
        await update.message.reply_text(f"Tch. **Oye {user.first_name}!** No filth. Keep it clean, or get out.")

    # 3. AFK Handler
    if user.id in afk_users:
        del afk_users[user.id]
        await update.message.reply_text(f"Tch. **Welcome back, {user.first_name}.** Don't make a mess.")

    if update.message.reply_to_message:
        replied_id = update.message.reply_to_message.from_user.id
        if replied_id in afk_users:
            await update.message.reply_text(f"Tch. **He's AFK.** Reason: {afk_users[replied_id]}. Back off.")

    # 4. Auto Reply
    if text_lower in auto_replies:
        await update.message.reply_text(auto_replies[text_lower])

# --- RUN ---
if __name__ == '__main__':
    keep_alive()
    if not TOKEN:
        print("❌ Error: TOKEN missing.")
        exit()
        
    app = ApplicationBuilder().token(TOKEN).build()
    
    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("login", login))
    app.add_handler(CommandHandler("warn", warn_user))
    app.add_handler(CommandHandler("shout", shout))
    app.add_handler(CommandHandler("nuke", nuke_panel)) # Updated to Panel
    app.add_handler(CommandHandler("promote", promote))
    app.add_handler(CommandHandler("demote", demote))
    app.add_handler(CommandHandler("block", block_user))
    app.add_handler(CommandHandler("pin", pin_msg))
    app.add_handler(CommandHandler("unpin", unpin_msg))
    app.add_handler(CommandHandler("afk", afk))
    app.add_handler(CommandHandler("roll", roll))
    app.add_handler(CommandHandler("setautoreply", set_auto_reply))
    app.add_handler(CommandHandler("deleteautoreply", delete_auto_reply))

    # Handlers
    app.add_handler(CallbackQueryHandler(nuke_callback))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    
    print("🚀 Bot Started. Tch. Keeping it clean...")
    app.run_polling()
