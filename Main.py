import os
import logging
import html
from telegram import Update, ChatPermissions, InlineKeyboardButton, InlineKeyboardMarkup, constants
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

# --- DATABASE & LISTS ---
authorized_users = set()
warns = {}
afk_users = {}
auto_replies = {}

# List of abuse words (Hinglish/English)
ABUSE_LIST = [
    "bsdk", "bhosdike", "mc", "madarchod", "bc", "bhenchod", "chutiya", 
    "gandu", "lavde", "lawde", "laude", "kutta", "kamina", "harami", 
    "Tu pi le per Mera mut", "Tu .pi le. per Mera mut", "Tu pi le per Mera mut..", "bitch", "randi", "saale", "suar"
]

# --- HELPER: AUTH CHECK ---
async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    if user_id in authorized_users:
        return True
    
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        if member.status in ['administrator', 'creator']:
            return True
    except:
        pass
    return False

# --- CORE COMMANDS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = (
        "🙏 **Namaste Bhai!** System Updated v2.0\n\n"
        "**New Features:**\n"
        "🛠️ `/panel` - Admin Control Panel (GUI)\n"
        "🛡️ **Anti-Abuse** - Gali galoch allowed nahi hai\n"
        "🏏 **Thala Logic** - Type '7' to see magic\n\n"
        "**Commands:**\n"
        "/warn, /nuke, /shout, /afk, /bala\n"
        "/setautoreply, /login"
    )
    await update.message.reply_text(txt, parse_mode='Markdown')

async def login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args and context.args[0] == ADMIN_PASSWORD:
        authorized_users.add(update.effective_user.id)
        await update.message.reply_text("😎 **System Set!** Ab tu Admin hai.")
    else:
        await update.message.reply_text("🤨 **Galat Password!**")

# --- ADMIN PANEL (NEW) ---

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return await update.message.reply_text("⛔ Sirf Admins ke liye hai ye!")

    keyboard = [
        [
            InlineKeyboardButton("☢️ Nuke Chat", callback_data='panel_nuke'),
            InlineKeyboardButton("📌 Unpin All", callback_data='panel_unpinall'),
        ],
        [
            InlineKeyboardButton("🐢 Slow Mode (10s)", callback_data='panel_slow10'),
            InlineKeyboardButton("🚀 Slow Mode (OFF)", callback_data='panel_slow0'),
        ],
        [
            InlineKeyboardButton("🎲 Roll Dice", callback_data='panel_roll'),
            InlineKeyboardButton("❌ Close Panel", callback_data='panel_close'),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("🛠️ **Admin Control Panel:**\nSelect an action:", reply_markup=reply_markup)

# --- UNIFIED CALLBACK HANDLER ---

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    chat_id = query.message.chat_id

    # --- NUKE CONFIRMATION LOGIC ---
    if data == 'nuke_yes':
        await query.edit_message_text("☢️ **Nuke Incoming...**")
        try:
            message_id = query.message.message_id
            for i in range(1, 50):
                try:
                    await context.bot.delete_message(chat_id, message_id - i)
                except:
                    pass
            await context.bot.send_message(chat_id, "💥 **Chat Safa Chat!** (Recent msgs deleted)")
        except:
            await context.bot.send_message(chat_id, "❌ Error clearing chat.")
    
    elif data == 'nuke_no':
        await query.edit_message_text("👍 **Nuke Cancelled.**")

    # --- PANEL LOGIC ---
    elif data == 'panel_close':
        await query.message.delete()

    elif data == 'panel_nuke':
        # Trigger the confirmation check
        keyboard = [
            [InlineKeyboardButton("✅ Yes, Do it", callback_data='nuke_yes'),
             InlineKeyboardButton("❌ No", callback_data='nuke_no')]
        ]
        await query.edit_message_text("💣 **Are you sure?**", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == 'panel_unpinall':
        try:
            await context.bot.unpin_all_chat_messages(chat_id)
            await query.message.reply_text("📌 **Sab Unpin kar diya!**")
        except:
            await query.message.reply_text("❌ Rights nahi hai mere paas.")

    elif data == 'panel_slow10':
        try:
            await context.bot.set_chat_slow_mode_delay(chat_id, 10)
            await query.message.reply_text("🐢 **Slow Mode: 10s**")
        except:
            await query.message.reply_text("❌ Error setting slow mode.")

    elif data == 'panel_slow0':
        try:
            await context.bot.set_chat_slow_mode_delay(chat_id, 0)
            await query.message.reply_text("🚀 **Slow Mode Removed!** Bhagao ab.")
        except:
            await query.message.reply_text("❌ Error.")

    elif data == 'panel_roll':
        await context.bot.send_dice(chat_id)

# --- STANDARD MODERATION ---

async def warn_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): return
    if not update.message.reply_to_message: return await update.message.reply_text("Reply to someone!")

    target = update.message.reply_to_message.from_user
    current = warns.get(target.id, 0) + 1
    warns[target.id] = current

    msg = f"⚠️ **Warning!** {target.first_name} ({current}/3)"
    if current >= 3:
        try:
            await context.bot.ban_chat_member(update.effective_chat.id, target.id)
            warns[target.id] = 0
            msg = f"🚫 **Banned!** {target.first_name} ko uda diya."
        except:
            msg += "\n(Ban failed, check admin rights)"
    
    await update.message.reply_text(msg)

async def nuke_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): return
    keyboard = [[InlineKeyboardButton("✅ Confirm", callback_data='nuke_yes'), InlineKeyboardButton("❌ Cancel", callback_data='nuke_no')]]
    await update.message.reply_text("💣 **Confirm Nuke?**", reply_markup=InlineKeyboardMarkup(keyboard))

async def shout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = " ".join(context.args).upper()
    if not msg: return
    await update.message.reply_text(f"📢 **{msg}**", parse_mode='Markdown')

async def afk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    afk_users[update.effective_user.id] = " ".join(context.args) or "Chilling"
    await update.message.reply_text(f"💤 **{update.effective_user.first_name}** is now AFK.")

async def bala(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_animation(update.effective_chat.id, "https://media1.tenor.com/m/C3eR0iU1tBIAAAAd/akshay-kumar-dance.gif", caption="🕺 **Shaitan ka Saala!**")

# --- AUTO REPLY & FILTER LOGIC ---

async def set_auto_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): return
    text = " ".join(context.args)
    if "|" in text:
        trigger, response = text.split("|", 1)
        auto_replies[trigger.strip().lower()] = response.strip()
        await update.message.reply_text(f"✅ Auto-reply saved for '{trigger.strip()}'")

async def delete_auto_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): return
    trigger = " ".join(context.args).lower().strip()
    if trigger in auto_replies:
        del auto_replies[trigger]
        await update.message.reply_text("🗑️ Deleted.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    
    user = update.effective_user
    text = update.message.text
    text_lower = text.lower()

    # --- 1. SPECIAL "7" (THALA) LOGIC ---
    # Trigger if message is exactly "7" OR contains "if they type 7" logic requested
    if text_lower == "7" or "type 7" in text_lower:
        return await update.message.reply_text("Tere upar Bala")

    # --- 2. ABUSE FILTER (Respect kra bsdk) ---
    # Split text into words to match exact bad words, prevents triggering on "scunthorpe"
    words = text_lower.split()
    if any(bad_word == word for word in words for bad_word in ABUSE_LIST):
        return await update.message.reply_text("Respect kra bsdk 😡")

    # --- 3. AFK LOGIC ---
    if user.id in afk_users:
        del afk_users[user.id]
        await update.message.reply_text(f"👋 **Welcome Back {user.first_name}!**")

    if update.message.reply_to_message:
        target_id = update.message.reply_to_message.from_user.id
        if target_id in afk_users:
            await update.message.reply_text(f"🤫 **Shh!** Wo AFK hai.\nReason: {afk_users[target_id]}")

    # --- 4. CUSTOM AUTO REPLIES ---
    if text_lower in auto_replies:
        await update.message.reply_text(auto_replies[text_lower])

# --- MAIN EXECUTION ---
if __name__ == '__main__':
    keep_alive()
    
    if not TOKEN:
        print("❌ Error: BOT_TOKEN missing.")
        exit()

    app = ApplicationBuilder().token(TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("panel", admin_panel)) # New Admin Panel
    app.add_handler(CommandHandler("login", login))
    app.add_handler(CommandHandler("warn", warn_user))
    app.add_handler(CommandHandler("nuke", nuke_request))
    app.add_handler(CommandHandler("shout", shout))
    app.add_handler(CommandHandler("afk", afk))
    app.add_handler(CommandHandler("bala", bala))
    app.add_handler(CommandHandler("setautoreply", set_auto_reply))
    app.add_handler(CommandHandler("deleteautoreply", delete_auto_reply))

    # Handlers
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    
    print("🚀 Bot Started with Admin Panel & Abuse Filter...")
    app.run_polling()
