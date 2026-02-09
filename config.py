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
        "defaultType": "linear",   # USDT Perpetual Futures
        "adjustForTimeDifference": True,
    },
})

# Charger les marchés
exchange.load_markets()

# =========================
# PAIRS À TRADER (MULTI-PAIRES)
# =========================
# Dans Coolify ou .env :
# SYMBOLS=BTC/USDT:USDT,ETH/USDT:USDT,SOL/USDT:USDT

symbols_env = os.getenv("SYMBOLS", "ETH/USDT:USDT")

SYMBOLS = [s.strip() for s in symbols_env.split(",") if s.strip()]

# Compatibilité ancienne version (si encore utilisée)
SYMBOL = SYMBOLS[0]

# =========================
# PARAMÈTRES GÉNÉRAUX
# =========================
TIMEFRAME = os.getenv("TIMEFRAME", "5m")

# Capital de référence (sert uniquement au calcul du risque théorique)
# ⚠️ Le vrai garde-fou est le wallet Futures réel
CAPITAL = float(os.getenv("CAPITAL", "30"))

# Risque par trade (ex: 0.05 = 5%)
RISK_PER_TRADE = float(os.getenv("RISK_PER_TRADE", "0.05"))

# Levier Futures
LEVERAGE = int(os.getenv("LEVERAGE", "2"))

# =========================
# LOG DE DÉMARRAGE (OPTIONNEL)
# =========================
print("⚙️ CONFIG LOADED")
print("Pairs:", SYMBOLS)
print("Timeframe:", TIMEFRAME)
print("Capital ref:", CAPITAL)
print("Risk per trade:", RISK_PER_TRADE)
print("Leverage:", LEVERAGE)
