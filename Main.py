import os
import logging
import threading
import asyncio
from flask import Flask
from telegram import Update, ChatPermissions
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, filters

# --- CONFIGURATION ---
TOKEN = os.getenv("TOKEN")  # You will set this in Render Environment Variables
PORT = int(os.environ.get('PORT', 5000))

# --- LOGGING ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# --- FLASK KEEP-ALIVE SERVER ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running and alive!", 200

def run_flask():
    # Run Flask on 0.0.0.0 to be accessible within Render
    app.run(host="0.0.0.0", port=PORT)

# --- HELPER: CHECK ADMIN ---
async def is_user_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    member = await context.bot.get_chat_member(chat_id, user_id)
    return member.status in ['administrator', 'creator']

# --- BOT COMMANDS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "I am online! \nCommands:\n/mute (reply)\n/demote (reply)\n/admin (reply)\n/clear <count>\n/ask <question>"
    )

# 1. MUTE (Mutes a user indefinitely)
async def mute_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_user_admin(update, context):
        await update.message.reply_text("❌ You are not an admin.")
        return

    reply = update.message.reply_to_message
    if not reply:
        await update.message.reply_text("⚠️ Please reply to a user to mute them.")
        return

    try:
        # Restrict permissions to False
        mute_permissions = ChatPermissions(can_send_messages=False)
        await context.bot.restrict_chat_member(
            chat_id=update.effective_chat.id,
            user_id=reply.from_user.id,
            permissions=mute_permissions
        )
        await update.message.reply_text(f"🔇 {reply.from_user.first_name} has been muted.")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

# 2. DEMOTE (Removes admin rights)
async def demote_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_user_admin(update, context):
        return

    reply = update.message.reply_to_message
    if not reply:
        await update.message.reply_text("⚠️ Reply to an admin to demote them.")
        return

    try:
        # Promote with all False flags effectively demotes (if bot has permission)
        await context.bot.promote_chat_member(
            chat_id=update.effective_chat.id,
            user_id=reply.from_user.id,
            is_anonymous=False,
            can_manage_chat=False,
            can_delete_messages=False,
            can_manage_video_chats=False,
            can_restrict_members=False,
            can_promote_members=False,
            can_change_info=False,
            can_invite_users=False,
            can_post_messages=False,
            can_edit_messages=False,
            can_pin_messages=False
        )
        await update.message.reply_text(f"📉 {reply.from_user.first_name} has been demoted.")
    except Exception as e:
        await update.message.reply_text(f"Failed to demote. Ensure I am Admin and have 'Add Admins' permission.\nError: {e}")

# 3. ADMIN (Promote user)
async def admin_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_user_admin(update, context):
        return

    reply = update.message.reply_to_message
    if not reply:
        await update.message.reply_text("⚠️ Reply to a user to promote them.")
        return

    try:
        await context.bot.promote_chat_member(
            chat_id=update.effective_chat.id,
            user_id=reply.from_user.id,
            can_delete_messages=True,
            can_invite_users=True,
            can_restrict_members=True,
            can_pin_messages=True
        )
        await update.message.reply_text(f"👮‍♂️ {reply.from_user.first_name} is now an Admin.")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

# 4. CLEAR (Delete X messages)
async def clear_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_user_admin(update, context):
        return

    args = context.args
    if not args:
        await update.message.reply_text("Usage: /clear <number>")
        return

    try:
        amount = int(args[0])
        message_id = update.message.message_id
        chat_id = update.effective_chat.id
        
        # Delete the command message first
        await context.bot.delete_message(chat_id, message_id)

        # Simple loop to delete messages (Note: Bulk delete API exists but this is simpler for logic)
        # In a real production bot, use delete_messages (plural) if available or careful loops
        count = 0
        # We iterate backwards from the current message
        for i in range(amount):
            try:
                # Attempt to delete previous messages
                await context.bot.delete_message(chat_id, message_id - (i + 1))
                count += 1
            except Exception:
                continue # Skip if message doesn't exist or too old
        
        msg = await context.bot.send_message(chat_id, f"🧹 Cleared {count} messages.")
        # Auto-delete the notification after 3 seconds
        await asyncio.sleep(3)
        await context.bot.delete_message(chat_id, msg.message_id)
        
    except ValueError:
        await update.message.reply_text("Please provide a number.")

# 5. PERMISSIONS (Check user status)
async def permissions_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reply = update.message.reply_to_message
    target = reply.from_user if reply else update.effective_user
    
    member = await context.bot.get_chat_member(update.effective_chat.id, target.id)
    status = member.status
    
    await update.message.reply_text(f"👤 User: {target.first_name}\n🔰 Status: {status}")

# 6. ASK (Simple Q&A Logic)
async def ask_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /ask <your question>")
        return
    
    question = ' '.join(context.args)
    # Here you could integrate ChatGPT API. 
    # For now, we will use a simple logic.
    if "hello" in question.lower():
        answer = "Hi there! How can I help?"
    elif "admin" in question.lower():
        answer = "Admins are the rulers of this chat."
    else:
        answer = f"That is an interesting question about: '{question}'. I am just a bot though!"
        
    await update.message.reply_text(f"🤖 <b>Question:</b> {question}\n\n<b>Answer:</b> {answer}", parse_mode='HTML')

# --- MAIN EXECUTION ---
if __name__ == '__main__':
    # 1. Start Flask in a separate thread (Daemon so it dies when main dies)
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()

    # 2. Start Bot
    if not TOKEN:
        print("Error: TOKEN environment variable not set.")
    else:
        application = ApplicationBuilder().token(TOKEN).build()

        # Handlers
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("mute", mute_user))
        application.add_handler(CommandHandler("demote", demote_user))
        application.add_handler(CommandHandler("admin", admin_user))
        application.add_handler(CommandHandler("clear", clear_messages))
        application.add_handler(CommandHandler("permissions", permissions_check))
        application.add_handler(CommandHandler("ask", ask_command))

        print("Bot is polling...")
        application.run_polling()
