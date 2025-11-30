import os
import logging
import asyncio
import random
from telegram import Update, ChatPermissions, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler, filters
from keep_alive import keep_alive

# --- LOGGING ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# --- CONFIG ---
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_PASSWORD = os.getenv("ADMIN_PASS", "BhaiKaSystem")

# --- DATA ---
authorized_users = set()
warns = {}

# --- HELPER: CHECK POWER ---
async def check_auth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    
    # Check Temporary Login
    if user.id in authorized_users: return True
    
    # Check Real Admin
    try:
        member = await context.bot.get_chat_member(chat.id, user.id)
        if member.status in ['creator', 'administrator']: return True
    except: pass
        
    await update.message.reply_text("✋ **Ruk ja lala!** Tu Admin nahi hai.")
    return False

async def is_admin(chat_id, user_id, context):
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        return member.status in ['creator', 'administrator'] or user_id in authorized_users
    except: return False

# --- 1. MODERATION UPGRADED ---

# /shout - Improved
async def shout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update, context): return
    
    msg = " ".join(context.args)
    if not msg: return await update.message.reply_text("Are bhai likhna kya hai? `/shout Hello`")
    
    # Delete commander's message for cleanliness
    try: await update.message.delete()
    except: pass
    
    formatted_msg = f"📢 **SYSTEM KA AILAAN!** 📢\n\n👉 {msg}\n\n~ *{update.effective_user.first_name}*"
    await context.bot.send_message(update.effective_chat.id, formatted_msg, parse_mode=ParseMode.MARKDOWN)

# /warn - Smart (No Self/Admin Warn)
async def warn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update, context): return
    if not update.message.reply_to_message: return await update.message.reply_text("Reply karke warn de bhai.")
    
    target = update.message.reply_to_message.from_user
    chat_id = update.effective_chat.id
    bot_id = context.bot.id

    # SELF PROTECTION & ADMIN PROTECTION
    if target.id == bot_id:
        return await update.message.reply_text("😡 **Mazaak hai kya?** Main khud ko warn nahi dunga.")
    
    if await is_admin(chat_id, target.id, context):
        return await update.message.reply_text("❌ **Galti!** Wo Admin hai, usko warn nahi de sakte.")

    if chat_id not in warns: warns[chat_id] = {}
    if target.id not in warns[chat_id]: warns[chat_id][target.id] = 0
    
    warns[chat_id][target.id] += 1
    count = warns[chat_id][target.id]
    
    await update.message.reply_text(f"⚠️ **Oye {target.first_name}!** Sudhar ja.\nWarning: {count}/3")
    
    if count >= 3:
        try:
            await context.bot.ban_chat_member(chat_id, target.id)
            warns[chat_id][target.id] = 0
            await update.message.reply_text(f"🚫 **Khatam!** {target.first_name} ko 3 warnings ke baad uda diya.")
        except: await update.message.reply_text("❌ Error: Banda power mein hai, ban nahi hua.")

# /nuke - With Confirmation Button
async def nuke_ask(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update, context): return
    
    keyboard = [
        [
            InlineKeyboardButton("✅ Udado Sab", callback_data='nuke_yes'),
            InlineKeyboardButton("❌ Ruk Jao", callback_data='nuke_no')
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("☢️ **WARNING:** Bhai tu pichle 100 messages udaane wala hai. Soch le!", reply_markup=reply_markup)

async def nuke_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    # Check if clicker is admin
    if not await is_admin(query.message.chat.id, query.from_user.id, context):
        return await query.answer("Tu mat chhu button!", show_alert=True)

    if query.data == 'nuke_yes':
        await query.edit_message_text("💥 **BOOM!** Safayi shuru...")
        # Delete 100 messages
        chat_id = query.message.chat_id
        msg_id = query.message.message_id
        for i in range(100):
            try: await context.bot.delete_message(chat_id, msg_id - i)
            except: pass
        msg = await context.bot.send_message(chat_id, "☢️ **Area Clear!** Radiation level normal.")
        await asyncio.sleep(5)
        await msg.delete()
    else:
        await query.edit_message_text("😌 **Bach gaye!** Nuke cancel kar diya.")

# --- 2. NEW FUN & UTILITY FEATURES (10+) ---

# 1. /roast - Beizzati
async def roast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    insults = [
        "Shakal dekh ke lagta hai bhagwan ne 'Rough Draft' save kar diya.",
        "Tere dimaag mein akal nahi, sirf 'Loading...' ka circle ghoomta hai.",
        "Bhai tu paida hua tha ya download hua tha?",
        "Jitna tu bolta hai, utna agar sochta toh aaj NASA mein hota.",
        "Tera IQ room temperature se bhi kam hai.",
        "Tujhe dekh ke lagta hai evolution abhi complete nahi hua."
    ]
    target = update.message.reply_to_message.from_user if update.message.reply_to_message else update.effective_user
    await update.message.reply_text(f"🔥 **{target.first_name}**, {random.choice(insults)}")

# 2. /dp - Profile Pic Stealer
async def get_dp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = update.message.reply_to_message.from_user if update.message.reply_to_message else update.effective_user
    photos = await target.get_profile_photos(limit=1)
    if not photos.total_count:
        return await update.message.reply_text("❌ Isne DP chupa rakhi hai ya hai hi nahi.")
    await update.message.reply_photo(photos.photos[0][-1].file_id, caption=f"📸 Ye le **{target.first_name}** ki DP.")

# 3. /slap - Fun Action
async def slap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message: return await update.message.reply_text("Kisko maarna hai? Reply kar.")
    attacker = update.effective_user.first_name
    victim = update.message.reply_to_message.from_user.first_name
    await update.message.reply_text(f"👋 **DHADAAAAM!**\n{attacker} ne {victim} ke kaan ke neeche bajaya!")

# 4. /toss - Coin Flip
async def toss(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = random.choice(["Heads 🪙", "Tails 🦅"])
    await update.message.reply_text(f"Sikka uchhal diya hai...\n👉 **{result}** aaya hai!")

# 5. /report - Snitch to Admins
async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message: return await update.message.reply_text("Reply karke `/report` likh.")
    chat_name = update.effective_chat.title
    user = update.effective_user.first_name
    reported_user = update.message.reply_to_message.from_user.first_name
    msg_link = f"https://t.me/c/{str(update.effective_chat.id)[4:]}/{update.message.reply_to_message.message_id}"
    
    # Send generic alert
    await update.message.reply_text("👮‍♂️ **Report Bhej Di!** Admins check kar lenge.")
    
    # Tag Admins (Bot functionality to notify admins)
    admins = await context.bot.get_chat_administrators(update.effective_chat.id)
    admin_text = f"🚨 **REPORT ALERT** in {chat_name}\n👤 Reporter: {user}\n😈 Culprit: {reported_user}\n🔗 Message: [Link]({msg_link})"
    
    for admin in admins:
        if not admin.user.is_bot:
            try: await context.bot.send_message(admin.user.id, admin_text, parse_mode=ParseMode.MARKDOWN)
            except: pass # Can't DM admin if they haven't started bot

# 6. /stats - Group Info
async def chat_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    members = await context.bot.get_chat_member_count(chat.id)
    await update.message.reply_text(f"📊 **Group Stats:**\n\n📛 Naam: {chat.title}\n👥 Members: {members}\n🆔 ID: `{chat.id}`", parse_mode=ParseMode.MARKDOWN)

# 7. /roll - Dice
async def roll(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await context.bot.send_dice(update.effective_chat.id)
    await asyncio.sleep(3)
    await update.message.reply_text(f"🎲 Number **{msg.dice.value}** aaya hai!")

# 8. /welcome - Fake Welcome (Manual)
async def welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message: return
    new_user = update.message.reply_to_message.from_user.first_name
    await update.message.reply_text(f"🎉 **Swagat hai {new_user}!**\nChappal bahar utaar ke aana group mein. Mauj kar! 🥳")

# 9. /invitelink - Link Generator
async def invite_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update, context): return
    link = await context.bot.export_chat_invite_link(update.effective_chat.id)
    await update.message.reply_text(f"🔗 **Ye le Link:**\n{link}")

# 10. /joke - Random Joke
async def joke(update: Update, context: ContextTypes.DEFAULT_TYPE):
    jokes = [
        "Teacher: 'M' se meaning batao?\nStudent: Main hoon na!\nTeacher: 'T' se?\nStudent: Tu hai kaun? 😂",
        "Pappu: Papa, mujhe shaadi nahi karni.\nPapa: Kyun?\nPappu: Sab ladkiya aapse maangti hai paise, mujhe sharam aati hai! 🤣",
        "Zindagi mein do hi log khush hai:\nEk wo jise koi nahi jaanta,\nAur dusra wo jo kisi ki nahi sunta. 😎"
    ]
    await update.message.reply_text(f"😂 **Joke:**\n{random.choice(jokes)}")

# --- OLD FEATURES (Standard) ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🙏 **Namaste!**\nGangster Bot Online hai.\nCommands ke liye `/help` dabao.")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = """
💀 **BHAI KA MENU** 💀

**👮 Admin Power:**
/kick, /ban, /unban, /mute, /unmute
/warn (Smart System)
/nuke (With Confirmation)
/shout (Announcement)
/pin, /unpin
/lock, /unlock
/clear [num]

**🎭 Fun & Gang:**
/roast - Beizzati
/slap - Chamat
/dp - Photo churao
/toss - Sikka
/roll - Ludo dice
/joke - Hasi mazaak
/report - Shikayat karo
/stats - Group info
/welcome - Swagat

**⚙️ System:**
/login [pass], /logout
"""
    await update.message.reply_text(text)

async def login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args: return await update.message.reply_text("Pass toh daal bhai! `/login [pass]`")
    if context.args[0] == ADMIN_PASSWORD:
        authorized_users.add(update.effective_user.id)
        await update.message.reply_text("😎 **Access Granted!** Power aa gayi.")
    else:
        await update.message.reply_text("🤨 **Chal nikal!** Galat password.")

async def kick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update, context): return
    if not update.message.reply_to_message: return
    try:
        await context.bot.ban_chat_member(update.effective_chat.id, update.message.reply_to_message.from_user.id)
        await context.bot.unban_chat_member(update.effective_chat.id, update.message.reply_to_message.from_user.id)
        await update.message.reply_text("🦶 **Kick!** Bahar fek diya.")
    except: await update.message.reply_text("❌ Error.")

async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update, context): return
    if not update.message.reply_to_message: return
    try:
        await context.bot.ban_chat_member(update.effective_chat.id, update.message.reply_to_message.from_user.id)
        await update.message.reply_text("🔨 **Banned!** Ab nahi dikhega.")
    except: await update.message.reply_text("❌ Error.")

async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update, context): return
    if not context.args: return
    try:
        await context.bot.unban_chat_member(update.effective_chat.id, int(context.args[0]))
        await update.message.reply_text("😇 **Unbanned!**")
    except: pass

async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update, context): return
    if not update.message.reply_to_message: return
    try:
        perms = ChatPermissions(can_send_messages=False)
        await context.bot.restrict_chat_member(update.effective_chat.id, update.message.reply_to_message.from_user.id, permissions=perms)
        await update.message.reply_text("🤐 **Muted!**")
    except: pass

async def unmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update, context): return
    if not update.message.reply_to_message: return
    try:
        perms = ChatPermissions(can_send_messages=True, can_send_media_messages=True, can_send_other_messages=True)
        await context.bot.restrict_chat_member(update.effective_chat.id, update.message.reply_to_message.from_user.id, permissions=perms)
        await update.message.reply_text("🗣️ **Unmuted!**")
    except: pass

async def clear_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update, context): return
    try:
        amount = int(context.args[0]) if context.args else 5
        msg_id = update.message.message_id
        chat_id = update.effective_chat.id
        for i in range(amount + 1):
            try: await context.bot.delete_message(chat_id, msg_id - i)
            except: pass
        msg = await context.bot.send_message(chat_id, "🧹 **Saaf!**")
        await asyncio.sleep(2)
        await msg.delete()
    except: pass

async def pin_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update, context): return
    if update.message.reply_to_message:
        await update.message.reply_to_message.pin()
        await update.message.reply_text("📌 **Pinned!**")

async def unpin_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update, context): return
    await context.bot.unpin_chat_message(update.effective_chat.id)
    await update.message.reply_text("📍 **Unpinned!**")

async def lock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update, context): return
    perms = ChatPermissions(can_send_messages=False)
    await context.bot.set_chat_permissions(update.effective_chat.id, perms)
    await update.message.reply_text("🔒 **Chat LOCKED!**")

async def unlock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update, context): return
    perms = ChatPermissions(can_send_messages=True, can_send_media_messages=True, can_send_other_messages=True)
    await context.bot.set_chat_permissions(update.effective_chat.id, perms)
    await update.message.reply_text("🔓 **Chat UNLOCKED!**")

# --- EXECUTION ---
if __name__ == '__main__':
    keep_alive()
    if not TOKEN:
        print("Error: TOKEN Missing")
        exit()

    app = ApplicationBuilder().token(TOKEN).build()

    # Handlers List
    handlers = [
        ('start', start), ('help', help_cmd), ('login', login),
        ('kick', kick), ('ban', ban), ('unban', unban),
        ('mute', mute), ('unmute', unmute),
        ('warn', warn), ('nuke', nuke_ask), ('shout', shout),
        ('clear', clear_chat), ('pin', pin_msg), ('unpin', unpin_msg),
        ('lock', lock), ('unlock', unlock),
        ('roast', roast), ('dp', get_dp), ('slap', slap),
        ('toss', toss), ('roll', roll), ('stats', chat_stats),
        ('report', report), ('welcome', welcome),
        ('invitelink', invite_link), ('joke', joke)
    ]

    for cmd, func in handlers:
        app.add_handler(CommandHandler(cmd, func))
    
    # Callback Handler for Nuke Buttons
    app.add_handler(CallbackQueryHandler(nuke_confirm, pattern='^nuke_'))

    print("🤖 Gangster Bot Started...")
    app.run_polling()
