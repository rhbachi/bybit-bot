import time
import pandas as pd
from datetime import datetime, timezone

from config import (
    exchange,
    SYMBOL,
    TIMEFRAME,
    CAPITAL,
    RISK_PER_TRADE,
    LEVERAGE,
)

from strategy_main import apply_indicators, check_signal
from risk import calculate_position_size
from notifier import send_telegram
from logger import init_logger, log_trade

# =========================
# PARAMÈTRES STRATÉGIE
# =========================
STOP_LOSS_PCT = 0.006
RR_MULTIPLIER = 2.3
MAX_TRADES_PER_DAY = 10
COOLDOWN_SECONDS = 600

# =========================
# ÉTAT
# =========================
in_position = False
trades_today = 0
last_trade_time = None
current_day = datetime.now(timezone.utc).date()

# Variables pour tracker le trade en cours
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
        print("🔄 Nouveau jour", flush=True)
        send_telegram("🔄 Nouveau jour — compteurs réinitialisés")


def fetch_data():
    ohlcv = exchange.fetch_ohlcv(SYMBOL, TIMEFRAME, limit=120)
    return pd.DataFrame(
        ohlcv,
        columns=["time", "open", "high", "low", "close", "volume"],
    )


def get_available_balance():
    """
    Récupère le solde USDT disponible
    """
    try:
        balance = exchange.fetch_balance()
        usdt_balance = balance.get('USDT', {})
        available = safe_float(usdt_balance.get('free', 0))
        
        print(f"💰 Solde disponible: {available} USDT", flush=True)
        return available
    
    except Exception as e:
        print(f"⚠️ Erreur get_available_balance: {e}", flush=True)
        return 0


def get_min_notional(symbol):
    """
    Bybit / ccxt peut retourner None → fallback obligatoire
    """
    try:
        market = exchange.market(symbol)
        min_notional = market.get("limits", {}).get("cost", {}).get("min")

        if min_notional is None or min_notional <= 0:
            return 5.0

        return float(min_notional)

    except Exception as e:
        print("⚠️ Erreur get_min_notional:", e, flush=True)
        return 5.0


def adjust_qty_to_min_notional(symbol, qty, price):
    min_notional = get_min_notional(symbol)
    notional = qty * price

    if notional >= min_notional:
        return qty

    min_qty = min_notional / price

    print(
        f"⚠️ Ajustement qty → minNotional | "
        f"Old notional={round(notional,2)} | "
        f"MinNotional={min_notional} | "
        f"New qty={round(min_qty,6)}",
        flush=True,
    )

    return round(min_qty, 6)


def place_sl_tp_orders(symbol, side, qty, entry_price, sl_price, tp_price):
    """
    Place les ordres Stop Loss et Take Profit conditionnels sur Bybit
    
    Args:
        symbol: Symbole de trading (ex: ETH/USDT:USDT)
        side: 'long' ou 'short'
        qty: Quantité
        entry_price: Prix d'entrée
        sl_price: Prix du Stop Loss
        tp_price: Prix du Take Profit
    """
    try:
        # Pour Bybit, les ordres conditionnels utilisent des paramètres spécifiques
        if side == "long":
            # Stop Loss pour position LONG
            sl_params = {
                'stopLoss': {
                    'triggerPrice': sl_price,
                    'price': sl_price,
                    'type': 'market',
                }
            }
            
            # Take Profit pour position LONG
            tp_params = {
                'takeProfit': {
                    'triggerPrice': tp_price,
                    'price': tp_price,
                    'type': 'market',
                }
            }
            
        else:  # short
            # Stop Loss pour position SHORT
            sl_params = {
                'stopLoss': {
                    'triggerPrice': sl_price,
                    'price': sl_price,
                    'type': 'market',
                }
            }
            
            # Take Profit pour position SHORT
            tp_params = {
                'takeProfit': {
                    'triggerPrice': tp_price,
                    'price': tp_price,
                    'type': 'market',
                }
            }
        
        # Bybit V5 : placer SL/TP via modify position
        exchange.set_margin_mode('isolated', symbol)
        exchange.edit_order(
            id=None,
            symbol=symbol,
            type='market',
            side='buy' if side == 'long' else 'sell',
            amount=qty,
            params={
                'stopLoss': sl_price,
                'takeProfit': tp_price,
                'positionIdx': 0,  # One-way mode
            }
        )
        
        print(f"✅ SL/TP placés: SL={round(sl_price, 2)} | TP={round(tp_price, 2)}", flush=True)
        return True
        
    except Exception as e:
        print(f"⚠️ Erreur placement SL/TP: {e}", flush=True)
        # Essayer méthode alternative
        try:
            # Utiliser les ordres conditionnels standards
            if side == "long":
                # Stop Loss = ordre de vente si prix descend
                exchange.create_order(
                    symbol,
                    'stop_market',
                    'sell',
                    qty,
                    params={'stopPrice': sl_price, 'reduceOnly': True}
                )
                
                # Take Profit = ordre de vente si prix monte
                exchange.create_order(
                    symbol,
                    'take_profit_market',
                    'sell',
                    qty,
                    params={'stopPrice': tp_price, 'reduceOnly': True}
                )
            else:
                # Stop Loss = ordre d'achat si prix monte
                exchange.create_order(
                    symbol,
                    'stop_market',
                    'buy',
                    qty,
                    params={'stopPrice': sl_price, 'reduceOnly': True}
                )
                
                # Take Profit = ordre d'achat si prix descend
                exchange.create_order(
                    symbol,
                    'take_profit_market',
                    'buy',
                    qty,
                    params={'stopPrice': tp_price, 'reduceOnly': True}
                )
            
            print(f"✅ SL/TP placés (méthode alternative)", flush=True)
            return True
            
        except Exception as e2:
            print(f"❌ Échec placement SL/TP (toutes méthodes): {e2}", flush=True)
            send_telegram(f"⚠️ ATTENTION: Trade ouvert SANS SL/TP!\nErreur: {e2}")
            return False


# =========================
# MAIN
# =========================
def run():
    global in_position, trades_today, last_trade_time, current_trade

    print("🤖 Bot Bybit V6.0 IMPROVED démarré", flush=True)
    send_telegram("🤖 Bot Bybit V6.0 IMPROVED démarré\n✅ SL/TP automatiques activés")

    init_logger()

    try:
        exchange.set_leverage(LEVERAGE, SYMBOL)
        print(f"⚙️ Leverage configuré: {LEVERAGE}x", flush=True)
    except Exception as e:
        print(f"⚠️ Erreur set_leverage: {e}", flush=True)

    while True:
        try:
            print("⏳ Analyse marché...", flush=True)

            reset_daily()

            if trades_today >= MAX_TRADES_PER_DAY:
                print("🛑 Max trades atteints", flush=True)
                time.sleep(300)
                continue

            if last_trade_time and time.time() - last_trade_time < COOLDOWN_SECONDS:
                print("⏸ Cooldown actif", flush=True)
                time.sleep(60)
                continue

            df = fetch_data()
            df = apply_indicators(df)
            signal = check_signal(df)

            # ===== OUVERTURE DE POSITION =====
            if signal and not in_position:
                # 1️⃣ Vérifier le solde disponible
                available_balance = get_available_balance()
                
                if available_balance < 5:  # Minimum 5 USDT
                    print("❌ Solde insuffisant pour trader", flush=True)
                    send_telegram(f"⚠️ Solde insuffisant: {available_balance} USDT")
                    time.sleep(300)
                    continue
                
                # 2️⃣ Calculer la position
                price = df.iloc[-1].close

                qty = calculate_position_size(
                    CAPITAL,
                    RISK_PER_TRADE,
                    STOP_LOSS_PCT,
                    price,
                    LEVERAGE,
                )

                # Vérifier que la position ne dépasse pas le capital disponible
                position_value = (qty * price) / LEVERAGE
                if position_value > available_balance:
                    print(f"⚠️ Position trop grande ({position_value} > {available_balance}), ajustement...", flush=True)
                    qty = (available_balance * 0.95 * LEVERAGE) / price  # 95% du capital pour sécurité
                    qty = round(qty, 4)

                # Ajuster pour minNotional
                qty = adjust_qty_to_min_notional(SYMBOL, qty, price)

                if qty <= 0:
                    print("⚠️ Qty invalide → trade ignoré", flush=True)
                    time.sleep(300)
                    continue

                # 3️⃣ Calculer SL et TP
                if signal == "long":
                    sl_price = price * (1 - STOP_LOSS_PCT)
                    tp_price = price * (1 + (STOP_LOSS_PCT * RR_MULTIPLIER))
                    order_side = "buy"
                else:  # short
                    sl_price = price * (1 + STOP_LOSS_PCT)
                    tp_price = price * (1 - (STOP_LOSS_PCT * RR_MULTIPLIER))
                    order_side = "sell"

                # 4️⃣ Passer l'ordre d'entrée
                print(f"📊 Ouverture {signal.upper()} | Qty={qty} | Prix={round(price, 2)}", flush=True)
                
                order = exchange.create_market_order(
                    SYMBOL,
                    order_side,
                    qty,
                )

                # 5️⃣ Placer les ordres SL/TP
                sl_tp_success = place_sl_tp_orders(SYMBOL, signal, qty, price, sl_price, tp_price)

                # 6️⃣ Mettre à jour l'état
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

                # 7️⃣ Notification
                msg = (
                    f"🚀 TRADE OUVERT\n"
                    f"Direction: {signal.upper()}\n"
                    f"Prix: {round(price, 2)} USDT\n"
                    f"Quantité: {qty}\n"
                    f"SL: {round(sl_price, 2)} (-{STOP_LOSS_PCT*100}%)\n"
                    f"TP: {round(tp_price, 2)} (+{STOP_LOSS_PCT*RR_MULTIPLIER*100}%)\n"
                    f"Risk/Reward: 1:{RR_MULTIPLIER}\n"
                    f"SL/TP: {'✅' if sl_tp_success else '❌ MANUEL REQUIS'}"
                )
                print(msg, flush=True)
                send_telegram(msg)

            # ===== VÉRIFIER CLÔTURE =====
            if in_position:
                positions = exchange.fetch_positions([SYMBOL])
                pos = next((p for p in positions if p.get("symbol") == SYMBOL), None)

                # Position fermée
                if pos and safe_float(pos.get("contracts")) == 0:
                    pnl = safe_float(pos.get("unrealizedPnl"))
                    
                    # Déterminer si c'est un WIN ou LOSS
                    result = "WIN" if pnl > 0 else "LOSS"
                    
                    # Estimer le prix de sortie
                    exit_price = current_trade["tp_price"] if pnl > 0 else current_trade["sl_price"]

                    # Logger avec les vraies données
                    log_trade(
                        SYMBOL,
                        current_trade["side"],
                        current_trade["qty"],
                        current_trade["entry_price"],
                        exit_price,
                        pnl,
                        result
                    )

                    # Calculer la durée du trade
                    duration = datetime.now(timezone.utc) - current_trade["entry_time"]
                    duration_minutes = int(duration.total_seconds() / 60)

                    # Notification détaillée
                    msg = (
                        f"{'🟢 WIN' if pnl > 0 else '🔴 LOSS'} - TRADE FERMÉ\n"
                        f"Direction: {current_trade['side'].upper()}\n"
                        f"Entrée: {round(current_trade['entry_price'], 2)} USDT\n"
                        f"Sortie: {round(exit_price, 2)} USDT\n"
                        f"PnL: {round(pnl, 2)} USDT ({round((pnl/CAPITAL)*100, 2)}%)\n"
                        f"Durée: {duration_minutes} min\n"
                        f"Trades aujourd'hui: {trades_today}/{MAX_TRADES_PER_DAY}"
                    )
                    print(msg, flush=True)
                    send_telegram(msg)

                    # Reset état
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
            print("❌ Erreur bot:", e, flush=True)
            send_telegram(f"❌ Erreur bot: {e}")
            time.sleep(60)


if __name__ == "__main__":
    run()
