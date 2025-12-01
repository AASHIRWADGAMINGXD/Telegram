import os
import json
import logging
import asyncio
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from dotenv import load_dotenv
from keep_alive import keep_alive

# --- CONFIGURATION ---
load_dotenv()
TOKEN = os.getenv('TOKEN')

# Logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Files
DATA_FILE = 'data.json'
JOKES_FILE = 'jokes.json'
ROASTS_FILE = 'roasts.json'

# --- GANGSTER DICTIONARY ---
ABUSE_WORDS = ["kutta", "kamina", "bc", "mc", "bhosdike", "chutiya", "stupid", "idiot", "saale"]
GANGSTER_REPLIES = [
    "Abey dhakkan! Kisko gaali diya?",
    "Zuban sambhal ke baat kar, varna jabda tod dunga.",
    "Ae! Khopdi tod saale ka.",
    "Baap ko mat sikha, chal nikal.",
    "Jyada shana mat ban, apun ke ilake me hai tu."
]

# --- HELPER FUNCTIONS ---
def load_json(filename):
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return [] if filename != DATA_FILE else {}

def save_json(filename, data):
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

# --- COMMANDS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Aur Bhai! Kya bolti public? Apun aa gaya hai. 😎\n\n"
        "Commands dekh le chhote:\n"
        "🎬 /bala - Nacho bc\n"
        "🔇 /mute - Muh band karwa de\n"
        "🦵 /kick - Laat maar ke nikaal\n"
        "😂 /joke - Ek mast joke sun\n"
        "🔥 /roast - Izzat ka falooda kar\n"
        "📢 /shout - Chilllaaaa\n"
        "💣 /nuke - Sab khatam (Admin Only)\n"
        "⚙️ /setautoreply - System set kar\n"
        "🗑 /deleteautoreply - System hata"
    )

async def bala(update: Update, context: ContextTypes.DEFAULT_TYPE):
    gif_url = "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExbm90eG50eG50eG50eG50eG50eG50eG50eG50eG50/l3vRlT2k2L35Cnn5C/giphy.gif"
    await context.bot.send_animation(chat_id=update.effective_chat.id, animation=gif_url, caption="Bala... Bala... Shaitan ka saala!")

async def joke(update: Update, context: ContextTypes.DEFAULT_TYPE):
    jokes = load_json(JOKES_FILE)
    if not jokes:
        await update.message.reply_text("Jokes khatam ho gaye bidu! Admin ko bol naya maal laye.")
        return
    await update.message.reply_text(f"😂 **Sun be:**\n\n{random.choice(jokes)}", parse_mode='Markdown')

async def roast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    roasts = load_json(ROASTS_FILE)
    if not roasts:
        await update.message.reply_text("Abhi mood nahi hai beizzat karne ka.")
        return
    
    target = update.effective_user.first_name
    if update.message.reply_to_message:
        target = update.message.reply_to_message.from_user.first_name
        
    await update.message.reply_text(f"🔥 **Oye {target}!**\n{random.choice(roasts)}", parse_mode='Markdown')

async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("Hawa mein mute karu kya? Reply kar uske message pe.")
        return
    
    user = update.message.reply_to_message.from_user
    try:
        await context.bot.restrict_chat_member(
            chat_id=update.effective_chat.id,
            user_id=user.id,
            permissions={"can_send_messages": False}
        )
        await update.message.reply_text(f"🤫 Oye {user.first_name}! Muh band rakh abhi. Mute kar diya tereko.")
    except Exception:
        await update.message.reply_text("Apun ke paas power nahi hai (Make me Admin).")

async def kick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("Kisko laat marna hai? Reply kar pehle.")
        return

    user = update.message.reply_to_message.from_user
    try:
        await context.bot.ban_chat_member(update.effective_chat.id, user.id)
        await context.bot.unban_chat_member(update.effective_chat.id, user.id) 
        await update.message.reply_text(f"🦵 Nikal lawde! {user.first_name} gaya tel lene.")
    except Exception:
        await update.message.reply_text("Admin bana na be pehle apun ko.")

async def afk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(f"😴 {user.first_name} bhai abhi gayab hai. Disturb na karne ka.")

async def shout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Kya chillaun be? Likh ke de aage.")
        return
    
    text = " ".join(context.args).upper()
    shouted_text = " 📢 ".join(list(text))
    await update.message.reply_text(f"📢 {shouted_text} 📢")

# --- NUKE COMMAND ---
async def nuke_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        await query.edit_message_text(text="💣 BOMB GIROOO! Safayi chalu...")
        message_id = query.message.message_id
        count = 0
        try:
            for i in range(50):
                try:
                    # Trying to delete previous messages
                    await context.bot.delete_message(chat_id=query.message.chat_id, message_id=message_id - i)
                    count += 1
                    await asyncio.sleep(0.1) # Small delay to prevent flood limits
                except Exception:
                    continue # Skip if message doesn't exist or too old
            
            msg = await context.bot.send_message(chat_id=query.message.chat_id, text=f"💥 Dhamaka ho gaya! {count} kachra saaf.")
            await asyncio.sleep(5)
            await msg.delete()
            
        except Exception as e:
            await context.bot.send_message(chat_id=query.message.chat_id, text="Kuch lafda ho gaya delete karne me.")
            
    else:
        await query.edit_message_text(text="Thik hai, maaf kiya aaj.")

# --- JSON AUTO REPLY COMMANDS ---
async def set_autoreply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = " ".join(context.args)
    if "|" not in text:
        await update.message.reply_text("Format galat hai bidu. Aise likh: \n`/setautoreply hello | Aur bhai kaisa hai`", parse_mode='Markdown')
        return

    trigger, response = text.split("|", 1)
    trigger = trigger.strip().lower()
    response = response.strip()

    data = load_json(DATA_FILE)
    data[trigger] = response
    save_json(DATA_FILE, data)

    await update.message.reply_text(f"Set kar diya! Jab koi bolega '{trigger}', apun bolega '{response}'.")

async def delete_autoreply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    trigger = " ".join(context.args).strip().lower()
    data = load_json(DATA_FILE)
    
    if trigger in data:
        del data[trigger]
        save_json(DATA_FILE, data)
        await update.message.reply_text(f"Hata diya '{trigger}' ko list se.")
    else:
        await update.message.reply_text("Ye to list me hai hi nahi be.")

# --- MAIN MESSAGE HANDLER ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    text_lower = update.message.text.lower()

    # 1. Abuse Check
    if any(word in text_lower for word in ABUSE_WORDS):
        await update.message.reply_text(random.choice(GANGSTER_REPLIES))
        return 

    # 2. Auto Reply Check
    data = load_json(DATA_FILE)
    if text_lower in data:
        await update.message.reply_text(data[text_lower])

# --- APP RUN ---
if __name__ == '__main__':
    keep_alive()
    
    print("Bot chalu ho raha hai...")
    
    # Init Application
    application = Application.builder().token(TOKEN).build()

    # Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("bala", bala))
    application.add_handler(CommandHandler("mute", mute))
    application.add_handler(CommandHandler("kick", kick))
    application.add_handler(CommandHandler("afk", afk))
    application.add_handler(CommandHandler("shout", shout))
    application.add_handler(CommandHandler("joke", joke))
    application.add_handler(CommandHandler("roast", roast))
    application.add_handler(CommandHandler("nuke", nuke_command))
    application.add_handler(CommandHandler("setautoreply", set_autoreply))
    application.add_handler(CommandHandler("deleteautoreply", delete_autoreply))
    
    application.add_handler(CallbackQueryHandler(nuke_confirm))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Fix for Conflict Error: Drop pending updates on restart
    print("Cleaning old connections...")
    application.run_polling(drop_pending_updates=True)
