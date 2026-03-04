import os
import ccxt

print("⚙️ CONFIG START", flush=True)

# =========================
# API KEYS
# =========================
BYBIT_API_KEY = os.getenv("BYBIT_API_KEY", "")
BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET", "")

# =========================
# TRADING SETTINGS
# =========================
TIMEFRAME = os.getenv("TIMEFRAME", "5m")
SCORE_THRESHOLD = int(os.getenv("SCORE_THRESHOLD", "3"))
SYMBOL = os.getenv("SYMBOL", "ETH/USDT:USDT")

CAPITAL = float(os.getenv("CAPITAL", "200"))
RISK_PER_TRADE = float(os.getenv("RISK_PER_TRADE", "0.05"))
LEVERAGE = int(os.getenv("LEVERAGE", "2"))

# =========================
# MULTI SYMBOL SUPPORT
# =========================
symbols_env = os.getenv("SYMBOLS", "")

SYMBOLS = []

if symbols_env:
    SYMBOLS = [s.strip() for s in symbols_env.split(",") if s.strip()]
else:
    i = 0
    while True:
        key = f"SYMBOLS_{i}"
        value = os.getenv(key)
        if not value:
            break
        SYMBOLS.append(value.strip())
        i += 1

if not SYMBOLS:
    SYMBOLS = [SYMBOL]

print(f"📌 SYMBOLS ACTIVE: {SYMBOLS}", flush=True)

# =========================
# EXCHANGE
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

try:
    exchange.load_markets()
    print("📊 Markets loaded", flush=True)
except Exception as e:
    print("⚠️ Markets load error:", e, flush=True)

print("⚙️ CONFIG READY", flush=True)
