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

# ---- MULTI SYMBOL (CSV via ENV) ----
symbols_env = os.getenv("SYMBOLS", "")
if symbols_env:
    SYMBOLS = [s.strip() for s in symbols_env.split(",")]
else:
    # fallback automatique
    SYMBOLS = [SYMBOL]

CAPITAL = float(os.getenv("CAPITAL", "30"))
RISK_PER_TRADE = float(os.getenv("RISK_PER_TRADE", "0.05"))
LEVERAGE = int(os.getenv("LEVERAGE", "2"))

print("🔑 ENV loaded", flush=True)
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