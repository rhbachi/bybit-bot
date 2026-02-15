import time
import pandas as pd
from datetime import datetime, timezone

from config import exchange, SYMBOL, CAPITAL, RISK_PER_TRADE, LEVERAGE
from strategy_bollinger_scalping import (
    calculate_bollinger_bands,
    detect_band_touch_5m,
    check_entry_pattern_1m,
    calculate_sl_tp_bollinger,
    check_exit_conditions_bollinger,
    reset_state
)
from risk_improved import calculate_position_size
from notifier import send_telegram
from logger import init_logger, log_trade

# =========================
# PARAMÈTRES STRATÉGIE BOLLINGER
# =========================
TIMEFRAME_TREND = "5m"  # Détection rebond Bollinger
TIMEFRAME_EXEC = "1m"   # Exécution
MAX_CANDLES = 3         # Sortie à la 3ème bougie

# Pas de limite de trades pour le scalping
COOLDOWN_SECONDS = 60   # 1 minute entre trades

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
    "candles_count": 0,
    "bb_middle": 0,  # Pour le TP dynamique
}

last_trade_time = None

# =========================
# UTILS
# =========================
def safe_float(v, default=0.0):
    try:
        return float(v) if v is not None else default
    except Exception:
        return default


def fetch_ohlcv(timeframe, limit=100):
    """Récupère les données OHLCV pour un timeframe"""
    ohlcv = exchange.fetch_ohlcv(SYMBOL, timeframe, limit=limit)
    return pd.DataFrame(
        ohlcv,
        columns=["time", "open", "high", "low", "close", "volume"],
    )


def get_available_balance():
    try:
        balance = exchange.fetch_balance()
        usdt_balance = balance.get('USDT', {})
        available = safe_float(usdt_balance.get('free', 0))
        print(f"💰 Main Bollinger - Solde disponible: {available} USDT", flush=True)
        return available
    except Exception as e:
        print(f"⚠️ Main Bollinger - Erreur get_balance: {e}", flush=True)
        return 0


def get_min_notional(symbol):
    try:
        market = exchange.market(symbol)
        min_notional = market.get("limits", {}).get("cost", {}).get("min")
        if min_notional is None or min_notional <= 0:
            return 5.0
        return float(min_notional)
    except Exception:
        return 5.0


def adjust_qty_to_min_notional(symbol, qty, price):
    min_notional = get_min_notional(symbol)
    notional = qty * price
    if notional >= min_notional:
        return qty
    min_qty = min_notional / price
    print(f"⚠️ Main Bollinger - Ajustement qty: {round(min_qty,6)}", flush=True)
    return round(min_qty, 6)


def place_sl_tp_orders(symbol, side, qty, entry_price, sl_price, tp_price):
    """
    Place SL/TP avec optimisation des fees
    
    SL : Market order (sécurité, 0.055%)
    TP : Limit order (économie, 0.02%)
    """
    try:
        # Méthode 1 : Endpoint trading_stop (OPTIMISÉ)
        try:
            exchange.private_post_v5_position_trading_stop({
                'category': 'linear',
                'symbol': symbol.replace('/', '').replace(':USDT', ''),
                'stopLoss': str(sl_price),
                'takeProfit': str(tp_price),
                'tpTriggerBy': 'LastPrice',
                'slTriggerBy': 'LastPrice',
                'tpslMode': 'Full',
                'tpOrderType': 'Limit',  # ✅ TP en LIMIT (économise 64% fees)
                'slOrderType': 'Market',  # ✅ SL en MARKET (sécurité)
                'positionIdx': 0,
            })
            
            print(f"✅ Main Bollinger - SL/TP optimisés: SL={round(sl_price, 2)} (Market) | TP={round(tp_price, 2)} (Limit)", flush=True)
            print(f"💰 Économie fees: 64% sur TP", flush=True)
            return True
            
        except Exception as e1:
            print(f"⚠️ Main Bollinger - Méthode 1 échouée: {e1}", flush=True)
            
            # Méthode 2 : Ordres séparés OPTIMISÉS
            try:
                order_side_close = 'sell' if side == 'long' else 'buy'
                
                # STOP LOSS - Market order (sécurité)
                exchange.create_order(
                    symbol, 'market', order_side_close, qty, None,
                    params={
                        'stopLoss': sl_price,
                        'triggerDirection': 'descending' if side == 'long' else 'ascending',
                        'triggerBy': 'LastPrice',
                        'reduceOnly': True,
                        'orderType': 'Market',
                        'triggerPrice': sl_price,
                    }
                )
                
                print(f"✅ Stop Loss placé: {round(sl_price, 2)} (Market - 0.055%)", flush=True)
                
                # TAKE PROFIT - Limit order (économise fees)
                exchange.create_order(
                    symbol, 'limit', order_side_close, qty, tp_price,  # ✅ LIMIT
                    params={
                        'triggerDirection': 'ascending' if side == 'long' else 'descending',
                        'triggerBy': 'LastPrice',
                        'reduceOnly': True,
                        'triggerPrice': tp_price,
                        'timeInForce': 'GTC',
                    }
                )
                
                print(f"✅ Take Profit placé: {round(tp_price, 2)} (Limit - 0.02%)", flush=True)
                print(f"💰 Économie fees TP: 64%", flush=True)
                
                print(f"✅ Main Bollinger - SL/TP optimisés (méthode 2)", flush=True)
                return True
                
            except Exception as e2:
                print(f"❌ Main Bollinger - Méthode 2 échouée: {e2}", flush=True)
                return False
        
    except Exception as e:
        print(f"❌ Main Bollinger - Erreur SL/TP: {e}", flush=True)
        return False


def close_position_immediately(symbol, side, qty):
    """Ferme immédiatement si SL/TP impossibles"""
    try:
        close_side = 'sell' if side == 'long' else 'buy'
        exchange.create_market_order(symbol, close_side, qty, params={'reduceOnly': True})
        print(f"🛑 Main Bollinger - Position fermée (sécurité)", flush=True)
        send_telegram(f"🛑 MAIN BOLLINGER - Position fermée par sécurité")
        return True
    except Exception as e:
        print(f"❌ Main Bollinger - Impossible de fermer: {e}", flush=True)
        return False


# =========================
# MAIN
# =========================
def run():
    global in_position, current_trade, last_trade_time

    print("🤖 Bot MAIN BOLLINGER BANDS V1.0 OPTIMISÉ démarré", flush=True)
    send_telegram("🤖 Bot MAIN BOLLINGER BANDS V1.0\n📊 Rebond sur bandes de Bollinger\n📈 5m detection + 1m execution\n💰 TP en LIMIT (économie 40% fees)")

    init_logger()

    try:
        exchange.set_leverage(LEVERAGE, SYMBOL)
        print(f"⚙️ Main Bollinger - Leverage: {LEVERAGE}x", flush=True)
    except Exception as e:
        if "110043" not in str(e):
            print(f"⚠️ Main Bollinger - Erreur leverage: {e}", flush=True)

    while True:
        try:
            print("⏳ Main Bollinger - Analyse marché...", flush=True)

            # Cooldown entre trades
            if last_trade_time and time.time() - last_trade_time < COOLDOWN_SECONDS:
                time.sleep(10)
                continue

            # ===== PHASE 1 : Détection rebond Bollinger sur 5m =====
            df_5m = fetch_ohlcv(TIMEFRAME_TREND, limit=100)
            df_5m = calculate_bollinger_bands(df_5m)
            band_signal = detect_band_touch_5m(df_5m)

            if band_signal:
                signal_type = "LONG" if band_signal == 'lower_bounce' else "SHORT"
                print(f"📊 Bollinger - Signal {signal_type} détecté", flush=True)

            # ===== PHASE 2 : Vérifier pattern sur 1m =====
            if not in_position and band_signal:
                df_1m = fetch_ohlcv(TIMEFRAME_EXEC, limit=50)
                signal = check_entry_pattern_1m(df_1m, band_signal)

                if signal:
                    print(f"🎯 Signal d'entrée: {signal.upper()}", flush=True)

                    # Vérifier solde
                    available_balance = get_available_balance()
                    if available_balance < 5:
                        print("❌ Main Bollinger - Solde insuffisant", flush=True)
                        time.sleep(60)
                        continue

                    # Capital effectif
                    effective_capital = min(CAPITAL, available_balance * 0.95)

                    # Prix actuel
                    price = df_1m.iloc[-1].close
                    
                    # Récupérer les bandes actuelles
                    current_bb = df_5m.iloc[-1]
                    bb_upper = current_bb['bb_upper']
                    bb_middle = current_bb['bb_middle']
                    bb_lower = current_bb['bb_lower']

                    # Calculer SL/TP basés sur Bollinger
                    sl_price, tp_price = calculate_sl_tp_bollinger(
                        price, signal, bb_upper, bb_middle, bb_lower
                    )
                    
                    # Calculer le SL en pourcentage pour calculate_position_size
                    if signal == 'long':
                        sl_pct = abs(price - sl_price) / price
                    else:
                        sl_pct = abs(sl_price - price) / price
                    
                    # Calculer position
                    qty = calculate_position_size(
                        effective_capital,
                        RISK_PER_TRADE,
                        sl_pct,
                        price,
                        LEVERAGE
                    )

                    qty = adjust_qty_to_min_notional(SYMBOL, qty, price)

                    if qty <= 0:
                        print("⚠️ Main Bollinger - Qty invalide", flush=True)
                        time.sleep(60)
                        continue

                    # Passer ordre
                    order_side = "buy" if signal == 'long' else "sell"
                    print(f"📊 Main Bollinger - Ouverture {signal.upper()} | Qty={qty}", flush=True)

                    order = exchange.create_market_order(SYMBOL, order_side, qty)

                    # Placer SL/TP
                    print("🔒 Main Bollinger - Placement SL/TP...", flush=True)
                    sl_tp_success = place_sl_tp_orders(SYMBOL, signal, qty, price, sl_price, tp_price)

                    if not sl_tp_success:
                        print("🚨 Main Bollinger - SL/TP impossible → Fermeture", flush=True)
                        send_telegram(f"🚨 MAIN BOLLINGER ALERTE\nSL/TP impossible\nPosition fermée")
                        close_position_immediately(SYMBOL, signal, qty)
                        time.sleep(60)
                        continue

                    # Mettre à jour état
                    in_position = True
                    last_trade_time = time.time()

                    current_trade = {
                        "entry_price": price,
                        "side": signal,
                        "qty": qty,
                        "sl_price": sl_price,
                        "tp_price": tp_price,
                        "entry_time": datetime.now(timezone.utc),
                        "candles_count": 0,
                        "bb_middle": bb_middle,
                    }

                    # Calculer R:R
                    if signal == 'long':
                        risk = price - sl_price
                        reward = tp_price - price
                    else:
                        risk = sl_price - price
                        reward = price - tp_price
                    
                    rr_ratio = reward / risk if risk > 0 else 0

                    # Notification
                    msg = (
                        f"📊 MAIN BOLLINGER TRADE OUVERT\n"
                        f"Stratégie: Bollinger Bounce\n"
                        f"Direction: {signal.upper()}\n"
                        f"Prix: {round(price, 2)} USDT\n"
                        f"Quantité: {qty}\n"
                        f"SL: {round(sl_price, 2)} (bande)\n"
                        f"TP: {round(tp_price, 2)} (moyenne)\n"
                        f"R:R: 1:{round(rr_ratio, 1)}\n"
                        f"BB Middle: {round(bb_middle, 2)}\n"
                        f"SL/TP: ✅ PLACÉS ET OPTIMISÉS"
                    )
                    print(msg, flush=True)
                    send_telegram(msg)

            # ===== PHASE 3 : Gestion position ouverte =====
            if in_position:
                # Incrémenter compteur de bougies (cycle 1m)
                current_trade["candles_count"] += 1

                # Récupérer prix actuel et bandes actuelles
                df_1m = fetch_ohlcv(TIMEFRAME_EXEC, limit=2)
                current_price = df_1m.iloc[-1].close
                
                df_5m = fetch_ohlcv(TIMEFRAME_TREND, limit=100)
                df_5m = calculate_bollinger_bands(df_5m)
                current_bb_middle = df_5m.iloc[-1]['bb_middle']

                # Vérifier conditions de sortie
                should_exit = check_exit_conditions_bollinger(
                    current_trade["entry_price"],
                    current_price,
                    current_trade["side"],
                    current_bb_middle,
                    current_trade["candles_count"]
                )

                if should_exit:
                    print(f"🚪 Sortie détectée (bougie #{current_trade['candles_count']})", flush=True)
                    
                    # Fermer manuellement
                    try:
                        close_side = 'sell' if current_trade["side"] == 'long' else 'buy'
                        close_order = exchange.create_market_order(
                            SYMBOL,
                            close_side,
                            current_trade["qty"],
                            params={'reduceOnly': True}
                        )
                        
                        # Calculer P&L
                        if current_trade["side"] == 'long':
                            pnl_pct = (current_price - current_trade["entry_price"]) / current_trade["entry_price"] * 100
                        else:
                            pnl_pct = (current_trade["entry_price"] - current_price) / current_trade["entry_price"] * 100
                        
                        result = "WIN" if pnl_pct > 0 else "LOSS"
                        
                        # Logger
                        log_trade(
                            SYMBOL,
                            current_trade["side"],
                            current_trade["qty"],
                            current_trade["entry_price"],
                            current_price,
                            pnl_pct,
                            result
                        )
                        
                        # Notification
                        duration = (datetime.now(timezone.utc) - current_trade["entry_time"]).seconds
                        msg = (
                            f"{'🟢 WIN' if pnl_pct > 0 else '🔴 LOSS'} - MAIN BOLLINGER FERMÉ\n"
                            f"Stratégie: Bollinger Bounce\n"
                            f"Direction: {current_trade['side'].upper()}\n"
                            f"Entrée: {round(current_trade['entry_price'], 2)}\n"
                            f"Sortie: {round(current_price, 2)}\n"
                            f"P&L: {pnl_pct:+.2f}%\n"
                            f"Durée: {duration}s\n"
                            f"Bougies: {current_trade['candles_count']}"
                        )
                        send_telegram(msg)
                        
                    except Exception as e:
                        print(f"❌ Erreur fermeture: {e}", flush=True)
                    
                    # Reset
                    in_position = False
                    current_trade = {
                        "entry_price": 0,
                        "side": None,
                        "qty": 0,
                        "sl_price": 0,
                        "tp_price": 0,
                        "entry_time": None,
                        "candles_count": 0,
                        "bb_middle": 0,
                    }

                # Vérifier aussi si position fermée par SL/TP
                positions = exchange.fetch_positions([SYMBOL])
                pos = next((p for p in positions if p.get("symbol") == SYMBOL), None)

                if pos and safe_float(pos.get("contracts")) == 0:
                    print("🔔 Position fermée par SL/TP", flush=True)
                    in_position = False
                    current_trade = {
                        "entry_price": 0,
                        "side": None,
                        "qty": 0,
                        "sl_price": 0,
                        "tp_price": 0,
                        "entry_time": None,
                        "candles_count": 0,
                        "bb_middle": 0,
                    }

            # Attendre 1 minute (cycle 1m)
            time.sleep(60)

        except Exception as e:
            print("❌ Main Bollinger error:", e, flush=True)
            send_telegram(f"❌ Main Bollinger error: {e}")
            time.sleep(60)


if __name__ == "__main__":
    run()
