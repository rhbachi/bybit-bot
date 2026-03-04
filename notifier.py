import os
import requests

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

print("📨 Telegram BOT TOKEN:", BOT_TOKEN)
print("📨 Telegram CHAT ID:", CHAT_ID)

def send_telegram(message):

    if not BOT_TOKEN or not CHAT_ID:
        print("❌ Telegram variables manquantes")
        return

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }

    try:

        r = requests.post(url, json=payload, timeout=10)

        print("📩 Telegram status:", r.status_code)

        if r.status_code != 200:
            print("❌ Telegram error:", r.text)

    except Exception as e:

        print("❌ Telegram exception:", e)