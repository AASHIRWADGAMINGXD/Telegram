import logging
import asyncio
import google.generativeai as genai
from telegram import Update, ChatPermissions
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
from keep_alive import keep_alive

# --- CONFIGURATION ---
TOKEN = "YOUR_BOT_TOKEN_HERE"  # ⚠️ REPLACE THIS WITH YOUR TELEGRAM BOT TOKEN
GEMINI_API_KEY = "AIzaSyAjUI-SgoHBIiXH8TasuA8dTq4F7A_6LuI" # Your provided API Key

# --- SETUP ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Configure Google Gemini AI
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# Dictionary to track 'Thala' counts: {user_id: count}
thala_counts = {}

# --- PERMISSION CHECK ---
async def is_user_admin(update: Update):
    if not update.effective_chat or not update.effective_user:
        return False
    member = await update.effective_chat.get_member(update.effective_user.id)
    return member.status in ['administrator', 'creator']

# --- MODERATOR COMMANDS ---

async def mute_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_user_admin(update):
        await update.message.reply_text("❌ You don't have permission.")
        return
    reply = update.message.reply_to_message
    if not reply:
        await update.message.reply_text("⚠️ Reply to the user to mute.")
        return
    try:
        await update.effective_chat.restrict_member(reply.from_user.id, permissions=ChatPermissions(can_send_messages=False))
        await update.message.reply_text(f"🔇 <b>{reply.from_user.first_name}</b> has been muted.", parse_mode='HTML')
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

async def unmute_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_user_admin(update): return
    reply = update.message.reply_to_message
    if not reply:
        await update.message.reply_text("⚠️ Reply to the user to unmute.")
        return
    try:
        await update.effective_chat.restrict_member(
            reply.from_user.id, 
            permissions=ChatPermissions(can_send_messages=True, can_send_media_messages=True, can_send_other_messages=True)
        )
        await update.message.reply_text(f"🔊 <b>{reply.from_user.first_name}</b> has been unmuted.", parse_mode='HTML')
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

async def promote_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_user_admin(update): return
    reply = update.message.reply_to_message
    if not reply:
        await update.message.reply_text("⚠️ Reply to a user to promote.")
        return
    try:
        await update.effective_chat.promote_member(
            user_id=reply.from_user.id,
            can_manage_chat=True, can_delete_messages=True, can_restrict_members=True, can_invite_users=True
        )
        await update.message.reply_text(f"👮‍♂️ <b>{reply.from_user.first_name}</b> is now an Admin!", parse_mode='HTML')
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

async def demote_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_user_admin(update): return
    reply = update.message.reply_to_message
    if not reply:
        await update.message.reply_text("⚠️ Reply to an admin to demote.")
        return
    try:
        await update.effective_chat.promote_member(
            user_id=reply.from_user.id,
            can_manage_chat=False, can_delete_messages=False, can_restrict_members=False
        )
        await update.message.reply_text(f"📉 <b>{reply.from_user.first_name}</b> has been demoted.", parse_mode='HTML')
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

async def clear_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_user_admin(update): return
    if not context.args:
        await update.message.reply_text("⚠️ Usage: /clear <number>")
        return
    try:
        amount = int(context.args[0])
        msg_id = update.message.message_id
        chat_id = update.message.chat_id
        await update.message.delete()
        deleted = 0
        for i in range(1, amount + 1):
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=msg_id - i)
                deleted += 1
            except Exception: continue
        status = await context.bot.send_message(chat_id, f"🧹 Cleared {deleted} messages.")
        await asyncio.sleep(3)
        await status.delete()
    except ValueError:
        await update.message.reply_text("⚠️ Please provide a valid number.")

# --- AI FEATURE (Updated with your API) ---

async def ask_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Queries Google Gemini AI."""
    if not context.args:
        await update.message.reply_text("❓ Usage: `/ask What is the capital of India?`", parse_mode='Markdown')
        return

    user_query = ' '.join(context.args)
    status_msg = await update.message.reply_text("🤔 Thinking...")

    try:
        # Send request to Gemini
        response = model.generate_content(user_query)
        ai_text = response.text
        
        # Telegram has a message limit, split if too long
        if len(ai_text) > 4000:
            ai_text = ai_text[:4000] + "..."

        await context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=status_msg.message_id, text=ai_text, parse_mode='Markdown')
    
    except Exception as e:
        await context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=status_msg.message_id, text=f"❌ API Error: {e}")

# --- THALA CHECKER ---

async def anti_thala_monitor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Checks for the word 'thala' and limits usage to 3 times."""
    if not update.message or not update.message.text:
        return

    text = update.message.text.lower()
    user_id = update.effective_user.id
    
    # Check if message contains "thala"
    if "thala" in text:
        current_count = thala_counts.get(user_id, 0) + 1
        thala_counts[user_id] = current_count

        # Logic: Only send message when they hit exactly 3
        if current_count == 3:
            await update.message.reply_text("🛑 You thala limit reached")
        
        # Optional: If they continue (count > 3), we do nothing (or you can delete their msg)
        # if current_count > 3:
        #    await update.message.delete()

# --- MAIN ---

if __name__ == '__main__':
    keep_alive() # Start Web Server
    app = ApplicationBuilder().token(TOKEN).build()

    # Admin Commands
    app.add_handler(CommandHandler("mute", mute_user))
    app.add_handler(CommandHandler("unmute", unmute_user))
    app.add_handler(CommandHandler("admin", promote_user))
    app.add_handler(CommandHandler("demote", demote_user))
    app.add_handler(CommandHandler("clear", clear_messages))
    
    # AI Command
    app.add_handler(CommandHandler("ask", ask_command))
    
    # Message Monitor (Anti-Thala) - No longer filters spam
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), anti_thala_monitor))

    print("Bot is running...")
    app.run_polling()
