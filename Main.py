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
import imghdr_pure as imghdr
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

# === Configuration ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
VEO2_API = os.getenv("VEO2_API")  # could be a key or full endpoint depending on provider
DATA_FILE = Path("data.json")
# salt for hashing - random per-deploy; stored in file for repeatable hashes
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
# ensure salt exists
if DEFAULT_SALT_KEY not in data:
    data[DEFAULT_SALT_KEY] = secrets.token_hex(16)
    save_data(data)

def hash_password(password: str) -> str:
    """Return hex digest of password with per-repo salt."""
    salt = data.get(DEFAULT_SALT_KEY, "")
    h = hashlib.sha256((password + salt).encode("utf-8")).hexdigest()
    return h

def set_owner(owner_id: int, password: str):
    data["owner_id"] = owner_id
    data["password_hash"] = hash_password(password)
    data.setdefault("allowed", [])
    # owner should be allowed
    if owner_id not in data["allowed"]:
        data["allowed"].append(owner_id)
    save_data(data)

def change_password(new_password: str):
    data["password_hash"] = hash_password(new_password)
    save_data(data)

def check_password(password: str) -> bool:
    stored = data.get("password_hash")
    if not stored:
        return False
    return hash_password(password) == stored

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
        user_id = update.effective_user.id
        if data.get("owner_id") != user_id:
            update.message.reply_text("Only the owner can run this command.")
            return
        return func(update, context)
    return wrapper

# === VEO2 image request logic ===
def call_veo2_api(prompt: str) -> dict:
    """
    Generic call to VEO2 API.
    This function tries two common patterns:
     - POST to VEO2_API (if VEO2_API looks like a URL) with JSON {"prompt": ...}
     - POST to a fixed endpoint using the VEO2_API as an API key: header Authorization: Bearer <VEO2_API>
    The actual VEO2 provider may require tweaks. Adjust as necessary.
    Returns a dict with keys:
      - 'image_bytes' (bytes) OR 'image_url' (str)
    """
    headers = {}
    payload = {"prompt": prompt}
    try:
        if VEO2_API is None:
            raise RuntimeError("VEO2_API is not configured.")
        # Decide if VEO2_API looks like a URL
        if VEO2_API.lower().startswith("http://") or VEO2_API.lower().startswith("https://"):
            # treat VEO2_API as a full endpoint
            endpoint = VEO2_API
            resp = requests.post(endpoint, json=payload, timeout=60)
        else:
            # treat VEO2_API as an API key for a default endpoint
            # Replace below default endpoint with provider's if you know it.
            default_endpoint = "https://api.veo.example/v2/generate"  # placeholder
            headers["Authorization"] = f"Bearer {VEO2_API}"
            resp = requests.post(default_endpoint, json=payload, headers=headers, timeout=60)

        resp.raise_for_status()
        j = resp.json()
    except Exception as e:
        # Try to treat VEO2_API as an endpoint and fallback to a simplified POST (no JSON)
        logger.exception("VEO2 API call failed")
        raise

    # Normalized response handling:
    # Common patterns:
    #  1) { "image": "<base64string>" }
    #  2) { "image_base64": "..." }
    #  3) { "url": "https://..." }
    #  4) { "images": ["https://..."] }
    if isinstance(j, dict):
        if "image" in j and isinstance(j["image"], str):
            try:
                img_bytes = base64.b64decode(j["image"])
                return {"image_bytes": img_bytes}
            except Exception:
                pass
        if "image_base64" in j and isinstance(j["image_base64"], str):
            img_bytes = base64.b64decode(j["image_base64"])
            return {"image_bytes": img_bytes}
        if "url" in j and isinstance(j["url"], str):
            return {"image_url": j["url"]}
        if "images" in j and isinstance(j["images"], list) and j["images"]:
            first = j["images"][0]
            # if it's base64:
            if isinstance(first, str) and first.startswith("data:"):
                # data URI
                comma = first.find(",")
                payload = first[comma+1:]
                img_bytes = base64.b64decode(payload)
                return {"image_bytes": img_bytes}
            else:
                return {"image_url": first}
    # If unknown format, return the full json for debug
    return {"raw": j}

# === Bot command handlers ===
def start_handler(update: Update, context: CallbackContext):
    user = update.effective_user
    txt = (
        "Hello. This is a private image-generation bot.\n\n"
        "If password not set, the first person to run /setpass <password> will become the owner.\n\n"
        "Commands:\n"
        "/setpass <password> - set password and become owner (only if not set)\n"
        "/changepass <newpassword> - change password (owner only)\n"
        "/register <password> - register yourself to use the bot\n"
        "/generate <prompt> - generate an image (registered users only)\n"
        "/status - show owner and registration status\n"
    )
    update.message.reply_text(txt)

def status_handler(update: Update, context: CallbackContext):
    owner = data.get("owner_id")
    owner_line = f"{owner}" if owner else "No owner set"
    allowed = data.get("allowed", [])
    you_allowed = "Yes" if update.effective_user.id in allowed else "No"
    update.message.reply_text(
        f"Owner: {owner_line}\nRegistered users: {len(allowed)}\nYou registered: {you_allowed}"
    )

def setpass_handler(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    args = context.args
    if not args:
        update.message.reply_text("Usage: /setpass <password>")
        return
    password = " ".join(args).strip()
    if "owner_id" in data:
        update.message.reply_text("Password already set. Owner already exists.")
        return
    set_owner(user_id, password)
    update.message.reply_text("Password set. You are now owner and registered.")

@owner_only
def changepass_handler(update: Update, context: CallbackContext):
    args = context.args
    if not args:
        update.message.reply_text("Usage: /changepass <newpassword>")
        return
    newpass = " ".join(args).strip()
    change_password(newpass)
    update.message.reply_text("Password changed successfully.")

def register_handler(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    args = context.args
    if "password_hash" not in data:
        update.message.reply_text("No password configured yet. Owner must set one with /setpass.")
        return
    if not args:
        update.message.reply_text("Usage: /register <password>")
        return
    password = " ".join(args).strip()
    if check_password(password):
        add_allowed(user_id)
        update.message.reply_text("Registration successful. You can now use /generate.")
    else:
        update.message.reply_text("Incorrect password.")

def generate_handler(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if not is_allowed(user_id):
        update.message.reply_text("You are not registered. Use /register <password> to register.")
        return
    args = context.args
    if not args:
        update.message.reply_text("Usage: /generate <prompt>\nOr reply to the bot with /generate while including your prompt.")
        return
    prompt = " ".join(args).strip()
    message = update.message.reply_text("Generating image... please wait.")
    try:
        result = call_veo2_api(prompt)
    except Exception as e:
        logger.exception("Generation failed")
        message.edit_text(f"Image generation failed: {e}")
        return

    # send image depending on result
    if result.get("image_bytes"):
        bio = BytesIO(result["image_bytes"])
        bio.name = "image.png"
        bio.seek(0)
        update.message.reply_photo(photo=InputFile(bio), caption="Here is your image.")
        message.delete()
        return
    if result.get("image_url"):
        url = result["image_url"]
        update.message.reply_photo(photo=url, caption="Here is your image.")
        message.delete()
        return

    # fallback: show raw JSON
    message.edit_text(f"Received unexpected response: {json.dumps(result)[:800]}")

# small helper for BytesIO
from io import BytesIO

def unknown_handler(update: Update, context: CallbackContext):
    update.message.reply_text("Unknown command. Use /start to see usage.")

# === Main ===
def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN is not set. Exiting.")
        return
    updater = Updater(token=BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start_handler))
    dp.add_handler(CommandHandler("status", status_handler))
    dp.add_handler(CommandHandler("setpass", setpass_handler))
    dp.add_handler(CommandHandler("changepass", changepass_handler))
    dp.add_handler(CommandHandler("register", register_handler))
    dp.add_handler(CommandHandler("generate", generate_handler))

    dp.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), unknown_handler))

    logger.info("Starting bot. Press Ctrl+C to stop.")
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
