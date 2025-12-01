import os
import json
import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from dotenv import load_dotenv
from keep_alive import keep_alive

# Load Environment Variables
load_dotenv()
TOKEN = os.getenv('TOKEN')

# Logging Setup
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# JSON File Path
DATA_FILE = 'data.json'

# --- HELPER FUNCTIONS FOR JSON ---
def load_data():
    try:
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_data(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=4)

# --- GANGSTER DIALOGUES ---
ABUSE_WORDS = ["kutta", "kamina", "bc", "mc", "bhosdike", "chutiya", "stupid", "idiot"]
GANGSTER_REPLIES = [
    "Abey dhakkan! Kisko gaali diya?",
    "Zyada shana mat ban, varna uda duga.",
    "Ae! Khopdi tod saale ka.",
    "Baap ko mat sikha, chal nikal."
]

# --- COMMANDS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Aur Bhai! Kya bolti public? Apun aa gaya hai. \n\n"
        "Commands dekh le chhote:\n"
        "/bala - Nacho bc\n"
        "/mute - Muh band karwa de\n"
        "/kick - Laat maar ke nikaal\n"
        "/shout - Chilllaaaa\n"
        "/nuke - Sab khatam (Admin Only)\n"
        "/setautoreply - System set kar\n"
        "/deleteautoreply - System hata"
    )

# /bala send gif
async def bala(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Just a placeholder GIF URL, replace with your preferred one
    gif_url = "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExbm90eG50eG50eG50eG50eG50eG50eG50eG50eG50/l3vRlT2k2L35Cnn5C/giphy.gif"
    await context.bot.send_animation(chat_id=update.effective_chat.id, animation=gif_url, caption="Bala... Bala... Shaitan ka saala!")

# /mute (Reply to user)
async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("Abey hawa mein kisko mute karu? Reply kar uske message pe.")
        return
    
    user = update.message.reply_to_message.from_user
    try:
        await context.bot.restrict_chat_member(
            chat_id=update.effective_chat.id,
            user_id=user.id,
            permissions={"can_send_messages": False}
        )
        await update.message.reply_text(f"Oye {user.first_name}! Muh band rakh abhi. Mute kar diya tereko.")
    except Exception as e:
        await update.message.reply_text("Apun ka power nahi chal raha (Admin permissions check kar).")

# /kick (Reply to user)
async def kick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("Kisko laat marna hai? Reply kar pehle.")
        return

    user = update.message.reply_to_message.from_user
    try:
        await context.bot.ban_chat_member(update.effective_chat.id, user.id)
        await context.bot.unban_chat_member(update.effective_chat.id, user.id) # Unban immediately to allow rejoin (Kick)
        await update.message.reply_text(f"Nikal lawde! Pehli fursat mein nikal. {user.first_name} gaya tel lene.")
    except Exception as e:
        await update.message.reply_text("Admin bana na be pehle apun ko.")

# /afk
async def afk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(f"{user.first_name} bhai abhi gayab hai. Disturb na karne ka.")

# /shout advanced level
async def shout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Kya chillaun be? Likh ke de aage.")
        return
    
    text = " ".join(context.args).upper()
    shouted_text = " 📢 ".join(list(text))
    await update.message.reply_text(f"📢 {shouted_text} 📢")

# /nuke logic
async def nuke_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Check Admin
    user_id = update.effective_user.id
    chat_member = await context.bot.get_chat_member(update.effective_chat.id, user_id)
    if chat_member.status not in ['administrator', 'creator']:
        await update.message.reply_text("Tera aukat nahi hai ye button dabane ka.")
        return

    keyboard = [
        [InlineKeyboardButton("Ha uda de (YES)", callback_data='nuke_yes')],
        [InlineKeyboardButton("Nahi Bhai Rehne de (NO)", callback_data='nuke_no')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("⚠ *WARNING* ⚠\n50 Message uda du kya seedha? Pakka?", reply_markup=reply_markup, parse_mode='Markdown')

async def nuke_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == 'nuke_yes':
        await query.edit_message_text(text="💣 BOMB GIROOO! Ginti shuru...")
        try:
            # Delete last 50 messages
            message_id = query.message.message_id
            count = 0
            for i in range(51):
                try:
                    await context.bot.delete_message(chat_id=query.message.chat_id, message_id=message_id - i)
                    count += 1
                except:
                    pass # Skip if message too old or already deleted
            
            msg = await context.bot.send_message(chat_id=query.message.chat_id, text=f"💥 Dhamaka ho gaya! {count} messages udh gaye.")
            # Delete confirmation message after 5 seconds
            await asyncio.sleep(5)
            await msg.delete()
            
        except Exception as e:
            await context.bot.send_message(chat_id=query.message.chat_id, text="Lafda ho gaya delete karne me.")
            
    else:
        await query.edit_message_text(text="Thik hai, maaf kiya aaj.")

# /setautoreply trigger | response
async def set_autoreply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = " ".join(context.args)
    if "|" not in text:
        await update.message.reply_text("Format galat hai bidu. Aise likh: \n`/setautoreply hello | Aur bhai kaisa hai`", parse_mode='Markdown')
        return

    trigger, response = text.split("|", 1)
    trigger = trigger.strip().lower()
    response = response.strip()

    data = load_data()
    data[trigger] = response
    save_data(data)

    await update.message.reply_text(f"Set kar diya! Jab koi bolega '{trigger}', apun bolega '{response}'.")

# /deleteautoreply trigger
async def delete_autoreply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    trigger = " ".join(context.args).strip().lower()
    data = load_data()
    
    if trigger in data:
        del data[trigger]
        save_data(data)
        await update.message.reply_text(f"Hata diya '{trigger}' ko list se.")
    else:
        await update.message.reply_text("Ye to list me hai hi nahi be.")

# MESSAGE HANDLER (Abuse & Auto-Reply)
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    text_lower = update.message.text.lower()

    # 1. Abuse Check
    for bad_word in ABUSE_WORDS:
        if bad_word in text_lower:
            import random
            await update.message.reply_text(random.choice(GANGSTER_REPLIES))
            return # Stop processing if abused

    # 2. Auto Reply Check
    data = load_data()
    if text_lower in data:
        await update.message.reply_text(data[text_lower])

# --- MAIN EXECUTION ---
if __name__ == '__main__':
    # Start Keep Alive Server
    keep_alive()
    
    print("Bot chalu ho gaya hai bidu...")
    application = Application.builder().token(TOKEN).build()

    # Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("bala", bala))
    application.add_handler(CommandHandler("mute", mute))
    application.add_handler(CommandHandler("kick", kick))
    application.add_handler(CommandHandler("afk", afk))
    application.add_handler(CommandHandler("shout", shout))
    application.add_handler(CommandHandler("nuke", nuke_command))
    application.add_handler(CommandHandler("setautoreply", set_autoreply))
    application.add_handler(CommandHandler("deleteautoreply", delete_autoreply))
    
    # Callback Handler for Nuke
    application.add_handler(CallbackQueryHandler(nuke_confirm))

    # Message Handler (Must be last)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Run Bot
    application.run_polling()
