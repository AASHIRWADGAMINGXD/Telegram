import telebot
import os
import json
import random
import time
from telebot import types
from keep_alive import keep_alive
from dotenv import load_dotenv

# Load Environment Variables
load_dotenv()
TOKEN = os.getenv('BOT_TOKEN')
BOT_PASSWORD = os.getenv('BOT_PASSWORD')

bot = telebot.TeleBot(TOKEN)

# --- DATABASE FOR AUTO-REPLY (JSON) ---
try:
    with open('autoreply.json', 'r') as f:
        auto_replies = json.load(f)
except:
    auto_replies = {}

# --- LISTS FOR FUN ---
jokes = [
    "Teacher: Pappu, batao hospital mein sabse mehnga bed kaunsa hota hai?\nPappu: Death bed sir, uspar letne ke liye jaan deni padti hai! 😂",
    "Girl: Mere pet mein chuhe daud rahe hain.\nBoy: To muh khol, billi daal deta hoon! 🤣",
    "Santa: Oye, tu school kyu nahi gaya?\nBanta: Yaar, kal school walo ne weight check kiya tha, aaj height check karenge. Main darr gaya ki kahi saale lund na naap de! 💀"
]

roasts = [
    "Shakal dekh ke lagta hai aadha download hua hai tu.",
    "Bhai tu rehne de, tujhse na ho payega.",
    "Jitna dimaag tere paas hai, utna to main chutta chhod deta hoon.",
    "Teri shakal dekh ke WiFi bhi disconnect ho jata hai."
]

# Authorized Users (Who entered password)
authorized_users = []

# --- HELPER FUNCTIONS ---
def save_replies():
    with open('autoreply.json', 'w') as f:
        json.dump(auto_replies, f)

def is_admin(message):
    try:
        chat_member = bot.get_chat_member(message.chat.id, message.from_user.id)
        return chat_member.status in ['administrator', 'creator'] or message.from_user.id in authorized_users
    except:
        return False

# --- PASSWORD SYSTEM ---
@bot.message_handler(commands=['login'])
def login_system(message):
    try:
        msg_text = message.text.split()
        if len(msg_text) < 2:
            bot.reply_to(message, "Arey password to daal bhai! Usage: `/login <password>`")
            return
        
        password = msg_text[1]
        if password == BOT_PASSWORD:
            if message.from_user.id not in authorized_users:
                authorized_users.append(message.from_user.id)
                bot.reply_to(message, "Badhai ho Bhai! Access mil gaya. Ab tu Don hai. 😎")
            else:
                bot.reply_to(message, "Tu pehle se hi login hai chomu.")
        else:
            bot.reply_to(message, "Galat password! Nikal yahan se. 😡")
    except Exception as e:
        bot.reply_to(message, f"Error aa gaya bhai: {e}")

# --- MODERATION COMMANDS ---

@bot.message_handler(commands=['kick'])
def kick_user(message):
    if not is_admin(message):
        bot.reply_to(message, "Chal be, tu Admin nahi hai!")
        return
    if not message.reply_to_message:
        bot.reply_to(message, "Kis ko udana hai? Reply to kar uske message pe.")
        return
    try:
        bot.kick_chat_member(message.chat.id, message.reply_to_message.from_user.id)
        bot.reply_to(message, f"Uda diya saale ko! {message.reply_to_message.from_user.first_name} gaya tel lene. ✈️")
    except Exception as e:
        bot.reply_to(message, "Power kam pad gayi bhai (Permission Error).")

@bot.message_handler(commands=['mute'])
def mute_user(message):
    if not is_admin(message):
        bot.reply_to(message, "Tu Admin nahi hai, shant baith.")
        return
    if not message.reply_to_message:
        bot.reply_to(message, "Kiska muh band karna hai? Reply kar.")
        return
    try:
        bot.restrict_chat_member(message.chat.id, message.reply_to_message.from_user.id, until_date=time.time()+300) # Mute for 5 mins
        bot.reply_to(message, "Chup karja thodi der! (Muted for 5 mins) 🤐")
    except:
        bot.reply_to(message, "Admin rights check karle bhai.")

@bot.message_handler(commands=['clear', 'purge'])
def clear_messages(message):
    if not is_admin(message):
        bot.reply_to(message, "Tere bas ki baat nahi hai.")
        return
    try:
        args = message.text.split()
        amount = int(args[1]) if len(args) > 1 else 10
        
        # Limit to avoid API errors
        if amount > 100: amount = 100
        
        message_ids = [message.message_id - i for i in range(amount + 1)]
        for mid in message_ids:
            try:
                bot.delete_message(message.chat.id, mid)
            except:
                pass
        bot.send_message(message.chat.id, f"Safai Abhiyan Complete! {amount} messages uda diye. 🧹")
    except:
        bot.reply_to(message, "Usage: `/clear 10`")

@bot.message_handler(commands=['promote'])
def promote_user(message):
    if not is_admin(message): return
    if not message.reply_to_message: return
    try:
        bot.promote_chat_member(message.chat.id, message.reply_to_message.from_user.id, can_change_info=True, can_delete_messages=True, can_invite_users=True, can_restrict_members=True, can_pin_messages=True)
        bot.reply_to(message, "Mubarak ho! Naya Admin bana diya isko. 👮‍♂️")
    except:
        bot.reply_to(message, "Main isko promote nahi kar sakta bhai.")

# --- UTILITY COMMANDS ---

@bot.message_handler(commands=['pin'])
def pin_message(message):
    if not is_admin(message): return
    if not message.reply_to_message:
        bot.reply_to(message, "Reply to kar jisko Pin karna hai.")
        return
    bot.pin_chat_message(message.chat.id, message.reply_to_message.message_id)
    bot.reply_to(message, "Thok diya pin! 📌")

@bot.message_handler(commands=['unpin'])
def unpin_message(message):
    if not is_admin(message): return
    bot.unpin_chat_message(message.chat.id)
    bot.reply_to(message, "Pin hata diya bhai.")

@bot.message_handler(commands=['shout'])
def shout_msg(message):
    text = message.text.replace("/shout", "").upper()
    if text:
        bot.send_message(message.chat.id, f"📢 **{text}** 📢", parse_mode="Markdown")
    else:
        bot.reply_to(message, "Kya chillaun? Kuch likh to sahi.")

@bot.message_handler(commands=['nuke'])
def nuke_chat(message):
    if not is_admin(message):
        bot.reply_to(message, "Ye button dabane ki aukaat nahi hai teri.")
        return
    
    bot.reply_to(message, "☢️ ATOMIC BOMB DETECTED... 3... 2... 1... BOOM! (Just kidding, deleting 50 messages)")
    # Reuse clear logic
    try:
        message_ids = [message.message_id - i for i in range(51)]
        for mid in message_ids:
            try:
                bot.delete_message(message.chat.id, mid)
            except: pass
    except: pass

# --- AUTO REPLY SYSTEM ---

@bot.message_handler(commands=['setreply'])
def set_auto_reply(message):
    if not is_admin(message): return
    try:
        # Syntax: /setreply word | response
        content = message.text.replace("/setreply", "").strip()
        if "|" in content:
            trigger, response = content.split("|", 1)
            auto_replies[trigger.strip().lower()] = response.strip()
            save_replies()
            bot.reply_to(message, f"Set kar diya boss! Jab koi bolega '{trigger.strip()}', main bolunga '{response.strip()}'.")
        else:
            bot.reply_to(message, "Sahi se likh bhai: `/setreply Hello | Namaste`")
    except Exception as e:
        bot.reply_to(message, "Error aa gaya.")

@bot.message_handler(commands=['delreply'])
def del_auto_reply(message):
    if not is_admin(message): return
    try:
        word = message.text.replace("/delreply", "").strip().lower()
        if word in auto_replies:
            del auto_replies[word]
            save_replies()
            bot.reply_to(message, f"Hata diya '{word}' ko memory se.")
        else:
            bot.reply_to(message, "Ye to list mein hai hi nahi.")
    except: pass

# --- FUN COMMANDS ---

@bot.message_handler(commands=['bala'])
def bala_command(message):
    bot.send_message(message.chat.id, "🕺 Shaitaan ka Saala... Bala Bala! 🕺\n(Imagine music playing)")

@bot.message_handler(commands=['joke'])
def send_joke(message):
    bot.reply_to(message, random.choice(jokes))

@bot.message_handler(commands=['roast'])
def send_roast(message):
    target = message.reply_to_message.from_user.first_name if message.reply_to_message else message.from_user.first_name
    roast_line = random.choice(roasts)
    bot.send_message(message.chat.id, f"Oye {target}! {roast_line} 🔥")

# --- LISTENER FOR AUTO-REPLIES & MESSAGES ---
@bot.message_handler(func=lambda message: True)
def handle_messages(message):
    # Check for auto-replies
    msg_text = message.text.lower()
    if msg_text in auto_replies:
        bot.reply_to(message, auto_replies[msg_text])

# --- START BOT ---
print("Bot Start ho gaya hai bhai log...")
keep_alive() # Starts the web server
bot.infinity_polling()
