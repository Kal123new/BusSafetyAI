from telegram import Bot

# ===============================
# TELEGRAM CONFIG
# ===============================
BOT_TOKEN = "8187151276:AAGHoM95Mu20ppF4vokSWYx0xgrKaJr_RC0"
CHAT_ID = 8510772668  # integer, no quotes

bot = Bot(token=BOT_TOKEN)

def send_telegram(message):
    try:
        bot.send_message(chat_id=CHAT_ID, text=message)
        print("Telegram alert sent")
    except Exception as e:
        print("Telegram failed:", e)
