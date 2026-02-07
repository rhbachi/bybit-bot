import os
import ccxt
from dotenv import load_dotenv

# =========================
# LOAD ENV
# =========================
load_dotenv()

# =========================
# API BYBIT
# =========================
exchange = ccxt.bybit({
    "apiKey": os.getenv("BYBIT_API_KEY"),
    "secret": os.getenv("BYBIT_API_SECRET"),
    "enableRateLimit": True,
    "options": {
        "defaultType": "linear",   # Futures USDT Perpetual
    },
})

# Charger les marchés
exchange.load_markets()

# =========================
# PAIRE À TRADER (VIA COOLIFY)
# =========================
# Exemple dans Coolify :
# TRADE_SYMBOL=ETH/USDT:USDT
# TRADE_SYMBOL=SOL/USDT:USDT
# TRADE_SYMBOL=BTC/USDT:USDT

SYMBOL = os.getenv("TRADE_SYMBOL", "ETH/USDT:USDT")

# =========================
# PARAMÈTRES GÉNÉRAUX
# =========================
TIMEFRAME = os.getenv("TIMEFRAME", "5m")

# Capital de référence (sert uniquement au calcul du risque théorique)
CAPITAL = float(os.getenv("CAPITAL", "30"))

# Risque par trade (ex: 0.05 = 5%)
RISK_PER_TRADE = float(os.getenv("RISK_PER_TRADE", "0.05"))

# Levier
LEVERAGE = int(os.getenv("LEVERAGE", "2"))
