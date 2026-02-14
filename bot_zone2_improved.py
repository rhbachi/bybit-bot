import time
import pandas as pd
from datetime import datetime, timezone

from config import exchange, SYMBOL, TIMEFRAME, CAPITAL, RISK_PER_TRADE, LEVERAGE
from strategy_zone2_improved import apply_indicators, check_signal
from risk import calculate_position_size
from notifier import send_telegram
from logger import init_logger, log_trade

# =========================
# PARAMÈTRES STRATÉGIE ZONE2
# =========================
STOP_LOSS_PCT = 0.006
RR_MULTIPLIER = 2.0
MAX_TRADES_PER_DAY = 8
COOLDOWN_SECONDS = 900

# =========================
# ÉTAT
# =========================
in_position = False
trades_today = 0
last_trade_time = None
current_day = datetime.now(timezone.utc).date()

current_trade = {
    "entry_price": 0,
    "side": None,
    "qty": 0,
    "sl_price": 0,
    "tp_price": 0,
}

# =========================
# UTILS
# =========================
def safe_float(v, default=0.0):
    try:
        return float(v) if v is not None else default
    except Exception:
        return default


def reset_daily():
    global trades_today, current_day
    today = datetime.now(timezone.utc).date()
    if today != current_day:
        trades_today = 0
        current_day = today
        print("🔄 Nouveau jour (Zone2)", flush=True)
        send_telegram("🔄 Zone2 - Nouveau jour")


def fetch_data():
    ohlcv = exchange.fetch_ohlcv(SYMBOL, TIMEFRAME, limit=100)
    return pd.DataFrame(
        ohlcv,
        columns=["time", "open", "high", "low", "close", "volume"]
    )


def get_available_balance():
    try:
        balance = exchange.fetch_balance()
        usdt_balance = balance.get('USDT', {})
        available = safe_float(usdt_balance.get('free', 0))
        print(f"💰 Zone2 - Solde disponible: {available} USDT", flush=True)
        return available
    except Exception as e:
        print(f"⚠️ Zone2 - Erreur get_available_balance: {e}", flush=True)
        return 0


def get_min_notional(symbol):
    try:
        market = exchange.market(symbol)
        min_notional = market.get("limits", {}).get("cost", {}).get("min")
        if min_notional is None or min_notional <= 0:
            return 5.0
        return float(min_notional)
    except Exception as e:
        print("⚠️ Zone2 - Erreur get_min_notional:", e, flush=True)
        return 5.0


def adjust_qty_to_min_notional(symbol, qty, price):
    min_notional = get_min_notional(symbol)
    notional = qty * price

    if notional >= min_notional:
        return qty

    min_qty = min_notional / price
    print(
        f"⚠️ Zone2 - Ajustement qty | "
        f"Old={round(notional,2)} | Min={min_notional} | "
        f"New qty={round(min_qty,6)}",
        flush=True,
    )
    return round(min_qty, 6)


def place_sl_tp_orders(symbol, side, qty, entry_price, sl_price, tp_price):
    """Place SL/TP avec triggerDirection (Bybit V5)"""
    try:
        # Méthode 1 : trading_stop endpoint
        try:
            exchange.private_post_v5_position_trading_stop({
                'category': 'linear',
                'symbol': symbol.replace('/', '').replace(':USDT', ''),
                'stopLoss': str(sl_price),
                'takeProfit': str(tp_price),
                'tpTriggerBy': 'LastPrice',
                'slTriggerBy': 'LastPrice',
                'positionIdx': 0,
            })
            
            print(f"✅ Zone2 - SL/TP placés: SL={round(sl_price, 2)} | TP={round(tp_price, 2)}", flush=True)
            return True
            
        except Exception as e1:
            print(f"⚠️ Zone2 - Méthode 1 échouée: {e1}", flush=True)
            
            # Méthode 2 : Ordres conditionnels avec triggerDirection
            try:
                order_side_close = 'sell' if side == 'long' else 'buy'
                
                # Stop Loss
                exchange.create_order(
                    symbol,
                    'market',
                    order_side_close,
                    qty,
                    None,
                    params={
                        'stopLoss': sl_price,
                        'triggerDirection': 'descending' if side == 'long' else 'ascending',
                        'triggerBy': 'LastPrice',
                        'reduceOnly': True,
                        'orderType': 'Market',
                        'triggerPrice': sl_price,
                    }
                )
                
                # Take Profit
                exchange.create_order(
                    symbol,
                    'market',
                    order_side_close,
                    qty,
                    None,
                    params={
                        'takeProfit': tp_price,
                        'triggerDirection': 'ascending' if side == 'long' else 'descending',
                        'triggerBy': 'LastPrice',
                        'reduceOnly': True,
                        'orderType': 'Market',
                        'triggerPrice': tp_price,
                    }
                )
                
                print(f"✅ Zone2 - SL/TP placés (méthode 2)", flush=True)
                return True
                
            except Exception as e2:
                print(f"❌ Zone2 - Méthode 2 échouée: {e2}", flush=True)
                return False
        
    except Exception as e:
        print(f"❌ Zone2 - Erreur SL/TP: {e}", flush=True)
        return False


def close_position_immediately(symbol, side, qty):
    """Ferme immédiatement si SL/TP impossibles"""
    try:
        close_side = 'sell' if side == 'long' else 'buy'
        exchange.create_market_order(symbol, close_side, qty, params={'reduceOnly': True})
        print(f"🛑 Zone2 - Position fermée (pas de SL/TP)", flush=True)
        send_telegram(f"🛑 ZONE2 - Position fermée par sécurité")
        return True
    except Exception as e:
        print(f"❌ Zone2 - Impossible de fermer: {e}", flush=True)
        return False


# =========================
# MAIN
# =========================
def run():
    global in_position, trades_today, last_trade_time, current_trade

    print("🤖 Zone2 Bot V6.1 FIXED démarré", flush=True)
    send_telegram("🤖 Zone2 Bot V6.1 FIXED démarré\n✅ SL/TP obligatoires activés")

    init_logger()

    try:
        exchange.set_leverage(LEVERAGE, SYMBOL)
        print(f"⚙️ Zone2 - Leverage: {LEVERAGE}x", flush=True)
    except Exception as e:
        if "110043" not in str(e):
            print(f"⚠️ Zone2 - Erreur set_leverage: {e}", flush=True)
        else:
            print(f"⚙️ Zone2 - Leverage déjà à {LEVERAGE}x", flush=True)

    while True:
        try:
            print("⏳ Zone2 - Analyse marché...", flush=True)

            reset_daily()

            if trades_today >= MAX_TRADES_PER_DAY:
                print("🛑 Zone2 - Max trades atteints", flush=True)
                time.sleep(300)
                continue

            if last_trade_time and time.time() - last_trade_time < COOLDOWN_SECONDS:
                print("⏸ Zone2 - Cooldown actif", flush=True)
                time.sleep(60)
                continue

            df = fetch_data()
            df = apply_indicators(df)
            signal = check_signal(df)

            # ===== OUVERTURE =====
            if signal and not in_position:
                # Vérifier solde
                available_balance = get_available_balance()
                
                if available_balance < 5:
                    print("❌ Zone2 - Solde insuffisant", flush=True)
                    send_telegram(f"⚠️ ZONE2 - Solde insuffisant: {available_balance} USDT")
                    time.sleep(300)
                    continue
                
                # Capital effectif
                effective_capital = min(CAPITAL, available_balance * 0.95)
                print(f"📊 Zone2 - Capital effectif: {round(effective_capital, 2)} USDT", flush=True)
                
                price = df.iloc[-1].close

                qty = calculate_position_size(
                    effective_capital,
                    RISK_PER_TRADE,
                    STOP_LOSS_PCT,
                    price,
                    LEVERAGE
                )

                qty = adjust_qty_to_min_notional(SYMBOL, qty, price)

                if qty <= 0:
                    print("⚠️ Zone2 - Qty invalide", flush=True)
                    time.sleep(300)
                    continue

                # Calculer SL/TP
                # STRATÉGIE MEAN REVERSION : On inverse SL et TP !
                # Le prix devrait revenir vers l'EMA (ancien SL devient TP)
                # Si ça continue dans la direction, on coupe (ancien TP devient SL)
                if signal == "long":
                    # Prix calculé "SL" = objectif de retour = TP réel
                    calculated_sl = price * (1 - STOP_LOSS_PCT)
                    # Prix calculé "TP" = protection si continue = SL réel
                    calculated_tp = price * (1 + (STOP_LOSS_PCT * RR_MULTIPLIER))
                    
                    # INVERSION : SL ↔ TP
                    sl_price = calculated_tp  # Protection si ça monte
                    tp_price = calculated_sl  # Objectif de retour vers le bas
                    order_side = "buy"
                else:
                    # Prix calculé "SL" = objectif de retour = TP réel
                    calculated_sl = price * (1 + STOP_LOSS_PCT)
                    # Prix calculé "TP" = protection si continue = SL réel
                    calculated_tp = price * (1 - (STOP_LOSS_PCT * RR_MULTIPLIER))
                    
                    # INVERSION : SL ↔ TP
                    sl_price = calculated_tp  # Protection si ça baisse
                    tp_price = calculated_sl  # Objectif de retour vers le haut
                    order_side = "sell"

                # Passer ordre
                print(f"📊 Zone2 - Ouverture {signal.upper()} | Qty={qty}", flush=True)
                
                order = exchange.create_market_order(
                    SYMBOL,
                    order_side,
                    qty
                )

                # Placer SL/TP (OBLIGATOIRE)
                print("🔒 Zone2 - Placement SL/TP...", flush=True)
                sl_tp_success = place_sl_tp_orders(SYMBOL, signal, qty, price, sl_price, tp_price)

                # SI ÉCHEC → FERMER
                if not sl_tp_success:
                    print("🚨 Zone2 - SL/TP impossible → Fermeture immédiate", flush=True)
                    send_telegram(f"🚨 ZONE2 ALERTE\nSL/TP impossible\nPosition fermée par sécurité")
                    
                    close_position_immediately(SYMBOL, signal, qty)
                    time.sleep(300)
                    continue

                # Mettre à jour état (seulement si SL/TP OK)
                in_position = True
                trades_today += 1
                last_trade_time = time.time()

                current_trade = {
                    "entry_price": price,
                    "side": signal,
                    "qty": qty,
                    "sl_price": sl_price,
                    "tp_price": tp_price,
                    "entry_time": datetime.now(timezone.utc),
                }

                # Notification
                msg = (
                    f"🎯 ZONE2 TRADE OUVERT\n"
                    f"Type: Mean Reversion\n"
                    f"Direction: {signal.upper()}\n"
                    f"Prix: {round(price, 2)} USDT\n"
                    f"Quantité: {qty}\n"
                    f"SL: {round(sl_price, 2)}\n"
                    f"TP: {round(tp_price, 2)}\n"
                    f"R:R = 1:{RR_MULTIPLIER}\n"
                    f"SL/TP: ✅ PLACÉS ET CONFIRMÉS"
                )
                print(msg, flush=True)
                send_telegram(msg)

            # ===== VÉRIFIER CLÔTURE =====
            if in_position:
                positions = exchange.fetch_positions([SYMBOL])
                pos = next((p for p in positions if p.get("symbol") == SYMBOL), None)

                if pos and safe_float(pos.get("contracts")) == 0:
                    pnl = safe_float(pos.get("unrealizedPnl"))
                    result = "WIN" if pnl > 0 else "LOSS"
                    exit_price = current_trade["tp_price"] if pnl > 0 else current_trade["sl_price"]

                    log_trade(
                        SYMBOL,
                        current_trade["side"],
                        current_trade["qty"],
                        current_trade["entry_price"],
                        exit_price,
                        pnl,
                        result
                    )

                    duration = datetime.now(timezone.utc) - current_trade["entry_time"]
                    duration_minutes = int(duration.total_seconds() / 60)

                    msg = (
                        f"{'🟢 WIN' if pnl > 0 else '🔴 LOSS'} - ZONE2 FERMÉ\n"
                        f"Type: Mean Reversion\n"
                        f"Direction: {current_trade['side'].upper()}\n"
                        f"Entrée: {round(current_trade['entry_price'], 2)}\n"
                        f"Sortie: {round(exit_price, 2)}\n"
                        f"PnL: {round(pnl, 2)} USDT\n"
                        f"Durée: {duration_minutes} min\n"
                        f"Trades: {trades_today}/{MAX_TRADES_PER_DAY}"
                    )
                    print(msg, flush=True)
                    send_telegram(msg)

                    in_position = False
                    current_trade = {
                        "entry_price": 0,
                        "side": None,
                        "qty": 0,
                        "sl_price": 0,
                        "tp_price": 0,
                    }

            time.sleep(300)

        except Exception as e:
            print("❌ Zone2 error:", e, flush=True)
            send_telegram(f"❌ Zone2 error: {e}")
            time.sleep(60)


if __name__ == "__main__":
    run()
