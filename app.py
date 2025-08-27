import requests
import json
import asyncio
import os
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

BOT_TOKEN = os.getenv("BOT_TOKEN")
WATCHLIST_FILE = "watchlist.json"
CHECK_INTERVAL = 20 * 60  # seconds (20 minutes)

# Load or initialize watchlists (per chat)
try:
    with open(WATCHLIST_FILE, "r") as f:
        watchlists = json.load(f)  # { chat_id: [usernames] }
except FileNotFoundError:
    watchlists = {}

# Save watchlist
def save_watchlists():
    with open(WATCHLIST_FILE, "w") as f:
        json.dump(watchlists, f)

# Track last known statuses { chat_id: { username: status } }
last_statuses = {}

# Check Instagram account status
def check_account_status(username):
    profile_url = f"https://www.instagram.com/{username}/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept-Language": "en-US,en;q=0.9"
    }

    try:
        r = requests.get(profile_url, headers=headers, timeout=10)
        page_text = r.text.lower()

        if r.status_code == 404:
            return "BANNED / NOT FOUND"

        unavailable_phrases = [
            "sorry, this page isn't available",
            "the link you followed may be broken",
            "page may have been removed",
            "page isn&#39;t available"
        ]
        if any(phrase in page_text for phrase in unavailable_phrases):
            return "BANNED / SUSPENDED"

        if 'og:title' not in page_text and 'profilepage_' not in page_text:
            return "BANNED / SUSPENDED"

        return "ACTIVE"

    except Exception as e:
        return f"ERROR: {e}"

# Telegram commands
async def add_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if not context.args:
        await update.message.reply_text("Usage: /add username")
        return
    username = context.args[0].lower()

    if chat_id not in watchlists:
        watchlists[chat_id] = []

    if username not in watchlists[chat_id]:
        watchlists[chat_id].append(username)
        save_watchlists()
        await update.message.reply_text(f"✅ Added {username} to your watchlist.")
    else:
        await update.message.reply_text(f"{username} is already in your watchlist.")

async def remove_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if not context.args:
        await update.message.reply_text("Usage: /remove username")
        return
    username = context.args[0].lower()

    if chat_id in watchlists and username in watchlists[chat_id]:
        watchlists[chat_id].remove(username)
        save_watchlists()
        await update.message.reply_text(f"❌ Removed {username} from your watchlist.")
    else:
        await update.message.reply_text(f"{username} not found in your watchlist.")

async def list_accounts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if chat_id not in watchlists or not watchlists[chat_id]:
        await update.message.reply_text("📭 Your watchlist is empty.")
    else:
        await update.message.reply_text("📌 Your watchlist:\n" + "\n".join(watchlists[chat_id]))

async def check_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /check username")
        return
    username = context.args[0].lower()
    status = check_account_status(username)
    await update.message.reply_text(f"🔎 {username} → {status}")

# Background monitoring loop
async def monitor_loop(application):
    global last_statuses
    while True:
        for chat_id, usernames in watchlists.items():
            if chat_id not in last_statuses:
                last_statuses[chat_id] = {}

            for username in usernames:
                status = check_account_status(username)
                last_status = last_statuses[chat_id].get(username)

                if last_status is None:
                    last_statuses[chat_id][username] = status
                elif last_status != status:
                    last_statuses[chat_id][username] = status
                    await application.bot.send_message(
                        chat_id=int(chat_id),
                        text=f"⚠ ALERT: {username} changed status → {status}"
                    )
        await asyncio.sleep(CHECK_INTERVAL)

# Post init hook to start monitoring in background
async def on_startup(app):
    asyncio.create_task(monitor_loop(app))

# Main
app = ApplicationBuilder().token(BOT_TOKEN).post_init(on_startup).build()

app.add_handler(CommandHandler("add", add_account))
app.add_handler(CommandHandler("remove", remove_account))
app.add_handler(CommandHandler("list", list_accounts))
app.add_handler(CommandHandler("check", check_account))

if __name__ == "__main__":
    app.run_polling()
