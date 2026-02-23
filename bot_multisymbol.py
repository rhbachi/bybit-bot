"""
Bot Multi-Symboles avec stratégie AI avancée
Scanne plusieurs paires et trade la meilleure opportunité
"""
import time
import pandas as pd
import numpy as np
from datetime import datetime, timezone
import heapq
from collections import defaultdict

from config import exchange, CAPITAL, LEVERAGE
from risk_improved import calculate_position_size
from notifier import send_telegram
from logger import init_logger, log_trade
from logger_enhanced import get_logger
from strategy_ai_enhanced import (
    apply_indicators, debug_check_signal, calculate_sl_tp_adaptive,
    reset_state, get_state
)

# =========================
# PARAMÈTRES
# =========================
# Liste des symboles à scanner (ajoutez/enlevez selon vos préférences)
SYMBOLS = [
    "BTC/USDT:USDT",  # Bitcoin
    "ETH/USDT:USDT",  # Ethereum
    "SOL/USDT:USDT",  # Solana
    "BNB/USDT:USDT",  # Binance Coin
    "ADA/USDT:USDT",  # Cardano
    "DOT/USDT:USDT",  # Polkadot
    "LINK/USDT:USDT", # Chainlink
    "MATIC/USDT:USDT", # Polygon
    "AVAX/USDT:USDT", # Avalanche
    "UNI/USDT:USDT",  # Uniswap
]

# Timeframe
TIMEFRAME = "5m"

# Mode papier trading
PAPER_TRADING = True

# Paramètres de sélection
MAX_POSITIONS = 1  # Nombre maximum de positions simultanées (1 par défaut)
SCORE_THRESHOLD = 2  # Score minimum pour considérer un signal (sur 3)
COOLDOWN_SECONDS = 300  # 5 minutes entre chaque scan

# Trailing stop
TRAILING_STOP_ACTIVATION = 0.01
TRAILING_STOP_DISTANCE = 0.005

# Circuit breaker
MAX_DAILY_LOSS_PCT = 5
MAX_CONSECUTIVE_LOSSES = 3

# Capital par symbole (réparti équitablement)
CAPITAL_PER_SYMBOL = CAPITAL / min(MAX_POSITIONS, 3)  # Max 3 positions simultanées

# =========================
# ÉTAT
# =========================
positions = {}  # Dict des positions ouvertes par symbole
consecutive_losses = 0
daily_pnl = 0
initial_capital = CAPITAL
last_scan_time = None
total_trades = 0
symbol_stats = defaultdict(lambda: {'trades': 0, 'wins': 0, 'pnl': 0})

# Logger amélioré
enhanced_logger = get_logger("MULTI_SYMBOL")

# =========================
# UTILS
# =========================
def fetch_ohlcv(symbol, limit=100):
    """Récupère les données OHLCV pour un symbole"""
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
        print(f"📝 PAPER - {symbol} SL/TP simulés: SL={sl_price:.2f}, TP={tp_price:.2f}", flush=True)
        return True
        
    try:
        exchange.private_post_v5_position_trading_stop({
            'category': 'linear',
            'symbol': symbol.replace('/', '').replace(':USDT', ''),
            'stopLoss': str(sl_price),
            'takeProfit': str(tp_price),
            'tpTriggerBy': 'LastPrice',
            'slTriggerBy': 'MarkPrice',  # Protection liquidation
            'tpslMode': 'Full',
            'tpOrderType': 'Limit',
            'slOrderType': 'Market',
            'positionIdx': 0,
        })
        print(f"✅ {symbol} SL/TP placés | SL={sl_price:.2f} | TP={tp_price:.2f}", flush=True)
        return True
    except Exception as e:
        enhanced_logger.log_error(f"Erreur SL/TP {symbol}", e)
        return False

def update_trailing_stop(symbol, side, qty, current_price, current_sl):
    """Met à jour le trailing stop"""
    if PAPER_TRADING or symbol not in positions:
        return current_sl
    
    trade = positions[symbol]
    
    if side == 'long':
        if current_price > trade['highest_price']:
            trade['highest_price'] = current_price
            
        gain_pct = (current_price - trade['entry_price']) / trade['entry_price']
        
        if gain_pct > TRAILING_STOP_ACTIVATION:
            new_sl = current_price * (1 - TRAILING_STOP_DISTANCE)
            if new_sl > current_sl:
                print(f"📈 {symbol} Trailing stop: {current_sl:.2f} → {new_sl:.2f}", flush=True)
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
                    enhanced_logger.log_error(f"Erreur trailing stop {symbol}", e)
    
    return current_sl

def check_circuit_breaker():
    """Vérifie si on doit arrêter le trading"""
    global consecutive_losses, initial_capital
    
    if total_trades < 5:
        return False, "OK - Phase de chauffe"
    
    current_balance = get_available_balance()
    daily_loss_pct = (initial_capital - current_balance) / initial_capital * 100 if initial_capital > 0 else 0
    
    if daily_loss_pct > MAX_DAILY_LOSS_PCT and daily_loss_pct < 100:
        msg = f"🚨 CIRCUIT BREAKER: Perte journalière {daily_loss_pct:.1f}% > {MAX_DAILY_LOSS_PCT}%"
        print(msg, flush=True)
        send_telegram(msg)
        enhanced_logger.log_error(msg)
        return True, f"Daily loss: {daily_loss_pct:.1f}%"
    
    if consecutive_losses >= MAX_CONSECUTIVE_LOSSES:
        msg = f"🚨 CIRCUIT BREAKER: {consecutive_losses} pertes consécutives"
        print(msg, flush=True)
        send_telegram(msg)
        enhanced_logger.log_error(msg)
        return True, f"{consecutive_losses} losses"
    
    return False, "OK"

def scan_all_symbols():
    """
    Scanne tous les symboles et retourne les meilleures opportunités
    """
    opportunities = []
    
    print(f"\n🔍 Scan de {len(SYMBOLS)} symboles à {datetime.now().strftime('%H:%M:%S')}", flush=True)
    
    for symbol in SYMBOLS:
        # Ignorer si déjà en position
        if symbol in positions:
            continue
            
        # Récupérer les données
        df = fetch_ohlcv(symbol, limit=100)
        if df.empty:
            continue
        
        # Appliquer les indicateurs
        df_with_indicators = apply_indicators(df)
        
        # Vérifier le signal
        signal = debug_check_signal(df_with_indicators)
        
        if signal:
            # Calculer le score de l'opportunité
            last_row = df_with_indicators.iloc[-1]
            
            # Prix actuel
            current_price = last_row['close']
            
            # Calculer SL/TP
            sl_price, tp_price, atr_pct = calculate_sl_tp_adaptive(
                current_price, signal, df_with_indicators
            )
            
            # Calculer le ratio risque/récompense
            if signal == 'long':
                rr_ratio = (tp_price - current_price) / (current_price - sl_price)
            else:
                rr_ratio = (current_price - tp_price) / (sl_price - current_price)
            
            # Score composite
            score = 0
            score += 1 if rr_ratio > 2 else 0  # Bon RR
            score += 1 if atr_pct > 0.01 else 0  # Volatilité suffisante
            score += 1 if 40 < last_row['rsi'] < 60 else 0  # RSI idéal
            
            opportunities.append({
                'symbol': symbol,
                'signal': signal,
                'price': current_price,
                'sl_price': sl_price,
                'tp_price': tp_price,
                'atr_pct': atr_pct,
                'rr_ratio': rr_ratio,
                'score': score,
                'rsi': last_row['rsi'],
                'timestamp': datetime.now()
            })
            
            print(f"   {symbol}: {signal.upper()} @ {current_price:.2f} | Score: {score}/3 | RR: {rr_ratio:.2f}", flush=True)
    
    # Trier par score (meilleur d'abord)
    opportunities.sort(key=lambda x: x['score'], reverse=True)
    
    return opportunities

def execute_trade(opportunity):
    """Exécute un trade sur une opportunité"""
    global total_trades, last_scan_time, positions
    
    symbol = opportunity['symbol']
    signal = opportunity['signal']
    current_price = opportunity['price']
    sl_price = opportunity['sl_price']
    tp_price = opportunity['tp_price']
    
    print(f"\n🎯 EXÉCUTION sur {symbol} - {signal.upper()}", flush=True)
    
    # Vérifier solde
    available = get_available_balance()
    if available < 5:
        print(f"❌ Solde insuffisant pour {symbol}", flush=True)
        return False
    
    # Capital pour ce trade
    trade_capital = min(CAPITAL_PER_SYMBOL, available * 0.95 / max(1, len(positions) + 1))
    
    # Calculer taille position
    qty = calculate_position_size(
        trade_capital,
        0.02,  # 2% risque
        abs(current_price - sl_price) / current_price,
        current_price,
        LEVERAGE
    )
    
    if qty <= 0:
        print(f"⚠️ Quantité invalide pour {symbol}", flush=True)
        return False
    
    # Ouvrir position
    order_side = "buy" if signal == "long" else "sell"
    
    try:
        if PAPER_TRADING:
            print(f"📝 PAPER - {symbol} Ordre {order_side} {qty} à {current_price}", flush=True)
            order_success = True
        else:
            order = exchange.create_market_order(symbol, order_side, qty)
            order_success = True
        
        if order_success:
            # Placer SL/TP
            success = place_sl_tp_orders(
                symbol, signal, qty, current_price, sl_price, tp_price
            )
            
            if success:
                # Enregistrer la position
                positions[symbol] = {
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
                
                last_scan_time = time.time()
                
                # Notification
                msg = (
                    f"🟢 NOUVEAU TRADE ({symbol})\n"
                    f"Direction: {signal.upper()}\n"
                    f"Prix: {current_price:.2f}\n"
                    f"Qty: {qty}\n"
                    f"SL: {sl_price:.2f} ({abs(current_price-sl_price)/current_price*100:.2f}%)\n"
                    f"TP: {tp_price:.2f} ({abs(tp_price-current_price)/current_price*100:.2f}%)\n"
                    f"RR: {opportunity['rr_ratio']:.2f}\n"
                    f"Score: {opportunity['score']}/3"
                )
                send_telegram(msg)
                
                return True
            else:
                # Fermer si SL/TP échouent
                if not PAPER_TRADING:
                    close_side = "sell" if signal == "long" else "buy"
                    exchange.create_market_order(symbol, close_side, qty, params={'reduceOnly': True})
                print(f"🚨 {symbol} Position fermée (SL/TP failed)", flush=True)
                
    except Exception as e:
        enhanced_logger.log_error(f"Erreur execution {symbol}", e)
        print(f"❌ Erreur execution {symbol}: {e}", flush=True)
    
    return False

def check_positions():
    """Vérifie l'état des positions ouvertes"""
    global positions, consecutive_losses, total_trades, daily_pnl
    
    for symbol in list(positions.keys()):
        trade = positions[symbol]
        
        # Récupérer prix actuel
        df = fetch_ohlcv(symbol, limit=2)
        if df.empty:
            continue
        
        current_price = df['close'].iloc[-1]
        
        # Mettre à jour trailing stop
        new_sl = update_trailing_stop(
            symbol,
            trade['side'],
            trade['qty'],
            current_price,
            trade['sl_price']
        )
        
        if new_sl != trade['sl_price']:
            trade['sl_price'] = new_sl
            trade['trailing_activated'] = True
        
        # Vérifier si position fermée
        if PAPER_TRADING:
            # Simulation papier
            if trade['side'] == 'long':
                if current_price <= trade['sl_price'] or current_price >= trade['tp_price']:
                    position_closed = True
                    exit_reason = "SL" if current_price <= trade['sl_price'] else "TP"
                else:
                    position_closed = False
                    exit_reason = None
            else:
                if current_price >= trade['sl_price'] or current_price <= trade['tp_price']:
                    position_closed = True
                    exit_reason = "SL" if current_price >= trade['sl_price'] else "TP"
                else:
                    position_closed = False
                    exit_reason = None
        else:
            # Vérification réelle
            try:
                positions_data = exchange.fetch_positions([symbol])
                pos = next((p for p in positions_data if p.get("symbol") == symbol), None)
                position_closed = pos and float(pos.get("contracts", 0)) == 0
                exit_reason = "SL/TP" if position_closed else None
            except:
                position_closed = False
                exit_reason = None
        
        if position_closed:
            # Calculer P&L
            if trade['side'] == 'long':
                pnl_pct = (current_price - trade['entry_price']) / trade['entry_price'] * 100
                pnl_usdt = (current_price - trade['entry_price']) * trade['qty']
            else:
                pnl_pct = (trade['entry_price'] - current_price) / trade['entry_price'] * 100
                pnl_usdt = (trade['entry_price'] - current_price) * trade['qty']
            
            result = "WIN" if pnl_pct > 0 else "LOSS"
            
            # Mettre à jour stats
            if result == "LOSS":
                consecutive_losses += 1
            else:
                consecutive_losses = 0
            
            total_trades += 1
            daily_pnl += pnl_usdt
            
            # Stats par symbole
            symbol_stats[symbol]['trades'] += 1
            symbol_stats[symbol]['wins'] += 1 if result == "WIN" else 0
            symbol_stats[symbol]['pnl'] += pnl_usdt
            
            # Logger
            log_trade(
                symbol,
                trade['side'],
                trade['qty'],
                trade['entry_price'],
                current_price,
                pnl_pct,
                result
            )
            
            # Notification
            duration = (datetime.now(timezone.utc) - trade['entry_time']).seconds
            msg = (
                f"{'🟢 WIN' if pnl_pct>0 else '🔴 LOSS'} - {symbol} FERMÉ\n"
                f"Direction: {trade['side'].upper()}\n"
                f"Entrée: {trade['entry_price']:.2f}\n"
                f"Sortie: {current_price:.2f}\n"
                f"P&L: {pnl_pct:+.2f}% ({pnl_usdt:+.2f} USDT)\n"
                f"Durée: {duration}s\n"
                f"Raison: {exit_reason}"
            )
            send_telegram(msg)
            
            # Retirer des positions actives
            del positions[symbol]

def print_stats():
    """Affiche les statistiques"""
    print("\n" + "="*50, flush=True)
    print(f"📊 STATISTIQUES MULTI-SYMBOLES", flush=True)
    print(f"Positions ouvertes: {len(positions)}", flush=True)
    print(f"Total trades: {total_trades}", flush=True)
    print(f"P&L journalier: {daily_pnl:+.2f} USDT", flush=True)
    print(f"Pertes consécutives: {consecutive_losses}", flush=True)
    
    if symbol_stats:
        print("\n🏆 Performance par symbole:", flush=True)
        for symbol, stats in sorted(symbol_stats.items(), key=lambda x: x[1]['pnl'], reverse=True):
            winrate = (stats['wins'] / stats['trades'] * 100) if stats['trades'] > 0 else 0
            print(f"   {symbol}: {stats['trades']} trades | {winrate:.1f}% WR | {stats['pnl']:+.2f} USDT", flush=True)
    
    print("="*50 + "\n", flush=True)

# =========================
# MAIN
# =========================
def run():
    global last_scan_time
    
    print("🤖 Bot MULTI-SYMBOLES AI ENHANCED démarré", flush=True)
    print(f"📊 Stratégie: EMA20/50 + MACD + RSI + Stochastic + OTE Fibonacci", flush=True)
    print(f"📝 Mode PAPER: {PAPER_TRADING}", flush=True)
    print(f"🎯 Symboles scannés: {len(SYMBOLS)}", flush=True)
    print(f"⚡ Positions max: {MAX_POSITIONS}", flush=True)
    
    init_logger()
    
    # Notification démarrage
    mode = "📝 PAPER" if PAPER_TRADING else "💰 REAL"
    send_telegram(
        f"🤖 MULTI-SYMBOLES {mode}\n"
        f"📊 {len(SYMBOLS)} symboles | {TIMEFRAME}\n"
        f"⚙️ Capital: {CAPITAL} USDT | Lev: {LEVERAGE}x\n"
        f"⚡ Max positions: {MAX_POSITIONS}\n"
        f"🛡️ Circuit breaker: {MAX_DAILY_LOSS_PCT}% daily"
    )
    
    while True:
        try:
            # Circuit breaker
            should_stop, reason = check_circuit_breaker()
            if should_stop:
                print(f"⛔ Trading arrêté: {reason}", flush=True)
                time.sleep(300)
                continue
            
            # Scanner les symboles si pas trop de positions
            if len(positions) < MAX_POSITIONS:
                opportunities = scan_all_symbols()
                
                # Exécuter sur la meilleure opportunité si score suffisant
                if opportunities and opportunities[0]['score'] >= SCORE_THRESHOLD:
                    execute_trade(opportunities[0])
            
            # Vérifier les positions ouvertes
            if positions:
                check_positions()
            
            # Afficher stats périodiquement
            if total_trades % 10 == 0 and total_trades > 0:
                print_stats()
            
            # Attendre avant prochain scan
            time.sleep(COOLDOWN_SECONDS)
            
        except Exception as e:
            enhanced_logger.log_error("Erreur loop principale", e)
            print(f"❌ Erreur loop: {e}", flush=True)
            send_telegram(f"❌ Erreur Multi-Symboles: {e}")
            time.sleep(60)

if __name__ == "__main__":
    run()