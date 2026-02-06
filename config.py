import ccxt
import os
from dotenv import load_dotenv

load_dotenv()

exchange = ccxt.bybit({
    "apiKey": os.getenv("BYBIT_API_KEY"),
    "secret": os.getenv("BYBIT_API_SECRET"),
    "enableRateLimit": True,
    "options": {
        "defaultType": "linear"  # 🔥 USDT Perpetual (OBLIGATOIRE)
    }
})

# === BOT CONFIG ===
SYMBOL = "BTCUSDT"       # Linear Perpetual
TIMEFRAME = "5m"

CAPITAL = 15             # USDT (micro capital)
RISK_PER_TRADE = 0.05    # 5%
LEVERAGE = 2
