import os
import ccxt

# print("⚙️ CONFIG READY", flush=True)

# =========================
# API KEYS
# =========================
BYBIT_API_KEY = os.getenv("BYBIT_API_KEY", "")
BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET", "")

# ================= TELEGRAM =================

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# ================= RISK =================

MAX_POSITIONS = int(os.getenv("MAX_POSITIONS", "2"))
COOLDOWN_SECONDS = int(os.getenv("COOLDOWN_SECONDS", "300"))

# =========================
# ATR RISK MANAGEMENT
# =========================

SL_ATR_MULTIPLIER = float(os.getenv("SL_ATR_MULTIPLIER", "1.5"))
TP_ATR_MULTIPLIER = float(os.getenv("TP_ATR_MULTIPLIER", "3.0"))

# =========================
# TRADING SETTINGS
# =========================
TIMEFRAME = os.getenv("TIMEFRAME", "1m")
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
