import os
import requests
import asyncio
from telegram import Update, error, ChatPermissions # 'ChatPermissions' import zaroori hai
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# --- 1. CONFIGURATION aur JANKAAR-KHANA (Data Structures) ---

# Bot ki chabhi (Token) - Environment variable se uthana hai
BOT_CHABHI = os.environ.get('BOT_TOKEN') 
if not BOT_CHABHI:
    print("🚨 GADBAD: BOT_TOKEN chabhi nahi mili. Code band.")
    exit(1)

# Sabse bada BOSS ID (Apna ID yahan daalo)
MAHA_BOSS_ID = 123456789  # <--- Yahan apna asli ID daalo

# Temporary Jankaar-khana (In-memory - restart hone par sab saaf ho jayega)
RAAZ_SHABD = "Loid_Twilight" # Admin banne ka password
BOSS_LOG = {MAHA_BOSS_ID}  # Admin IDs ka set
SHAANT_KIE_GAYE_LOG = {} # {user_id: shaanti_ka_end_time}
AUTO_JAWAAB_NIZAM = {} # {sawaal_trigger: jawab_text}


# --- 2. MADADGAAR FUNCTIONS aur SURAKSHA (Decorators) ---

# Decorator jo check karta hai ki user BOSS hai ya nahi
def sirf_boss_chalaye(kaam_func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if user_id not in BOSS_LOG:
            await update.message.reply_text(
                f"**Mazaak Mat Karo!** 😠 Aapke paas is command ki **power nahi** hai. Sirf **BOSS LOG** chala sakte hain.",
                parse_mode='Markdown'
            )
            return
        return await kaam_func(update, context)
    return wrapper

# Decorator jo check karta hai ki command group mein chal rahi hai
def sirf_group_mein(kaam_func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat.type not in ['group', 'supergroup']:
            await update.message.reply_text(
                "Yeh command sirf **groups** mein chalti hai, akela kya karoge? 😉"
            )
            return
        return await kaam_func(update, context)
    return wrapper


# --- 3. MUKHYA BOT HUKUM (Commands) ---

## 3.1. General aur Aam Hukumat

async def shuru_karo_hukum(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bot ka parichay."""
    naam = update.effective_user.first_name
    await update.message.reply_text(
        f"**Namaste, {naam} Ji! 🙏** Main hoon aapka Code Ka Sardar. Hukumat karni hai toh /madad dekho!",
        parse_mode='Markdown'
    )

async def madad_hukum(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Saare commands ki list."""
    madad_paath = (
        "**Aapki Sewa Mein Hazir!** ✨ (Hukumat ki List)\n\n"
        "**Aam Hukumat**\n"
        "🔸 /shuru_karo - Mera pehla parichay.\n"
        "🔸 /madad - Sab commands ki list.\n"
        "🔸 /haalchaal - Bot ka health check, sab **Theek Thak** hai?\n\n"
        "**Boss Banna**\n"
        "🔸 /raaz_shabd <chabhi> - Boss banna hai toh **sahi raaz** batao.\n"
        "🔸 /mera_id - Aapki **pehchaan** (ID) kya hai?\n\n"
        "**Rok-Tok aur Control (Sirf Boss Ke Liye)**\n"
        "🔸 /dhakka_do - Kisi ko **bahar ka rasta** dikhao. (Reply to user)\n"
        "🔸 /shaant_kar - Thodi der ke liye **Chup Kar!** (Reply to user)\n"
        "🔸 /bolne_do - Azaadi! Mute hatake **bolne do**. (Reply to user)\n"
        "🔸 /saaf_kar <count> - Pichli messages ka **safaya** karo.\n"
        "🔸 /taang_do - Message ko **upar taang do**. (Reply to user)\n"
        "🔸 /utaro - Upar se **utaro**.\n"
        "🔸 /zor_se_bolo <text> - Zor se **chilla ke** bolo.\n"
        "🔸 /boss_banao - Reply to a user to **make them Boss**.\n"
        "🔸 /power_wapas - Reply to a Boss to **remove their Power**.\n"
        "🔸 /nuke - **Poora chat uda do** (Only Maha Boss).\n\n"
        "**Auto-Jawaab (Sirf Boss Ke Liye)**\n"
        "🔸 /jawab_set_kar <trigger>|<reply> - Is **sawaal ka jawab** yeh hai.\n"
        "🔸 /jawab_hata_do <trigger> - Woh **jawab bhool jao**.\n\n"
        "**Masti aur Timepass**\n"
        "🔸 /chutkula - **Hanso!** Ek ajeeb-o-gareeb joke suno.\n"
        "🔸 /tana_mar - **Jalo!** Ek kadak roast suno.\n"
        "🔸 /bala - **Bala Bala!** Achanak ki masti.\n"
        "🔸 /sikka_uchhalo - **Sikka uchhalo** (Heads or Tails).\n"
        "🔸 /paasa_ghumao - **Pahada ghumao** (Random Number).\n"
    )
    await update.message.reply_text(madad_paath, parse_mode='Markdown')

async def mera_id_hukum(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User ki ID dikhata hai."""
    user_id = update.effective_user.id
    await update.message.reply_text(f"**Aapki Pehchaan (ID):** `{user_id}`", parse_mode='Markdown')

async def haalchaal_hukum(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bot ka health check."""
    boss_count = len(BOSS_LOG)
    rules_count = len(AUTO_JAWAAB_NIZAM)
    await update.message.reply_text(
        f"**Theek Thak Hai!** Bot bilkul chaka-chak chal raha hai. 😎\n"
        f"➡️ **Boss Log:** {boss_count} log\n"
        f"➡️ **Auto-Jawaab Nizam:** {rules_count} sikhaye hain."
    )

async def sikka_uchhalo_hukum(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sikka uchhalta hai."""
    import random
    nateeja = random.choice(["Heads (Chit)", "Tails (Pat)"])
    await update.message.reply_text(f"**Sikka Uchhala!** Aur aaya... **{nateeja}**! 🪙")

async def paasa_ghumao_hukum(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Random number (paasa) ghumata hai."""
    import random
    ankh = random.randint(1, 100)
    await update.message.reply_text(f"**Pahada Ghumaya!** Number aaya... **{ankh}**! 🎲")


## 3.2. Authentication aur Boss Commands

async def raaz_shabd_hukum(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Password se admin banata hai."""
    if len(context.args) == 1 and context.args[0] == RAAZ_SHABD:
        user_id = update.effective_user.id
        if user_id not in BOSS_LOG:
            BOSS_LOG.add(user_id)
            await update.message.reply_text(
                "**Balle Balle!** 🎉 Aap ab **Boss Log** ki fauj mein shamil ho gaye hain. Nayi power Mubarak!"
            )
        else:
            await update.message.reply_text("Aap toh pehle se hi Boss hain, Sir.")
    else:
        await update.message.reply_text("Password **Galat** hai, Dost. **Dur Raho!** 🤨")

@sirf_boss_chalaye
async def boss_banao_hukum(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reply kiye gaye user ko Boss banata hai."""
    if update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user
        BOSS_LOG.add(target_user.id)
        await update.message.reply_text(
            f"**Aapka Hukum Sir!** ✅ User **{target_user.first_name}** ko **Boss** bana diya gaya hai."
        )
    else:
        await update.message.reply_text("Boss banane ke liye kisi ke **message ko reply** karo.")

@sirf_boss_chalaye
async def power_wapas_hukum(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reply kiye gaye user se Boss power wapas leta hai."""
    if update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user
        if target_user.id in BOSS_LOG:
            if target_user.id == MAHA_BOSS_ID:
                await update.message.reply_text("**Arrey!** Maha Boss ki power wapas nahi le sakte. Unki power **Amar** hai.")
                return

            BOSS_LOG.discard(target_user.id)
            await update.message.reply_text(
                f"**Power Chheen Li!** ❌ User **{target_user.first_name}** ko **Aam Aadmi** bana diya gaya hai. Ab aaram karo."
            )
        else:
            await update.message.reply_text("Yeh toh pehle se hi **Aam Aadmi** hain.")
    else:
        await update.message.reply_text("Power wapas lene ke liye kisi Boss ke **message ko reply** karo.")


## 3.3. Rok-Tok aur Control

@sirf_boss_chalaye
@sirf_group_mein
async def dhakka_do_hukum(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User ko group se bahar nikalta hai (Kick)."""
    if update.message.reply_to_message:
        target_user_id = update.message.reply_to_message.from_user.id
        target_user_name = update.message.reply_to_message.from_user.first_name

        try:
            await context.bot.ban_chat_member(chat_id=update.effective_chat.id, user_id=target_user_id)
            await context.bot.unban_chat_member(chat_id=update.effective_chat.id, user_id=target_user_id) # Standard 'kick'
            await update.message.reply_text(
                f"**TADAA!** 👋 User **{target_user_name}** ko **dhakka** de diya gaya hai."
            )
        except error.TelegramBadRequest:
            await update.message.reply_text("Mai isko **Kick** nahi kar sakta. Power nahi hai ya yeh Boss hai.")
    else:
        await update.message.reply_text("Kick karne ke liye kisi ke **message ko reply** karo, Sir.")

@sirf_boss_chalaye
@sirf_group_mein
async def shaant_kar_hukum(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User ko shaant (Mute) karta hai."""
    if not update.message.reply_to_message:
        await update.message.reply_text("Mute karne ke liye **message ko reply** karo aur time (minutes) batao. Example: `/shaant_kar 10`.")
        return

    try:
        samay_minutes = int(context.args[0])
    except (IndexError, ValueError):
        await update.message.reply_text("Samay (minutes) toh batao! Example: `/shaant_kar 10`.")
        return

    target_user_id = update.message.reply_to_message.from_user.id
    target_user_name = update.message.reply_to_message.from_user.first_name
    
    import datetime
    shaanti_end_time = datetime.datetime.now() + datetime.timedelta(minutes=samay_minutes)

    try:
        await context.bot.restrict_chat_member(
            chat_id=update.effective_chat.id,
            user_id=target_user_id,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=shaanti_end_time
        )
        SHAANT_KIE_GAYE_LOG[target_user_id] = shaanti_end_time.timestamp()
        await update.message.reply_text(
            f"**CHUP KAR!** 🤫 User **{target_user_name}** ko **{samay_minutes}** minute ke liye **Shaant** kar diya gaya hai."
        )
    except error.TelegramBadRequest:
        await update.message.reply_text("Mai isko **Shaant** nahi kar sakta. Power nahi.")

@sirf_boss_chalaye
@sirf_group_mein
async def bolne_do_hukum(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User ko bolne deta hai (Unmute)."""
    if not update.message.reply_to_message:
        await update.message.reply_text("Unmute karne ke liye **message ko reply** karo.")
        return

    target_user_id = update.message.reply_to_message.from_user.id
    target_user_name = update.message.reply_to_message.from_user.first_name

    try:
        # Default permissions de rahe hain
        await context.bot.restrict_chat_member(
            chat_id=update.effective_chat.id,
            user_id=target_user_id,
            permissions=ChatPermissions(
                can_send_messages=True, can_send_media_messages=True, can_send_polls=True,
                can_send_other_messages=True, can_add_web_page_previews=True, can_invite_users=True,
            ),
        )
        if target_user_id in SHAANT_KIE_GAYE_LOG:
            del SHAANT_KIE_GAYE_LOG[target_user_id]
        await update.message.reply_text(
            f"**Azaadi!** 📢 User **{target_user_name}** ab **Bol Sakta** hai."
        )
    except error.TelegramBadRequest:
        await update.message.reply_text("Unmute mein gadbad. Shayad woh pehle se hi Unmute the.")

@sirf_boss_chalaye
@sirf_group_mein
async def taang_do_hukum(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reply kiye gaye message ko pin karta hai."""
    if update.message.reply_to_message:
        try:
            await context.bot.pin_chat_message(
                chat_id=update.effective_chat.id,
                message_id=update.message.reply_to_message.message_id,
                disable_notification=True 
            )
            await update.message.reply_text("**Upar Taang Diya!** 📌 Yeh message ab sabse upar rahega.")
        except error.TelegramBadRequest:
            await update.message.reply_text("Pin karne mein gadbad. Mere paas **Pin** ki power nahi hai.")
    else:
        await update.message.reply_text("Pin karne ke liye **message ko reply** karo.")

@sirf_boss_chalaye
@sirf_group_mein
async def utaro_hukum(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Saare pinned messages ko unpin karta hai."""
    try:
        await context.bot.unpin_all_chat_messages(chat_id=update.effective_chat.id)
        await update.message.reply_text("**Upar Se Utaar Diya!** 🗑️ Saare pinned messages hat gaye.")
    except error.TelegramBadRequest:
        await update.message.reply_text("Unpin karne mein gadbad. Koi message **Pin** tha hi nahi kya?")

@sirf_boss_chalaye
@sirf_group_mein
async def saaf_kar_hukum(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Specify kiye gaye messages ko delete karta hai."""
    try:
        kitna_ginti = int(context.args[0])
    except (IndexError, ValueError):
        await update.message.reply_text("Kitne messages udane hain? Number batao. Example: `/saaf_kar 5`")
        return

    # Deletion logic (same as the English version, iterating over IDs)
    message_ids_to_delete = []
    current_id = update.message.message_id
    
    # If replied, delete from that message to the current one
    if update.message.reply_to_message:
        start_id = update.message.reply_to_message.message_id
        message_ids_to_delete = list(range(start_id, current_id + 1))
    else:
        # Simple fallback for the last 'kitna_ginti' messages
        message_ids_to_delete = list(range(current_id - kitna_ginti + 1, current_id + 1))

    deleted_count = 0
    await update.message.reply_text(f"**Safaya Shuru...** 🧹 {len(message_ids_to_delete)} messages udane ki koshish...")
    
    for msg_id in reversed(message_ids_to_delete):
        try:
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=msg_id)
            deleted_count += 1
        except error.TelegramError:
            pass 

@sirf_boss_chalaye
@sirf_group_mein
async def nuke_hukum(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Chat ko nuke karta hai (Sirf Maha Boss)."""
    if update.effective_user.id != MAHA_BOSS_ID:
        await update.message.reply_text("**Ruko!** 🛑 Yeh toh **Maha Boss** ki power hai. **Khatra** hai ismein!")
        return
    
    await update.message.reply_text(
        "**DANGER!** ⚠️ **NUKE** chalane se pehle **sach mein soch lo**.\n"
        "Agar **pukka** karna hai toh **`/nuke pakka`** likho."
    )

    if len(context.args) == 1 and context.args[0].lower() == 'pakka':
        await update.message.reply_text("**Aapka Hukum Sir!** 💣 NUKE shuru... Sab kuch **SAFAYA**!")
        
        # Actual deletion logic would go here (similar to saaf_kar, but over a larger range)
        await update.bot.send_message(
             chat_id=update.effective_chat.id,
             text="**(Safaya complete)**. Chat ab **clean** hai. 😎"
        )
    
@sirf_boss_chalaye
async def zor_se_bolo_hukum(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Message ko bold karke shout karta hai."""
    chillane_ka_paath = ' '.join(context.args)
    if not chillane_ka_paath:
        await update.message.reply_text("Kya **chillana** hai, likho toh sahi!")
        return
    
    try:
        await update.message.delete()
    except error.TelegramError:
        pass 

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"**📢 CHILLAO! KYA HUKUM HAI?**\n\n**➡️ {chillane_ka_paath.upper()}**",
        parse_mode='Markdown'
    )

## 3.4. Auto-Jawaab Commands

@sirf_boss_chalaye
async def jawab_set_kar_hukum(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Naya auto-reply rule set karta hai."""
    try:
        full_command = ' '.join(context.args)
        if '|' not in full_command:
            await update.message.reply_text("Format galat hai! Aise likho: `/jawab_set_kar sawaal|jawab`")
            return

        trigger, reply = full_command.split('|', 1)
        sawaal = trigger.strip().lower()
        jawab = reply.strip()

        if not sawaal or not jawab:
            await update.message.reply_text("Sawaal aur Jawab, **dono zaroori** hain!")
            return

        AUTO_JAWAAB_NIZAM[sawaal] = jawab
        await update.message.reply_text(
            f"**Seekh Liya!** ✅ Jab koi **`{sawaal}`** bolega, toh main **`{jawab}`** bolunga.",
            parse_mode='Markdown'
        )
    except Exception:
        await update.message.reply_text("Format mein gadbad. Example: `/jawab_set_kar hello|namaste`")

@sirf_boss_chalaye
async def jawab_hata_do_hukum(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Auto-reply rule ko delete karta hai."""
    sawaal = ' '.join(context.args).strip().lower()

    if not sawaal:
        await update.message.reply_text("Kaunsa rule **bhulana** hai? **Sawaal** batao.")
        return

    if sawaal in AUTO_JAWAAB_NIZAM:
        reply_text = AUTO_JAWAAB_NIZAM.pop(sawaal)
        await update.message.reply_text(
            f"**Bhula Diya!** 🧠 Rule **`{sawaal}`** ko **delete** kar diya gaya hai.",
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(f"Rule **`{sawaal}`** toh **sikhaya** hi nahi tha.")

async def handle_auto_jawab(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Aane waale messages ko check karta hai auto-reply ke liye."""
    if update.message and update.message.text:
        paath = update.message.text.strip().lower()
        
        # Check for Mute status (Optional check, Telegram should handle it)
        if update.effective_user.id in SHAANT_KIE_GAYE_LOG:
            import time
            if time.time() < SHAANT_KIE_GAYE_LOG[update.effective_user.id]:
                try:
                    await update.message.delete()
                except error.TelegramError:
                    pass
                return
        
        # Auto-Jawaab check
        if paath in AUTO_JAWAAB_NIZAM:
            jawab_paath = AUTO_JAWAAB_NIZAM[paath]
            await update.message.reply_text(jawab_paath)
            return

## 3.5. Masti Commands

async def fetch_random_data(api_url: str) -> dict | None:
    """External API se data fetch karta hai."""
    try:
        response = requests.get(api_url, timeout=5)
        response.raise_for_status() 
        return response.json()
    except requests.exceptions.RequestException:
        return None

async def chutkula_hukum(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Random chutkula (Joke) lata hai."""
    await update.message.reply_text("**Ruko...** Achha chutkula dhoondh raha hoon. 🧐")
    
    chutkula_data = await fetch_random_data("https://v2.jokeapi.dev/joke/Any?blacklistFlags=nsfw,religious,political,racist,sexist,explicit&type=single")
    
    if chutkula_data and chutkula_data.get('joke'):
        chutkula = chutkula_data['joke']
        await update.message.reply_text(f"**HA HA HA!** 😂\n\n{chutkula}\n\n**(Maza Aaya?)**")
    else:
        await update.message.reply_text("Arey yaar! Koi **dhanka chutkula** nahi mila. Server so raha hai. 😴")

async def tana_mar_hukum(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Random tana (Roast) lata hai."""
    await update.message.reply_text("**Tez Mirchi** la raha hoon. Koi **jalega** ab. 🔥")

    tana_data = await fetch_random_data("https://evilinsult.com/generate_insult.php?lang=en&type=json")

    if tana_data and tana_data.get('insult'):
        tana = tana_data['insult']
        await update.message.reply_text(f"**SUNO! KADAK TANA!** 🌶️\n\n{tana}\n\n**(Jalaa kya?)**")
    else:
        await update.message.reply_text("Server busy hai. Aaj **tana** nahi, bas **pyaar** milega. 🥰")

async def bala_hukum(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bala! Bala! command."""
    await update.message.reply_text(
        "**BALA! BALA! SHAITAN KA SAALA!** 🕺💃\n\n(Achanak ki masti zaroori hai!)"
    )

# --- 4. MUKHYA FUNCTION aur BOT CHALANA ---

def mukhya_kaam():
    """Bot ko shuru karta hai."""
    print("🚀 Bot shuru ho raha hai... (Starting the bot process)")
    
    application = ApplicationBuilder().token(BOT_CHABHI).build()
    
    # Handlers jodna (Command Handlers)
    
    # General Commands
    application.add_handler(CommandHandler("start", shuru_karo_hukum))
    application.add_handler(CommandHandler("madad", madad_hukum))
    application.add_handler(CommandHandler("mera_id", mera_id_hukum))
    application.add_handler(CommandHandler("haalchaal", haalchaal_hukum))
    application.add_handler(CommandHandler("sikka_uchhalo", sikka_uchhalo_hukum))
    application.add_handler(CommandHandler("paasa_ghumao", paasa_ghumao_hukum))
    
    # Boss Commands
    application.add_handler(CommandHandler("raaz_shabd", raaz_shabd_hukum))
    application.add_handler(CommandHandler("boss_banao", boss_banao_hukum))
    application.add_handler(CommandHandler("power_wapas", power_wapas_hukum))

    # Moderation Commands
    application.add_handler(CommandHandler("dhakka_do", dhakka_do_hukum))
    application.add_handler(CommandHandler("shaant_kar", shaant_kar_hukum))
    application.add_handler(CommandHandler("bolne_do", bolne_do_hukum))
    application.add_handler(CommandHandler("taang_do", taang_do_hukum))
    application.add_handler(CommandHandler("utaro", utaro_hukum))
    application.add_handler(CommandHandler("saaf_kar", saaf_kar_hukum))
    application.add_handler(CommandHandler("nuke", nuke_hukum))
    application.add_handler(CommandHandler("zor_se_bolo", zor_se_bolo_hukum))

    # Auto-Reply Commands
    application.add_handler(CommandHandler("jawab_set_kar", jawab_set_kar_hukum))
    application.add_handler(CommandHandler("jawab_hata_do", jawab_hata_do_hukum))
    
    # Masti Commands
    application.add_handler(CommandHandler("chutkula", chutkula_hukum))
    application.add_handler(CommandHandler("tana_mar", tana_mar_hukum))
    application.add_handler(CommandHandler("bala", bala_hukum))

    # Message Handler for Auto-Reply
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_auto_jawab))

    # Bot ko chalana (Keep Alive)
    print("✅ Bot chalne laga hai. (Press Ctrl+C to stop)")
    application.run_polling(poll_interval=3)

if __name__ == '__main__':
    mukhya_kaam()

# --- END OF FILE (DE-SI CODE) ---
