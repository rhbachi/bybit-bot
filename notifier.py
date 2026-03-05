import os
import requests

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


def send_telegram(message):

    if not BOT_TOKEN or not CHAT_ID:
        print("⚠️ Telegram not configured")
        return

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": CHAT_ID,
        "text": message
    }

    try:

        r = requests.post(url, json=payload, timeout=10)

        print(f"📩 Telegram status: {r.status_code}")

        if r.status_code != 200:
            print("Telegram error:", r.text)

    except Exception as e:

        print("Telegram send error:", e)