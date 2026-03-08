"""
Bot Zone2 avec stratégie AI avancée (EMA, MACD, RSI, Stochastic, OTE Fibonacci)
Version avec API Flask pour le dashboard
"""
import time
import pandas as pd
from datetime import datetime, timezone
import threading
from flask import Flask, jsonify
import os
import json
from database import init_db, insert_trade, get_recent_trades

# =========================
# API POUR LE DASHBOARD (LANCÉE EN PREMIER)
# =========================
api_app = Flask(__name__)

@api_app.route('/api/health')
def health():
    """Endpoint de santé pour vérifier que le bot répond"""
    return jsonify({'status': 'ok', 'bot': 'ZONE2_AI'})

@api_app.route('/api/signals')
def get_signals():
    """Endpoint pour le dashboard - retourne les 50 derniers signaux"""
    try:
        if os.path.exists('logs/signals_log.csv'):
            df = pd.read_csv('logs/signals_log.csv')
            df = df.tail(50)
            signals = df.to_dict('records')
            
            formatted_signals = []
            for s in signals:
                formatted_signals.append({
                    'timestamp': s.get('timestamp', ''),
                    'bot': 'ZONE2_AI',
                    'signal': s.get('signal', 'none'),
                    'price': s.get('price', 0),
                    'strength': f"{s.get('signal_strength', 0)}/3",
                    'executed': s.get('executed', False),
                    'reason': s.get('reason_not_executed', '')
                })
            return jsonify(formatted_signals)
        return jsonify([])
    except Exception as e:
        print(f"FAILED - API signals: {e}", flush=True)
        return jsonify([])

@api_app.route('/api/trades')
def get_trades_api():
    """Retreive recent trades from the log file"""
    try:
        trades = enhanced_logger.get_recent_trades(50)
        return jsonify(trades)
    except Exception as e:
        print(f"FAILED - API trades: {e}", flush=True)
        return jsonify([])


@api_app.route('/api/positions')
def get_positions_api():
    """Return all current active positions"""
    try:
        # On renvoie toutes les positions suivies
        return jsonify(list(trades_state.values()))
    except Exception as e:
        print(f"FAILED - API positions: {e}", flush=True)
        return jsonify([])

def run_api():
    """Lance l'API Flask dans un thread séparé"""
    try:
        print("API dashboard demarree sur le port 5002", flush=True)
        api_app.run(host='0.0.0.0', port=5002, debug=False, threaded=True)
    except Exception as e:
        print(f"FAILED - demarrage API: {e}", flush=True)
        time.sleep(5)
        threading.Thread(target=run_api, daemon=True).start()

# IMPORTS DU BOT
from config import exchange, SYMBOLS, CAPITAL, LEVERAGE
from risk_improved import calculate_position_size
from notifier import send_telegram
from logger import init_logger, log_trade
from logger_enhanced import get_logger
from strategy_ai_enhanced import (
    apply_indicators, check_signal, calculate_sl_tp_adaptive,
    reset_state, get_state, calculate_signal_strength
)

# =========================
# PARAMÈTRES AVEC VARIABLES D'ENV
# =========================
TIMEFRAME = os.getenv('TIMEFRAME', '5m')
MIN_BODY_PCT = float(os.getenv('MIN_BODY_PCT', '0.0005'))
COOLDOWN_SECONDS = int(os.getenv('COOLDOWN_SECONDS', '60'))
PAPER_TRADING = os.getenv('PAPER_TRADING', 'true').lower() == 'true'
TRAILING_STOP_ACTIVATION = float(os.getenv('TRAILING_STOP_ACTIVATION', '0.01'))
TRAILING_STOP_DISTANCE = float(os.getenv('TRAILING_STOP_DISTANCE', '0.005'))
MAX_DAILY_LOSS_PCT = float(os.getenv('MAX_DAILY_LOSS_PCT', '5'))
MAX_CONSECUTIVE_LOSSES = int(os.getenv('MAX_CONSECUTIVE_LOSSES', '3'))
RISK_PER_TRADE = float(os.getenv('RISK_PER_TRADE', '0.02'))

# =========================
# ÉTAT MULTI-SYMBOLE
# =========================
active_positions = {} 
trades_state = {}     
last_trade_times = {} 

consecutive_losses = 0
daily_pnl = 0.0
initial_capital = CAPITAL
total_trades = 0

enhanced_logger = get_logger("ZONE2_AI")

STATE_FILE = "data/zone2_state.json"
last_state_save_date = datetime.now().date().isoformat()

def save_state():
    state = {
        "daily_pnl": daily_pnl,
        "consecutive_losses": consecutive_losses,
        "total_trades": total_trades,
        "last_save_date": last_state_save_date
    }
    try:
        os.makedirs("data", exist_ok=True)
        with open(STATE_FILE, "w") as f:
            json.dump(state, f)
    except Exception as e:
        enhanced_logger.log_error("Error saving state", e)

def load_state():
    global daily_pnl, consecutive_losses, total_trades, last_state_save_date
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                state = json.load(f)
            
            # Reset daily metrics if it's a new day
            current_date = datetime.now().date().isoformat()
            if state.get("last_save_date") == current_date:
                daily_pnl = state.get("daily_pnl", 0.0)
                consecutive_losses = state.get("consecutive_losses", 0)
            else:
                daily_pnl = 0.0
                consecutive_losses = 0
                last_state_save_date = current_date
                
            total_trades = state.get("total_trades", 0)
            print(f"📊 Zone2 State loaded: PnL Today={daily_pnl:.2f}, Trades={total_trades}")
        except Exception as e:
            enhanced_logger.log_error("Error loading state", e)

# =========================
# UTILS
# =========================
def fetch_ohlcv(symbol, limit=100):
    """Récupère les données OHLCV pour un symbole spécifique"""
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, TIMEFRAME, limit=limit)
        df = pd.DataFrame(
            ohlcv,
            columns=["timestamp", "open", "high", "low", "close", "volume"],
        )
        return df
    except Exception as e:
        enhanced_logger.log_error(f"Erreur fetch_ohlcv {symbol}", e)
        return pd.DataFrame()

def cooldown_ok(symbol):
    """Vérifie le cooldown pour un symbole"""
    if symbol not in last_trade_times:
        return True
    elapsed = time.time() - last_trade_times[symbol]
    return elapsed > COOLDOWN_SECONDS

def has_open_position(symbol, ignore_cache=False):
    """Vérifie si une position est déjà ouverte sur Bybit pour ce symbole"""
    try:
        # Cache local d'abord
        if not ignore_cache and active_positions.get(symbol):
            return True
            
        # Bypass cache et vérification réelle sur l'échange
        pos = exchange.fetch_position(symbol)
        is_open = pos and float(pos.get('contracts', 0)) > 0
        
        if is_open:
            active_positions[symbol] = True
            return True
        else:
            active_positions[symbol] = False
            return False
    except Exception as e:
        enhanced_logger.log_error(f"Error checking position for {symbol}", e)
        return True # Prudence par défaut

def get_available_balance():
    """Récupère le solde disponible"""
    try:
        balance = exchange.fetch_balance()
        usdt = balance.get('USDT', {})
        return float(usdt.get('free', 0))
    except Exception as e:
        enhanced_logger.log_error("Erreur balance", e)
        return 0

def place_sl_tp_orders(symbol, side, qty, entry_price, sl_price, tp_price):
    """Place les ordres SL/TP optimisés"""
    if PAPER_TRADING:
        print(f"📝 PAPER - SL/TP simulés: SL={sl_price:.2f}, TP={tp_price:.2f}", flush=True)
        return True
        
    try:
        exchange.private_post_v5_position_trading_stop({
            'category': 'linear',
            'symbol': symbol.split(':')[0].replace('/', ''),
            'stopLoss': str(sl_price),
            'takeProfit': str(tp_price),
            'tpTriggerBy': 'LastPrice',
            'slTriggerBy': 'MarkPrice',
            'tpslMode': 'Full',
            'tpOrderType': 'Market',
            'slOrderType': 'Market',
            'positionIdx': 0,
        })
        print(f"✅ [{symbol}] SL/TP placés | SL={sl_price:.2f} | TP={tp_price:.2f}", flush=True)
        return True
    except Exception as e:
        enhanced_logger.log_error(f"Erreur SL/TP {symbol}", e)
        return False

@api_app.route('/api/status')
def get_status():
    """Retourne l'etat global du bot"""
    try:
        return jsonify({
            'bot': 'ZONE2_MULTI',
            'active_symbols': SYMBOLS,
            'paper_mode': PAPER_TRADING,
            'capital': CAPITAL,
            'leverage': LEVERAGE,
            'status': 'running',
            'active_count': sum(1 for p in active_positions.values() if p),
            'daily_pnl': daily_pnl,
            'total_trades': total_trades,
            'consecutive_losses': consecutive_losses,
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def update_trailing_stop(symbol, side, qty, current_price, current_sl):
    """Met à jour le trailing stop avec sécurisation du prix d'entrée (Break-even)"""
    trade = trades_state.get(symbol)
    if not trade:
        return current_sl

    entry_price = trade['entry_price']

    if side == 'long':
        if current_price > trade['highest_price']:
            trade['highest_price'] = current_price

        gain_pct = (current_price - entry_price) / entry_price

        if gain_pct > TRAILING_STOP_ACTIVATION:
            theoretical_sl = current_price * (1 - TRAILING_STOP_DISTANCE)
            new_sl = max(theoretical_sl, entry_price * 1.001)

            if new_sl > current_sl:
                print(f"📈 [{symbol}] Trailing stop: {current_sl:.2f} → {new_sl:.2f} (Profit sécurisé)", flush=True)
                if not PAPER_TRADING:
                    try:
                        exchange.private_post_v5_position_trading_stop({
                            'category': 'linear',
                            'symbol': symbol.split(':')[0].replace('/', ''),
                            'stopLoss': str(new_sl),
                            'slTriggerBy': 'MarkPrice',
                            'positionIdx': 0,
                        })
                    except Exception as e:
                        enhanced_logger.log_error(f"Erreur trailing stop {symbol}", e)
                        return current_sl
                return new_sl

    else:  # short
        if current_price < trade['lowest_price']:
            trade['lowest_price'] = current_price

        gain_pct = (entry_price - current_price) / entry_price

        if gain_pct > TRAILING_STOP_ACTIVATION:
            theoretical_sl = current_price * (1 + TRAILING_STOP_DISTANCE)
            new_sl = min(theoretical_sl, entry_price * 0.999)

            if new_sl < current_sl:
                print(f"📈 [{symbol}] Trailing stop: {current_sl:.2f} → {new_sl:.2f} (Profit sécurisé)", flush=True)
                if not PAPER_TRADING:
                    try:
                        exchange.private_post_v5_position_trading_stop({
                            'category': 'linear',
                            'symbol': symbol.split(':')[0].replace('/', ''),
                            'stopLoss': str(new_sl),
                            'slTriggerBy': 'MarkPrice',
                            'positionIdx': 0,
                        })
                    except Exception as e:
                        enhanced_logger.log_error(f"Erreur trailing stop {symbol}", e)
                        return current_sl
                return new_sl

    return current_sl

def check_circuit_breaker():
    """Vérifie si on doit arrêter le trading"""
    global consecutive_losses, initial_capital, total_trades
    
    if total_trades < 5:
        return False, "OK - Phase de chauffe"
    
    current_balance = get_available_balance()
    daily_loss_pct = (initial_capital - current_balance) / initial_capital * 100 if initial_capital > 0 else 0
    
    if daily_loss_pct > MAX_DAILY_LOSS_PCT and daily_loss_pct < 100:
        msg = f"CIRCUIT BREAKER: Perte journaliere {daily_loss_pct:.1f}% > {MAX_DAILY_LOSS_PCT}%"
        print(msg, flush=True)
        send_telegram(msg)
        enhanced_logger.log_error(msg)
        return True, f"Daily loss: {daily_loss_pct:.1f}%"
    
    if consecutive_losses >= MAX_CONSECUTIVE_LOSSES:
        msg = f"CIRCUIT BREAKER: {consecutive_losses} pertes consecutives"
        print(msg, flush=True)
        send_telegram(msg)
        enhanced_logger.log_error(msg)
        return True, f"{consecutive_losses} losses"
    
    return False, "OK"

def check_signal_with_logging(symbol, df):
    """Calcule le signal FVG+Fibonacci+Momentum et le logue"""
    from strategy_ai_enhanced import apply_indicators, check_signal, detect_trend, calculate_signal_strength

    df_with_indicators = apply_indicators(df)
    signal = check_signal(df_with_indicators)
    reason_not_executed = "" if signal else "Pas de signal FVG/Fib"

    last_row = df_with_indicators.iloc[-1] if not df_with_indicators.empty else None
    if last_row is not None:
        bb_position = 0
        if 'bb_upper' in last_row.index and 'bb_lower' in last_row.index:
            bb_range = last_row['bb_upper'] - last_row['bb_lower']
            if bb_range > 0:
                bb_position = (last_row['close'] - last_row['bb_lower']) / bb_range

        signal_data = {
            'symbol': symbol,
            'signal': signal if signal else 'none',
            'price': last_row['close'],
            'trend': detect_trend(df_with_indicators) or 'unknown',
            'rsi': last_row.get('rsi', 0),
            'macd': last_row.get('macd', 0),
            'stoch_k': last_row.get('stoch_k', 0),
            'stoch_d': last_row.get('stoch_d', 0),
            'bb_position': bb_position,
            'ote_zone': False,
            'bios_detected': False,
            'signal_strength': calculate_signal_strength(df_with_indicators, signal) if signal else 0,
            'executed': signal is not None,
            'reason_not_executed': reason_not_executed
        }
        enhanced_logger.log_signal(signal_data)

    return signal, df_with_indicators

def detect_trend(df):
    """Fonction helper pour détecter la tendance"""
    from strategy_ai_enhanced import detect_trend as dt
    return dt(df)

# =========================
# MAIN
# =========================
# =========================
# MAIN MULTI-SYMBOL
# =========================
def run():
    global daily_pnl, total_trades, consecutive_losses, last_state_save_date
    
    print("🤖 Bot ZONE2 MULTI-SYMBOL démarré", flush=True)
    print("📊 Stratégie: EMA20/50 + MACD + RSI + Stochastic + OTE Fibonacci", flush=True)
    print(f"📝 Mode PAPER: {PAPER_TRADING}", flush=True)
    
    init_logger()
    
    if not PAPER_TRADING:
        for symbol in SYMBOLS:
            try:
                exchange.set_leverage(LEVERAGE, symbol)
                print(f"⚙️ Leverage set for {symbol}: {LEVERAGE}x", flush=True)
            except Exception as e:
                if "110043" not in str(e):
                    print(f"⚠️ Erreur leverage {symbol}: {e}", flush=True)
    
    mode = "📝 PAPER" if PAPER_TRADING else "💰 REAL"
    send_telegram(
        f"🤖 ZONE2 AI MULTI-SYMBOL {mode}\n"
        f"📊 Symbols: {len(SYMBOLS)}\n"
        f"⚙️ Capital: {CAPITAL} USDT | Lev: {LEVERAGE}x\n"
        f"🛡️ Circuit breaker actif"
    )
    
    while True:
        for symbol in SYMBOLS:
            try:
                # 1. Gestion des positions existantes
                if active_positions.get(symbol):
                    trade_info = trades_state.get(symbol)
                    if trade_info:
                        df_trail = fetch_ohlcv(symbol, limit=2)
                        if not df_trail.empty:
                            current_price = df_trail['close'].iloc[-1]
                            trade_info['last_price'] = current_price
                            
                            new_sl = update_trailing_stop(
                                symbol,
                                trade_info['side'],
                                trade_info['qty'],
                                current_price,
                                trade_info['sl_price']
                            )
                            if new_sl != trade_info['sl_price']:
                                trade_info['sl_price'] = new_sl
                                trade_info['trailing_activated'] = True
                
                        # Check exit
                        position_closed = False
                        exit_reason = None
                        
                        if PAPER_TRADING:
                            if trade_info['side'] == 'long':
                                if current_price <= trade_info['sl_price']:
                                    position_closed, exit_reason = True, "SL"
                                elif current_price >= trade_info['tp_price']:
                                    position_closed, exit_reason = True, "TP"
                            else: # short
                                if current_price >= trade_info['sl_price']:
                                    position_closed, exit_reason = True, "SL"
                                elif current_price <= trade_info['tp_price']:
                                    position_closed, exit_reason = True, "TP"
                        else:
                            try:
                                # On ignore le cache ici car Bybit est la source de vérité pour la fermeture
                                if not has_open_position(symbol, ignore_cache=True):
                                    position_closed, exit_reason = True, "SL/TP (Market)"
                            except: pass

                        if position_closed:
                            finalize_trade(symbol, trade_info, current_price, exit_reason or "EXIT")
                            active_positions[symbol] = False
                            trades_state.pop(symbol, None)
                            last_trade_times[symbol] = time.time()
                            continue

                # 2. Recherche de nouveaux signaux
                if not active_positions.get(symbol):
                    if not cooldown_ok(symbol): continue
                    
                    df = fetch_ohlcv(symbol, limit=100)
                    if df.empty: continue
                    
                    signal, df_with_indicators = check_signal_with_logging(symbol, df)
                    
                    if signal:
                        print(f"🎯 [{symbol}] Signal détecté: {signal.upper()}", flush=True)
                        execute_entry(symbol, signal, df_with_indicators)

            except Exception as e:
                enhanced_logger.log_error(f"Loop error on {symbol}", e)
                
        time.sleep(60)

def get_base_currency(symbol):
    """Extrait la devise de base d'un symbole. Ex: BTC/USDT:USDT → BTC"""
    return symbol.split('/')[0]

def execute_entry(symbol, signal, df):
    """Gère l'ouverture d'une position"""
    global total_trades

    # Pas deux positions sur le même actif de base
    base = get_base_currency(symbol)
    for open_sym, is_open in active_positions.items():
        if is_open and get_base_currency(open_sym) == base and open_sym != symbol:
            print(f"🚫 [{symbol}] Position déjà ouverte sur {open_sym} (même base: {base}), ouverture annulée.", flush=True)
            return

    current_price = df['close'].iloc[-1]
    sl_price, tp_price, atr_pct = calculate_sl_tp_adaptive(current_price, signal, df)
    
    qty = calculate_position_size(
        CAPITAL,
        0.02,
        abs(current_price - sl_price) / current_price,
        current_price,
        LEVERAGE
    )
    
    if qty <= 0: return

    try:
        if PAPER_TRADING:
            order_success = True
        else:
            order_side = "buy" if signal == "long" else "sell"
            exchange.create_market_order(symbol, order_side, qty)
            order_success = True
        
        if order_success:
            success = place_sl_tp_orders(symbol, signal, qty, current_price, sl_price, tp_price)
            if success:
                active_positions[symbol] = True
                trades_state[symbol] = {
                    "symbol": symbol,
                    "entry_price": current_price,
                    "side": signal,
                    "qty": qty,
                    "sl_price": sl_price,
                    "tp_price": tp_price,
                    "entry_time": datetime.now(timezone.utc).isoformat(),
                    "highest_price": current_price,
                    "lowest_price": current_price,
                    "trailing_activated": False,
                    "last_price": current_price
                }
                
                # Save state after opening position
                save_state()
                
                msg = f"🟢 [{symbol}] TRADE OUVERT ({signal.upper()})\nPrix: {current_price:.2f} | SL: {sl_price:.2f} | TP: {tp_price:.2f}"
                print(msg, flush=True)
                send_telegram(msg)
    except Exception as e:
        enhanced_logger.log_error(f"Entry error {symbol}", e)

def finalize_trade(symbol, trade, exit_price, reason):
    """Finalise et log un trade terminé"""
    global consecutive_losses, daily_pnl, total_trades, last_state_save_date
    
    if trade['side'] == 'long':
        pnl_pct = (exit_price - trade['entry_price']) / trade['entry_price'] * 100
        pnl_usdt = (exit_price - trade['entry_price']) * trade['qty']
    else:
        pnl_pct = (trade['entry_price'] - exit_price) / trade['entry_price'] * 100
        pnl_usdt = (trade['entry_price'] - exit_price) * trade['qty']
    
    result = "WIN" if pnl_pct > 0 else "LOSS"
    if result == "LOSS": consecutive_losses += 1
    else: consecutive_losses = 0
    
    daily_pnl += pnl_usdt
    total_trades += 1
    
    trade_data = {
        'timestamp': datetime.now().isoformat(),
        'bot_name': 'ZONE2_MULTI',
        'symbol': symbol,
        'side': trade['side'],
        'entry_price': trade['entry_price'],
        'exit_price': exit_price,
        'quantity': trade['qty'],
        'pnl_usdt': pnl_usdt,
        'pnl_percent': pnl_pct,
        'result': result,
        'exit_reason': reason
    }
    enhanced_logger.log_trade_detailed(trade_data)
    log_trade(symbol, trade['side'], trade['qty'], trade['entry_price'], exit_price, pnl_pct, result)
    save_state()
    
    msg = f"{result} - [{symbol}] FERMÉ\nP&L: {pnl_pct:+.2f}% ({pnl_usdt:+.2f} USDT)\nRaison: {reason}"
    send_telegram(msg)
    print(msg, flush=True)

if __name__ == "__main__":
    # LANCER L'API ICI (APRES TOUTES LES ROUTES)
    print("START - Lancement de l'API dashboard...", flush=True)
    load_state()
    threading.Thread(target=run_api, daemon=True).start()
    time.sleep(1)
    
    run()