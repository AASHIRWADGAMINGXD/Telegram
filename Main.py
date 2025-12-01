import telebot
import os
import json
import time
import random
import logging
from telebot import types
from keep_alive import keep_alive
from dotenv import load_dotenv

# --- SETUP & CONFIGURATION ---
load_dotenv()
TOKEN = os.getenv('BOT_TOKEN')
BOT_PASSWORD = os.getenv('BOT_PASSWORD')

# Logging setup (Errors dekhne ke liye)
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

bot = telebot.TeleBot(TOKEN)

# --- DATABASE (JSON) ---
# Auto-replies save karne ke liye
AUTOREPLY_FILE = 'autoreply.json'

def load_replies():
    try:
        with open(AUTOREPLY_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_replies(data):
    with open(AUTOREPLY_FILE, 'w') as f:
        json.dump(data, f)

auto_replies = load_replies()

# --- TEMPORARY ADMIN LIST ---
# Jo password dalega wo yahan aayega
authorized_users = []

# --- DESI CONTENT ---
jokes = [
    "Teacher: Pappu, homework kyu nahi kiya?\nPappu: Sir, light chali gayi thi.\nTeacher: To mombatti jala lete?\nPappu: Maachis mandir mein rakhi thi.\nTeacher: To wahan se le aate?\nPappu: Nahaya nahi tha sir.\nTeacher: To naha lete?\nPappu: Pani nahi tha sir, motor nahi chal rahi thi, light jo gayi thi! 😂",
    "Banta: Doctor sahab, pure jism mein dard hai.\nDoctor: (Check karke) Abe tu jahan ungli laga raha hai wahan dard nahi hai, teri ungli tooti hui hai! 🤣",
    "Girl: Main papa ki pari hu.\nBoy: To udd ke dikha.\nGirl: Udd nahi sakti.\nBoy: To fir tu papa ki pari nahi, papa ki para-glider hai! ✈️"
]

roasts = [
    "Bhai tu rehne de, tujhse na ho payega.",
    "Teri shakal dekh ke to Google Maps bhi rasta bhool jaye.",
    "Itna sannata kyu hai bhai? Koi logic baat kar le kabhi.",
    "Jitna dimag tere paas hai, utna to main chutta chhod deta hoon.",
    "Agar stupidity currency hoti, to tu aaj Ambani hota."
]

# --- HELPER FUNCTIONS ---
def is_admin(message):
    """Checks if user is Group Admin OR Logged in via Password"""
    user_id = message.from_user.id
    if user_id in authorized_users:
        return True
    try:
        chat_member = bot.get_chat_member(message.chat.id, user_id)
        return chat_member.status in ['administrator', 'creator']
    except:
        return False

# --- CORE COMMANDS ---

@bot.message_handler(commands=['start'])
def start_msg(message):
    bot.reply_to(message, "Namaste Bhai! 🙏\nMain hu is group ka naya Don.\nCommands dekhne ke liye '/help' type kar.")

@bot.message_handler(commands=['login'])
def login_system(message):
    try:
        args = message.text.split()
        if len(args) < 2:
            bot.reply_to(message, "Password to likh bhai! Usage: `/login password123`")
            return
        
        if args[1] == BOT_PASSWORD:
            if message.from_user.id not in authorized_users:
                authorized_users.append(message.from_user.id)
                bot.reply_to(message, "Access Granted! 🔓\nAb tu bhai hai, kuch bhi kar sakta hai.")
            else:
                bot.reply_to(message, "Tu pehle se hi login hai bhai.")
        else:
            bot.reply_to(message, "Galat password! Nikal yahan se. 😡")
    except Exception as e:
        logger.error(e)

# --- MODERATION ---

@bot.message_handler(commands=['kick'])
def kick_user(message):
    if not is_admin(message):
        bot.reply_to(message, "Tu Admin nahi hai, aukaat mein reh!")
        return
    if not message.reply_to_message:
        bot.reply_to(message, "Kisko laat maarni hai? Reply kar uske message pe.")
        return
    try:
        user_to_kick = message.reply_to_message.from_user
        bot.kick_chat_member(message.chat.id, user_to_kick.id)
        bot.reply_to(message, f"Uda diya {user_to_kick.first_name} ko! 👋 Chal nikal!")
    except Exception as e:
        bot.reply_to(message, "Bhai main Admin nahi hu ya power kam hai.")

@bot.message_handler(commands=['mute'])
def mute_user(message):
    if not is_admin(message): return
    if not message.reply_to_message:
        bot.reply_to(message, "Reply to kar bhai.")
        return
    try:
        bot.restrict_chat_member(message.chat.id, message.reply_to_message.from_user.id, until_date=time.time()+300)
        bot.reply_to(message, "🤫 Shhh! 5 minute ke liye muh band.")
    except:
        bot.reply_to(message, "Error aa gaya bhai.")

@bot.message_handler(commands=['clear', 'purge'])
def clear_msgs(message):
    if not is_admin(message):
        bot.reply_to(message, "Bas Admin kar sakta hai ye.")
        return
    try:
        args = message.text.split()
        num = int(args[1]) if len(args) > 1 else 5
        if num > 100: num = 100 # Safety limit
        
        msg_ids = [message.message_id - i for i in range(num + 1)]
        for mid in msg_ids:
            try:
                bot.delete_message(message.chat.id, mid)
            except: pass
        
        temp_msg = bot.send_message(message.chat.id, f"🧹 Safai Abhiyan! {num} messages delete kar diye.")
        time.sleep(3)
        bot.delete_message(message.chat.id, temp_msg.message_id) # Delete notification too
    except:
        bot.reply_to(message, "Usage: `/clear 10`")

@bot.message_handler(commands=['pin'])
def pin_msg(message):
    if not is_admin(message): return
    if message.reply_to_message:
        bot.pin_chat_message(message.chat.id, message.reply_to_message.message_id)
        bot.reply_to(message, "📌 Thok diya Pin!")
    else:
        bot.reply_to(message, "Reply kar jisko pin karna hai.")

@bot.message_handler(commands=['unpin'])
def unpin_msg(message):
    if not is_admin(message): return
    bot.unpin_chat_message(message.chat.id)
    bot.reply_to(message, "Pin hata diya.")

@bot.message_handler(commands=['nuke'])
def nuke_chat(message):
    if not is_admin(message): return
    bot.send_message(message.chat.id, "☢️ ATOMIC BOMB LAUNCHED! (Deleting last 50 messages...)")
    # Reuse clear logic slightly modified
    try:
        for i in range(50):
            try:
                bot.delete_message(message.chat.id, message.message_id - i)
            except: pass
    except: pass

@bot.message_handler(commands=['shout'])
def shout_text(message):
    text = message.text.replace("/shout", "").strip().upper()
    if text:
        bot.send_message(message.chat.id, f"📢 **{text}** 📢", parse_mode="Markdown")

# --- AUTO REPLY SYSTEM ---

@bot.message_handler(commands=['setreply'])
def set_reply(message):
    if not is_admin(message): return
    try:
        text = message.text.replace("/setreply", "").strip()
        if "|" in text:
            trigger, response = text.split("|", 1)
            auto_replies[trigger.strip().lower()] = response.strip()
            save_replies(auto_replies)
            bot.reply_to(message, f"✅ Set ho gaya! '{trigger.strip()}' -> '{response.strip()}'")
        else:
            bot.reply_to(message, "Format galat hai. Use: `/setreply Hi | Namaste`")
    except:
        bot.reply_to(message, "Error aa gaya.")

@bot.message_handler(commands=['delreply'])
def del_reply(message):
    if not is_admin(message): return
    trigger = message.text.replace("/delreply", "").strip().lower()
    if trigger in auto_replies:
        del auto_replies[trigger]
        save_replies(auto_replies)
        bot.reply_to(message, f"❌ Hata diya '{trigger}' ko.")
    else:
        bot.reply_to(message, "Ye word list mein nahi hai.")

# --- FUN COMMANDS ---

@bot.message_handler(commands=['bala'])
def bala_dance(message):
    bot.send_message(message.chat.id, "🕺 Shaitaan ka Saala... BALA BALA! 🕺")

@bot.message_handler(commands=['joke'])
def tell_joke(message):
    bot.reply_to(message, random.choice(jokes))

@bot.message_handler(commands=['roast'])
def roast_guy(message):
    target = message.reply_to_message.from_user.first_name if message.reply_to_message else message.from_user.first_name
    bot.send_message(message.chat.id, f"Oye {target}! {random.choice(roasts)} 🔥")

# --- TEXT HANDLER (Auto Reply & Filters) ---
@bot.message_handler(func=lambda message: True)
def handle_text(message):
    # 1. Check Auto Reply
    txt = message.text.lower()
    if txt in auto_replies:
        bot.reply_to(message, auto_replies[txt])
    
    # 2. Bad Words Filter (Basic)
    bad_words = ["badword1", "badword2"] # Add gaalis here
    if any(word in txt for word in bad_words):
        bot.delete_message(message.chat.id, message.message_id)
        bot.send_message(message.chat.id, f"{message.from_user.first_name}, gaali mat de saale! 😡")

# --- MAIN EXECUTION (FIX FOR 409 CONFLICT) ---
if __name__ == "__main__":
    print("🤖 Bot Start ho raha hai...")
    
    # 1. Webserver start karo (Render ke liye)
    keep_alive()
    
    # 2. Conflict Fixer: Purane webhooks hatao
    try:
        bot.remove_webhook()
        time.sleep(1) # Thoda saans lene do server ko
    except Exception as e:
        print(f"Webhook remove error (Ignorable): {e}")

    # 3. Infinity Polling (Retry mechanism ke saath)
    print("✅ Bot is Online via Long Polling!")
    while True:
        try:
            # timeout=60 means connection stays open for 60s
            # long_polling_timeout=5 ensures stability
            bot.infinity_polling(timeout=60, long_polling_timeout=5)
        except Exception as e:
            print(f"⚠️ Connection toot gaya: {e}")
            time.sleep(5) # 5 second ruko fir wapas try karo
            print("🔄 Reconnecting...")
