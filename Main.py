import telebot
import time
import threading
from flask import Flask
from google import genai
from telebot import types

# ==========================================
# CONFIGURATION
# ==========================================
# Replace these with your NEW, SECURE keys
GOOGLE_API_KEY = "AIzaSyB9UTpO26FD5ErSJbpsKe-W3gJpFV9HcVs" 
BOT_TOKEN = "8578532543:AAE-r1vXUkNPVmIIDuMRz1oFhAg9GY0UQH4"

# Initialize Google AI Client
# Note: Ensure you use a valid model name. "gemini-1.5-flash" is the current standard.
client = genai.Client(api_key=GOOGLE_API_KEY)

# Initialize Telegram Bot
bot = telebot.TeleBot(BOT_TOKEN)

# AFK Storage
afk_users = {}

# ==========================================
# KEEP ALIVE SERVER
# ==========================================
app = Flask(__name__)

@app.route('/')
def home():
    return "I am alive"

def run_web_server():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = threading.Thread(target=run_web_server)
    t.start()

# ==========================================
# HELPER FUNCTIONS
# ==========================================
def is_admin(message):
    """Check if the user triggering the command is an admin."""
    try:
        chat_member = bot.get_chat_member(message.chat.id, message.from_user.id)
        return chat_member.status in ['administrator', 'creator']
    except Exception:
        return False

# ==========================================
# BOT COMMANDS
# ==========================================

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    help_text = (
        "🤖 **Bot Commands:**\n\n"
        "**AI:**\n"
        "`/ask <query>` - Ask Google Gemini AI a question.\n\n"
        "**Moderation (Admins):**\n"
        "`/clear <number>` - Delete X messages.\n"
        "`/mute` - Mute a user (reply to them).\n"
        "`/admin` - Promote a user to full admin (reply to them).\n"
        "`/demote` - Demote an admin (reply to them).\n\n"
        "**Utility:**\n"
        "`/afk <reason>` - Set yourself as AFK.\n"
        "`/afkclear` - Remove AFK status.\n"
    )
    bot.reply_to(message, help_text, parse_mode='Markdown')

# --- AI COMMAND ---
@bot.message_handler(commands=['ask'])
def ask_ai(message):
    try:
        # Extract prompt
        prompt = message.text[len('/ask '):].strip()
        if not prompt:
            bot.reply_to(message, "Please provide a question. Example: `/ask How does AI work?`", parse_mode='Markdown')
            return

        sent_msg = bot.reply_to(message, "🤔 Thinking...")

        # Call Google Gemini
        response = client.models.generate_content(
            model="gemini-1.5-flash", 
            contents=prompt
        )

        # Telegram has a 4096 character limit per message. Split if necessary.
        response_text = response.text
        if len(response_text) > 4000:
            for x in range(0, len(response_text), 4000):
                bot.reply_to(message, response_text[x:x+4000])
        else:
            bot.edit_message_text(chat_id=message.chat.id, message_id=sent_msg.message_id, text=response_text, parse_mode='Markdown')

    except Exception as e:
        bot.reply_to(message, f"❌ Error: {str(e)}")

# --- MODERATION COMMANDS ---
@bot.message_handler(commands=['clear'])
def clear_messages(message):
    if not is_admin(message):
        bot.reply_to(message, "❌ You must be an admin to use this.")
        return

    try:
        args = message.text.split()
        if len(args) < 2:
            count = 1  # Default to 1 if no number provided
        else:
            count = int(args[1])

        bot.delete_message(message.chat.id, message.message_id) # Delete the command itself
        
        # Delete previous messages
        for i in range(count):
            try:
                bot.delete_message(message.chat.id, message.message_id - (i + 1))
            except:
                pass # Skip if message too old or already deleted
                
        bot.send_message(message.chat.id, f"🧹 Cleared {count} messages.")
    except Exception as e:
        bot.reply_to(message, "❌ Error clearing messages. Make sure I have 'Delete Messages' permission.")

@bot.message_handler(commands=['mute'])
def mute_user(message):
    if not is_admin(message):
        return
    
    if not message.reply_to_message:
        bot.reply_to(message, "Please reply to the user you want to mute.")
        return

    try:
        user_id = message.reply_to_message.from_user.id
        # Mute indefinitely (until manual unmute)
        bot.restrict_chat_member(message.chat.id, user_id, can_send_messages=False)
        bot.reply_to(message, f"🔇 Muted {message.reply_to_message.from_user.first_name}.")
    except Exception as e:
        bot.reply_to(message, f"❌ Error: {e}")

@bot.message_handler(commands=['admin'])
def promote_user(message):
    # Security: Only Creator/Admins should run this
    if not is_admin(message):
        return

    if not message.reply_to_message:
        bot.reply_to(message, "Please reply to the user you want to promote.")
        return

    try:
        user_id = message.reply_to_message.from_user.id
        bot.promote_chat_member(
            message.chat.id, user_id,
            can_change_info=True, can_post_messages=True,
            can_edit_messages=True, can_delete_messages=True,
            can_invite_users=True, can_restrict_members=True,
            can_pin_messages=True, can_promote_members=True
        )
        bot.reply_to(message, f"👑 {message.reply_to_message.from_user.first_name} is now an Admin with full permissions.")
    except Exception as e:
        bot.reply_to(message, f"❌ Error: {e}")

@bot.message_handler(commands=['demote'])
def demote_user(message):
    if not is_admin(message):
        return

    if not message.reply_to_message:
        bot.reply_to(message, "Please reply to the user you want to demote.")
        return

    try:
        user_id = message.reply_to_message.from_user.id
        bot.promote_chat_member(
            message.chat.id, user_id,
            can_change_info=False, can_post_messages=False,
            can_edit_messages=False, can_delete_messages=False,
            can_invite_users=False, can_restrict_members=False,
            can_pin_messages=False, can_promote_members=False
        )
        bot.reply_to(message, f"📉 {message.reply_to_message.from_user.first_name} has been demoted.")
    except Exception as e:
        bot.reply_to(message, f"❌ Error: {e}")

# --- AFK SYSTEM ---
@bot.message_handler(commands=['afk'])
def set_afk(message):
    user_id = message.from_user.id
    reason = message.text[len('/afk '):].strip()
    if not reason:
        reason = "No reason provided"
    
    afk_users[user_id] = reason
    bot.reply_to(message, f"💤 You are now AFK.\nReason: {reason}")

@bot.message_handler(commands=['afkclear'])
def clear_afk_command(message):
    user_id = message.from_user.id
    if user_id in afk_users:
        del afk_users[user_id]
        bot.reply_to(message, "👋 Welcome back! AFK status removed.")
    else:
        bot.reply_to(message, "You were not AFK.")

# AFK Logic: Listen to all messages
@bot.message_handler(func=lambda message: True)
def check_afk(message):
    user_id = message.from_user.id
    
    # 1. If an AFK user speaks, remove their AFK status automatically
    if user_id in afk_users:
        del afk_users[user_id]
        bot.reply_to(message, f"👋 Welcome back {message.from_user.first_name}! I removed your AFK status.")
        return

    # 2. If someone replies to/mentions an AFK user
    if message.reply_to_message:
        replied_user_id = message.reply_to_message.from_user.id
        if replied_user_id in afk_users:
            reason = afk_users[replied_user_id]
            bot.reply_to(message, f"🤫 {message.reply_to_message.from_user.first_name} is currently AFK.\nReason: {reason}")

# ==========================================
# MAIN LOOP
# ==========================================
if __name__ == "__main__":
    print("Starting Keep Alive Server...")
    keep_alive()
    print("Bot is running...")
    bot.infinity_polling()
