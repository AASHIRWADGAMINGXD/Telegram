import os
import json
import time
import datetime
from flask import Flask, request
from telegram import Update, ChatPermissions, ChatMember
from telegram.ext import Application, Dispatcher, MessageHandler, filters, CommandHandler

app = Flask(__name__)

TOKEN = '8203076967:AAGPApD2JB_6ZmtZsB4fb0PTyEAFB1IwRpQ'  # Replace with your actual bot token from BotFather

# Data storage
user_data = {}  # For thala limits {user_id: {'count': int, 'date': date}}
user_messages = {}  # For spam detection {user_id: [timestamps]}

DATA_FILE = 'data.json'

def load_data():
    global user_data
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r') as f:
                user_data = json.load(f)
        except json.JSONDecodeError:
            user_data = {}

def save_data():
    with open(DATA_FILE, 'w') as f:
        json.dump(user_data, f)

load_data()

async def message_handler(update: Update, context):
    message = update.message
    if not message or not message.text:
        return

    user_id = message.from_user.id
    chat_id = message.chat_id
    text = message.text.lower().strip()

    # Spam detection: flood control (more than 5 messages in 10 seconds)
    current_time = time.time()
    if user_id not in user_messages:
        user_messages[user_id] = []
    user_messages[user_id].append(current_time)
    user_messages[user_id] = [t for t in user_messages[user_id] if current_time - t < 10]

    if len(user_messages[user_id]) > 5:
        # Check if user is admin
        member = await context.bot.get_chat_member(chat_id, user_id)
        if member.status not in (ChatMember.ADMINISTRATOR, ChatMember.OWNER):
            # Mute for 10 minutes
            until_date = int(current_time + 600)
            permissions = ChatPermissions(
                can_send_messages=False,
                can_send_media_messages=False,
                can_send_polls=False,
                can_send_other_messages=False,
                can_add_web_page_previews=False,
                can_change_info=False,
                can_invite_users=False,
                can_pin_messages=False
            )
            await context.bot.restrict_chat_member(
                chat_id, user_id, permissions=permissions, until_date=until_date
            )
            await message.reply_text("You have been muted for 10 minutes due to spamming.")
            user_messages[user_id] = []  # Reset after mute

    # Thala limit check
    if text == 'thala':
        today = datetime.date.today()
        if user_id not in user_data:
            user_data[user_id] = {'count': 0, 'date': today}
        
        if user_data[user_id]['date'] != today:
            user_data[user_id]['count'] = 0
            user_data[user_id]['date'] = today
        
        if user_data[user_id]['count'] < 3:
            user_data[user_id]['count'] += 1
            save_data()
        else:
            await message.delete()
            await message.reply_text("Your thala limit has reached!")

    # !rules command
    if message.text.startswith('!rules'):
        await message.reply_text("#1 spam is not allowed")

async def help_command(update: Update, context):
    help_text = """
Help:
- Spam detection: Users muted for 10 minutes if sending more than 5 messages in 10 seconds.
- Thala limit: You can type 'thala' only 3 times per day. Exceeding deletes the message and notifies you.
- !rules: Shows rules.
- Made by aashirwadgamerzz
"""
    await update.message.reply_text(help_text)

# Set up dispatcher
application = Application.builder().token(TOKEN).build()
dispatcher = application.dispatcher
dispatcher.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
dispatcher.add_handler(CommandHandler('help', help_command))

@app.route('/' + TOKEN, methods=['GET', 'POST'])
def webhook():
    if request.method == 'POST':
        update = Update.de_json(request.get_json(force=True), application.bot)
        dispatcher.process_update(update)
    return 'OK'

if __name__ == '__main__':
    # For local testing: app.run(port=5000)
    # For Render: Run as web service (no need for app.run, use gunicorn)
    pass
