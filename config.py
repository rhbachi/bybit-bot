import os
import ccxt

print("⚙️ CONFIG START", flush=True)

# =========================
# ENV VARS SAFE
# =========================
BYBIT_API_KEY = os.getenv("BYBIT_API_KEY", "")
BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET", "")

TIMEFRAME = os.getenv("TIMEFRAME", "5m")

# ---- SINGLE SYMBOL ----
SYMBOL = os.getenv("SYMBOL", "ETH/USDT:USDT")

# ---- MULTI SYMBOL SUPPORT ----

# Option 1: SYMBOLS="BTC/USDT:USDT,ETH/USDT:USDT"
symbols_env = os.getenv("SYMBOLS", "")

SYMBOLS = []

if symbols_env:
    SYMBOLS = [s.strip() for s in symbols_env.split(",") if s.strip()]
else:
    # Option 2: SYMBOLS_0, SYMBOLS_1, SYMBOLS_2 ...
    i = 0
    while True:
        key = f"SYMBOLS_{i}"
        value = os.getenv(key)
        if not value:
            break
        SYMBOLS.append(value.strip())
        i += 1

# Fallback
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

# =========================
# LOAD MARKETS
# =========================
try:
    exchange.load_markets()
    print("📊 Markets loaded", flush=True)
except Exception as e:
    print("⚠️ Markets NOT loaded:", e, flush=True)

print("⚙️ CONFIG READY", flush=True)