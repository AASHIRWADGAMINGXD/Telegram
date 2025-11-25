import logging
from telegram import (
    Update, ChatPermissions, InlineKeyboardButton,
    InlineKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler,
    MessageHandler, CallbackQueryHandler, ContextTypes,
    filters
)

logging.basicConfig(level=logging.INFO)

TOKEN = "8578532543:AAE-r1vXUkNPVmIIDuMRz1oFhAg9GY0UQH4"

AFK_USERS = {}  # {user_id: reason}


# ---------------------------
# Auto AFK detection
# ---------------------------
async def message_detector(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id in AFK_USERS:
        del AFK_USERS[user_id]
        await update.message.reply_text(f"{update.effective_user.first_name} is back.")


# ---------------------------
# /afk
# ---------------------------
async def afk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    reason = " ".join(context.args) if context.args else "Away"

    AFK_USERS[user.id] = reason
    await update.message.reply_text(f"{user.first_name} is AFK. Reason: {reason}")


# ---------------------------
# Helper: Get admin list
# ---------------------------
async def admin_ids(update):
    admins = await update.effective_chat.get_administrators()
    return [a.user.id for a in admins]


# ---------------------------
# /clear
# ---------------------------
async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in await admin_ids(update):
        return

    chat = update.effective_chat
    async for msg in context.bot.get_chat_history(chat.id, limit=200):
        try:
            await context.bot.delete_message(chat.id, msg.message_id)
        except:
            pass

    await update.message.reply_text("Chat cleared.")


# ---------------------------
# MUTE USER
# ---------------------------
async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in await admin_ids(update):
        return

    if not update.message.reply_to_message:
        return await update.message.reply_text("Reply to a message to mute.")

    target = update.message.reply_to_message.from_user.id

    await context.bot.restrict_chat_member(
        update.effective_chat.id,
        target,
        ChatPermissions(can_send_messages=False)
    )
    await update.message.reply_text("User muted.")


# ---------------------------
# UNMUTE
# ---------------------------
async def unmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in await admin_ids(update):
        return

    if not update.message.reply_to_message:
        return await update.message.reply_text("Reply to unmute.")

    target = update.message.reply_to_message.from_user.id

    await context.bot.restrict_chat_member(
        update.effective_chat.id,
        target,
        ChatPermissions(can_send_messages=True)
    )

    await update.message.reply_text("User unmuted.")


# ---------------------------
# PROMOTE
# ---------------------------
async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in await admin_ids(update):
        return

    if not update.message.reply_to_message:
        return await update.message.reply_text("Reply to promote user.")

    target = update.message.reply_to_message.from_user.id

    await context.bot.promote_chat_member(
        update.effective_chat.id,
        target,
        can_delete_messages=True,
        can_manage_chat=True,
        can_restrict_members=True
    )
    await update.message.reply_text("User promoted to admin.")


# ---------------------------
# DEMOTE
# ---------------------------
async def demote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in await admin_ids(update):
        return

    if not update.message.reply_to_message:
        return await update.message.reply_text("Reply to demote user.")

    target = update.message.reply_to_message.from_user.id

    await context.bot.promote_chat_member(
        update.effective_chat.id,
        target,
        can_delete_messages=False,
        can_manage_chat=False,
        can_restrict_members=False
    )
    await update.message.reply_text("User demoted.")


# ---------------------------
# BALA GIF
# ---------------------------
async def bala(update: Update, context: ContextTypes.DEFAULT_TYPE):
    gif = "https://media.tenor.com/kacrQ4PzNl4AAAAM/bala.gif"
    await update.message.reply_animation(gif)


# ---------------------------
# AI Ask (mock)
# ---------------------------
async def ask(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = " ".join(context.args)
    if not text:
        return await update.message.reply_text("Write: /ask something")

    await update.message.reply_text(f"AI: {text}")


# ---------------------------
# ADMIN PANEL (INLINE BUTTONS)
# ---------------------------
async def panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in await admin_ids(update):
        return

    keyboard = [
        [InlineKeyboardButton("Clear Chat", callback_data="panel_clear")],
        [
            InlineKeyboardButton("Mute", callback_data="panel_mute"),
            InlineKeyboardButton("Unmute", callback_data="panel_unmute")
        ],
        [
            InlineKeyboardButton("Promote", callback_data="panel_promote"),
            InlineKeyboardButton("Demote", callback_data="panel_demote")
        ]
    ]

    await update.message.reply_text(
        "Admin panel:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ---------------------------
# PANEL HANDLER
# ---------------------------
async def panel_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    chat = query.message.chat

    try:
        msg = (await context.bot.get_chat_history(chat.id, limit=2))[1]
        target = msg.from_user.id
    except:
        return await query.edit_message_text("Action failed. Reply to a user first.")

    if query.data == "panel_clear":
        async for m in context.bot.get_chat_history(chat.id, limit=200):
            try:
                await context.bot.delete_message(chat.id, m.message_id)
            except:
                pass
        return await query.edit_message_text("Chat cleared.")

    if query.data == "panel_mute":
        await context.bot.restrict_chat_member(
            chat.id,
            target,
            ChatPermissions(can_send_messages=False)
        )
        return await query.edit_message_text("User muted.")

    if query.data == "panel_unmute":
        await context.bot.restrict_chat_member(
            chat.id,
            target,
            ChatPermissions(can_send_messages=True)
        )
        return await query.edit_message_text("User unmuted.")

    if query.data == "panel_promote":
        await context.bot.promote_chat_member(
            chat.id,
            target,
            can_delete_messages=True,
            can_manage_chat=True,
            can_restrict_members=True
        )
        return await query.edit_message_text("User promoted.")

    if query.data == "panel_demote":
        await context.bot.promote_chat_member(
            chat.id,
            target,
            can_delete_messages=False,
            can_manage_chat=False,
            can_restrict_members=False
        )
        return await query.edit_message_text("User demoted.")


# ---------------------------
# MAIN
# ---------------------------
async def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_detector))

    app.add_handler(CommandHandler("afk", afk))
    app.add_handler(CommandHandler("clear", clear))
    app.add_handler(CommandHandler("mute", mute))
    app.add_handler(CommandHandler("unmute", unmute))
    app.add_handler(CommandHandler("admin", admin))
    app.add_handler(CommandHandler("demote", demote))
    app.add_handler(CommandHandler("bala", bala))
    app.add_handler(CommandHandler("ask", ask))
    app.add_handler(CommandHandler("panel", panel))

    app.add_handler(CallbackQueryHandler(panel_buttons))

    print("Bot running...")
    await app.run_polling()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
