import os
import ccxt

print("⚙️ CONFIG START", flush=True)

# =========================
# ENV VARS SAFE
# =========================
BYBIT_API_KEY = os.getenv("BYBIT_API_KEY", "")
BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET", "")

TIMEFRAME = os.getenv("TIMEFRAME", "5m")
SYMBOL = os.getenv("SYMBOL", "ETH/USDT:USDT")

CAPITAL = float(os.getenv("CAPITAL", "30"))
RISK_PER_TRADE = float(os.getenv("RISK_PER_TRADE", "0.05"))
LEVERAGE = int(os.getenv("LEVERAGE", "2"))

print("🔑 ENV loaded", flush=True)

# =========================
# EXCHANGE (SAFE INIT)
# =========================
exchange = ccxt.bybit({
    "apiKey": BYBIT_API_KEY,
    "secret": BYBIT_API_SECRET,
    "enableRateLimit": True,
    "options": {
        "defaultType": "linear",
        "adjustForTimeDifference": True,
    },
})

print("🌍 Exchange created", flush=True)

# =========================
# OPTIONAL: load markets (SAFE)
# =========================
try:
    exchange.load_markets()
    print("📊 Markets loaded", flush=True)
except Exception as e:
    print("⚠️ Markets NOT loaded (will retry later):", e, flush=True)

print("⚙️ CONFIG READY", flush=True)
