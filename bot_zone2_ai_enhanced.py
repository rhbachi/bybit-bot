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
from strategy_fvg_confluence import validate_fvg_confluence
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

def run_api():
    """Lance l'API Flask dans un thread séparé"""
    try:
        print("API dashboard demarree sur le port 5001", flush=True)
        api_app.run(host='0.0.0.0', port=5001, debug=False, threaded=True)
    except Exception as e:
        print(f"FAILED - demarrage API: {e}", flush=True)
        time.sleep(5)
        threading.Thread(target=run_api, daemon=True).start()

# IMPORTS DU BOT
from config import exchange, SYMBOL, CAPITAL, LEVERAGE
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
# ÉTAT
# =========================
in_position = False
current_trade = {
    "entry_price": 0,
    "side": None,
    "qty": 0,
    "sl_price": 0,
    "tp_price": 0,
    "entry_time": None,
    "highest_price": 0,
    "lowest_price": 0,
    "trailing_activated": False
}

consecutive_losses = 0
daily_pnl = 0
initial_capital = CAPITAL
last_trade_time = None
total_trades = 0

enhanced_logger = get_logger("ZONE2_AI")

# =========================
# UTILS
# =========================
def fetch_ohlcv(limit=100):
    """Récupère les données OHLCV"""
    try:
        ohlcv = exchange.fetch_ohlcv(SYMBOL, TIMEFRAME, limit=limit)
        df = pd.DataFrame(
            ohlcv,
            columns=["timestamp", "open", "high", "low", "close", "volume"],
        )
        return df
    except Exception as e:
        enhanced_logger.log_error("Erreur fetch_ohlcv", e)
        return pd.DataFrame()

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
            'symbol': symbol.replace('/', '').replace(':USDT', ''),
            'stopLoss': str(sl_price),
            'takeProfit': str(tp_price),
            'tpTriggerBy': 'LastPrice',
            'slTriggerBy': 'MarkPrice',
            'tpslMode': 'Full',
            'tpOrderType': 'Limit',
            'slOrderType': 'Market',
            'positionIdx': 0,
        })
        print(f"✅ SL/TP placés | SL={sl_price:.2f} | TP={tp_price:.2f}", flush=True)
        return True
    except Exception as e:
        enhanced_logger.log_error("Erreur SL/TP", e)
        return False

@api_app.route('/api/status')
def get_status():
    """Retourne l'etat du bot"""
    try:
        from config import exchange, SYMBOL, CAPITAL, LEVERAGE, PAPER_TRADING
        # Balance simplifiee pour eviter les erreurs de timeout
        return jsonify({
            'bot': 'ZONE2_AI',
            'symbol': SYMBOL,
            'paper_mode': PAPER_TRADING,
            'capital': CAPITAL,
            'leverage': LEVERAGE,
            'status': 'running'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def update_trailing_stop(symbol, side, qty, current_price, current_sl):
    """Met à jour le trailing stop"""
    global current_trade
    
    if PAPER_TRADING:
        return current_sl
    
    if side == 'long':
        if current_price > current_trade['highest_price']:
            current_trade['highest_price'] = current_price
            
        gain_pct = (current_price - current_trade['entry_price']) / current_trade['entry_price']
        
        if gain_pct > TRAILING_STOP_ACTIVATION:
            new_sl = current_price * (1 - TRAILING_STOP_DISTANCE)
            if new_sl > current_sl:
                print(f"📈 Trailing stop: {current_sl:.2f} → {new_sl:.2f}", flush=True)
                try:
                    exchange.private_post_v5_position_trading_stop({
                        'category': 'linear',
                        'symbol': symbol.replace('/', '').replace(':USDT', ''),
                        'stopLoss': str(new_sl),
                        'slTriggerBy': 'MarkPrice',
                        'positionIdx': 0,
                    })
                    return new_sl
                except Exception as e:
                    enhanced_logger.log_error("Erreur trailing stop", e)
                    
    else:  # short
        if current_price < current_trade['lowest_price']:
            current_trade['lowest_price'] = current_price
            
        gain_pct = (current_trade['entry_price'] - current_price) / current_trade['entry_price']
        
        if gain_pct > TRAILING_STOP_ACTIVATION:
            new_sl = current_price * (1 + TRAILING_STOP_DISTANCE)
            if new_sl < current_sl:
                print(f"📈 Trailing stop: {current_sl:.2f} → {new_sl:.2f}", flush=True)
                try:
                    exchange.private_post_v5_position_trading_stop({
                        'category': 'linear',
                        'symbol': symbol.replace('/', '').replace(':USDT', ''),
                        'stopLoss': str(new_sl),
                        'slTriggerBy': 'MarkPrice',
                        'positionIdx': 0,
                    })
                    return new_sl
                except Exception as e:
                    enhanced_logger.log_error("Erreur trailing stop", e)
    
    return current_sl

def check_circuit_breaker():
    """Vérifie si on doit arrêter le trading"""
    global consecutive_losses, initial_capital
    
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

def check_signal_with_logging(df):
    """Wrapper pour logger tous les signaux avec filtres de confluence"""
    from strategy_ai_enhanced import debug_check_signal, detect_trend, get_state, calculate_signal_strength
    
    # 1. Calculer les indicateurs et le signal AI de base
    df_with_indicators = apply_indicators(df)
    signal = debug_check_signal(df_with_indicators)
    
    # 2. Appliquer le filtre de confluence FVG Institutional si un signal AI est présent
    reason_not_executed = ""
    if signal:
        fvg_ok = validate_fvg_confluence(df_with_indicators, signal)
        if not fvg_ok:
            reason_not_executed = "Rejete - Pas de confluence FVG"
            print(f"SIGNAL AI ({signal}) rejete - pas de confluence FVG", flush=True)
            signal = None
    else:
        reason_not_executed = "Pas de signal AI"
    
    # 3. Logging détaillé pour le dashboard
    last_row = df_with_indicators.iloc[-1] if not df_with_indicators.empty else None
    
    if last_row is not None:
        bb_position = 0
        if 'bb_upper' in last_row and 'bb_lower' in last_row:
            bb_range = last_row['bb_upper'] - last_row['bb_lower']
            if bb_range > 0:
                bb_position = (last_row['close'] - last_row['bb_lower']) / bb_range
        
        signal_data = {
            'symbol': SYMBOL,
            'signal': signal if signal else 'none',
            'price': last_row['close'],
            'trend': detect_trend(df_with_indicators) or 'unknown',
            'rsi': last_row.get('rsi', 0),
            'macd': last_row.get('macd', 0),
            'stoch_k': last_row.get('stoch_k', 0),
            'stoch_d': last_row.get('stoch_d', 0),
            'bb_position': bb_position,
            'ote_zone': get_state().get('ote_active', False),
            'bios_detected': get_state().get('bios_level') is not None,
            'signal_strength': calculate_signal_strength(df_with_indicators, signal) if signal else 0,
            'executed': True if signal else False,
            'reason_not_executed': reason_not_executed if not signal else ''
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
def run():
    global in_position, current_trade, consecutive_losses, daily_pnl, last_trade_time, total_trades
    
    print("🤖 Bot ZONE2 AI ENHANCED démarré", flush=True)
    print("📊 Stratégie: EMA20/50 + MACD + RSI + Stochastic + OTE Fibonacci", flush=True)
    print(f"📝 Mode PAPER: {PAPER_TRADING}", flush=True)
    
    init_logger()
    
    if not PAPER_TRADING:
        try:
            exchange.set_leverage(LEVERAGE, SYMBOL)
            print(f"⚙️ Leverage: {LEVERAGE}x", flush=True)
        except Exception as e:
            if "110043" not in str(e):
                print(f"⚠️ Erreur leverage: {e}", flush=True)
    
    mode = "📝 PAPER" if PAPER_TRADING else "💰 REAL"
    send_telegram(
        f"🤖 ZONE2 AI ENHANCED {mode}\n"
        f"📊 {SYMBOL} | {TIMEFRAME}\n"
        f"⚙️ Capital: {CAPITAL} USDT | Lev: {LEVERAGE}x\n"
        f"📈 Stratégie: OTE Fibonacci + Multi-indicateurs\n"
        f"🛡️ Circuit breaker: {MAX_DAILY_LOSS_PCT}% daily | {MAX_CONSECUTIVE_LOSSES} losses"
    )
    
    while True:
        try:
            if total_trades > 5:
                should_stop, reason = check_circuit_breaker()
                if should_stop:
                    print(f"⛔ Trading arrêté: {reason}", flush=True)
                    time.sleep(300)
                    continue
            else:
                print(f"⏳ Phase de chauffe: {total_trades}/5 trades avant activation circuit breaker", flush=True)
            
            if last_trade_time and time.time() - last_trade_time < COOLDOWN_SECONDS:
                time.sleep(10)
                continue
            
            df = fetch_ohlcv(limit=100)
            if df.empty:
                print("⚠️ Pas de données OHLCV", flush=True)
                time.sleep(60)
                continue
            
            signal, df_with_indicators = check_signal_with_logging(df)
            
            if not in_position and signal:
                print(f"🎯 Signal détecté: {signal.upper()}", flush=True)
                
                available = get_available_balance()
                if available < 5:
                    print("❌ Solde insuffisant", flush=True)
                    time.sleep(60)
                    continue
                
                effective_capital = min(CAPITAL, available * 0.95)
                current_price = df_with_indicators['close'].iloc[-1]
                sl_price, tp_price, atr_pct = calculate_sl_tp_adaptive(current_price, signal, df_with_indicators)
                
                qty = calculate_position_size(
                    effective_capital,
                    0.02,
                    abs(current_price - sl_price) / current_price,
                    current_price,
                    LEVERAGE
                )
                
                if qty <= 0:
                    print("⚠️ Quantité invalide", flush=True)
                    time.sleep(60)
                    continue
                
                order_side = "buy" if signal == "long" else "sell"
                print(f"📊 Ouverture {signal.upper()} | Qty={qty}", flush=True)
                
                try:
                    if PAPER_TRADING:
                        print(f"📝 PAPER - Ordre {order_side} {qty} {SYMBOL} à {current_price}", flush=True)
                        order_success = True
                    else:
                        order = exchange.create_market_order(SYMBOL, order_side, qty)
                        order_success = True
                    
                    if order_success:
                        success = place_sl_tp_orders(SYMBOL, signal, qty, current_price, sl_price, tp_price)
                        
                        if success:
                            in_position = True
                            last_trade_time = time.time()
                            
                            current_trade = {
                                "entry_price": current_price,
                                "side": signal,
                                "qty": qty,
                                "sl_price": sl_price,
                                "tp_price": tp_price,
                                "entry_time": datetime.now(timezone.utc),
                                "highest_price": current_price if signal == "long" else 0,
                                "lowest_price": current_price if signal == "short" else float('inf'),
                                "trailing_activated": False
                            }
                            
                            msg = (
                                f"🟢 TRADE OUVERT ({signal.upper()})\n"
                                f"Prix: {current_price:.2f}\n"
                                f"Qty: {qty}\n"
                                f"SL: {sl_price:.2f} ({abs(current_price-sl_price)/current_price*100:.2f}%)\n"
                                f"TP: {tp_price:.2f} ({abs(tp_price-current_price)/current_price*100:.2f}%)\n"
                                f"ATR: {atr_pct*100:.2f}%\n"
                                f"R:R: {abs(tp_price-current_price)/abs(current_price-sl_price):.2f}"
                            )
                            print(msg, flush=True)
                            send_telegram(msg)
                            
                        else:
                            if not PAPER_TRADING:
                                close_side = "sell" if signal == "long" else "buy"
                                exchange.create_market_order(SYMBOL, close_side, qty, params={'reduceOnly': True})
                            print("ALERT - Position fermee (SL/TP failed)", flush=True)
                            enhanced_logger.log_error("SL/TP failed - position fermee")
                
                except Exception as e:
                    enhanced_logger.log_error("Erreur execution ordre", e)
                    print(f"FAILED - Erreur execution: {e}", flush=True)
            
            elif in_position:
                current_price = df_with_indicators['close'].iloc[-1]
                
                new_sl = update_trailing_stop(
                    SYMBOL,
                    current_trade['side'],
                    current_trade['qty'],
                    current_price,
                    current_trade['sl_price']
                )
                
                if new_sl != current_trade['sl_price']:
                    current_trade['sl_price'] = new_sl
                    current_trade['trailing_activated'] = True
                
                if PAPER_TRADING:
                    if current_trade['side'] == 'long':
                        if current_price <= current_trade['sl_price'] or current_price >= current_trade['tp_price']:
                            position_closed = True
                            exit_reason = "SL" if current_price <= current_trade['sl_price'] else "TP"
                        else:
                            position_closed = False
                            exit_reason = None
                    else:
                        if current_price >= current_trade['sl_price'] or current_price <= current_trade['tp_price']:
                            position_closed = True
                            exit_reason = "SL" if current_price >= current_trade['sl_price'] else "TP"
                        else:
                            position_closed = False
                            exit_reason = None
                else:
                    try:
                        positions = exchange.fetch_positions([SYMBOL])
                        pos = next((p for p in positions if p.get("symbol") == SYMBOL), None)
                        position_closed = pos and float(pos.get("contracts", 0)) == 0
                        exit_reason = "SL/TP" if position_closed else None
                    except Exception as e:
                        enhanced_logger.log_error("Erreur verification position", e)
                        position_closed = False
                        exit_reason = None
                
                if position_closed:
                    print(f"NOTIF - Position fermee par {exit_reason}", flush=True)
                    
                    if current_trade['side'] == 'long':
                        pnl_pct = (current_price - current_trade['entry_price']) / current_trade['entry_price'] * 100
                        pnl_usdt = (current_price - current_trade['entry_price']) * current_trade['qty']
                    else:
                        pnl_pct = (current_trade['entry_price'] - current_price) / current_trade['entry_price'] * 100
                        pnl_usdt = (current_trade['entry_price'] - current_price) * current_trade['qty']
                    
                    result = "WIN" if pnl_pct > 0 else "LOSS"
                    
                    if result == "LOSS":
                        consecutive_losses += 1
                    else:
                        consecutive_losses = 0
                    
                    total_trades += 1
                    
                    trade_data = {
                        'timestamp': datetime.now().isoformat(),
                        'bot_name': 'ZONE2_AI',
                        'symbol': SYMBOL,
                        'side': current_trade['side'],
                        'entry_price': current_trade['entry_price'],
                        'exit_price': current_price,
                        'quantity': current_trade['qty'],
                        'pnl_usdt': pnl_usdt,
                        'pnl_percent': pnl_pct,
                        'result': result,
                        'duration_seconds': (datetime.now(timezone.utc) - current_trade['entry_time']).seconds,
                        'exit_reason': exit_reason or 'unknown',
                        'entry_signal_strength': 2,
                        'entry_rsi': df_with_indicators['rsi'].iloc[-1] if 'rsi' in df_with_indicators else 0,
                        'entry_macd': df_with_indicators['macd'].iloc[-1] if 'macd' in df_with_indicators else 0,
                        'entry_stoch_k': df_with_indicators['stoch_k'].iloc[-1] if 'stoch_k' in df_with_indicators else 0,
                        'entry_stoch_d': df_with_indicators['stoch_d'].iloc[-1] if 'stoch_d' in df_with_indicators else 0,
                        'entry_bb_position': 0,
                        'entry_atr_percent': 0,
                        'entry_ema_trend': detect_trend(df_with_indicators) or '',
                        'exit_rsi': df_with_indicators['rsi'].iloc[-1] if 'rsi' in df_with_indicators else 0,
                        'exit_macd': df_with_indicators['macd'].iloc[-1] if 'macd' in df_with_indicators else 0,
                        'max_favorable_price': current_trade.get('highest_price', 0),
                        'max_adverse_price': current_trade.get('lowest_price', 0),
                        'trailing_activated': current_trade.get('trailing_activated', False),
                        'commission_paid': 0,
                        'slippage_bps': 0
                    }
                    
                    enhanced_logger.log_trade_detailed(trade_data)
                    log_trade(SYMBOL, current_trade['side'], current_trade['qty'], 
                             current_trade['entry_price'], current_price, pnl_pct, result)
                    
                    enhanced_logger.update_performance_metrics({
                        'total_trades': total_trades,
                        'win_rate': 0,
                        'daily_pnl': daily_pnl
                    })
                    
                    duration = (datetime.now(timezone.utc) - current_trade['entry_time']).seconds
                    msg = (
                        f"WIN - TRADE FERME\n" if pnl_pct>0 else "LOSS - TRADE FERME\n"
                        f"Direction: {current_trade['side'].upper()}\n"
                        f"Entree: {current_trade['entry_price']:.2f}\n"
                        f"Sortie: {current_price:.2f}\n"
                        f"P&L: {pnl_pct:+.2f}% ({pnl_usdt:+.2f} USDT)\n"
                        f"Duree: {duration}s\n"
                        f"Raison: {exit_reason}"
                    )
                    send_telegram(msg)
                    
                    in_position = False
                    current_trade = {
                        "entry_price": 0,
                        "side": None,
                        "qty": 0,
                        "sl_price": 0,
                        "tp_price": 0,
                        "entry_time": None,
                        "highest_price": 0,
                        "lowest_price": 0,
                        "trailing_activated": False
                    }
            
            time.sleep(300)
            
        except Exception as e:
            enhanced_logger.log_error("Erreur loop principale", e)
            print(f"FAILED - Erreur loop: {e}", flush=True)
            send_telegram(f"FAILED - Erreur: {e}")
            time.sleep(60)

if __name__ == "__main__":
    # LANCER L'API ICI (APRES TOUTES LES ROUTES)
    print("START - Lancement de l'API dashboard...", flush=True)
    threading.Thread(target=run_api, daemon=True).start()
    time.sleep(1)
    
    run()