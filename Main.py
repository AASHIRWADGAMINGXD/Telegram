import os
import logging
import asyncio
from telegram import (
    Update, ChatPermissions, InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder, ContextTypes, CommandHandler, 
    MessageHandler, CallbackQueryHandler, filters
)
from keep_alive import keep_alive

# --- LOGGING ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# --- CONFIG ---
TOKEN = os.getenv("BOT_TOKEN") 
ADMIN_PASSWORD = os.getenv("ADMIN_PASS", "BhaiKaSystem") 

# --- MEMORY (Database ki jagah RAM use kar rahe hai) ---
authorized_users = set()       # Logged in admins
warns = {}                     # {user_id: count}
afk_users = {}                 # {user_id: reason}
auto_replies = {}              # {trigger_word: response}

# --- HELPER: Check Admin ---
async def is_authorized(update: Update):
    user = update.effective_user
    chat = update.effective_chat
    if user.id in authorized_users:
        return True
    # Real Telegram Admins ko bhi allow karein
    member = await chat.get_member(user.id)
    if member.status in ['administrator', 'creator']:
        return True
    return False

# ================= OLD COMMANDS (UNCHANGED) =================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🙏 **Namaste Bhai!** SYSTEM UPDATE 2.0 Loaded.\n\n"
        "Main hoon is group ka naya Moderator.\n"
        "Pehle `/login` kar, fir jalwa dekh.\n\n"
        "**Basic:** /kick, /mute, /clear\n"
        "**New:** /warn, /nuke, /promote, /afk, /pin, /bala\n"
        "**Fun:** /roll, /shout\n"
        "**Auto:** /setautoreply, /deleteautoreply"
    )

async def login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Pass toh likh! `/login [password]`")
        return
    if context.args[0] == ADMIN_PASSWORD:
        authorized_users.add(update.effective_user.id)
        await update.message.reply_text(f"😎 **Swagat hai Boss!** System tera hua.")
    else:
        await update.message.reply_text("🤨 **Galat Password!** Nikal pehli fursat mein.")

async def kick_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_authorized(update): return await update.message.reply_text("Power nahi hai tere paas!")
    if not update.message.reply_to_message: return await update.message.reply_text("Reply karke bol kisko udana hai.")
    try:
        await context.bot.ban_chat_member(update.effective_chat.id, update.message.reply_to_message.from_user.id)
        await update.message.reply_text("👋 **Tata Bye Bye!** Udd gaya wo.")
    except: await update.message.reply_text("❌ Error: Admin ko kick nahi kar sakta.")

async def mute_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_authorized(update): return await update.message.reply_text("Power nahi hai tere paas!")
    if not update.message.reply_to_message: return await update.message.reply_text("Reply karke bol kisko chup karana hai.")
    try:
        permissions = ChatPermissions(can_send_messages=False)
        await context.bot.restrict_chat_member(update.effective_chat.id, update.message.reply_to_message.from_user.id, permissions=permissions)
        await update.message.reply_text("🤐 **Muh Band!** Shanti bani rahe.")
    except: await update.message.reply_text("❌ Error.")

async def clear_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_authorized(update): return await update.message.reply_text("Power nahi hai tere paas!")
    try:
        amount = int(context.args[0]) if context.args else 5
        msg_id = update.message.message_id
        for i in range(amount + 1):
            try: await context.bot.delete_message(update.effective_chat.id, msg_id - i)
            except: pass
        await context.bot.send_message(update.effective_chat.id, f"🧹 **Safayi Complete!** {amount} messages saaf.")
    except: await update.message.reply_text("Number likh bhai!")

# ================= NEW FEATURES (20+) =================

# 1. SHOUT
async def shout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = " ".join(context.args).upper()
    if not text: return
    await update.message.reply_text(f"📢 **{text}** 📢")

# 2. WARN (No warn self)
async def warn_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_authorized(update): return
    if not update.message.reply_to_message:
        return await update.message.reply_text("Reply karke `/warn` likh.")
    
    target = update.message.reply_to_message.from_user
    if target.id == context.bot.id:
        return await update.message.reply_text("🤬 **Hoshiyari?** Mujhe warn dega?")
    
    # Init warn count
    if target.id not in warns: warns[target.id] = 0
    warns[target.id] += 1
    
    await update.message.reply_text(f"⚠️ **Warning di gayi hai!**\n{target.first_name} ki warnings: {warns[target.id]}/3")
    
    if warns[target.id] >= 3:
        warns[target.id] = 0
        try:
            await context.bot.ban_chat_member(update.effective_chat.id, target.id)
            await update.message.reply_text(f"🚫 **Limit Cross!** {target.first_name} ko ban kar diya.")
        except:
            await update.message.reply_text("❌ Ban nahi kar paya (Admin issue).")

# 3. NUKE (With Confirmation)
async def nuke_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_authorized(update): return
    
    keyboard = [[
        InlineKeyboardButton("✅ HAAN UDA DO", callback_data='confirm_nuke'),
        InlineKeyboardButton("❌ NAHI MAZAK THA", callback_data='cancel_nuke')
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("☢️ **NUKE WARNING!**\nKya pakka last 50 messages udana chahta hai?", reply_markup=reply_markup)

async def nuke_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == 'cancel_nuke':
        await query.edit_message_text("😌 **Bach gaye!** Nuke cancel kar diya.")
    elif query.data == 'confirm_nuke':
        await query.edit_message_text("💥 **BOOM!** Safayi shuru...")
        chat_id = query.message.chat_id
        msg_id = query.message.message_id
        count = 0
        for i in range(50): # Limit 50 to prevent freezing
            try:
                await context.bot.delete_message(chat_id, msg_id - i)
                count += 1
            except: pass
        await context.bot.send_message(chat_id, f"☢️ **Nuke Successful!** {count} messages raakh ho gaye.")

# 4. PROMOTE / DEMOTE
async def promote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_authorized(update): return
    if not update.message.reply_to_message: return await update.message.reply_text("Kisko promote karna hai? Reply kar.")
    
    user_id = update.message.reply_to_message.from_user.id
    try:
        await context.bot.promote_chat_member(
            update.effective_chat.id, user_id,
            can_manage_chat=True, can_delete_messages=True, can_invite_users=True
        )
        await update.message.reply_text(f"👮‍♂️ **Mubarak ho!** Ab tu bhi Admin hai.")
    except: await update.message.reply_text("❌ Main khud full admin nahi hu shayad.")

async def demote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_authorized(update): return
    if not update.message.reply_to_message: return
    user_id = update.message.reply_to_message.from_user.id
    try:
        await context.bot.promote_chat_member(
            update.effective_chat.id, user_id,
            can_manage_chat=False, can_delete_messages=False, can_invite_users=False
        )
        await update.message.reply_text(f"📉 **Demoted!** Power chheen li gayi hai.")
    except: await update.message.reply_text("❌ Error.")

# 5. SLOW MODE
async def set_slow_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_authorized(update): return
    if not context.args: return await update.message.reply_text("Seconds bata! Ex: `/setslowmode 10`")
    
    seconds = int(context.args[0])
    try:
        await context.bot.set_chat_slow_mode_delay(update.effective_chat.id, seconds)
        await update.message.reply_text(f"🐢 **Slow Mode On!** Ab har {seconds} sec mein ek msg aayega.")
    except: await update.message.reply_text("❌ Error.")

# 6. AFK (Away From Keyboard)
async def afk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    reason = " ".join(context.args) if context.args else "Busy hoon bhai"
    afk_users[user.id] = reason
    await update.message.reply_text(f"💤 **{user.first_name} ab AFK hai.**\nReason: {reason}")

# 7. PIN / UNPIN
async def pin_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_authorized(update): return
    if not update.message.reply_to_message: return
    try:
        await context.bot.pin_chat_message(update.effective_chat.id, update.message.reply_to_message.message_id)
        await update.message.reply_text("📌 **Pinned!** Sab dhyan do idhar.")
    except: pass

async def unpin_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_authorized(update): return
    try:
        await context.bot.unpin_chat_message(update.effective_chat.id)
        await update.message.reply_text("📍 **Unpinned!**")
    except: pass

# 8. ROLL & BALA
async def roll(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_dice(update.effective_chat.id)

async def bala(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Sends Bala GIF (Housefull 4 reference)
    gif_url = "https://media1.tenor.com/m/Yk3y0U0mSzkAAAAC/akshay-kumar-bala.gif"
    await context.bot.send_animation(update.effective_chat.id, gif_url, caption="💃 **Shaitan ka Saala!**")

# 9. AUTO REPLY SYSTEM
async def set_auto_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_authorized(update): return
    if len(context.args) < 2:
        return await update.message.reply_text("Aise likh: `/setautoreply [word] [reply]`")
    
    trigger = context.args[0].lower()
    response = " ".join(context.args[1:])
    auto_replies[trigger] = response
    await update.message.reply_text(f"🤖 **Auto Reply Set!**\nJab koi bolega '{trigger}', main bolunga '{response}'.")

async def del_auto_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_authorized(update): return
    trigger = context.args[0].lower() if context.args else ""
    if trigger in auto_replies:
        del auto_replies[trigger]
        await update.message.reply_text(f"🗑️ '{trigger}' ka reply hata diya.")
    else:
        await update.message.reply_text("Ye word set hi nahi tha.")

# --- MESSAGE MONITOR (AFK & AUTO REPLY CHECKER) ---
async def message_monitor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    
    user = update.effective_user
    text = update.message.text.lower()
    
    # 1. Check if sender was AFK -> Remove AFK
    if user.id in afk_users:
        del afk_users[user.id]
        await update.message.reply_text(f"👋 **Welcome Back {user.first_name}!** AFK hata diya.")

    # 2. Check if replying to AFK user
    if update.message.reply_to_message:
        target_id = update.message.reply_to_message.from_user.id
        if target_id in afk_users:
            reason = afk_users[target_id]
            await update.message.reply_text(f"🤫 **Disturb mat kar!** Wo AFK hai.\nReason: {reason}")
            
    # 3. Check Auto Replies
    for word, reply in auto_replies.items():
        if word in text:
            await update.message.reply_text(reply)
            break

async def admin_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await is_authorized(update):
        await update.message.reply_text("👑 **System Admin!** Tu hi hai karta dharta.")
    else:
        await update.message.reply_text("👶 **Bachcha hai tu.**")

# --- MAIN SETUP ---
if __name__ == '__main__':
    keep_alive()
    
    if not TOKEN:
        print("❌ Error: BOT_TOKEN env variable missing hai!")
        exit()

    app = ApplicationBuilder().token(TOKEN).build()

    # Admin/Mod Commands
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('login', login))
    app.add_handler(CommandHandler('admin', admin_check))
    
    app.add_handler(CommandHandler('kick', kick_user))
    app.add_handler(CommandHandler('mute', mute_user))
    app.add_handler(CommandHandler('clear', clear_chat))
    
    # New Features
    app.add_handler(CommandHandler('shout', shout))
    app.add_handler(CommandHandler('warn', warn_user))
    app.add_handler(CommandHandler('nuke', nuke_request))
    app.add_handler(CallbackQueryHandler(nuke_callback, pattern='^.*nuke$')) # Handles Yes/No buttons
    
    app.add_handler(CommandHandler('promote', promote))
    app.add_handler(CommandHandler('demote', demote))
    app.add_handler(CommandHandler('setslowmode', set_slow_mode))
    
    app.add_handler(CommandHandler('pin', pin_msg))
    app.add_handler(CommandHandler('unpin', unpin_msg))
    
    app.add_handler(CommandHandler('roll', roll))
    app.add_handler(CommandHandler('bala', bala))
    
    app.add_handler(CommandHandler('afk', afk))
    
    app.add_handler(CommandHandler('setautoreply', set_auto_reply))
    app.add_handler(CommandHandler('deleteautoreply', del_auto_reply))

    # Message Monitor (Must be last)
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), message_monitor))

    print("🤖 Bot System Fully Upgraded! (Started)...")
    app.run_polling()
