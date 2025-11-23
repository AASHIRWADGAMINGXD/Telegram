import logging
import http.client
import json
import asyncio
import os
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
from keep_alive import keep_alive

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# --- Configuration ---
# REPLACE 'YOUR_TELEGRAM_BOT_TOKEN' with the token from @BotFather
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")

# Your RapidAPI Key
RAPID_API_KEY = os.environ.get("RAPID_API_KEY", "fc841d3a88msh005d875d98f2e62p186a2ejsn8a7a33ad1274")

def get_llama_response(user_text):
    """
    Synchronous function to call the Llama API using http.client.
    """
    try:
        conn = http.client.HTTPSConnection("open-ai21.p.rapidapi.com")
        
        # safely escape the user text for JSON
        payload_dict = {
            "messages": [{"role": "user", "content": user_text}],
            "web_access": False
        }
        payload = json.dumps(payload_dict)

        headers = {
            'x-rapidapi-key': RAPID_API_KEY,
            'x-rapidapi-host': "open-ai21.p.rapidapi.com",
            'Content-Type': "application/json"
        }

        conn.request("POST", "/conversationllama", payload, headers)

        res = conn.getresponse()
        data = res.read()
        
        # Decode and parse response
        decoded_data = data.decode("utf-8")
        json_data = json.loads(decoded_data)
        
        # Adjust this key based on the exact API response structure.
        # usually it is 'result' or inside 'choices' for Llama APIs on RapidAPI.
        # Based on common RapidAPI patterns, we return the whole text or specific field:
        return json_data.get('result', decoded_data)

    except Exception as e:
        logging.error(f"API Error: {e}")
        return "Sorry, I couldn't process that request."

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hello! I am your AI Moderator powered by Llama. Send me a message!")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    
    # Notify user the bot is "typing"
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
    
    # Run the synchronous http.client code in a separate thread to avoid blocking
    loop = asyncio.get_running_loop()
    response_text = await loop.run_in_executor(None, get_llama_response, user_text)
    
    await update.message.reply_text(response_text)

if __name__ == '__main__':
    # 1. Start the keep_alive server (Flask)
    keep_alive()
    
    # 2. Start the Telegram Bot
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    start_handler = CommandHandler('start', start)
    echo_handler = MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message)
    
    application.add_handler(start_handler)
    application.add_handler(echo_handler)
    
    print("Bot is running...")
    application.run_polling()
