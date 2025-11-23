import os
import telebot
import time
from telebot import types
from flask import Flask
from threading import Thread

# --- CONFIGURATION ---
# Get token from Environment Variable (Set this in Render)
API_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')

if not API_TOKEN:
    raise ValueError("No BOT TOKEN found in environment variables!")

bot = telebot.TeleBot(API_TOKEN)

# --- KEEP ALIVE SERVER (For Render) ---
app = Flask('')

@app.route('/')
def home():
    return "I am alive and running!"

def run_http():
    # Render assigns a PORT env var, default to 8080 if not found
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_http)
    t.start()

# --- HELPER FUNCTIONS ---

def is_admin(message):
    """Checks if the user matches admin rights"""
    chat_id = message.chat.id
    user_id = message.from_user.id
    member = bot.get_chat_member(chat_id, user_id)
    return member.status in ['administrator', 'creator']

def get_target(message):
    """Gets the target user from a reply"""
    if message.reply_to_message:
        return message.reply_to_message.from_user
    return None

# --- MODERATION COMMANDS ---

@bot.message_handler(commands=['kick'])
def kick_user(message):
    if not is_admin(message):
        return bot.reply_to(message, "❌ You are not an admin.")
    
    target = get_target(message)
    if not target:
        return bot.reply_to(message, "❌ Reply to a user to kick them.")

    try:
        bot.unban_chat_member(message.chat.id, target.id) # Unban kicks the user but allows rejoin
        bot.reply_to(message, f"✅ {target.first_name} has been kicked.")
    except Exception as e:
        bot.reply_to(message, f"❌ Error: {e}")

@bot.message_handler(commands=['ban'])
def ban_user(message):
    if not is_admin(message):
        return bot.reply_to(message, "❌ You are not an admin.")
    
    target = get_target(message)
    if not target:
        return bot.reply_to(message, "❌ Reply to a user to ban them.")

    try:
        bot.ban_chat_member(message.chat.id, target.id)
        bot.reply_to(message, f"⛔ {target.first_name} has been banned.")
    except Exception as e:
        bot.reply_to(message, f"❌ Error: {e}")

@bot.message_handler(commands=['mute'])
def mute_user(message):
    """Usage: /mute [seconds] (Reply to user)"""
    if not is_admin(message):
        return bot.reply_to(message, "❌ You are not an admin.")
    
    target = get_target(message)
    if not target:
        return bot.reply_to(message, "❌ Reply to a user to mute them.")

    args = message.text.split()
    duration = 60 # Default 60 seconds
    if len(args) > 1:
        try:
            duration = int(args[1])
        except ValueError:
            return bot.reply_to(message, "❌ Time must be a number (in seconds).")

    try:
        # Restrict permissions
        bot.restrict_chat_member(
            message.chat.id, 
            target.id, 
            until_date=time.time() + duration,
            can_send_messages=False
        )
        bot.reply_to(message, f"😶 {target.first_name} muted for {duration} seconds.")
    except Exception as e:
        bot.reply_to(message, f"❌ Error: {e}")

@bot.message_handler(commands=['unmute'])
def unmute_user(message):
    if not is_admin(message):
        return bot.reply_to(message, "❌ You are not an admin.")
    
    target = get_target(message)
    if not target:
        return bot.reply_to(message, "❌ Reply to a user to unmute.")

    try:
        # Restore permissions (Default user permissions)
        bot.restrict_chat_member(
            message.chat.id,
            target.id,
            can_send_messages=True,
            can_send_media_messages=True,
            can_send_other_messages=True,
            can_add_web_page_previews=True
        )
        bot.reply_to(message, f"🗣️ {target.first_name} has been unmuted.")
    except Exception as e:
        bot.reply_to(message, f"❌ Error: {e}")

@bot.message_handler(commands=['clear', 'purge'])
def clear_messages(message):
    """Usage: /clear [amount]"""
    if not is_admin(message):
        return bot.reply_to(message, "❌ You are not an admin.")

    args = message.text.split()
    if len(args) < 2:
        return bot.reply_to(message, "⚠️ Usage: /clear [amount]")

    try:
        amount = int(args[1])
        if amount > 100:
            amount = 100 # Telegram limit per request
            
        # Delete current message first
        try:
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass

        # Iterate backward to delete
        message_ids = []
        start_id = message.message_id - 1
        for i in range(amount):
            message_ids.append(start_id - i)
        
        # Note: delete_messages (batch) is supported in newer APIs, 
        # but looping delete_message is safer for general compatibility
        deleted_count = 0
        for msg_id in message_ids:
            try:
                bot.delete_message(message.chat.id, msg_id)
                deleted_count += 1
            except:
                pass # Message might not exist or is too old
        
        confirmation = bot.send_message(message.chat.id, f"🧹 Cleared {deleted_count} messages.")
        time.sleep(3)
        bot.delete_message(message.chat.id, confirmation.message_id)

    except ValueError:
        bot.reply_to(message, "❌ Please enter a valid number.")

@bot.message_handler(commands=['undo_clear'])
def undo_clear(message):
    bot.reply_to(message, "⚠️ **System Limitations:**\nTelegram API does NOT allow restoring deleted messages. Once cleared, they are gone forever.")

@bot.message_handler(commands=['promote'])
def promote_user(message):
    if not is_admin(message):
        return bot.reply_to(message, "❌ You are not an admin.")
    
    target = get_target(message)
    if not target:
        return bot.reply_to(message, "❌ Reply to a user to promote.")

    try:
        bot.promote_chat_member(
            message.chat.id,
            target.id,
            can_change_info=True,
            can_post_messages=True,
            can_edit_messages=True,
            can_delete_messages=True,
            can_invite_users=True,
            can_restrict_members=True,
            can_pin_messages=True,
            can_promote_members=False
        )
        bot.reply_to(message, f"🌟 {target.first_name} is now an Admin.")
    except Exception as e:
        bot.reply_to(message, f"❌ Error: {e}")

@bot.message_handler(commands=['demote'])
def demote_user(message):
    if not is_admin(message):
        return bot.reply_to(message, "❌ You are not an admin.")
    
    target = get_target(message)
    if not target:
        return bot.reply_to(message, "❌ Reply to a user to demote.")

    try:
        bot.promote_chat_member(
            message.chat.id,
            target.id,
            can_change_info=False,
            can_post_messages=False,
            can_edit_messages=False,
            can_delete_messages=False,
            can_invite_users=False,
            can_restrict_members=False,
            can_pin_messages=False,
            can_promote_members=False
        )
        bot.reply_to(message, f"📉 {target.first_name} is no longer an Admin.")
    except Exception as e:
        bot.reply_to(message, f"❌ Error: {e}")

@bot.message_handler(commands=['invite'])
def create_invite(message):
    """Usage: /invite [uses] [seconds_valid]"""
    if not is_admin(message):
        return bot.reply_to(message, "❌ You are not an admin.")
    
    args = message.text.split()
    uses = 1
    duration = 0 # 0 means no expiry

    if len(args) > 1:
        try:
            uses = int(args[1])
        except: pass
    if len(args) > 2:
        try:
            duration = int(args[2])
        except: pass

    try:
        link = bot.create_chat_invite_link(
            message.chat.id, 
            member_limit=uses, 
            expire_date=int(time.time()) + duration if duration > 0 else None
        )
        
        text = f"🎫 **Custom Invite Link Created**\n"
        text += f"🔗 Link: {link.invite_link}\n"
        text += f"👥 Limit: {uses} uses\n"
        text += f"⏳ Expires: {duration if duration > 0 else 'Never'}"
        
        bot.reply_to(message, text, parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ Error: {e}")

# --- START POLLING ---
if __name__ == "__main__":
    keep_alive() # Start Flask server
    print("Bot is running...")
    bot.infinity_polling()
