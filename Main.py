import os
import logging
import html
import re  # Regex for advanced text cleaning
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

# --- IN-MEMORY DATABASE ---
authorized_users = set()
warns = {}
afk_users = {}
auto_replies = {}

# --- BAD WORDS LIST (Abuse Filter) ---
BAD_WORDS = {
    "madarchod", "bhenchod", "bsdk", "gand", "gaand", "chutiya", "choot", 
    "lodu", "lawde", "lund", "bhosdike", "randi", "randwa", "mc", "bc", 
    "mkc", "bkc", "behenchod", "kuttiya", "harami", "kamine", "chod",
    "saala", "kamina", "bhadwa"
}

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

# --- CORE FEATURES ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = (
        "🙏 Namaste Bhai! System update ho gaya hai. \n”

"Available Commands:"
"👮 /warn - Warning de bande ko \n"
"☢️ /nuke - Chat clear (Confirmation ke saath) \n"
"📢 /shout [msg] - Zor se bol \n"
"⬆️ /promote & ⬇️ /demote - Power control \n"
"🐢 /setslowmode [seconds] - Chat speed control \n"
"💤 /afk [reason] - Offline chala ja \n"
"📌 pin & /unpin - Message chipkao \n"
"🎲 /roll - Ludo khel le \n"
"🕺 /bala - Party shuru! \n"
"🤖 /setautoreply [word] | [reply] - Auto jawab \n"
"❌ /deleteautoreply [word] - Auto jawab delete \n"
"🔑 /login [pass] - Secret access \n"
    )
    await update.message.reply_text(txt, parse_mode='Markdown')

async def login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args and context.args[0] == ADMIN_PASSWORD:
        authorized_users.add(update.effective_user.id)
        await update.message.reply_text("😎 **System Set!** Ab tu Admin hai.")
    else:
        await update.message.reply_text("🤨 **Galat Password!**")

# --- MODERATION ---

async def warn_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return await update.message.reply_text("⛔ Power nahi hai tere paas!")
    
    if not update.message.reply_to_message:
        return await update.message.reply_text("Reply kar ke warn de!")

    target = update.message.reply_to_message.from_user
    chat_id = update.effective_chat.id

    if target.id == context.bot.id:
        return await update.message.reply_text("🤬 **Khud ko warn nahi dunga!**")

    current_warns = warns.get(target.id, 0) + 1
    warns[target.id] = current_warns

    msg = f"⚠️ **Warning!**\nUser: {target.first_name}\nCount: {current_warns}/3"
    
    if current_warns >= 3:
        try:
            await context.bot.ban_chat_member(chat_id, target.id)
            warns[target.id] = 0
            msg = f"🚫 **Khatam!** {target.first_name} ko uda diya (3 Warnings)."
        except:
            msg += "\n(Ban failed, Admin power check kar)"

    await update.message.reply_text(msg)

async def shout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = " ".join(context.args).upper()
    if not msg:
        return await update.message.reply_text("Likhna kya hai?")
    await update.message.reply_text(f"📢 **{msg}**", parse_mode='Markdown')

# --- NUKE SYSTEM ---
async def nuke_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): return
    keyboard = [[InlineKeyboardButton("✅ Haan", callback_data='nuke_yes'), InlineKeyboardButton("❌ Nahi", callback_data='nuke_no')]]
    await update.message.reply_text("💣 **Chat Clear Karein?**", reply_markup=InlineKeyboardMarkup(keyboard))

async def nuke_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == 'nuke_yes':
        await query.edit_message_text("☢️ **Uda Raha Hu...**")
        chat_id = query.message.chat_id
        msg_id = query.message.message_id
        try:
            for i in range(1, 50):
                try: await context.bot.delete_message(chat_id, msg_id - i)
                except: pass
            await context.bot.send_message(chat_id, "💥 **Chat Cleaned!**")
        except: pass
    else:
        await query.edit_message_text("👍 **Cancelled.**")

# --- ADMIN TOOLS ---
async def promote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): return
    if update.message.reply_to_message:
        try:
            await context.bot.promote_chat_member(update.effective_chat.id, update.message.reply_to_message.from_user.id, can_manage_chat=True, can_delete_messages=True, can_invite_users=True, can_pin_messages=True)
            await update.message.reply_text("🌟 **Promoted!**")
        except: await update.message.reply_text("❌ Error.")

async def demote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): return
    if update.message.reply_to_message:
        try:
            await context.bot.promote_chat_member(update.effective_chat.id, update.message.reply_to_message.from_user.id, can_manage_chat=False, can_delete_messages=False)
            await update.message.reply_text("🤡 **Demoted!**")
        except: await update.message.reply_text("❌ Error.")

async def set_slow_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): return
    if context.args:
        try:
            await context.bot.set_chat_slow_mode_delay(update.effective_chat.id, int(context.args[0]))
            await update.message.reply_text(f"🐢 Slow Mode: {context.args[0]}s")
        except: pass

async def pin_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await is_admin(update, context) and update.message.reply_to_message:
        await update.message.reply_to_message.pin()

async def unpin_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await is_admin(update, context) and update.message.reply_to_message:
        await update.message.reply_to_message.unpin()

# --- UTILS ---
async def afk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    afk_users[update.effective_user.id] = " ".join(context.args) or "Busy"
    await update.message.reply_text(f"💤 **{update.effective_user.first_name}** is now AFK.")

async def roll(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_dice(update.effective_chat.id)

async def bala(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_animation(update.effective_chat.id, "https://media1.tenor.com/m/C3eR0iU1tBIAAAAd/akshay-kumar-dance.gif", caption="🕺 **Bala O Bala!**")

async def set_auto_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await is_admin(update, context):
        text = " ".join(context.args)
        if "|" in text:
            t, r = text.split("|", 1)
            auto_replies[t.strip().lower()] = r.strip()
            await update.message.reply_text("✅ Saved.")

async def delete_auto_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    
    # 1. SPECIAL TRIGGER: "Tere Upar Bala" Logic
    # We create a version of text without spaces or dots
    # This turns "s.e.v.e.n" -> "seven" and "tu . pi . le" -> "tupile"
    clean_text = re.sub(r'[\s\.]', '', text_lower) 
    
    triggered_bala = False
    
    # Condition A: Number "7" anywhere in raw text (e.g. "7", "7.", "17")
    if "7" in text_raw:
        triggered_bala = True
        
    # Condition B: Word "seven" in clean text (e.g. "seven", "s.e.v.e.n", "s ev en")
    elif "seven" in clean_text:
        triggered_bala = True
        
    # Condition C: Specific Phrase "tupilepermeramut" in clean text
    elif "tupilepermeramut" in clean_text:
        triggered_bala = True
    
    if triggered_bala:
        await update.message.reply_text("Tere upar Bala")
        return # Priority: Stop further processing (like abuse check)

    # 2. ABUSE FILTER
    found_bad = False
    # Check strict words first (to avoid partial matches misfiring if needed, but here we do broad check)
    for bad in BAD_WORDS:
        if bad in text_lower:
            found_bad = True
            break
            
    if found_bad:
        await update.message.reply_text(f"⛔ **Oye {user.first_name}!** Gaali mat de, tameez se reh.")
        # try: await update.message.delete()
        # except: pass

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
        print("❌ Error: TOKEN missing.")
        exit()
        
    app = ApplicationBuilder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("login", login))
    app.add_handler(CommandHandler("warn", warn_user))
    app.add_handler(CommandHandler("shout", shout))
    app.add_handler(CommandHandler("nuke", nuke_request))
    app.add_handler(CommandHandler("promote", promote))
    app.add_handler(CommandHandler("demote", demote))
    app.add_handler(CommandHandler("setslowmode", set_slow_mode))
    app.add_handler(CommandHandler("pin", pin_msg))
    app.add_handler(CommandHandler("unpin", unpin_msg))
    app.add_handler(CommandHandler("afk", afk))
    app.add_handler(CommandHandler("roll", roll))
    app.add_handler(CommandHandler("bala", bala))
    app.add_handler(CommandHandler("setautoreply", set_auto_reply))
    app.add_handler(CommandHandler("deleteautoreply", delete_auto_reply))

    app.add_handler(CallbackQueryHandler(nuke_callback))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    
    print("🚀 Bot Started with Updated '7/Seven' Logic...")
    app.run_polling()
