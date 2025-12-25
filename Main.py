import os
import json
import logging
import asyncio
from functools import wraps
from dotenv import load_dotenv
from telegram import Update, ChatPermissions
from telegram.ext import (
    ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
)
from keep_alive import keep_alive

# --- CONFIGURATION ---
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_PASSWORD = "bala"
DB_FILE = "database.json"

# --- LOGGING SETUP ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- DATABASE MANAGEMENT ---
def load_db():
    if not os.path.exists(DB_FILE):
        return {"authorized_users": [], "settings": {}, "rules": "The world shall know pain."}
    with open(DB_FILE, "r") as f:
        return json.load(f)

def save_db(data):
    with open(DB_FILE, "w") as f:
        json.dump(data, f, indent=4)

db = load_db()

# --- AUTH DECORATOR ---
def restricted(func):
    """Decorator to restrict usage to logged-in users only."""
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        if user_id not in db["authorized_users"]:
            await update.message.reply_text(
                "🛑 **ACCESS DENIED**\n\n"
                "You are not authorized to command the Leader of the Akatsuki.\n"
                "Use `/login <password>` to prove your worth."
            )
            return
        return await func(update, context, *args, **kwargs)
    return wrapped

# --- COMMAND HANDLERS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "I am Nagato. Pain.\n\n"
        "To utilize my power, you must first authenticate.\n"
        "Use `/login <password>`."
    )

async def login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in db["authorized_users"]:
        await update.message.reply_text("You are already recognized by the Akatsuki.")
        return

    if not context.args:
        await update.message.reply_text("Usage: `/login <password>`")
        return

    password = context.args[0]
    if password == ADMIN_PASSWORD:
        db["authorized_users"].append(user_id)
        save_db(db)
        await update.message.reply_text(
            "✅ **Access Granted.**\n\n"
            "Welcome to the Akatsuki. My power is now yours to command.\n"
            "Type `/help` to see the jutsu list."
        )
    else:
        await update.message.reply_text("❌ **Incorrect.** Do not trifle with a God.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    commands = (
        "/admin - Toggle admin mode\n"
        "/antiRaid - Activate defense systems\n"
        "/approval - Approve new members\n"
        "/ban - Ban a user (Shinra Tensei)\n"
        "/blocklist - Manage blocked words\n"
        "/nuke - Destroy chat history\n"
        "/disable - Disable features\n"
        "/rules - View rules\n"
        "/report - Report an issue\n"
        "/pin - Pin a message\n"
        "/privacy - View privacy settings\n"
        "/locks - Lock chat permissions\n"
        "/log_channel - Set logging channel\n"
        "/custom_settings - Edit bot behavior\n"
        "/shout - Broadcast message"
    )
    await update.message.reply_text(f"**Available Jutsu:**\n\n{commands}")

# --- FEATURE COMMANDS ---

@restricted
async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Admin privileges acknowledged. I am listening.")

@restricted
async def anti_raid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status = "ACTIVE"
    await update.message.reply_text(f"🛡 **Anti-Raid System: {status}**\n\nNo intruders shall pass.")

@restricted
async def approval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("User approval mode is set to Manual. You decide their fate.")

@restricted
async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("Reply to a user to ban them.")
        return
    
    try:
        user_to_ban = update.message.reply_to_message.from_user
        await context.bot.ban_chat_member(chat_id=update.effective_chat.id, user_id=user_to_ban.id)
        await update.message.reply_text(f"**SHINRA TENSEI!**\n\n{user_to_ban.first_name} has been removed from this world.")
    except Exception as e:
        await update.message.reply_text(f"Failed to ban. My chakra is limited here: {e}")

@restricted
async def blocklist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Blocklist updated. Filthy words shall not be spoken here.")

@restricted
async def nuke(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⚠️ **CHAOTIC SHINRA TENSEI**\n\n(Simulation: In a real nuke, I would delete all recent messages here.)")

@restricted
async def disable(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Feature disabled. The path is closed.")

@restricted
async def rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rules_text = db.get("rules", "No rules set.")
    await update.message.reply_text(f"📜 **The Laws of Pain:**\n\n{rules_text}")

@restricted
async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Your report has been heard. Justice will be served.")

@restricted
async def pin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.reply_to_message:
        await update.message.reply_to_message.pin()
        await update.message.reply_text("📌 This message is now absolute.")
    else:
        await update.message.reply_text("Reply to a message to pin it.")

@restricted
async def privacy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Privacy Policy: We see everything. We know everything.")

@restricted
async def locks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Lock common permissions
    permissions = ChatPermissions(can_send_messages=False)
    await context.bot.set_chat_permissions(update.effective_chat.id, permissions)
    await update.message.reply_text("🔒 **Planetary Devastation.** Chat has been locked.")

@restricted
async def log_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    db["settings"]["log_channel"] = chat_id
    save_db(db)
    await update.message.reply_text(f"This channel ({chat_id}) is now the eyes of the Akatsuki.")

@restricted
async def custom_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Custom settings panel opened (Simulation).")

@restricted
async def shout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Give me words to shout.")
        return
    msg = " ".join(context.args).upper()
    await update.message.reply_text(f"📢 **{msg}**")

# --- ERROR HANDLING ---
async def error_handler(update: Object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error {context.error}")
    # Only send message if possible
    if isinstance(update, Update) and update.message:
         await update.message.reply_text("My vision is blurred... An internal error occurred.")

# --- MAIN EXECUTION ---
if __name__ == '__main__':
    # Start Keep Alive
    keep_alive()
    
    # Check Token
    if not TOKEN:
        print("Error: BOT_TOKEN not found in .env")
        exit(1)

    # Build Application
    app = ApplicationBuilder().token(TOKEN).build()

    # Public Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("login", login))
    app.add_handler(CommandHandler("help", help_command))

    # Restricted Handlers
    app.add_handler(CommandHandler("admin", admin))
    app.add_handler(CommandHandler("antiraid", anti_raid))
    app.add_handler(CommandHandler("approval", approval))
    app.add_handler(CommandHandler("ban", ban))
    app.add_handler(CommandHandler("blocklist", blocklist))
    app.add_handler(CommandHandler("nuke", nuke))
    app.add_handler(CommandHandler("disable", disable))
    app.add_handler(CommandHandler("rules", rules))
    app.add_handler(CommandHandler("report", report))
    app.add_handler(CommandHandler("pin", pin))
    app.add_handler(CommandHandler("privacy", privacy))
    app.add_handler(CommandHandler("locks", locks))
    app.add_handler(CommandHandler("log_channel", log_channel))
    app.add_handler(CommandHandler("custom_settings", custom_settings))
    app.add_handler(CommandHandler("shout", shout))

    # Error Handler
    app.add_error_handler(error_handler)

    print("Nagato is awake. The world shall know pain...")
    app.run_polling()
