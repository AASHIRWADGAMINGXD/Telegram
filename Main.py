import os
import logging
import asyncio
from threading import Thread
from flask import Flask
from telegram import Update, ChatPermissions
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ---------------- CONFIGURATION ---------------- #
# Get the token from Environment Variables (Set this in Render)
TOKEN = os.environ.get("TOKEN") 

# Global dictionary to store AFK status
# Format: {user_id: "Reason"}
AFK_USERS = {}

# ---------------- KEEP ALIVE (WEB SERVER) ---------------- #
app = Flask('')

@app.route('/')
def home():
    return "Bot is alive and running!"

def run():
    # Render usually assigns a port, or we default to 8080
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()

# ---------------- BOT COMMANDS ---------------- #

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Bot is Online! 🚀\nCommands:\n"
        "/bala - Send a GIF\n"
        "/mute - Mute a user (Reply to them)\n"
        "/clear <number> - Delete messages\n"
        "/permission - Check user permission\n"
        "/afk <reason> - Go AFK"
    )

# Feature: /bala send gif
async def bala(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # A funny GIF URL (You can change this link)
    gif_url = "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExcWc0aHV3emF4bmF4aHhpZnh4aHhpZnh4aHhpZnh4aHhpZnh4aHhpZiZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/LfpjDCLvC9xapD6zO8/giphy.gif"
    await update.message.reply_animation(gif_url, caption="Bala Bala! 🕺")

# Feature: /clear
async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Check if user is admin
    user = update.effective_user
    chat_member = await update.effective_chat.get_member(user.id)
    
    if chat_member.status not in ['administrator', 'creator']:
        await update.message.reply_text("You need Admin permissions to use this.")
        return

    # Delete the command message itself
    await update.message.delete()

    args = context.args
    if not args:
        await update.message.reply_text("Usage: /clear <number>", delete_after=5)
        return

    try:
        count = int(args[0])
        # Note: Bots can't easily bulk delete old messages due to API limits.
        # We will iterate and delete recent message IDs.
        # This is a basic implementation suitable for recent messages.
        message_id = update.message.message_id
        for i in range(1, count + 1):
            try:
                await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=message_id - i)
            except Exception:
                continue # Skip if message doesn't exist or too old
        
        confirmation = await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Tried clearing {count} messages.")
        # Delete the confirmation after 3 seconds
        await asyncio.sleep(3)
        await confirmation.delete()

    except ValueError:
        await update.message.reply_text("Please provide a valid number.")

# Feature: /mute
async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_member = await update.effective_chat.get_member(user.id)
    
    # Check Admin
    if chat_member.status not in ['administrator', 'creator']:
        await update.message.reply_text("❌ You are not an admin!")
        return

    # Check if it's a reply
    if not update.message.reply_to_message:
        await update.message.reply_text("ℹ️ Reply to a user to mute them.")
        return

    victim = update.message.reply_to_message.from_user
    try:
        permissions = ChatPermissions(can_send_messages=False)
        await update.effective_chat.restrict_member(victim.id, permissions=permissions)
        await update.message.reply_text(f"Qwiet please! 🤫 {victim.first_name} has been muted.")
    except Exception as e:
        await update.message.reply_text(f"Failed to mute. Ensure I am Admin and the user is not. Error: {e}")

# Feature: /permmision (Permission)
async def check_permission(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_member = await update.effective_chat.get_member(user.id)
    status = chat_member.status.upper()
    await update.message.reply_text(f"👤 <b>User:</b> {user.first_name}\n🔰 <b>Status:</b> {status}", parse_mode='HTML')

# Feature: /afk
async def set_afk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    reason = " ".join(context.args) if context.args else "No reason given"
    
    AFK_USERS[user.id] = reason
    await update.message.reply_text(f"😴 {user.first_name} is now AFK.\nReason: {reason}")

# Feature: Handle AFK Mentions and Returns
async def afk_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.from_user:
        return

    user_id = update.message.from_user.id
    
    # 1. Check if the sender is returning from AFK
    if user_id in AFK_USERS:
        reason = AFK_USERS.pop(user_id)
        await update.message.reply_text(f"👋 Welcome back {update.message.from_user.first_name}! You were away: {reason}")

    # 2. Check if the message mentions an AFK user (via Reply)
    if update.message.reply_to_message:
        replied_user_id = update.message.reply_to_message.from_user.id
        if replied_user_id in AFK_USERS:
            reason = AFK_USERS[replied_user_id]
            name = update.message.reply_to_message.from_user.first_name
            await update.message.reply_text(f"🤫 Shh! {name} is AFK currently.\nReason: {reason}")
            
    # 3. Check mentions in text entities (Basic check)
    if update.message.parse_entities(types=["mention", "text_mention"]):
        # This is more complex in Python-Telegram-Bot, simplified here:
        # If you need full mention support, we iterate entities. 
        # For simplicity, we stick to reply detection above.
        pass

# ---------------- MAIN EXECUTION ---------------- #

def main():
    # 1. Start the Web Server for Render
    keep_alive()

    # 2. Check Token
    if not TOKEN:
        print("Error: TOKEN environment variable not set.")
        return

    # 3. Setup Bot
    application = Application.builder().token(TOKEN).build()

    # 4. Add Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("bala", bala))
    application.add_handler(CommandHandler("clear", clear))
    application.add_handler(CommandHandler("mute", mute))
    application.add_handler(CommandHandler("permission", check_permission))
    application.add_handler(CommandHandler("afk", set_afk))
    
    # Message Handler for AFK logic (Must be last)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, afk_handler))

    # 5. Run
    print("Bot is running...")
    application.run_polling()

if __name__ == '__main__':
    main()
