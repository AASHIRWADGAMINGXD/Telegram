import os
import logging
import html
from telegram import Update, ChatPermissions, InlineKeyboardButton, InlineKeyboardMarkup, constants
from telegram.ext import (
    ApplicationBuilder, 
    ContextTypes, 
    CommandHandler, 
    MessageHandler, 
    CallbackQueryHandler, 
    filters
)
from keep_alive import keep_alive

# --- LOGGING ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- CONFIG ---
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_PASSWORD = os.getenv("ADMIN_PASS", "BhaiKaSystem")

# --- IN-MEMORY DATABASE (Resets on Restart) ---
# Note: Database use karne se data save rehta hai, ye simple RAM storage hai.
authorized_users = set()  # Users logged in via password
warns = {}                # {user_id: count}
afk_users = {}            # {user_id: reason}
auto_replies = {}         # {trigger_word: reply_text}
nuke_status = {}          # Check confirmation

# --- HELPER: AUTH CHECK ---
async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    # Check 1: Login password wala user
    if user_id in authorized_users:
        return True
    
    # Check 2: Real Telegram Admin
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        if member.status in ['administrator', 'creator']:
            return True
    except:
        pass
    
    return False

# --- CORE FEATURES ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = (
        "🙏 **Namaste Bhai!** System update ho gaya hai.\n\n"
        "**Available Commands:**\n"
        "👮 `/warn` - Warning de bande ko\n"
        "☢️ `/nuke` - Chat clear (Confirmation ke saath)\n"
        "📢 `/shout [msg]` - Zor se bol\n"
        "⬆️ `/promote` & ⬇️ `/demote` - Power control\n"
        "🐢 `/setslowmode [seconds]` - Chat speed control\n"
        "💤 `/afk [reason]` - Offline chala ja\n"
        "📌 `/pin` & `/unpin` - Message chipkao\n"
        "🎲 `/roll` - Ludo khel le\n"
        "🕺 `/bala` - Party shuru!\n"
        "🤖 `/setautoreply [word] | [reply]` - Auto jawab\n"
        "❌ `/deleteautoreply [word]` - Auto jawab delete\n"
        "🔑 `/login [pass]` - Secret access"
    )
    await update.message.reply_text(txt, parse_mode='Markdown')

async def login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args and context.args[0] == ADMIN_PASSWORD:
        authorized_users.add(update.effective_user.id)
        await update.message.reply_text("😎 **System Set!** Ab tu Admin hai.")
    else:
        await update.message.reply_text("🤨 **Galat Password!** Nikal pehli fursat mein.")

# --- MODERATION ---

async def warn_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return await update.message.reply_text("⛔ Power nahi hai tere paas!")
    
    if not update.message.reply_to_message:
        return await update.message.reply_text("Kisko warn du? Message pe reply kar!")

    target = update.message.reply_to_message.from_user
    chat_id = update.effective_chat.id

    # Bot self-protection
    if target.id == context.bot.id:
        return await update.message.reply_text("🤬 **Apne baap ko warning dega?**")

    # Increment warn
    current_warns = warns.get(target.id, 0) + 1
    warns[target.id] = current_warns

    msg = f"⚠️ **Warning!**\nUser: {target.first_name}\nCount: {current_warns}/3\nSudhar ja varna uda dunga!"
    
    if current_warns >= 3:
        try:
            await context.bot.ban_chat_member(chat_id, target.id)
            warns[target.id] = 0 # Reset after ban
            msg = f"🚫 **Khatam!** {target.first_name} ko 3 warning ke baad uda diya."
        except:
            msg += "\n(Main isko ban nahi kar pa raha, shayad ye Admin hai)"

    await update.message.reply_text(msg)

async def shout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = " ".join(context.args).upper()
    if not msg:
        return await update.message.reply_text("Kya chilana hai? Likh to sahi!")
    await update.message.reply_text(f"📢 **{msg}**", parse_mode='Markdown')

# --- NUKE SYSTEM ---
async def nuke_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return
    
    # Show confirmation button
    keyboard = [
        [
            InlineKeyboardButton("✅ Haan, Uda Do", callback_data='nuke_yes'),
            InlineKeyboardButton("❌ Nahi Bhai Mazak Tha", callback_data='nuke_no'),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("💣 **Confirm Nuke?**\nKya sach mein chat clear karni hai?", reply_markup=reply_markup)

async def nuke_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == 'nuke_no':
        await query.edit_message_text("👍 **Bach gaye!** Nuke cancel kar diya.")
    
    elif query.data == 'nuke_yes':
        await query.edit_message_text("☢️ **Nuke Incoming...** Messages ud rahe hain.")
        chat_id = query.message.chat_id
        message_id = query.message.message_id
        
        # Delete last 100 messages (Telegram Limit mostly allows recent bulk delete)
        # Loop se delete karna safe hai simple bots ke liye
        deleted_count = 0
        try:
            for i in range(1, 50): # Deleting last 50 messages
                try:
                    await context.bot.delete_message(chat_id, message_id - i)
                    deleted_count += 1
                except:
                    pass
            await context.bot.send_message(chat_id, f"💥 **Boom!** {deleted_count} messages ki chatni bana di.")
        except Exception as e:
            await context.bot.send_message(chat_id, "Error: Kuch messages delete nahi huye.")

# --- ADMIN TOOLS ---

async def promote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): return
    if not update.message.reply_to_message: return await update.message.reply_text("Reply kar jisko promote karna hai.")

    user_id = update.message.reply_to_message.from_user.id
    try:
        await context.bot.promote_chat_member(
            update.effective_chat.id, user_id, 
            can_manage_chat=True, can_delete_messages=True, can_invite_users=True, can_pin_messages=True
        )
        await update.message.reply_text(f"🌟 **Mubarak Ho!** Ab ye banda VIP (Admin) ban gaya hai.")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

async def demote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): return
    if not update.message.reply_to_message: return
    
    user_id = update.message.reply_to_message.from_user.id
    try:
        await context.bot.promote_chat_member(
            update.effective_chat.id, user_id,
            can_manage_chat=False, can_delete_messages=False, can_invite_users=False
        )
        await update.message.reply_text(f"🤡 **Power Khatam!** Ab ye aam aadmi hai.")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

async def set_slow_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): return
    
    if not context.args: return await update.message.reply_text("Time (seconds) likh bhai.")
    seconds = int(context.args[0])
    try:
        await context.bot.set_chat_slow_mode_delay(update.effective_chat.id, seconds)
        await update.message.reply_text(f"🐢 **Slow Mode On!** Ab har {seconds}s baad message aayega.")
    except:
        await update.message.reply_text("❌ Error: Valid seconds daal (0, 10, 30, 60...).")

async def pin_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): return
    if not update.message.reply_to_message: return
    
    try:
        await update.message.reply_to_message.pin()
        await update.message.reply_text("📌 **Chipka Diya!** (Pinned)")
    except:
        await update.message.reply_text("❌ Pin nahi kar pa raha.")

async def unpin_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): return
    if not update.message.reply_to_message: return
    try:
        await update.message.reply_to_message.unpin()
        await update.message.reply_text("📌 **Ukhad Diya!** (Unpinned)")
    except:
        pass

# --- FUN & UTILS ---

async def afk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    reason = " ".join(context.args) if context.args else "Bas aise hi"
    afk_users[user.id] = reason
    await update.message.reply_text(f"💤 **{user.first_name}** abhi neend mein hai (AFK).\nReason: {reason}")

async def roll(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_dice(update.effective_chat.id)

async def bala(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Sends a GIF (Using a public Tenor URL for Bala/Dance)
    gif_url = "https://media1.tenor.com/m/C3eR0iU1tBIAAAAd/akshay-kumar-dance.gif"
    await context.bot.send_animation(update.effective_chat.id, gif_url, caption="🕺 **Shaitan ka Saala!**")

# --- AUTO REPLY SYSTEM ---

async def set_auto_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): return
    
    # Expected format: /setautoreply Hello | Namaste Bhai
    text = " ".join(context.args)
    if "|" not in text:
        return await update.message.reply_text("❌ Format galat hai.\nAise likh: `/setautoreply Hello | Namaste Bhai`")
    
    trigger, response = text.split("|", 1)
    auto_replies[trigger.strip().lower()] = response.strip()
    await update.message.reply_text(f"✅ **Saved!** Jab koi '{trigger.strip()}' bolega, main '{response.strip()}' bolunga.")

async def delete_auto_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): return
    
    trigger = " ".join(context.args).lower().strip()
    if trigger in auto_replies:
        del auto_replies[trigger]
        await update.message.reply_text("🗑️ **Deleted!** Ab reply nahi karunga us word pe.")
    else:
        await update.message.reply_text("❌ Ye word set hi nahi tha bhai.")

# --- MESSAGE HANDLER (AFK & Auto Reply) ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    
    user = update.effective_user
    text = update.message.text.lower()
    
    # 1. Check if Sender was AFK -> Remove AFK
    if user.id in afk_users:
        del afk_users[user.id]
        await update.message.reply_text(f"👋 **Welcome Back {user.first_name}!**\nNeend khul gayi?")

    # 2. Check if Mentioned User is AFK
    if update.message.reply_to_message:
        replied_user_id = update.message.reply_to_message.from_user.id
        if replied_user_id in afk_users:
            reason = afk_users[replied_user_id]
            await update.message.reply_text(f"🤫 **Shh!** Wo abhi AFK hai.\nReason: {reason}")
    
    # 3. Auto Reply Check
    for trigger, response in auto_replies.items():
        if trigger == text: # Exact match
            await update.message.reply_text(response)
            break

# --- MAIN ---
if __name__ == '__main__':
    keep_alive()
    
    if not TOKEN:
        print("❌ Error: Bot Token Missing hai!")
        exit()
        
    app = ApplicationBuilder().token(TOKEN).build()
    
    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("login", login))
    app.add_handler(CommandHandler("warn", warn_user))
    app.add_handler(CommandHandler("shout", shout))
    app.add_handler(CommandHandler("nuke", nuke_request))
    app.add_handler(CommandHandler("promote", promote))
    app.add_handler(CommandHandler("demote", demote))
    app.add_handler(CommandHandler("setslowmode", set_slow_mode))
    app.add_handler(CommandHandler("pin", pin_msg))
    app.add_handler(CommandHandler("unpin", unpin_msg))
    app.add_handler(CommandHandler("afk", afk))
    app.add_handler(CommandHandler("roll", roll))
    app.add_handler(CommandHandler("bala", bala))
    app.add_handler(CommandHandler("setautoreply", set_auto_reply))
    app.add_handler(CommandHandler("deleteautoreply", delete_auto_reply))

    # Callbacks & Messages
    app.add_handler(CallbackQueryHandler(nuke_callback))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    
    print("🚀 Bot is Running in Indian Mode...")
    app.run_polling()
