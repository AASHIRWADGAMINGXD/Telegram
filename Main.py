import os
import logging
import asyncio
from telegram import Update, ChatPermissions
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, filters
from keep_alive import keep_alive

# --- LOGGING SETUP ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# --- CONFIG & VARIABLES ---
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_PASSWORD = os.getenv("ADMIN_PASS", "BhaiKaSystem")

# Database (Temporary RAM mein)
authorized_users = set() # Logged in temporary admins
warns = {} # User warnings count

# --- HELPER: CHECK POWER ---
async def check_auth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    
    # 1. Check if user is the Owner/Admin in Telegram
    member = await context.bot.get_chat_member(chat.id, user.id)
    if member.status in ['creator', 'administrator']:
        return True
        
    # 2. Check if logged in via Password
    if user.id in authorized_users:
        return True
        
    await update.message.reply_text("✋ **Ruk ja chotu!** Tere paas power nahi hai.")
    return False

# --- 1. BASIC COMMANDS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🙏 **Namaste Bhai!**\nMain hoon Group Manager Pro.\n\n"
        "📜 **Features:**\n"
        "• `/help` - Sab commands dekhne ke liye\n"
        "• `/login [pass]` - Admin banne ke liye"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
🔥 **Bhai Ka Menu (20+ Features):**

**👮‍♂️ Moderation:**
/kick - Bahar feko
/ban - Hamesha ke liye bye
/unban - Maaf kiya
/mute - Muh band
/unmute - Muh khola
/warn - Warning de (3 pe ban)
/resetwarn - Warning hata
/pin - Message chipka de
/unpin - Pin hata de
/lock - Chat band (Sirf admin)
/unlock - Chat chalu
/clear [num] - Message uda de
/nuke - Sab saaf (Last 100)

**⚙️ System:**
/login [pass] - Password access
/logout - Access khatam
/admin - Check power
/id - User/Chat ID
/info - User ki kundali
/staff - Admins ki list
/shout - Announcement
/ping - Bot speed check
"""
    await update.message.reply_text(help_text)

# --- 2. AUTH SYSTEM ---
async def login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args: return await update.message.reply_text("Pass toh daal bhai! `/login [pass]`")
    if context.args[0] == ADMIN_PASSWORD:
        authorized_users.add(update.effective_user.id)
        await update.message.reply_text("😎 **Access Granted!** Ab tu Boss hai.")
    else:
        await update.message.reply_text("🤨 **Galat Password!** Nikal pehli fursat mein.")

async def logout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id in authorized_users:
        authorized_users.remove(update.effective_user.id)
        await update.message.reply_text("👋 **Logged Out!** Power wapas le li gayi hai.")
    else:
        await update.message.reply_text("Tu pehle se hi logged out hai bhai.")

# --- 3. KICK & BAN ---
async def kick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update, context): return
    if not update.message.reply_to_message: return await update.message.reply_text("Reply karke bol kisko udana hai.")
    
    user = update.message.reply_to_message.from_user
    try:
        await context.bot.ban_chat_member(update.effective_chat.id, user.id)
        await context.bot.unban_chat_member(update.effective_chat.id, user.id) # Unban immediately just to kick
        await update.message.reply_text(f"🦶 **Kick!** {user.first_name} ko hawa mein uda diya.")
    except: await update.message.reply_text("❌ Error: Ye banda mujhse taqatwar hai.")

async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update, context): return
    if not update.message.reply_to_message: return await update.message.reply_text("Reply kar bhai.")
    user = update.message.reply_to_message.from_user
    try:
        await context.bot.ban_chat_member(update.effective_chat.id, user.id)
        await update.message.reply_text(f"🔨 **Ban Hammer!** {user.first_name}, ab tu kabhi wapas nahi aayega.")
    except: await update.message.reply_text("❌ Admin ko ban nahi kar sakta.")

async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update, context): return
    if not context.args: return await update.message.reply_text("User ID de bhai unban karne ke liye.")
    try:
        await context.bot.unban_chat_member(update.effective_chat.id, int(context.args[0]))
        await update.message.reply_text("😇 **Maaf kiya!** Banda wapas aa sakta hai.")
    except: await update.message.reply_text("❌ ID galat hai ya banda banned nahi hai.")

# --- 4. MUTE SYSTEM ---
async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update, context): return
    if not update.message.reply_to_message: return await update.message.reply_text("Kisko chup karana hai? Reply kar.")
    user = update.message.reply_to_message.from_user
    try:
        permissions = ChatPermissions(can_send_messages=False)
        await context.bot.restrict_chat_member(update.effective_chat.id, user.id, permissions=permissions)
        await update.message.reply_text(f"🤐 **Shhh!** {user.first_name} ke muh pe tape laga diya.")
    except: await update.message.reply_text("❌ Error aagaya.")

async def unmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update, context): return
    if not update.message.reply_to_message: return await update.message.reply_text("Reply kar bhai.")
    user = update.message.reply_to_message.from_user
    try:
        permissions = ChatPermissions(can_send_messages=True, can_send_media_messages=True, can_send_other_messages=True)
        await context.bot.restrict_chat_member(update.effective_chat.id, user.id, permissions=permissions)
        await update.message.reply_text(f"🗣️ **Bol sakta hai!** {user.first_name}, shuru ho ja.")
    except: await update.message.reply_text("❌ Error.")

# --- 5. WARNING SYSTEM ---
async def warn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update, context): return
    if not update.message.reply_to_message: return await update.message.reply_text("Reply to kar!")
    
    user = update.message.reply_to_message.from_user
    chat_id = update.effective_chat.id
    
    if chat_id not in warns: warns[chat_id] = {}
    if user.id not in warns[chat_id]: warns[chat_id][user.id] = 0
    
    warns[chat_id][user.id] += 1
    count = warns[chat_id][user.id]
    
    await update.message.reply_text(f"⚠️ **Warning {count}/3!** Sudhar ja {user.first_name}!")
    
    if count >= 3:
        try:
            await context.bot.ban_chat_member(chat_id, user.id)
            warns[chat_id][user.id] = 0
            await update.message.reply_text(f"🚫 **Limit Cross!** 3 warnings ho gayi, {user.first_name} gaya kaam se.")
        except: await update.message.reply_text("❌ Ban karne mein fail ho gaya.")

async def reset_warn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update, context): return
    if not update.message.reply_to_message: return
    user = update.message.reply_to_message.from_user
    if update.effective_chat.id in warns and user.id in warns[update.effective_chat.id]:
        warns[update.effective_chat.id][user.id] = 0
    await update.message.reply_text(f"♻️ **Reset!** {user.first_name} ki warnings clear kar di.")

# --- 6. CHAT CLEANUP ---
async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update, context): return
    try:
        amount = int(context.args[0]) if context.args else 5
        msg_id = update.message.message_id
        chat_id = update.effective_chat.id
        
        # Simple loop deletion (safe method)
        count = 0
        for i in range(amount + 1):
            try:
                await context.bot.delete_message(chat_id, msg_id - i)
                count += 1
            except: pass
        
        status_msg = await context.bot.send_message(chat_id, f"🧹 **Safayi Complete!** {count-1} messages uda diye.")
        await asyncio.sleep(3)
        await status_msg.delete()
    except ValueError: await update.message.reply_text("Number daal bhai.")

async def nuke(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update, context): return
    await update.message.reply_text("☢️ **NUKE START!** Sab uda raha hoon...")
    # Calls clear internally for 100 messages
    context.args = ["100"]
    await clear(update, context)

# --- 7. UTILITIES & FUN ---
async def pin_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update, context): return
    if not update.message.reply_to_message: return await update.message.reply_text("Reply kar jisko pin karna hai.")
    try:
        await update.message.reply_to_message.pin(disable_notification=False)
        await update.message.reply_text("📌 **Chipka Diya!** Message pin ho gaya.")
    except: await update.message.reply_text("❌ Pin nahi kar pa raha.")

async def unpin_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update, context): return
    try:
        await context.bot.unpin_chat_message(update.effective_chat.id)
        await update.message.reply_text("📍 **Pin Removed!**")
    except: pass

async def lock_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update, context): return
    perms = ChatPermissions(can_send_messages=False)
    await context.bot.set_chat_permissions(update.effective_chat.id, perms)
    await update.message.reply_text("🔒 **Chat LOCKED!** Ab koi kuch nahi bolega. Shanti.")

async def unlock_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update, context): return
    perms = ChatPermissions(can_send_messages=True, can_send_media_messages=True, can_send_other_messages=True)
    await context.bot.set_chat_permissions(update.effective_chat.id, perms)
    await update.message.reply_text("🔓 **Chat UNLOCKED!** Chalo shuru ho jao.")

async def get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    reply_id = update.message.reply_to_message.from_user.id if update.message.reply_to_message else "N/A"
    text = f"🆔 **IDs Information:**\n\n👤 **User ID:** `{user_id}`\n🏠 **Chat ID:** `{chat_id}`"
    if reply_id != "N/A": text += f"\n👉 **Replied User ID:** `{reply_id}`"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def user_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.reply_to_message.from_user if update.message.reply_to_message else update.effective_user
    text = (f"🕵️ **Jasoosi Report:**\n\n"
            f"👤 **Naam:** {user.full_name}\n"
            f"🆔 **ID:** `{user.id}`\n"
            f"🤖 **Bot hai?** {'Haan' if user.is_bot else 'Nahi'}\n"
            f"🔗 **Username:** @{user.username if user.username else 'Nahi hai'}")
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def shout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update, context): return
    msg = " ".join(context.args)
    if not msg: return await update.message.reply_text("Kya chilana hai? Likh toh sahi.")
    await update.message.reply_text(f"📢 **AILAAN:**\n\n{msg}")

async def staff(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admins = await context.bot.get_chat_administrators(update.effective_chat.id)
    text = "👮‍♂️ **Group ke Dons (Admins):**\n"
    for admin in admins:
        text += f"• {admin.user.first_name}\n"
    await update.message.reply_text(text)

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🏓 **Pong!** System full speed mein hai bhai.")

# --- MAIN ---
if __name__ == '__main__':
    keep_alive() # Start Flask
    
    if not TOKEN:
        print("Error: Token nahi mila env mein!")
        exit()

    app = ApplicationBuilder().token(TOKEN).build()

    # Handlers Add Kar Raha Hoon
    handlers = [
        ('start', start), ('help', help_command),
        ('login', login), ('logout', logout),
        ('kick', kick), ('ban', ban), ('unban', unban),
        ('mute', mute), ('unmute', unmute),
        ('warn', warn), ('resetwarn', reset_warn),
        ('clear', clear), ('nuke', nuke),
        ('pin', pin_msg), ('unpin', unpin_msg),
        ('lock', lock_chat), ('unlock', unlock_chat),
        ('id', get_id), ('info', user_info),
        ('shout', shout), ('staff', staff),
        ('ping', ping), ('admin', lambda u,c: check_auth(u,c))
    ]

    for cmd, func in handlers:
        app.add_handler(CommandHandler(cmd, func))

    print("🤖 Bot Start! System set hai...")
    app.run_polling()
