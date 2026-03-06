import time
import threading
import pandas as pd
import math
import os
from datetime import datetime

from config import *
from flask import Flask, jsonify
from notifier import send_telegram
from strategy_v6 import apply_indicators, check_signal
from logger_enhanced import get_logger

# ================= CONFIGURATION =================
BOT_NAME = "MULTI_SYMBOL_V6_3"
logger = get_logger(BOT_NAME)
signals_cache = []

app = Flask(__name__)

last_trade_time = {}

# ================= API =================

@app.route("/api/signals")
def signals():
    """Endpoint pour le dashboard"""
    return jsonify(signals_cache[-50:])

@app.route("/api/status")
def status():
    """État du bot"""
    return jsonify({
        "bot": BOT_NAME,
        "symbols": SYMBOLS,
        "threshold": SCORE_THRESHOLD,
        "capital": CAPITAL,
        "leverage": LEVERAGE
    })

def start_api():
    print(f"🌐 {BOT_NAME} API server started on port 5001")
    try:
        app.run(host="0.0.0.0", port=5001)
    except Exception as e:
        logger.log_error("API server error", e)

# ================= FETCH DATA =================

def fetch_data(symbol):
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, TIMEFRAME, limit=200)
        df = pd.DataFrame(
            ohlcv,
            columns=["time", "open", "high", "low", "close", "volume"]
        )
        return df
    except Exception as e:
        logger.log_error(f"Fetch data error {symbol}", e)
        return pd.DataFrame()

# ================= POSITION SIZE =================

def calculate_position_size(price, atr):
    if atr == 0:
        return None
        
    risk_amount = CAPITAL * RISK_PER_TRADE
    stop_distance = atr * SL_ATR_MULTIPLIER
    
    qty = (risk_amount / stop_distance) * LEVERAGE
    
    # Sécurité : Max 25% du capital par position
    max_position_value = CAPITAL * LEVERAGE * 0.25
    max_qty = max_position_value / price
    
    if qty > max_qty:
        qty = max_qty
        
    return qty

# ================= PRECISION FIX =================

def adjust_qty(symbol, qty, price):
    try:
        market = exchange.market(symbol)
        min_amount = market["limits"]["amount"]["min"]
        precision = market["precision"]["amount"]

        if isinstance(precision, float):
            precision = abs(int(round(-math.log10(precision))))

        qty = round(qty, precision)

        if qty < min_amount:
            return None

        # Bybit : minimum order value 5 USDT
        if qty * price < 5:
            return None

        return qty

    except Exception as e:
        logger.log_error(f"Precision error {symbol}", e)
        return None

# ================= COOLDOWN =================

def cooldown_ok(symbol):
    if symbol not in last_trade_time:
        return True
    elapsed = time.time() - last_trade_time[symbol]
    return elapsed > COOLDOWN_SECONDS

def set_trailing_stop(symbol, distance):
    """Active le trailing stop via un appel API séparé (Bybit V5)"""
    try:
        # Attendre un court instant que la position soit enregistrée par Bybit
        time.sleep(1.5)
        
        # Formatage du symbole pour l'appel privé (Bybit attend souvent ETHUSDT sans /)
        clean_symbol = symbol.split(':')[0].replace('/', '')
        
        exchange.private_post_v5_position_trading_stop({
            "category": "linear",
            "symbol": clean_symbol,
            "trailingStop": str(round(distance, 4)),
            "positionIdx": 0
        })
        print(f"📈 Trailing Stop activé pour {symbol} (distance: {round(distance, 2)})")
        return True
    except Exception as e:
        logger.log_error(f"Trailing Stop Error {symbol}", e)
        return False

# ================= OPEN TRADE =================

def open_trade(symbol, side, price, atr, score):
    qty = calculate_position_size(price, atr)
    if qty is None:
        return

    qty = adjust_qty(symbol, qty, price)
    if qty is None:
        print(f"⚠️ {symbol} Qty too small after adjustment")
        return

    if side == "long":
        sl = price - atr * SL_ATR_MULTIPLIER
        tp = price + atr * TP_ATR_MULTIPLIER
        order_side = "buy"
    else:
        sl = price + atr * SL_ATR_MULTIPLIER
        tp = price - atr * TP_ATR_MULTIPLIER
        order_side = "sell"

    # Calcul de la distance du trailing stop (ex: 50% de l'ATR)
    trailing_distance = atr * 0.5

    try:
        # Configuration SL/TP optimisée pour Bybit V5 (Linear)
        params = {
            "takeProfit": str(round(tp, 4)),
            "stopLoss": str(round(sl, 4)),
            "tpslMode": "Full",
            "tpOrderType": "Market",
            "slOrderType": "Market",
            "positionIdx": 0
        }

        order = exchange.create_order(
            symbol,
            "market",
            order_side,
            qty,
            None,
            params
        )

        # Activer le Trailing Stop dans un second temps (plus fiable sur Bybit)
        set_trailing_stop(symbol, trailing_distance)

        last_trade_time[symbol] = time.time()
        
        # Log détaillé du trade
        trade_data = {
            'timestamp': datetime.now().isoformat(),
            'bot_name': BOT_NAME,
            'symbol': symbol,
            'side': side,
            'entry_price': price,
            'quantity': qty,
            'entry_signal_strength': score,
            'entry_atr_percent': (atr/price)
        }
        logger.log_trade_detailed(trade_data)

        msg = f"🟢 TRADE OPEN {BOT_NAME}\n\nSymbol: {symbol}\nSide: {side.upper()}\nScore: {score}/3\nPrice: {price:.2f}\nSL: {sl:.2f}\nTP: {tp:.2f}\nQty: {qty}"
        send_telegram(msg)
        print(f"✅ {msg}")

    except Exception as e:
        logger.log_error(f"Trade error {symbol}", e)
        send_telegram(f"❌ Error opening {symbol}: {str(e)}")

# ================= BOT LOOP =================

def bot_loop():
    send_telegram(f"🚀 {BOT_NAME} STARTED\nSymbols: {len(SYMBOLS)}\nThreshold: {SCORE_THRESHOLD}")
    print(f"🤖 {BOT_NAME} Monitoring {SYMBOLS}")

    while True:
        for symbol in SYMBOLS:
            try:
                if not cooldown_ok(symbol):
                    continue

                df = fetch_data(symbol)
                if df.empty:
                    continue

                df = apply_indicators(df)
                signal, score, atr = check_signal(df)
                
                price = df.close.iloc[-1]
                reason = ""
                
                if signal:
                    if score >= SCORE_THRESHOLD:
                        open_trade(symbol, signal, price, atr, score)
                        executed = True
                    else:
                        reason = f"Score insuffisant ({score}/{SCORE_THRESHOLD})"
                        executed = False
                else:
                    reason = "Pas de signal EMA"
                    executed = False

                # Logging des signaux (même rejetés)
                signal_data = {
                    "symbol": symbol,
                    "signal": signal if signal else "none",
                    "price": price,
                    "signal_strength": score,
                    "executed": executed,
                    "reason_not_executed": reason
                }
                logger.log_signal(signal_data)
                
                # Mise à jour du cache API
                signals_cache.append({
                    "timestamp": datetime.now().strftime("%H:%M:%S"),
                    "symbol": symbol,
                    "signal": signal if signal else "none",
                    "score": score,
                    "reason": reason
                })
                if len(signals_cache) > 100:
                    signals_cache.pop(0)

                # Petit délai pour éviter de spammer l'API
                time.sleep(1)

            except Exception as e:
                logger.log_error(f"Loop error on {symbol}", e)
                time.sleep(10)

        # Pause entre les cycles
        time.sleep(60)

# ================= START =================

if __name__ == "__main__":
    # Correction d'éventuels problèmes de chargement des marchés
    try:
        exchange.load_markets()
    except:
        pass
        
    t = threading.Thread(target=start_api)
    t.daemon = True
    t.start()

    bot_loop()
