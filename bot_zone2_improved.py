import time
import pandas as pd
import pytz
from datetime import datetime, timezone

from config import exchange, SYMBOL, TIMEFRAME, CAPITAL, RISK_PER_TRADE, LEVERAGE
from strategy_zone2_improved import apply_indicators, check_signal
from risk import calculate_position_size
from notifier import send_telegram
from logger import init_logger, log_trade

# =========================
# PARAMÈTRES STRATÉGIE ZONE2
# =========================
NY_TZ = pytz.timezone("America/New_York")
JOURS_SEMAINE = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]

STOP_LOSS_PCT = 0.006
RR_MULTIPLIER = 2.0
MAX_TRADES_PER_DAY = 8
COOLDOWN_SECONDS = 900
TRAILING_STOP_PCT = 0.005        # 0.5% distance de suivi du trailing
TRAILING_ACTIVATION_PCT = 0.80  # S'active seulement à 80% de la distance vers le TP

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
    "peak_price": 0,
    "trailing_sl": 0,
    "trailing_active": False,
    "entry_time": None,
}

EMPTY_TRADE = {
    "entry_price": 0,
    "side": None,
    "qty": 0,
    "sl_price": 0,
    "tp_price": 0,
    "peak_price": 0,
    "trailing_sl": 0,
    "trailing_active": False,
    "entry_time": None,
}

# =========================
# UTILS
# =========================
def safe_float(v, default=0.0):
    try:
        return float(v) if v is not None else default
    except Exception:
        return default


def is_trading_hours():
    """Retourne True si on est Lun-Ven entre 10h00 et 16h00 heure New York."""
    now_ny = datetime.now(NY_TZ)
    if now_ny.weekday() >= 5:  # Samedi=5, Dimanche=6
        return False
    return 10 <= now_ny.hour < 16


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


def get_current_price():
    try:
        ticker = exchange.fetch_ticker(SYMBOL)
        return safe_float(ticker.get('last'))
    except Exception as e:
        print(f"⚠️ Zone2 - Erreur fetch_ticker: {e}", flush=True)
        return 0


def check_trailing_stop():
    """
    Trailing stop logiciel à 2 phases :
      Phase 1 - Attente : inactif jusqu'à ce que le prix atteigne 80% de la distance entry→sl_price
      Phase 2 - Actif   : trail_sl = max(entry+0.5%, peak-0.5%) pour long
                                    min(entry-0.5%, peak+0.5%) pour short
    Retourne True si la position a été fermée par le trailing stop.
    """
    global in_position, current_trade

    current_price = get_current_price()
    if current_price <= 0:
        return False

    side = current_trade["side"]
    entry_price = current_trade["entry_price"]
    sl_price = current_trade["sl_price"]
    qty = current_trade["qty"]

    # Seuil d'activation = entry + 80% de la distance entry→sl_price
    # sl_price est la borne "distante" dans la direction favorable :
    #   LONG  → sl_price = entry * 1.012 (au-dessus) → activation à entry * 1.0096
    #   SHORT → sl_price = entry * 0.988 (en-dessous) → activation à entry * 0.9904
    activation_price = round(
        entry_price + TRAILING_ACTIVATION_PCT * (sl_price - entry_price), 4
    )

    # ── Phase 1 : trailing pas encore actif ──────────────────────────────────
    if not current_trade["trailing_active"]:
        activated = (
            (side == "long"  and current_price >= activation_price) or
            (side == "short" and current_price <= activation_price)
        )
        if not activated:
            progress = abs(current_price - entry_price) / abs(activation_price - entry_price) * 100
            print(
                f"⏳ Trail inactif | Prix={current_price:.2f} | "
                f"Activation={activation_price:.2f} | Progression={progress:.1f}%",
                flush=True
            )
            return False

        # Activation !
        current_trade["trailing_active"] = True
        current_trade["peak_price"] = current_price

        # SL initial = breakeven + 0.5% (plancher garanti)
        if side == "long":
            current_trade["trailing_sl"] = round(
                max(entry_price * (1 + TRAILING_STOP_PCT),
                    current_price * (1 - TRAILING_STOP_PCT)), 4
            )
        else:
            current_trade["trailing_sl"] = round(
                min(entry_price * (1 - TRAILING_STOP_PCT),
                    current_price * (1 + TRAILING_STOP_PCT)), 4
            )

        print(
            f"✅ Zone2 - Trailing ACTIVÉ | {side.upper()} | Prix={current_price:.2f} | "
            f"Seuil={activation_price:.2f} | Trail SL initial={current_trade['trailing_sl']:.2f}",
            flush=True
        )
        send_telegram(
            f"✅ ZONE2 Trailing ACTIVÉ\n"
            f"Direction: {side.upper()}\n"
            f"Prix: {current_price:.2f}\n"
            f"Seuil activé à: {activation_price:.2f} (80% TP)\n"
            f"Trail SL initial: {current_trade['trailing_sl']:.2f} (breakeven +{TRAILING_STOP_PCT*100}%)"
        )

    # ── Phase 2 : trailing actif ──────────────────────────────────────────────
    if side == "long":
        if current_price > current_trade["peak_price"]:
            current_trade["peak_price"] = current_price

        # Trail SL = max(breakeven+0.5%, peak-0.5%)  → ne redescend jamais sous entry+0.5%
        new_trail = round(
            max(entry_price * (1 + TRAILING_STOP_PCT),
                current_trade["peak_price"] * (1 - TRAILING_STOP_PCT)), 4
        )
        current_trade["trailing_sl"] = new_trail

        print(
            f"📈 Trail LONG | Prix={current_price:.2f} | "
            f"Peak={current_trade['peak_price']:.2f} | Trail SL={new_trail:.2f}",
            flush=True
        )
        triggered = current_price <= new_trail

    else:  # short
        if current_price < current_trade["peak_price"]:
            current_trade["peak_price"] = current_price

        # Trail SL = min(breakeven-0.5%, peak+0.5%)  → ne remonte jamais au-dessus entry-0.5%
        new_trail = round(
            min(entry_price * (1 - TRAILING_STOP_PCT),
                current_trade["peak_price"] * (1 + TRAILING_STOP_PCT)), 4
        )
        current_trade["trailing_sl"] = new_trail

        print(
            f"📉 Trail SHORT | Prix={current_price:.2f} | "
            f"Peak={current_trade['peak_price']:.2f} | Trail SL={new_trail:.2f}",
            flush=True
        )
        triggered = current_price >= new_trail

    if not triggered:
        return False

    # ── Déclenchement ────────────────────────────────────────────────────────
    print(
        f"🔔 Zone2 - TRAILING STOP {side.upper()} déclenché | "
        f"Prix={current_price:.2f} | Trail SL={current_trade['trailing_sl']:.2f}",
        flush=True
    )
    try:
        close_side = 'sell' if side == 'long' else 'buy'
        exchange.create_market_order(SYMBOL, close_side, qty, params={'reduceOnly': True})

        pnl_approx = round(
            (current_price - entry_price) * qty if side == "long"
            else (entry_price - current_price) * qty, 2
        )
        result = "WIN" if pnl_approx > 0 else "LOSS"
        duration = datetime.now(timezone.utc) - current_trade["entry_time"]

        log_trade(SYMBOL, side, qty, entry_price, current_price, pnl_approx, result)
        send_telegram(
            f"🔔 ZONE2 TRAILING STOP DÉCLENCHÉ\n"
            f"Direction: {side.upper()}\n"
            f"Entrée: {entry_price:.2f}\n"
            f"Sortie: {current_price:.2f}\n"
            f"PnL: ~{pnl_approx} USDT\n"
            f"Durée: {int(duration.total_seconds() / 60)} min"
        )
        in_position = False
        current_trade = dict(EMPTY_TRADE)
        return True
    except Exception as e:
        print(f"❌ Zone2 - Erreur fermeture trailing stop: {e}", flush=True)
        return False


# =========================
# MAIN
# =========================
def run():
    global in_position, trades_today, last_trade_time, current_trade

    print("🤖 Zone2 Bot V6.3 démarré", flush=True)
    send_telegram(
        f"🤖 Zone2 Bot V6.3 démarré\n"
        f"✅ SL/TP obligatoires activés\n"
        f"✅ Trailing Stop: {TRAILING_STOP_PCT*100}% | Activation: {int(TRAILING_ACTIVATION_PCT*100)}% du TP\n"
        f"✅ Créneau: Lun-Ven 10h-16h New York"
    )

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
            reset_daily()

            # ═══════════════════════════════════════════════════════════════════
            # PRIORITÉ 1 : Trailing stop + surveillance position
            # → Toujours actif, QUELLE QUE SOIT L'HEURE
            # ═══════════════════════════════════════════════════════════════════
            if in_position:
                # Trailing stop logiciel
                if check_trailing_stop():
                    time.sleep(60)
                    continue

                # Vérifier si Bybit a fermé la position (SL/TP natifs)
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
                    current_trade = dict(EMPTY_TRADE)

                # En position → sleep court pour rester réactif
                time.sleep(30)
                continue

            # ═══════════════════════════════════════════════════════════════════
            # PRIORITÉ 2 : Ouverture de nouveaux trades
            # → Filtrée par créneau horaire, cooldown, max trades
            # ═══════════════════════════════════════════════════════════════════

            # Filtre max trades journaliers
            if trades_today >= MAX_TRADES_PER_DAY:
                print("🛑 Zone2 - Max trades atteints", flush=True)
                time.sleep(300)
                continue

            # Filtre cooldown
            if last_trade_time and time.time() - last_trade_time < COOLDOWN_SECONDS:
                print("⏸ Zone2 - Cooldown actif", flush=True)
                time.sleep(60)
                continue

            # Filtre créneau horaire XAUUSDT : Lun-Ven 10h-16h New York
            if not is_trading_hours():
                now_ny = datetime.now(NY_TZ)
                print(
                    f"🕐 Zone2 - Hors créneau | "
                    f"{JOURS_SEMAINE[now_ny.weekday()]} {now_ny.strftime('%H:%M')} NY | "
                    f"Lun-Ven 10h00-16h00",
                    flush=True
                )
                time.sleep(300)
                continue

            # Analyse signal
            print("⏳ Zone2 - Analyse marché...", flush=True)
            df = fetch_data()
            df = apply_indicators(df)
            signal = check_signal(df)

            # ===== OUVERTURE =====
            if signal:
                available_balance = get_available_balance()
                if available_balance < 5:
                    print("❌ Zone2 - Solde insuffisant", flush=True)
                    send_telegram(f"⚠️ ZONE2 - Solde insuffisant: {available_balance} USDT")
                    time.sleep(300)
                    continue

                effective_capital = min(CAPITAL, available_balance * 0.95)
                print(f"📊 Zone2 - Capital effectif: {round(effective_capital, 2)} USDT", flush=True)
                price = df.iloc[-1].close

                qty = calculate_position_size(
                    effective_capital, RISK_PER_TRADE, STOP_LOSS_PCT, price, LEVERAGE
                )
                qty = adjust_qty_to_min_notional(SYMBOL, qty, price)

                if qty <= 0:
                    print("⚠️ Zone2 - Qty invalide", flush=True)
                    time.sleep(300)
                    continue

                if signal == "long":
                    calculated_sl = price * (1 - STOP_LOSS_PCT)
                    calculated_tp = price * (1 + (STOP_LOSS_PCT * RR_MULTIPLIER))
                    sl_price   = calculated_tp
                    tp_price   = calculated_sl
                    order_side = "buy"
                else:
                    calculated_sl = price * (1 + STOP_LOSS_PCT)
                    calculated_tp = price * (1 - (STOP_LOSS_PCT * RR_MULTIPLIER))
                    sl_price   = calculated_tp
                    tp_price   = calculated_sl
                    order_side = "sell"

                print(f"📊 Zone2 - Ouverture {signal.upper()} | Qty={qty}", flush=True)
                exchange.create_market_order(SYMBOL, order_side, qty)

                print("🔒 Zone2 - Placement SL/TP...", flush=True)
                sl_tp_success = place_sl_tp_orders(SYMBOL, signal, qty, price, sl_price, tp_price)

                if not sl_tp_success:
                    print("🚨 Zone2 - SL/TP impossible → Fermeture immédiate", flush=True)
                    send_telegram("🚨 ZONE2 ALERTE\nSL/TP impossible\nPosition fermée par sécurité")
                    close_position_immediately(SYMBOL, signal, qty)
                    time.sleep(300)
                    continue

                in_position = True
                trades_today += 1
                last_trade_time = time.time()

                trail_activation = round(
                    price + TRAILING_ACTIVATION_PCT * (sl_price - price), 4
                )
                current_trade = {
                    "entry_price":    price,
                    "side":           signal,
                    "qty":            qty,
                    "sl_price":       sl_price,
                    "tp_price":       tp_price,
                    "peak_price":     price,
                    "trailing_sl":    0,
                    "trailing_active": False,
                    "entry_time":     datetime.now(timezone.utc),
                }

                msg = (
                    f"🎯 ZONE2 TRADE OUVERT\n"
                    f"Direction: {signal.upper()}\n"
                    f"Prix: {round(price, 2)} USDT\n"
                    f"Quantité: {qty}\n"
                    f"SL: {round(sl_price, 2)}\n"
                    f"TP: {round(tp_price, 2)}\n"
                    f"R:R = 1:{RR_MULTIPLIER}\n"
                    f"SL/TP: ✅ PLACÉS\n"
                    f"Trailing actif à: {trail_activation:.2f} (80% TP)\n"
                    f"Trailing SL: {TRAILING_STOP_PCT*100}% breakeven"
                )
                print(msg, flush=True)
                send_telegram(msg)

            # Pas en position, pas de signal → sleep long
            time.sleep(300)

        except Exception as e:
            print("❌ Zone2 error:", e, flush=True)
            send_telegram(f"❌ Zone2 error: {e}")
            time.sleep(60)


if __name__ == "__main__":
    run()
