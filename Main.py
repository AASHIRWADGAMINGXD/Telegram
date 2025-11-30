import os
import logging
import asyncio
import time
from telegram import Update, ChatPermissions
from telegram.constants import ChatMemberStatus
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
from keep_alive import keep_alive

# --- LOGGING ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# --- CONFIGURATION ---
TOKEN = os.getenv("BOT_TOKEN") 
ADMIN_PASSWORD = os.getenv("ADMIN_PASS", "BhaiKaSystem") 

# --- DATABASE (Temporary Memory) ---
# Note: Real bots use MongoDB/SQL. This resets if bot restarts.
authorized_users = set()        # Users who logged in
warns = {}                      # {user_id: count}
afk_status = {}                 # {user_id: reason}
auto_replies = {}               # {keyword: response}
nuke_state = {}                 # {chat_id: {initiator_id, time}}

# --- HELPER: AUTH CHECK ---
async def is_authorized(update: Update):
    user_id = update.effective_user.id
    if user_id in authorized_users:
        return True
    return False

# ================= OLD COMMANDS (KEPT) =================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🙏 **Namaste Bhai! Version 2.0 Live.** \n\n"
        "Main is ilake ka naya Don hoon.\n"
        "Commands ki list lambi hai, `/help` daba ke dekh le.\n\n"
        "Password daal ke power le: `/login [password]`"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📜 **Command List (System):**\n\n"
        "👮 **Admin:**\n"
        "/kick - Laat maaro\n"
        "/mute - Muh band karo\n"
        "/warn - Warning de (3 pe Kick)\n"
        "/nuke - Sab uda do (Dangerous)\n"
        "/shout - Zor se bolo\n"
        "/setslowmode [seconds] - Chat slow karo\n"
        "/promote /demote - Power do/cheeno\n"
        "/setautoreply [word] [reply] - Auto jawab set karo\n\n"
        "🙋 **Public:**\n"
        "/afk [reason] - Main ja raha hoon\n"
        "/admin - Check power\n"
        "/id - Apna ID dekho"
    )

async def login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not context.args:
        await update.message.reply_text("Password kaun likhega? `/login password`")
        return
    if context.args[0] == ADMIN_PASSWORD:
        authorized_users.add(user.id)
        await update.message.reply_text(f"😎 **Swagat hai Boss!** {user.first_name} ab System mein hai.")
    else:
        await update.message.reply_text("🤨 **Chal nikal!** Galat password.")

async def kick_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_authorized(update): return await update.message.reply_text("✋ Power nahi hai tere paas.")
    if not update.message.reply_to_message: return await update.message.reply_text("Reply toh kar bhai!")
    
    target = update.message.reply_to_message.from_user
    try:
        await context.bot.ban_chat_member(update.effective_chat.id, target.id)
        await update.message.reply_text(f"🦶 **Udta Teer!**\n{target.first_name} ko maidan se bahar fek diya.")
    except:
        await update.message.reply_text("❌ Error: Wo mujhse zyada takatwar hai.")

async def mute_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_authorized(update): return await update.message.reply_text("✋ Power nahi hai.")
    if not update.message.reply_to_message: return await update.message.reply_text("Reply kar!")
    
    target = update.message.reply_to_message.from_user
    try:
        await context.bot.restrict_chat_member(update.effective_chat.id, target.id, ChatPermissions(can_send_messages=False))
        await update.message.reply_text(f"🤐 **Khamosh!**\n{target.first_name} ab nahi bolega.")
    except:
        await update.message.reply_text("❌ Error.")

async def clear_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_authorized(update): return await update.message.reply_text("✋ Power nahi hai.")
    if not context.args: return await update.message.reply_text("Kitna udana hai? `/clear 5`")
    
    try:
        limit = int(context.args[0])
        msg_id = update.message.message_id
        count = 0
        for i in range(limit + 1):
            try:
                await context.bot.delete_message(update.effective_chat.id, msg_id - i)
                count += 1
            except: pass
        msg = await update.message.reply_text(f"🧹 **Safayi!** {count-1} messages gaye.")
        await asyncio.sleep(3)
        await msg.delete()
    except:
        await update.message.reply_text("Number daal bhai.")

async def admin_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await is_authorized(update): await update.message.reply_text("👑 Tu King hai bhai.")
    else: await update.message.reply_text("👶 Tu aam aadmi hai.")

# ================= NEW FEATURES (20+) =================

# 1. SHOUT (Announce)
async def shout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_authorized(update): return
    if not context.args: return await update.message.reply_text("Kya chilana hai?")
    
    text = " ".join(context.args).upper()
    await update.message.reply_text(f"📢 **SUNO SAB LOG!**\n\n{text}")

# 2. WARN SYSTEM
async def warn_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_authorized(update): return await update.message.reply_text("✋ Power nahi hai.")
    if not update.message.reply_to_message: return await update.message.reply_text("Reply kar ke warn de.")
    
    target = update.message.reply_to_message.from_user
    chat_id = update.effective_chat.id
    
    # Bot cannot warn itself
    if target.id == context.bot.id:
        await update.message.reply_text("😲 **Gaddari Karbe?** Apne bhai ko warn karega?")
        return

    # Logic
    current_warns = warns.get(target.id, 0) + 1
    warns[target.id] = current_warns
    
    await update.message.reply_text(f"⚠️ **Warning!**\n{target.first_name} sudhar ja!\nWarns: {current_warns}/3")
    
    if current_warns >= 3:
        try:
            await context.bot.ban_chat_member(chat_id, target.id)
            warns[target.id] = 0 # Reset
            await update.message.reply_text(f"🚫 **Khatam!** 3 Warns ho gaye. {target.first_name} gaya kaam se.")
        except:
            await update.message.reply_text("❌ Isko kick nahi kar pa raha.")

# 3. NUKE (Delete All with Confirmation)
async def nuke_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_authorized(update): return await update.message.reply_text("✋ Bas kar bhai, tere bas ka nahi.")
    
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    # Set state waiting for confirmation
    nuke_state[chat_id] = {'user': user_id, 'time': time.time()}
    
    await update.message.reply_text(
        "☢️ **NUKE WARNING!**\n"
        "Kya tu sach mein pichle 50 messages udana chahta hai?\n"
        "Confirm karne ke liye likh: `/confirm_nuke`"
    )

async def nuke_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    if chat_id not in nuke_state:
        return await update.message.reply_text("❌ Pehle `/nuke` toh likh.")
        
    data = nuke_state[chat_id]
    
    # Security: Only the person who requested can confirm
    if data['user'] != user_id:
        return await update.message.reply_text("✋ Tu beech mein mat bol.")
        
    await update.message.reply_text("💣 **Bum phatne wala hai!** (Deleting 50 msgs...)")
    
    # Deletion Loop (Simulating Nuke by deleting 50 messages)
    msg_id = update.message.message_id
    for i in range(50):
        try:
            await context.bot.delete_message(chat_id, msg_id - i)
            await asyncio.sleep(0.1) # Avoid flood limits
        except:
            pass
            
    await context.bot.send_message(chat_id, "☢️ **Area Clear Hai!**")
    del nuke_state[chat_id]

# 4. PROMOTE / DEMOTE
async def promote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_authorized(update): return
    if not update.message.reply_to_message: return await update.message.reply_text("Reply kar!")
    
    target = update.message.reply_to_message.from_user
    authorized_users.add(target.id)
    await update.message.reply_text(f"⏫ **Promotion!**\n{target.first_name} ab chota Don hai (Admin Added).")

async def demote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_authorized(update): return
    if not update.message.reply_to_message: return await update.message.reply_text("Reply kar!")
    
    target = update.message.reply_to_message.from_user
    if target.id in authorized_users:
        authorized_users.remove(target.id)
        await update.message.reply_text(f"⏬ **Demotion!**\n{target.first_name} ki power cheen li gayi.")
    else:
        await update.message.reply_text("Wo pehle se aam aadmi hai.")

# 5. SLOW MODE
async def set_slow_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_authorized(update): return await update.message.reply_text("✋ Power nahi hai.")
    
    if not context.args: return await update.message.reply_text("Seconds bata! Ex: `/setslowmode 10`")
    
    try:
        seconds = int(context.args[0])
        await context.bot.set_chat_slow_mode_delay(update.effective_chat.id, seconds)
        if seconds == 0:
            await update.message.reply_text("🏎️ **Slow mode hata diya!** Bhagegi ab gaadi.")
        else:
            await update.message.reply_text(f"🐢 **Slow Mode On!** Ab log har {seconds} second mein message karenge.")
    except Exception as e:
        await update.message.reply_text("❌ Error: Shayad main group ka pakka admin nahi hoon.")

# 6. AUTO REPLY SETTER
async def set_auto_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_authorized(update): return await update.message.reply_text("✋ Sirf admin.")
    
    # Ex: /setautoreply Hello Namaste
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Format: `/setautoreply [word] [reply]`")
        return
        
    keyword = args[0].lower()
    response = " ".join(args[1:])
    auto_replies[keyword] = response
    
    await update.message.reply_text(f"✅ **Set!** Jab koi bolega '{keyword}', main bolunga '{response}'.")

# 7. AFK SYSTEM
async def afk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    reason = " ".join(context.args) if context.args else "Bas aise hi"
    
    afk_status[user.id] = reason
    await update.message.reply_text(f"😴 **{user.first_name} so gaya.**\nReason: {reason}")

# --- GLOBAL MESSAGE HANDLER (Middleware) ---
# Handles AFK detection and Auto-Replies
async def global_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    
    user = update.effective_user
    text = update.message.text.lower()
    chat_id = update.effective_chat.id
    
    # 1. Check Auto Reply
    for keyword, reply in auto_replies.items():
        if keyword in text:
            await update.message.reply_text(reply)
            break

    # 2. Remove AFK if user speaks
    if user.id in afk_status:
        del afk_status[user.id]
        await update.message.reply_text(f"👋 **Welcome Back!** {user.first_name} wapas aa gaya.")

    # 3. Check if replying to AFK user
    if update.message.reply_to_message:
        target_id = update.message.reply_to_message.from_user.id
        if target_id in afk_status:
            reason = afk_status[target_id]
            await update.message.reply_text(f"🤫 **Disturb mat kar!**\nWo banda AFK hai.\nReason: {reason}")

    # 4. Check if mentioning AFK user (via @username)
    if update.message.entities:
        for entity in update.message.entities:
            if entity.type == "text_mention":
                if entity.user.id in afk_status:
                     await update.message.reply_text(f"🤫 **Disturb mat kar!** Wo banda AFK hai.")

async def get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"🆔 **Tera ID:** `{update.effective_user.id}`\n**Chat ID:** `{update.effective_chat.id}`", parse_mode='Markdown')

# --- MAIN EXECUTION ---
if __name__ == '__main__':
    keep_alive() # Render Support
    
    if not TOKEN:
        print("BOT_TOKEN gayab hai!")
        exit()

    app = ApplicationBuilder().token(TOKEN).build()

    # Admin Commands
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('help', help_command))
    app.add_handler(CommandHandler('login', login))
    app.add_handler(CommandHandler('kick', kick_user))
    app.add_handler(CommandHandler('mute', mute_user))
    app.add_handler(CommandHandler('clear', clear_chat))
    app.add_handler(CommandHandler('admin', admin_check))
    app.add_handler(CommandHandler('shout', shout))
    app.add_handler(CommandHandler('warn', warn_user))
    app.add_handler(CommandHandler('nuke', nuke_request))
    app.add_handler(CommandHandler('confirm_nuke', nuke_confirm))
    app.add_handler(CommandHandler('promote', promote))
    app.add_handler(CommandHandler('demote', demote))
    app.add_handler(CommandHandler('setslowmode', set_slow_mode))
    app.add_handler(CommandHandler('setautoreply', set_auto_reply))
    
    # Public Commands
    app.add_handler(CommandHandler('afk', afk))
    app.add_handler(CommandHandler('id', get_id))

    # Message Handler (Must be last)
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), global_message_handler))

    print("🤖 SYSTEM LIVE HAI BHAI (V2.0)...")
    app.run_polling()
