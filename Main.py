#!/usr/bin/env python3
"""
Telegram image generator bot with simple password privacy.
Requires two environment variables:
  BOT_TOKEN  -> Telegram bot token
  VEO2_API   -> API key or endpoint token for your VEO2 image service

Usage on Render:
- Add BOT_TOKEN and VEO2_API to environment.
- Start the service with: python bot.py
"""
import imghdr          # FIXED: imghdr-pure installs this module
import os
import json
import logging
import hashlib
import secrets
import base64
import requests
from pathlib import Path
from functools import wraps
from telegram import Update, InputFile
from telegram.ext import (
    Updater,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackContext,
)
from io import BytesIO

# === Configuration ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
VEO2_API = os.getenv("VEO2_API")
DATA_FILE = Path("data.json")
DEFAULT_SALT_KEY = "salt"

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# === Data persistence helpers ===
def load_data():
    if not DATA_FILE.exists():
        return {}
    try:
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    except Exception:
        logger.exception("Failed to read data file")
        return {}

def save_data(d):
    with open(DATA_FILE, "w") as f:
        json.dump(d, f, indent=2)

data = load_data()
if DEFAULT_SALT_KEY not in data:
    data[DEFAULT_SALT_KEY] = secrets.token_hex(16)
    save_data(data)

def hash_password(password: str) -> str:
    salt = data.get(DEFAULT_SALT_KEY, "")
    return hashlib.sha256((password + salt).encode()).hexdigest()

def set_owner(owner_id: int, password: str):
    data["owner_id"] = owner_id
    data["password_hash"] = hash_password(password)
    data.setdefault("allowed", [])
    if owner_id not in data["allowed"]:
        data["allowed"].append(owner_id)
    save_data(data)

def change_password(new_password: str):
    data["password_hash"] = hash_password(new_password)
    save_data(data)

def check_password(password: str) -> bool:
    stored = data.get("password_hash")
    return stored and hash_password(password) == stored

def add_allowed(user_id: int):
    data.setdefault("allowed", [])
    if user_id not in data["allowed"]:
        data["allowed"].append(user_id)
        save_data(data)

def is_allowed(user_id: int) -> bool:
    return user_id in data.get("allowed", [])

def owner_only(func):
    @wraps(func)
    def wrapper(update: Update, context: CallbackContext):
        if data.get("owner_id") != update.effective_user.id:
            update.message.reply_text("Only the owner can run this command.")
            return
        return func(update, context)
    return wrapper

# === VEO2 image request logic ===
def call_veo2_api(prompt: str) -> dict:
    headers = {}
    payload = {"prompt": prompt}
    try:
        if not VEO2_API:
            raise RuntimeError("VEO2_API is not configured.")
        if VEO2_API.lower().startswith("http"):
            resp = requests.post(VEO2_API, json=payload, timeout=60)
        else:
            default_endpoint = "https://api.veo.example/v2/generate"
            headers["Authorization"] = f"Bearer {VEO2_API}"
            resp = requests.post(default_endpoint, json=payload, headers=headers, timeout=60)

        resp.raise_for_status()
        j = resp.json()
    except Exception:
        logger.exception("VEO2 API call failed")
        raise

    if "image" in j:
        try:
            return {"image_bytes": base64.b64decode(j["image"])}
        except:
            pass
    if "image_base64" in j:
        return {"image_bytes": base64.b64decode(j["image_base64"])}
    if "url" in j:
        return {"image_url": j["url"]}
    if "images" in j and j["images"]:
        first = j["images"][0]
        if first.startswith("data:"):
            img = first.split(",", 1)[1]
            return {"image_bytes": base64.b64decode(img)}
        return {"image_url": first}

    return {"raw": j}

# === Bot commands ===
def start_handler(update: Update, context: CallbackContext):
    update.message.reply_text(
        "Hello. This is a private image bot.\n\n"
        "/setpass <password> — set password and become owner\n"
        "/changepass <newpass> — change password\n"
        "/register <password> — register yourself\n"
        "/generate <prompt> — generate an image\n"
        "/status — show registration status"
    )

def status_handler(update: Update, context: CallbackContext):
    owner = data.get("owner_id")
    allowed = data.get("allowed", [])
    you = update.effective_user.id
    update.message.reply_text(
        f"Owner: {owner or 'Not set'}\n"
        f"Registered users: {len(allowed)}\n"
        f"You registered: {'Yes' if you in allowed else 'No'}"
    )

def setpass_handler(update: Update, context: CallbackContext):
    if "owner_id" in data:
        update.message.reply_text("Password already set.")
        return
    if not context.args:
        update.message.reply_text("Usage: /setpass <password>")
        return
    pw = " ".join(context.args)
    set_owner(update.effective_user.id, pw)
    update.message.reply_text("Password set. You are now owner.")

@owner_only
def changepass_handler(update: Update, context: CallbackContext):
    if not context.args:
        update.message.reply_text("Usage: /changepass <password>")
        return
    pw = " ".join(context.args)
    change_password(pw)
    update.message.reply_text("Password changed.")

def register_handler(update: Update, context: CallbackContext):
    if "password_hash" not in data:
        update.message.reply_text("Owner must set password first.")
        return
    if not context.args:
        update.message.reply_text("Usage: /register <password>")
        return
    pw = " ".join(context.args)
    if check_password(pw):
        add_allowed(update.effective_user.id)
        update.message.reply_text("Registered. You can use /generate.")
    else:
        update.message.reply_text("Incorrect password.")

def generate_handler(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    if not is_allowed(uid):
        update.message.reply_text("You are not registered.")
        return
    if not context.args:
        update.message.reply_text("Usage: /generate <prompt>")
        return
    prompt = " ".join(context.args)
    msg = update.message.reply_text("Generating...")

    try:
        result = call_veo2_api(prompt)
    except Exception as e:
        msg.edit_text(f"Error: {e}")
        return

    if result.get("image_bytes"):
        bio = BytesIO(result["image_bytes"])
        bio.name = "image.png"
        update.message.reply_photo(photo=InputFile(bio), caption="Done.")
        msg.delete()
        return

    if result.get("image_url"):
        update.message.reply_photo(photo=result["image_url"], caption="Done.")
        msg.delete()
        return

    msg.edit_text("Unknown response from API.")

def unknown_handler(update: Update, context: CallbackContext):
    update.message.reply_text("Unknown command. Use /start.")

# === Main ===
def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN is missing.")
        return

    updater = Updater(BOT_TOKEN)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start_handler))
    dp.add_handler(CommandHandler("status", status_handler))
    dp.add_handler(CommandHandler("setpass", setpass_handler))
    dp.add_handler(CommandHandler("changepass", changepass_handler))
    dp.add_handler(CommandHandler("register", register_handler))
    dp.add_handler(CommandHandler("generate", generate_handler))

    dp.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unknown_handler))

    logger.info("Bot running...")
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
