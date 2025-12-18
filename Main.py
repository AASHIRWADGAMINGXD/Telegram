import telebot
import os
import threading
import time
from datetime import datetime, timedelta

# Environment variables
BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'defaultpass')  # Change this in env or hardcode securely

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable is required.")

bot = telebot.TeleBot(BOT_TOKEN)

# Global sets/dicts
admins = set()
blocked = set()
muted = set()  # For permanent mute (deletes messages)
auto_replies = {}  # keyword: reply_text

def is_admin(user_id):
    return user_id in admins

def is_allowed(user_id):
    return user_id not in blocked

# Keep-alive mechanism (simple thread to prevent idle timeout on some hosts)
def keep_alive():
    while True:
        print(f"Bot alive at {datetime.now()}")
        time.sleep(60)  # Ping every minute

keep_alive_thread = threading.Thread(target=keep_alive, daemon=True)
keep_alive_thread.start()

# Block handler: Ignore blocked users' non-command messages
@bot.message_handler(func=lambda m: not m.is_command() and m.from_user.id in blocked)
def ignore_blocked(m):
    pass  # Do nothing

# Mute handler: Delete muted users' messages
@bot.message_handler(func=lambda m: not m.is_command() and m.from_user.id in muted)
def delete_muted(m):
    try:
        bot.delete_message(m.chat.id, m.message_id)
    except Exception as e:
        print(f"Failed to delete muted message: {e}")

# Auto-reply handler for non-command messages
@bot.message_handler(func=lambda m: not m.is_command() and is_allowed(m.from_user.id))
def handle_auto_reply(m):
    if not m.text:
        return
    text_lower = m.text.lower()
    for keyword, reply_text in auto_replies.items():
        if keyword in text_lower:
            bot.reply_to(m, reply_text)
            return  # Only one reply per message for simplicity

@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    if message.chat.type == 'private':
        bot.reply_to(message, "Welcome! Use /login <password> in private chat to gain admin access.\n\nAdmin commands:\n/clear [count] - Clear recent messages\n/mute <user_id> - Mute user (delete their messages)\n/unmute <user_id> - Unmute user\n/ban <user_id> - Ban user from group\n/kick <user_id> - Kick user from group\n/block <user_id> - Block user from bot\n/unblock <user_id> - Unblock user\n/add_auto_reply <keyword> <reply_text> - Add auto reply\n/remove_auto_reply <keyword> - Remove auto reply\n/removeuser <user_id> - Logout a user")
    else:
        bot.reply_to(message, "Bot started. Admins, use commands accordingly.")

@bot.message_handler(commands=['login'])
def login(message):
    if message.chat.type != 'private':
        bot.reply_to(message, "Please use /login in a private chat with the bot.")
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) != 2:
        bot.reply_to(message, "Usage: /login <password>")
        return
    if parts[1] == ADMIN_PASSWORD:
        admins.add(message.from_user.id)
        bot.reply_to(message, "✅ Logged in successfully. You now have admin access.")
    else:
        bot.reply_to(message, "❌ Wrong password.")

@bot.message_handler(commands=['removeuser'])
def removeuser(message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        return
    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message, "Usage: /removeuser <user_id>")
        return
    try:
        target_id = int(parts[1])
        if target_id in admins:
            admins.remove(target_id)
            bot.reply_to(message, f"✅ Removed admin access for user {target_id}.")
        else:
            bot.reply_to(message, "❌ User is not an admin.")
    except ValueError:
        bot.reply_to(message, "❌ Invalid user ID. Must be a number.")

@bot.message_handler(commands=['clear'])
def clear_messages(message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        return
    parts = message.text.split()
    try:
        count = int(parts[1]) if len(parts) > 1 else 10  # Default 10 messages
    except ValueError:
        count = 10
        bot.reply_to(message, "Invalid count, using default 10.")
    chat_id = message.chat.id
    msg_id = message.message_id
    deleted = 0
    for i in range(count):
        try:
            bot.delete_message(chat_id, msg_id - i)
            deleted += 1
        except Exception:
            pass  # Ignore if can't delete (e.g., too old)
    bot.reply_to(message, f"🧹 Cleared {deleted} messages.", delete_after=3)

@bot.message_handler(commands=['mute'])
def mute_user(message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        return
    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message, "Usage: /mute <user_id>")
        return
    try:
        target_id = int(parts[1])
        muted.add(target_id)
        bot.reply_to(message, f"🔇 Muted user {target_id} (messages will be deleted).")
    except ValueError:
        bot.reply_to(message, "❌ Invalid user ID.")

@bot.message_handler(commands=['unmute'])
def unmute_user(message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        return
    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message, "Usage: /unmute <user_id>")
        return
    try:
        target_id = int(parts[1])
        muted.discard(target_id)
        bot.reply_to(message, f"🔊 Unmuted user {target_id}.")
    except ValueError:
        bot.reply_to(message, "❌ Invalid user ID.")

@bot.message_handler(commands=['ban'])
def ban_user(message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        return
    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message, "Usage: /ban <user_id> (in group)")
        return
    try:
        target_id = int(parts[1])
        bot.ban_chat_member(message.chat.id, target_id)
        bot.reply_to(message, f"🚫 Banned user {target_id} from group.")
    except Exception as e:
        bot.reply_to(message, f"❌ Failed to ban: {str(e)}")

@bot.message_handler(commands=['kick'])
def kick_user(message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        return
    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message, "Usage: /kick <user_id> (in group)")
        return
    try:
        target_id = int(parts[1])
        chat_id = message.chat.id
        bot.ban_chat_member(chat_id, target_id)
        bot.unban_chat_member(chat_id, target_id)
        bot.reply_to(message, f"👢 Kicked user {target_id} from group.")
    except Exception as e:
        bot.reply_to(message, f"❌ Failed to kick: {str(e)}")

@bot.message_handler(commands=['block'])
def block_user(message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        return
    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message, "Usage: /block <user_id>")
        return
    try:
        target_id = int(parts[1])
        blocked.add(target_id)
        bot.reply_to(message, f"⛔ Blocked user {target_id} from using the bot.")
    except ValueError:
        bot.reply_to(message, "❌ Invalid user ID.")

@bot.message_handler(commands=['unblock'])
def unblock_user(message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        return
    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message, "Usage: /unblock <user_id>")
        return
    try:
        target_id = int(parts[1])
        blocked.discard(target_id)
        bot.reply_to(message, f"✅ Unblocked user {target_id}.")
    except ValueError:
        bot.reply_to(message, "❌ Invalid user ID.")

@bot.message_handler(commands=['add_auto_reply'])
def add_auto_reply(message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        return
    parts = message.text.split(maxsplit=2)
    if len(parts) != 3:
        bot.reply_to(message, "Usage: /add_auto_reply <keyword> <reply_text>")
        return
    keyword = parts[1].lower()
    reply_text = parts[2]
    auto_replies[keyword] = reply_text
    bot.reply_to(message, f"✅ Added auto-reply: '{keyword}' -> '{reply_text}'")

@bot.message_handler(commands=['remove_auto_reply'])
def remove_auto_reply(message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        return
    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message, "Usage: /remove_auto_reply <keyword>")
        return
    keyword = parts[1].lower()
    if keyword in auto_replies:
        del auto_replies[keyword]
        bot.reply_to(message, f"✅ Removed auto-reply for '{keyword}'.")
    else:
        bot.reply_to(message, f"❌ No auto-reply found for '{keyword}'.")

# Error handler
@bot.message_handler(func=lambda message: True)
def handle_all(message):
    if message.from_user.id not in admins and not message.is_command():
        # Optional: Delete non-admin non-command messages? But not implemented for now.
        pass

if __name__ == '__main__':
    print("Bot starting...")
    bot.infinity_polling(none_stop=True, interval=1, timeout=20)
