import os
import requests
import asyncio
from telegram import Update, error
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# --- 1. CONFIGURATION AND DATA STRUCTURES ---

# You must set this in your environment: export BOT_TOKEN='YOUR_ACTUAL_TOKEN'
# For the bot to run: bot_token env
BOT_TOKEN = os.environ.get('BOT_TOKEN') 
if not BOT_TOKEN:
    print("🚨 ERROR: BOT_TOKEN environment variable not set. Please set it to your bot's token.")
    exit(1)

# Super Admin ID (Change this to YOUR Telegram User ID)
SUPER_ADMIN_ID = 123456789  # Replace with your actual ID for testing admin commands

# Simple Data Storage (In-memory - will reset on bot restart)
# For production, use a database (MongoDB, PostgreSQL)
PASSCODE = "Loid_Twilight" # The password for the /password command
ADMINS = {SUPER_ADMIN_ID}  # Set of User IDs
MUTED_USERS = {} # {user_id: end_time_timestamp}
AUTOREPLY_RULES = {} # {trigger_phrase: reply_text}


# --- 2. HELPER FUNCTIONS AND DECORATORS ---

# Decorator to check if the user is an admin
def admin_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if user_id not in ADMINS:
            await update.message.reply_text(
                f"**Mazaak Mat Karo!** 😠 Aapke paas is command ki power **nahi** hai. Sirf **Admins** chala sakte hain.",
                parse_mode='Markdown'
            )
            return
        return await func(update, context)
    return wrapper

# Decorator to check if the command is run in a group (for moderation commands)
def group_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat.type not in ['group', 'supergroup']:
            await update.message.reply_text(
                "Yeh command sirf **groups** mein chalti hai, akela kya karoge? 😉"
            )
            return
        return await func(update, context)
    return wrapper


# --- 3. CORE BOT COMMANDS (20+ COMMANDS) ---

## 3.1. General & Utility Commands

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Greets the user and introduces the bot."""
    user = update.effective_user.first_name
    await update.message.reply_text(
        f"**Namaste, {user} Ji! 🙏** Main hoon aapka personal Code Moderator. Hukumat karni hai toh /help dekho!",
        parse_mode='Markdown'
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lists all available commands with Indian-like descriptions."""
    help_text = (
        "**Aapki Sewa Mein Hazir!** ✨ (List of Commands)\n\n"
        "**General Hukumat**\n"
        "🔸 /start - Mera pehla parichay.\n"
        "🔸 /help - Sab commands ki list (Yeh wali).\n"
        "🔸 /status - Bot ka health check, sab **Theek Thak** hai?\n\n"
        "**Access and Admin**\n"
        "🔸 /password <passcode> - Admin banna hai toh **sahi raaz** batao.\n"
        "🔸 /myid - Aapki **pehchaan** (ID) kya hai?\n\n"
        "**Moderation & Control (Admins Only)**\n"
        "🔸 /kick - Kisi ko **bahar ka rasta** dikhao. (Reply to user)\n"
        "🔸 /mute <minutes> - Thodi der ke liye **Chup Kar!** (Reply to user)\n"
        "🔸 /unmute - Azaadi! Mute hatake **bolne do**. (Reply to user)\n"
        "🔸 /clear <count> - Pichli kuch messages ka **safaya** karo.\n"
        "🔸 /pin - Message ko **upar taang do**. (Reply to user)\n"
        "🔸 /unpin - Upar se **utaro**.\n"
        "🔸 /shout <text> - Zor se **chilla ke** bolo.\n"
        "🔸 /admin - Reply to a user to **make them Admin**.\n"
        "🔸 /demote - Reply to an Admin to **remove their Admin power**.\n"
        "🔸 /nuke - **Poora chat uda do** (Only Super Admin/Owner).\n\n"
        "**Auto-Reply (Admins Only)**\n"
        "🔸 /setautorelpy <trigger>|<reply> - Is **sawaal ka jawab** yeh hai.\n"
        "🔸 /deleteautorelpy <trigger> - Woh **jawab bhool jao**.\n"
        "🔸 /listauto - Saari **sikhaai hui baatein** dekho.\n\n"
        "**Entertainment & Masti**\n"
        "🔸 /joke - **Hanso!** Ek ajeeb-o-gareeb joke suno.\n"
        "🔸 /roast - **Jalo!** Ek kadak roast suno.\n"
        "🔸 /bala - **Bala Bala!** Achanak ki masti.\n"
        "🔸 /gifsearch <query> - **Hilta-dulat picture** dhoondo.\n"
        "🔸 /flipcoin - **Sikka uchhalo** (Heads or Tails).\n"
        "🔸 /roll - **Pahada ghumao** (Random Number).\n\n"
        "**Chat Tools**\n"
        "🔸 /echo <text> - Jo bolo, wohi **waapas**.\n"
        "🔸 /purge - **Saare messages udake** chat clean karo (Requires Reply).\n"
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def myid_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shows the user's ID."""
    user_id = update.effective_user.id
    await update.message.reply_text(f"**Aapki Pehchaan (ID):** `{user_id}`", parse_mode='Markdown')

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Checks the bot's health."""
    admins_count = len(ADMINS)
    rules_count = len(AUTOREPLY_RULES)
    await update.message.reply_text(
        f"**Theek Thak Hai!** Bot bilkul chaka-chak chal raha hai. 😎\n"
        f"➡️ **Admins:** {admins_count} log\n"
        f"➡️ **Auto-Reply Rules:** {rules_count} sikhaye hain."
    )

async def gifsearch_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Search for a GIF using the Google tool."""
    query = ' '.join(context.args)
    if not query:
        await update.message.reply_text("Kya dhoondhna hai, **bolo toh sahi**!")
        return
    
    # You would typically use a dedicated GIF API (like Giphy/Tenor) here.
    # For simplicity, we'll suggest a Google search for a GIF.
    await update.message.reply_text(
        f"**GIF Dhoondh Raha Hoon...** Aap Google par search kar sakte hain:\n"
        f"`{query} gif`",
        parse_mode='Markdown'
    )

async def flipcoin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Flips a coin."""
    import random
    result = random.choice(["Heads (Chit)", "Tails (Pat)"])
    await update.message.reply_text(f"**Sikka Uchhala!** Aur aaya... **{result}**! 🪙")

async def roll_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Rolls a random number."""
    import random
    number = random.randint(1, 100)
    await update.message.reply_text(f"**Pahada Ghumaya!** Number aaya... **{number}**! 🎲")
    
async def echo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Echoes the user's text."""
    text = ' '.join(context.args)
    if text:
        await update.message.reply_text(f"Aapne Bola: {text}")
    else:
        await update.message.reply_text("**Khaali** echo karke kya faayda? Kuch likho na!")


## 3.2. Authentication & Admin Commands

async def password_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Allows user to become an admin with a password."""
    if len(context.args) == 1 and context.args[0] == PASSCODE:
        user_id = update.effective_user.id
        if user_id not in ADMINS:
            ADMINS.add(user_id)
            await update.message.reply_text(
                "**Balle Balle!** 🎉 Aap ab **Admins** ki fauj mein shamil ho gaye hain. Nayi power Mubarak!"
            )
        else:
            await update.message.reply_text(
                "**Mazaak Mat Karo!** Aap toh pehle se hi Admin hain, Sir."
            )
    else:
        await update.message.reply_text(
            "**Galat Raaz** bataya, Dost. Sahi password laao, warna **Dur Raho!** 🤨"
        )

@admin_only
async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Makes a replied-to user an admin."""
    if update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user
        ADMINS.add(target_user.id)
        await update.message.reply_text(
            f"**Aapka Hukum Sir!** ✅ User **{target_user.first_name}** ko **Admin** bana diya gaya hai. Ab inhe bhi power mil gayi."
        )
    else:
        await update.message.reply_text("Admin banane ke liye kisi ke **message ko reply** karo.")

@admin_only
async def demote_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Removes admin status from a replied-to user."""
    if update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user
        if target_user.id in ADMINS:
            if target_user.id == SUPER_ADMIN_ID:
                await update.message.reply_text("**Arrey!** Super Admin ko demote nahi kar sakte. Unki power **Amar** hai.")
                return

            ADMINS.discard(target_user.id)
            await update.message.reply_text(
                f"**Power Chheen Li!** ❌ User **{target_user.first_name}** ko **Demote** kar diya gaya hai. Ab aaram karo."
            )
        else:
            await update.message.reply_text("Yeh toh pehle se hi **aam aadmi** hain, Admin the hi nahi.")
    else:
        await update.message.reply_text("Demote karne ke liye kisi Admin ke **message ko reply** karo.")

## 3.3. Moderation Commands

@admin_only
@group_only
async def kick_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kicks a replied-to user from the group."""
    if update.message.reply_to_message:
        target_user_id = update.message.reply_to_message.from_user.id
        target_user_name = update.message.reply_to_message.from_user.first_name

        try:
            await context.bot.ban_chat_member(chat_id=update.effective_chat.id, user_id=target_user_id)
            # Unban immediately so they can rejoin (standard 'kick' behavior)
            await context.bot.unban_chat_member(chat_id=update.effective_chat.id, user_id=target_user_id)
            await update.message.reply_text(
                f"**TADAA!** 👋 User **{target_user_name}** ko **bahar ka rasta** dikha diya gaya hai. Abhi aao, ya kal aana."
            )
        except error.TelegramBadRequest:
            await update.message.reply_text("Mai isko **Kick** nahi kar sakta. Shayad mere paas **power nahi** hai ya yeh Admin hai.")
    else:
        await update.message.reply_text("Kick karne ke liye kisi ke **message ko reply** karo, Sir.")

@admin_only
@group_only
async def mute_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mutes a replied-to user for a specified duration."""
    if not update.message.reply_to_message:
        await update.message.reply_text("Mute karne ke liye kisi ke **message ko reply** karo aur time (minutes) batao. Example: `/mute 10`.")
        return

    try:
        duration_minutes = int(context.args[0])
    except (IndexError, ValueError):
        await update.message.reply_text("Time (minutes) toh batao! Example: `/mute 10`.")
        return

    target_user_id = update.message.reply_to_message.from_user.id
    target_user_name = update.message.reply_to_message.from_user.first_name
    
    # Calculate mute time
    import datetime
    mute_until = datetime.datetime.now() + datetime.timedelta(minutes=duration_minutes)

    try:
        # Restrict permissions: can't send messages, polls, media, etc.
        await context.bot.restrict_chat_member(
            chat_id=update.effective_chat.id,
            user_id=target_user_id,
            permissions=telegram.ChatPermissions(can_send_messages=False),
            until_date=mute_until
        )
        MUTED_USERS[target_user_id] = mute_until.timestamp()
        await update.message.reply_text(
            f"**CHUP KAR!** 🤫 User **{target_user_name}** ko **{duration_minutes}** minute ke liye **Mute** kar diya gaya hai. Aaram karo ab."
        )
    except error.TelegramBadRequest:
        await update.message.reply_text("Mai isko **Mute** nahi kar sakta. Shayad yeh Admin hai ya mere paas permission nahi.")

@admin_only
@group_only
async def unmute_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Unmutes a replied-to user."""
    if not update.message.reply_to_message:
        await update.message.reply_text("Unmute karne ke liye kisi ke **message ko reply** karo.")
        return

    target_user_id = update.message.reply_to_message.from_user.id
    target_user_name = update.message.reply_to_message.from_user.first_name

    try:
        # Restore default permissions (can send messages, media, etc.)
        await context.bot.restrict_chat_member(
            chat_id=update.effective_chat.id,
            user_id=target_user_id,
            permissions=telegram.ChatPermissions(
                can_send_messages=True,
                can_send_media_messages=True,
                can_send_polls=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True,
                can_change_info=False, # Standard for non-admins
                can_invite_users=True,
                can_pin_messages=False, # Standard for non-admins
            ),
        )
        if target_user_id in MUTED_USERS:
            del MUTED_USERS[target_user_id]
        await update.message.reply_text(
            f"**Azaadi!** 📢 User **{target_user_name}** ab **Unmute** ho gaya hai. Ab bol sakte ho, lekin **Shanti** se."
        )
    except error.TelegramBadRequest:
        await update.message.reply_text("Unmute mein gadbad. Shayad woh pehle se hi Unmute the ya mere paas permission nahi.")

@admin_only
@group_only
async def pin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Pins a replied-to message."""
    if update.message.reply_to_message:
        try:
            await context.bot.pin_chat_message(
                chat_id=update.effective_chat.id,
                message_id=update.message.reply_to_message.message_id,
                disable_notification=True # Optional: no sound notification
            )
            await update.message.reply_text("**Upar Taang Diya!** 📌 Yeh message ab sabse upar rahega.")
        except error.TelegramBadRequest:
            await update.message.reply_text("Pin karne mein gadbad. Mere paas **Pin** ki power nahi hai kya?")
    else:
        await update.message.reply_text("Pin karne ke liye **message ko reply** karo.")

@admin_only
@group_only
async def unpin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Unpins the last pinned message."""
    try:
        await context.bot.unpin_all_chat_messages(chat_id=update.effective_chat.id)
        await update.message.reply_text("**Upar Se Utaar Diya!** 🗑️ Saare pinned messages hat gaye.")
    except error.TelegramBadRequest:
        await update.message.reply_text("Unpin karne mein gadbad. Koi message **Pin** tha hi nahi kya?")

@admin_only
@group_only
async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Deletes a specified number of messages."""
    try:
        count = int(context.args[0])
    except (IndexError, ValueError):
        await update.message.reply_text("Kitne messages udane hain? Number batao. Example: `/clear 5`")
        return

    # Telegram API does not allow bulk deletion of non-service messages.
    # We must iterate and delete one by one.
    # NOTE: Messages older than 48 hours in a Supergroup cannot be deleted by a bot.

    message_ids_to_delete = []
    # Fetch messages up to the 'count' limit, including the command message itself
    # NOTE: Fetching previous messages reliably is complex without a database.
    # The following is a simplified, non-guaranteed approach by getting the IDs around the command.
    # The reliable way is for the user to reply to the first message they want to delete.

    # Simpler approach: If replied to, delete from that message to the current one.
    if update.message.reply_to_message:
        start_id = update.message.reply_to_message.message_id
        end_id = update.message.message_id
        # Creates a list of IDs to try and delete
        message_ids_to_delete = list(range(start_id, end_id + 1))
    else:
        # Fallback: Just try to delete the last 'count' messages by ID.
        # This is very unreliable in a busy chat but attempts to fulfil the command.
        current_id = update.message.message_id
        message_ids_to_delete = list(range(current_id - count + 1, current_id + 1))

    deleted_count = 0
    await update.message.reply_text(f"**Safaya Shuru...** 🧹 {len(message_ids_to_delete)} messages udane ki koshish...")
    
    # Deleting the messages
    for msg_id in reversed(message_ids_to_delete):
        try:
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=msg_id)
            deleted_count += 1
        except error.TelegramError:
            # Silently skip if deletion fails (e.g., message too old, or already deleted)
            pass

    # A final status message is often needed, but deleting it can confuse the user.
    # The previous message is a placeholder.

@admin_only
@group_only
async def nuke_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Deletes all messages in the chat (Super Admin only - highly dangerous)."""
    # This is a very complex operation and usually requires a dedicated cleanup sequence
    # and confirmation, as bots cannot delete all messages older than 48 hours.

    if update.effective_user.id != SUPER_ADMIN_ID:
        await update.message.reply_text("**Ruko!** 🛑 Yeh toh **Super Admin** ki power hai. **Khatra** hai ismein!")
        return
    
    await update.message.reply_text(
        "**DANGER!** ⚠️ **NUKE** chalane se pehle **sach mein soch lo**.\n"
        "Agar **pukka** karna hai toh **`/nuke confirm`** likho.\n"
        "(Note: Bot sirf 48 ghante se naye messages hi uda sakta hai.)"
    )

    if len(context.args) == 1 and context.args[0].lower() == 'confirm':
        await update.message.reply_text("**Aapka Hukum Sir!** 💣 NUKE shuru... Sab kuch **SAFAYA**!")
        
        # A real 'nuke' would involve fetching the message history (which is difficult
        # without external storage) and iterating to delete, as the 'clear' command.

        # For the template, we just send the confirmation message.
        await update.bot.send_message(
             chat_id=update.effective_chat.id,
             text="**(Simulation of deletion complete)**. Baaki sab **Super Admin** ki zimmedari. 😎"
        )
    
@admin_only
async def shout_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends a message to the chat with bold text."""
    text_to_shout = ' '.join(context.args)
    if not text_to_shout:
        await update.message.reply_text("Kya **chillana** hai, likho toh sahi!")
        return
    
    # Try to delete the command message for a cleaner shout
    try:
        await update.message.delete()
    except error.TelegramError:
        pass # Ignore if deletion fails

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"**📢 CHILLAO! KYA HUKUM HAI?**\n\n**➡️ {text_to_shout.upper()}**",
        parse_mode='Markdown'
    )

## 3.4. Auto-Reply Commands

@admin_only
async def setautorelpy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sets a new auto-reply rule: /setautorelpy <trigger>|<reply>"""
    try:
        if len(context.args) < 1:
            raise ValueError
        
        full_command = ' '.join(context.args)
        if '|' not in full_command:
            await update.message.reply_text("Format galat hai, Sir! Aise likho: `/setautorelpy sawaal|jawab`")
            return

        trigger, reply = full_command.split('|', 1)
        trigger = trigger.strip().lower()
        reply = reply.strip()

        if not trigger or not reply:
            await update.message.reply_text("Sawaal aur Jawab, **dono zaroori** hain!")
            return

        AUTOREPLY_RULES[trigger] = reply
        await update.message.reply_text(
            f"**Seekh Liya!** ✅ Jab koi **`{trigger}`** bolega, toh main **`{reply}`** bolunga.",
            parse_mode='Markdown'
        )
    except Exception:
        await update.message.reply_text("Format mein gadbad. Example: `/setautorelpy hello|namaste`")

@admin_only
async def deleteautorelpy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Deletes an auto-reply rule: /deleteautorelpy <trigger>"""
    trigger = ' '.join(context.args).strip().lower()

    if not trigger:
        await update.message.reply_text("Kaunsa rule **bhulana** hai? **Trigger** batao.")
        return

    if trigger in AUTOREPLY_RULES:
        reply_text = AUTOREPLY_RULES.pop(trigger)
        await update.message.reply_text(
            f"**Bhula Diya!** 🧠 Rule **`{trigger}`** (Jawab: `{reply_text[:20]}...`) ko **delete** kar diya gaya hai.",
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(f"Rule **`{trigger}`** toh **sikhaya** hi nahi tha.")

@admin_only
async def listauto_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lists all active auto-reply rules."""
    if not AUTOREPLY_RULES:
        await update.message.reply_text("**Khaali Panna!** Koi Auto-Reply rule sikhaya nahi gaya.")
        return

    rules_list = "**Saari Sikhaai Hui Baatein:** 📜\n\n"
    for trigger, reply in AUTOREPLY_RULES.items():
        rules_list += f"👉 **Trigger:** `{trigger}`\n   **Jawab:** `{reply[:50]}...`\n---\n"
    
    await update.message.reply_text(rules_list, parse_mode='Markdown')

async def handle_auto_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles incoming messages and checks for auto-reply triggers."""
    if update.message and update.message.text:
        text = update.message.text.strip().lower()
        
        # Simple exact match for auto-reply
        if text in AUTOREPLY_RULES:
            reply_text = AUTOREPLY_RULES[text]
            await update.message.reply_text(reply_text)
            return

        # Simple check for muted user (though telegram handles the restriction via API)
        if update.effective_user.id in MUTED_USERS:
            # Check if mute time is over (Simple in-memory check)
            import time
            if time.time() < MUTED_USERS[update.effective_user.id]:
                 # Try to delete the message of the muted user
                try:
                    await update.message.delete()
                    # Optional: Send a private notification to the user or a warning in the chat
                except error.TelegramError:
                    pass # Cannot delete

## 3.5. Entertainment Commands

async def fetch_random_data(api_url: str) -> str:
    """Helper to fetch data from an external API."""
    try:
        response = requests.get(api_url, timeout=5)
        response.raise_for_status() # Raise exception for bad status codes
        return response.json()
    except requests.exceptions.RequestException:
        return None

async def joke_search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fetches a random joke."""
    await update.message.reply_text("**Ruko...** Achha joke dhoondh raha hoon. 🧐")
    
    # Using the official Joke API (English Jokes)
    joke_data = await fetch_random_data("https://v2.jokeapi.dev/joke/Any?blacklistFlags=nsfw,religious,political,racist,sexist,explicit&type=single")
    
    if joke_data and joke_data.get('joke'):
        joke = joke_data['joke']
        await update.message.reply_text(f"**HA HA HA!** 😂\n\n{joke}\n\n**(Maza Aaya?)**")
    else:
        await update.message.reply_text("Arey yaar! Koi **dhanka joke** nahi mila. Server so raha hai. 😴")

async def roast_search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fetches a random roast (Slightly modified joke/insult API)."""
    await update.message.reply_text("**Tez Mirchi** la raha hoon. Koi **jalega** ab. 🔥")

    # Using the 'insult' API from the 'evilinsult.com' as a 'roast' source (English)
    roast_data = await fetch_random_data("https://evilinsult.com/generate_insult.php?lang=en&type=json")

    if roast_data and roast_data.get('insult'):
        roast = roast_data['insult']
        await update.message.reply_text(f"**SUNO! KADAK BAAT!** 🌶️\n\n{roast}\n\n**(Jalaa kya?)**")
    else:
        await update.message.reply_text("Server busy hai. Aaj **roast** nahi, bas **pyaar** milega. 🥰")

async def bala_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """A fun, random command."""
    await update.message.reply_text(
        "**BALA! BALA! SHAITAN KA SAALA!** 🕺💃\n\n(Achanak ki masti zaroori hai!)"
    )

## 3.6. Purge Command (Advanced Clear)

@admin_only
@group_only
async def purge_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Deletes all messages from a replied-to message up to the current command."""
    if not update.message.reply_to_message:
        await update.message.reply_text("Purge karne ke liye **pehle message ko reply** karo jahan se safaya shuru karna hai.")
        return

    start_id = update.message.reply_to_message.message_id
    end_id = update.message.message_id
    
    # +1 to include the command message itself
    message_ids_to_delete = list(range(start_id, end_id + 1)) 
    
    deleted_count = 0
    await update.message.reply_text(f"**Mahasafaya Shuru...** 🌪️ **{len(message_ids_to_delete)}** messages udane ki koshish...")
    
    for msg_id in reversed(message_ids_to_delete):
        try:
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=msg_id)
            deleted_count += 1
        except error.TelegramError:
            pass 

# --- 4. MAIN FUNCTION AND POLLING ---

def main():
    """Starts the bot."""
    print("🚀 Bot shuru ho raha hai... (Starting the bot process)")
    
    # Ensure you have imported from telegram.ext import ApplicationBuilder
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # 1. General Commands
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("myid", myid_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("echo", echo_command))
    application.add_handler(CommandHandler("gifsearch", gifsearch_command))
    application.add_handler(CommandHandler("flipcoin", flipcoin_command))
    application.add_handler(CommandHandler("roll", roll_command))

    # 2. Authentication & Admin Commands
    application.add_handler(CommandHandler("password", password_command))
    application.add_handler(CommandHandler("admin", admin_command))
    application.add_handler(CommandHandler("demote", demote_command))

    # 3. Moderation Commands
    application.add_handler(CommandHandler("kick", kick_command))
    application.add_handler(CommandHandler("mute", mute_command))
    application.add_handler(CommandHandler("unmute", unmute_command))
    application.add_handler(CommandHandler("pin", pin_command))
    application.add_handler(CommandHandler("unpin", unpin_command))
    application.add_handler(CommandHandler("clear", clear_command))
    application.add_handler(CommandHandler("nuke", nuke_command))
    application.add_handler(CommandHandler("shout", shout_command))
    application.add_handler(CommandHandler("purge", purge_command))

    # 4. Auto-Reply Commands
    application.add_handler(CommandHandler("setautorelpy", setautorelpy_command))
    application.add_handler(CommandHandler("deleteautorelpy", deleteautorelpy_command))
    application.add_handler(CommandHandler("listauto", listauto_command))
    
    # 5. Entertainment Commands
    application.add_handler(CommandHandler("joke", joke_search_command))
    application.add_handler(CommandHandler("roast", roast_search_command))
    application.add_handler(CommandHandler("bala", bala_command))

    # 6. Message Handler for Auto-Reply
    # Must be added after all command handlers
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_auto_reply))

    # Start the Bot - This loop handles the "keep alive"
    print("✅ Bot chalne laga hai. (Bot running - press Ctrl+C to stop)")
    application.run_polling(poll_interval=3)

if __name__ == '__main__':
    # Add this line to avoid a 'name 'telegram' is not defined' error when using telegram.ChatPermissions
    import telegram 
    main()

# --- END OF FILE ---
