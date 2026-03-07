import time
import threading
import pandas as pd
import math
import os
import json
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
active_positions = {} # {symbol: trade_data}

# Performance stats
daily_pnl = 0.0
total_trades = 0
consecutive_losses = 0
last_state_save = datetime.now().date().isoformat()

STATE_FILE = "data/multisymbol_state.json"

def save_state():
    state = {
        "daily_pnl": daily_pnl,
        "total_trades": total_trades,
        "consecutive_losses": consecutive_losses,
        "last_save_date": last_state_save,
        "signals_cache": signals_cache[-100:] # Persist some history
    }
    try:
        os.makedirs("data", exist_ok=True)
        with open(STATE_FILE, "w") as f:
            json.dump(state, f)
    except Exception as e:
        logger.log_error("Error saving state", e)

def load_state():
    global daily_pnl, total_trades, consecutive_losses, last_state_save, signals_cache
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                state = json.load(f)
                
            # Check if it's a new day
            current_date = datetime.now().date().isoformat()
            if state.get("last_save_date") == current_date:
                daily_pnl = state.get("daily_pnl", 0.0)
                consecutive_losses = state.get("consecutive_losses", 0)
            else:
                daily_pnl = 0.0
                consecutive_losses = 0
                last_state_save = current_date
                
            total_trades = state.get("total_trades", 0)
            signals_cache = state.get("signals_cache", [])
            print(f"📊 State loaded: PnL Today={daily_pnl:.2f}, Trades={total_trades}")
        except Exception as e:
            logger.log_error("Error loading state", e)

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
        "leverage": LEVERAGE,
        "active_count": len(active_positions),
        "daily_pnl": daily_pnl,
        "total_trades": total_trades
    })

@app.route("/api/trades")
def trades():
    """Historique des trades récents"""
    return jsonify(logger.get_recent_trades(50))

@app.route("/api/positions")
def positions():
    """Positions actuellement ouvertes"""
    # On rafraîchit la liste avec Bybit pour être sûr
    return jsonify(list(active_positions.values()))

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

def has_open_position(symbol, ignore_cache=False):
    """Vérifie si une position est déjà ouverte pour ce symbole sur Bybit"""
    try:
        # On vérifie d'abord notre cache local pour la rapidité
        if not ignore_cache and symbol in active_positions:
            return True
            
        # Puis on vérifie réellement sur l'échange
        pos = exchange.fetch_position(symbol)
        is_open = pos and float(pos.get('contracts', 0)) > 0
        
        if is_open:
            # On en profite pour remettre à jour notre cache si besoin
            active_positions[symbol] = {
                "symbol": symbol,
                "side": pos.get('side'),
                "entry_price": pos.get('entryPrice'),
                "qty": pos.get('contracts'),
                "pnl_percent": pos.get('percentage'),
                "pnl_usdt": pos.get('unrealizedPnl'),
                "timestamp": datetime.now().isoformat()
            }
            return True
        else:
            # Si pas de position sur l'échange, on s'assure de nettoyer le cache
            if symbol in active_positions:
                print(f"🔄 Detection fmeture position {symbol}")
                handle_position_closed(symbol)
                del active_positions[symbol]
            return False
    except Exception as e:
        logger.log_error(f"Error checking position for {symbol}", e)
def handle_position_closed(symbol):
    global daily_pnl, total_trades, consecutive_losses
    try:
        # Attendre un peu pour que Bybit enregistre le trade fermé
        time.sleep(2)
        
        # Récupérer le PnL réalisé via l'API V5 de Bybit
        clean_symbol = symbol.split(':')[0].replace('/', '')
        pnl = 0.0
        
        try:
            pnl_resp = exchange.private_get_v5_position_closed_pnl({
                "category": "linear",
                "symbol": clean_symbol,
                "limit": 1
            })
            if pnl_resp.get('result', {}).get('list'):
                pnl = float(pnl_resp['result']['list'][0].get('closedPnl', 0))
        except Exception as e:
            logger.log_error(f"Error fetching closed PnL for {symbol}", e)
            # Fallback simple si l'API échoue
            pnl = 0.0

        daily_pnl += pnl
        total_trades += 1
        if pnl < 0:
            consecutive_losses += 1
        else:
            consecutive_losses = 0
        
        print(f"💰 {symbol} Position fermée. PnL: {pnl:.2f} USDT. Total Jour: {daily_pnl:.2f} USDT")
        save_state()
        
        # Log de sortie (minimaliste car réalisé sur l'échange)
        trade_data = {
            'timestamp': datetime.now().isoformat(),
            'bot_name': BOT_NAME,
            'symbol': symbol,
            'pnl_usdt': pnl,
            'result': "WIN" if pnl > 0 else "LOSS",
            'exit_reason': 'Exchange closed (SL/TP/Trailing)'
        }
        logger.log_trade_detailed(trade_data)
        
    except Exception as e:
        logger.log_error(f"Error handling closed position for {symbol}", e)

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
    # Sécurité ultime : On ne rentre pas si déjà en position
    if has_open_position(symbol):
        print(f"🚫 {symbol} déjà en position, ouverture annulée.")
        return

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
        
        # Ajouter à notre suivi local des positions actives
        active_positions[symbol] = {
            "symbol": symbol,
            "side": side,
            "entry_price": price,
            "qty": qty,
            "timestamp": datetime.now().isoformat()
        }

        msg = f"🟢 TRADE OPEN {BOT_NAME}\n\nSymbol: {symbol}\nSide: {side.upper()}\nScore: {score}/3\nPrice: {price:.2f}\nSL: {sl:.2f}\nTP: {tp:.2f}\nQty: {qty}"
        send_telegram(msg)
        print(f"✅ {msg}")
        save_state()

    except Exception as e:
        logger.log_error(f"Trade error {symbol}", e)
        send_telegram(f"❌ Error opening {symbol}: {str(e)}")

# ================= BOT LOOP =================

def bot_loop():
    global daily_pnl, consecutive_losses, last_state_save
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
                
                # Mise à jour du cache API (format harmonisé avec ZONE2_AI)
                signals_cache.append({
                    "timestamp": datetime.now().isoformat(),
                    "bot": "MULTI_SYMBOL",
                    "symbol": symbol,
                    "signal": signal if signal else "none",
                    "price": price,
                    "strength": f"{score}/3",
                    "executed": executed,
                    "reason": reason
                })
                if len(signals_cache) > 200:
                    signals_cache.pop(0)
                
                # Save state periodically and on signals
                if signal:
                    save_state()

                # Petit délai pour éviter de spammer l'API
                time.sleep(1)

            except Exception as e:
                logger.log_error(f"Loop error on {symbol}", e)
                time.sleep(10)

        # Nettoyage périodique du cache des positions actives (vérification réelle sur Bybit)
        try:
            for s in list(active_positions.keys()):
                # On force la vérification sur l'échange pour vider le cache si la position est fermée
                has_open_position(s, ignore_cache=True)
        except Exception as e:
            logger.log_error("Cleanup positions cache error", e)
            
        # Pause entre les cycles
        save_state()
        time.sleep(60)

# ================= START =================

if __name__ == "__main__":
    # Correction d'éventuels problèmes de chargement des marchés
    try:
        exchange.load_markets()
    except:
        pass
        
    load_state()
        
    t = threading.Thread(target=start_api)
    t.daemon = True
    t.start()

    bot_loop()
