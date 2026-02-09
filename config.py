import os
import ccxt

print("⚙️ CONFIG IMPORT START", flush=True)

# =========================
# API
# =========================
API_KEY = os.getenv("BYBIT_API_KEY", "")
API_SECRET = os.getenv("BYBIT_API_SECRET", "")

print("🔑 API vars loaded", flush=True)

exchange = ccxt.bybit({
    "apiKey": API_KEY,
    "secret": API_SECRET,
    "enableRateLimit": True,
    "options": {
        "defaultType": "linear",
    },
})

print("🌍 Exchange object created", flush=True)

# ❌ COMMENTÉ TEMPORAIREMENT
# exchange.load_markets()

# =========================
# PARAMS SAFE
# =========================
SYMBOL = "ETH/USDT:USDT"
TIMEFRAME = "5m"

CAPITAL = float(os.getenv("CAPITAL", "30"))
RISK_PER_TRADE = float(os.getenv("RISK_PER_TRADE", "0.05"))
LEVERAGE = int(os.getenv("LEVERAGE", "2"))

print("⚙️ CONFIG IMPORT END", flush=True)
