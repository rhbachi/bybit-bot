import time
import pandas as pd
from datetime import datetime, timezone

from config import exchange, SYMBOL, CAPITAL, RISK_PER_TRADE, LEVERAGE
from strategy_zone2_scalping import (
    apply_indicators_5m,
    detect_trend_5m,
    check_entry_pattern_1m,
    check_exit_conditions,
    reset_state
)
from risk_improved import calculate_position_size
from notifier import send_telegram
from logger import init_logger, log_trade

# =========================
# PARAMÈTRES STRATÉGIE SCALPING
# =========================
TIMEFRAME_TREND = "5m"  # Détection tendance
TIMEFRAME_EXEC = "1m"   # Exécution
STOP_LOSS_PCT = 0.01    # 1%
TAKE_PROFIT_PCT = 0.03  # 3%
MAX_CANDLES = 3         # Sortie à la 3ème bougie
MIN_BODY_PCT = 0.002    # 0.2% - Taille minimum du corps (ignore dojis)

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
        print(f"💰 Scalping - Solde disponible: {available} USDT", flush=True)
        return available
    except Exception as e:
        print(f"⚠️ Scalping - Erreur get_balance: {e}", flush=True)
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
    print(f"⚠️ Scalping - Ajustement qty: {round(min_qty,6)}", flush=True)
    return round(min_qty, 6)


def place_sl_tp_orders(symbol, side, qty, entry_price, sl_price, tp_price):
    """Place les ordres SL/TP"""
    try:
        # Méthode 1 : trading_stop
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
            print(f"✅ Scalping - SL/TP optimisés: SL={round(sl_price, 2)} (Market) | TP={round(tp_price, 2)} (Limit)", flush=True)
            print(f"💰 Économie fees: 64% sur TP", flush=True)
            return True
        except Exception as e1:
            print(f"⚠️ Scalping - Méthode 1 échouée: {e1}", flush=True)
            
            # Méthode 2 : Ordres conditionnels OPTIMISÉS
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
            
            print(f"✅ Scalping - SL/TP optimisés (méthode 2)", flush=True)
            return True
    except Exception as e:
        print(f"❌ Scalping - Erreur SL/TP: {e}", flush=True)
        return False


def close_position_immediately(symbol, side, qty):
    """Ferme immédiatement si SL/TP impossibles"""
    try:
        close_side = 'sell' if side == 'long' else 'buy'
        exchange.create_market_order(symbol, close_side, qty, params={'reduceOnly': True})
        print(f"🛑 Scalping - Position fermée (sécurité)", flush=True)
        send_telegram(f"🛑 SCALPING - Position fermée par sécurité")
        return True
    except Exception as e:
        print(f"❌ Scalping - Impossible de fermer: {e}", flush=True)
        return False


# =========================
# MAIN
# =========================
def run():
    global in_position, current_trade, last_trade_time

    print("🤖 Bot ZONE2 SCALPING 3 Bougies V1.1 OPTIMISÉ démarré", flush=True)
    send_telegram("🤖 Bot ZONE2 SCALPING V1.1 OPTIMISÉ\n📊 5m trend + 1m execution\n⚡ SL: 1% | TP: 3%\n🚫 Ignore dojis\n💰 TP en LIMIT (économie 40% fees)")

    init_logger()

    try:
        exchange.set_leverage(LEVERAGE, SYMBOL)
        print(f"⚙️ Scalping - Leverage: {LEVERAGE}x", flush=True)
    except Exception as e:
        if "110043" not in str(e):
            print(f"⚠️ Scalping - Erreur leverage: {e}", flush=True)

    while True:
        try:
            print("⏳ Scalping - Analyse marché...", flush=True)

            # Cooldown entre trades
            if last_trade_time and time.time() - last_trade_time < COOLDOWN_SECONDS:
                time.sleep(10)
                continue

            # ===== PHASE 1 : Détection tendance sur 5m =====
            df_5m = fetch_ohlcv(TIMEFRAME_TREND, limit=100)
            df_5m = apply_indicators_5m(df_5m)
            trend = detect_trend_5m(df_5m)

            if trend:
                print(f"📈 Tendance détectée: {trend.upper()}", flush=True)

            # ===== PHASE 2 : Vérifier pattern sur 1m =====
            if not in_position and trend:
                df_1m = fetch_ohlcv(TIMEFRAME_EXEC, limit=50)
                signal = check_entry_pattern_1m(df_1m, trend)

                if signal:
                    print(f"🎯 Signal d'entrée: {signal.upper()}", flush=True)

                    # Vérifier solde
                    available_balance = get_available_balance()
                    if available_balance < 5:
                        print("❌ Scalping - Solde insuffisant", flush=True)
                        time.sleep(60)
                        continue

                    # Capital effectif
                    effective_capital = min(CAPITAL, available_balance * 0.95)

                    # Prix actuel
                    price = df_1m.iloc[-1].close

                    # Calculer position
                    qty = calculate_position_size(
                        effective_capital,
                        RISK_PER_TRADE,
                        STOP_LOSS_PCT,
                        price,
                        LEVERAGE
                    )

                    qty = adjust_qty_to_min_notional(SYMBOL, qty, price)

                    if qty <= 0:
                        print("⚠️ Scalping - Qty invalide", flush=True)
                        time.sleep(60)
                        continue

                    # Calculer SL/TP
                    if signal == 'long':
                        sl_price = price * (1 - STOP_LOSS_PCT)
                        tp_price = price * (1 + TAKE_PROFIT_PCT)
                        order_side = "buy"
                    else:  # short
                        sl_price = price * (1 + STOP_LOSS_PCT)
                        tp_price = price * (1 - TAKE_PROFIT_PCT)
                        order_side = "sell"

                    # Passer ordre
                    print(f"📊 Scalping - Ouverture {signal.upper()} | Qty={qty}", flush=True)

                    order = exchange.create_market_order(SYMBOL, order_side, qty)

                    # Placer SL/TP
                    print("🔒 Scalping - Placement SL/TP...", flush=True)
                    sl_tp_success = place_sl_tp_orders(SYMBOL, signal, qty, price, sl_price, tp_price)

                    if not sl_tp_success:
                        print("🚨 Scalping - SL/TP impossible → Fermeture", flush=True)
                        send_telegram(f"🚨 SCALPING ALERTE\nSL/TP impossible\nPosition fermée")
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
                    }

                    # Notification
                    msg = (
                        f"⚡ SCALPING TRADE OUVERT\n"
                        f"Direction: {signal.upper()}\n"
                        f"Prix: {round(price, 2)} USDT\n"
                        f"Quantité: {qty}\n"
                        f"SL: {round(sl_price, 2)} (-0.25%)\n"
                        f"TP: {round(tp_price, 2)} (+2%)\n"
                        f"Sortie: 3ème bougie OU +2%\n"
                        f"SL/TP: ✅ PLACÉS"
                    )
                    print(msg, flush=True)
                    send_telegram(msg)

            # ===== PHASE 3 : Gestion position ouverte =====
            if in_position:
                # Incrémenter compteur de bougies (cycle 1m)
                current_trade["candles_count"] += 1

                # Récupérer prix actuel
                df_1m = fetch_ohlcv(TIMEFRAME_EXEC, limit=2)
                current_price = df_1m.iloc[-1].close

                # Vérifier conditions de sortie
                should_exit = check_exit_conditions(
                    current_trade["entry_price"],
                    current_price,
                    current_trade["side"],
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
                            f"{'🟢 WIN' if pnl_pct > 0 else '🔴 LOSS'} - SCALPING FERMÉ\n"
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
                    }

            # Attendre 1 minute (cycle 1m)
            time.sleep(60)

        except Exception as e:
            print("❌ Scalping error:", e, flush=True)
            send_telegram(f"❌ Scalping error: {e}")
            time.sleep(60)


if __name__ == "__main__":
    run()
