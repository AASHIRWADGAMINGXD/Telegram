import os
import logging
from telegram import Update, ChatPermissions
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, filters
from keep_alive import keep_alive

# Logging setup (Taaki pata chale kya chal raha hai)
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# --- CONFIGURATION ---
TOKEN = os.getenv("BOT_TOKEN")  # Get from Environment
ADMIN_PASSWORD = os.getenv("ADMIN_PASS", "BhaiKaSystem") # Default password
# List to store temporary admins who logged in via password
authorized_users = set()

# --- HELPER: Check Admin ---
async def is_authorized(update: Update):
    user_id = update.effective_user.id
    # Check if user is in our local list OR is a real telegram admin
    if user_id in authorized_users:
        return True
    return False

# --- COMMANDS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🙏 **Namaste Bhai!** \n\n"
        "Main hoon is group ka naya Moderator.\n"
        "Agar power chahiye toh password daal.\n\n"
        "Commands:\n"
        "/login [password] - Admin banne ke liye\n"
        "/kick - Bande ko bahar fekne ke liye\n"
        "/mute - Muh band karne ke liye\n"
        "/clear [number] - Kachra saaf karne ke liye"
    )

async def login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    try:
        # Check if password provided
        if not context.args:
            await update.message.reply_text("Bhai password toh likh! `/login password` aise.")
            return

        password_attempt = context.args[0]
        
        if password_attempt == ADMIN_PASSWORD:
            authorized_users.add(user.id)
            await update.message.reply_text(f"😎 **Swagat hai Boss!**\nAb tu is group ka Don hai. Full power access granted.")
        else:
            await update.message.reply_text("🤨 **Galat Password!**\nChup chap side hat ja, warna laat padegi.")
            
    except Exception as e:
        print(e)

async def kick_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_authorized(update):
        await update.message.reply_text("✋ **Ruk ja chotu!** Tere paas power nahi hai.")
        return

    # Check if command is a reply
    if not update.message.reply_to_message:
        await update.message.reply_text("Arre bhai, jisko nikalna hai uske message pe **Reply** kar ke `/kick` likh.")
        return

    user_to_kick = update.message.reply_to_message.from_user
    try:
        await context.bot.ban_chat_member(update.effective_chat.id, user_to_kick.id)
        await update.message.reply_text(f"👋 **Tata Bye Bye!**\n{user_to_kick.first_name} ko group se bahar fek diya gaya hai.")
    except Exception as e:
        await update.message.reply_text("❌ Error: Shayad wo banda mujhse bhi zyada power wala hai (Admin). Main usse kick nahi kar sakta.")

async def mute_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_authorized(update):
        await update.message.reply_text("✋ **Ruk ja chotu!** Tere paas power nahi hai.")
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("Arre bhai, jisko chup karana hai uske message pe **Reply** kar ke `/mute` likh.")
        return

    user_to_mute = update.message.reply_to_message.from_user
    permissions = ChatPermissions(can_send_messages=False)
    
    try:
        await context.bot.restrict_chat_member(update.effective_chat.id, user_to_mute.id, permissions=permissions)
        await update.message.reply_text(f"🤐 **Shhh!**\n{user_to_mute.first_name} ka muh band kar diya gaya hai. Ab shanti rahegi.")
    except Exception as e:
        await update.message.reply_text("❌ Error: Main isko mute nahi kar pa raha.")

async def clear_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_authorized(update):
        await update.message.reply_text("✋ **Ruk ja chotu!** Tere paas power nahi hai.")
        return

    try:
        if not context.args:
            await update.message.reply_text("Bhai kitne message udane hai? Likh toh sahi. Ex: `/clear 5`")
            return
            
        amount = int(context.args[0])
        
        # Deleting messages
        message_id = update.message.message_id
        chat_id = update.effective_chat.id
        
        # Determine range (Delete 'amount' messages before the command)
        # Note: Bulk delete works best, but here is a loop for compatibility
        counter = 0
        for i in range(amount + 1): # +1 to include the command itself
            try:
                await context.bot.delete_message(chat_id, message_id - i)
                counter += 1
            except:
                continue
                
        await context.bot.send_message(chat_id, f"🧹 **Safayi Abhiyaan Complete!**\n{counter-1} messages uda diye gaye.")
        
    except ValueError:
        await update.message.reply_text("Abe number likh, ABCD nahi!")
    except Exception as e:
        await update.message.reply_text(f"Error aaya bhai: {e}")

async def admin_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await is_authorized(update):
        await update.message.reply_text("👑 **Haan Bhai!** Tu hi hai asli Admin. System tera hai.")
    else:
        await update.message.reply_text("👶 **Tu kaun?** Pehle `/login` kar ke aa.")

# --- MAIN EXECUTION ---
if __name__ == '__main__':
    # Start Web Server for Render/Replit
    keep_alive()
    
    # Check Token
    if not TOKEN:
        print("Error: BOT_TOKEN env variable missing hai bhai!")
        exit()

    application = ApplicationBuilder().token(TOKEN).build()

    # Handlers
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('login', login))
    application.add_handler(CommandHandler('kick', kick_user))
    application.add_handler(CommandHandler('mute', mute_user))
    application.add_handler(CommandHandler('clear', clear_chat))
    application.add_handler(CommandHandler('admin', admin_check))

    print("🤖 Bot Start Ho Gaya Hai Bhai!...")
    application.run_polling()
