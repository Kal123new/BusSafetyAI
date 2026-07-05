import os
from telegram import Bot

# ===============================
# TELEGRAM CONFIG
# ===============================

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
bot = Bot(token=BOT_TOKEN)

def send_telegram(message):
    try:
        bot.send_message(chat_id=CHAT_ID, text=message)
        print("Telegram alert sent")
    except Exception as e:
        print("Telegram failed:", e)
