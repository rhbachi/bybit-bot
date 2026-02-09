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

from strategy import apply_indicators, check_signal
from risk import calculate_position_size
from notifier import send_telegram
from logger import init_logger, log_trade

# =========================
# PARAMÈTRES STRATÉGIE
# =========================
STOP_LOSS_PCT = 0.006
RR_MULTIPLIER = 2.3
MAX_TRADES_PER_DAY = 10
MAX_DAILY_LOSS_PCT = 0.20
COOLDOWN_SECONDS = 600  # 10 min après clôture

# =========================
# ÉTAT GLOBAL
# =========================
in_position = False
trades_today = 0
daily_loss = 0.0
current_day = datetime.now(timezone.utc).date()

last_trade_time = None
open_trade_ts = None
open_trade_side = None
open_trade_qty = None
open_trade_entry = None

# =========================
# UTILS
# =========================
def safe_float(v, default=0.0):
    try:
        return float(v) if v is not None else default
    except Exception:
        return default


def reset_daily():
    global trades_today, daily_loss, current_day
    today = datetime.now(timezone.utc).date()
    if today != current_day:
        trades_today = 0
        daily_loss = 0.0
        current_day = today
        send_telegram("🔄 Nouveau jour – compteurs réinitialisés")


def fetch_data():
    ohlcv = exchange.fetch_ohlcv(SYMBOL, TIMEFRAME, limit=120)
    return pd.DataFrame(
        ohlcv, columns=["time", "open", "high", "low", "close", "volume"]
    )


def get_max_safe_qty(price):
    """
    Borne la taille par le balance Futures réel.
    """
    balance = exchange.fetch_balance()
    usdt_free = safe_float(balance.get("USDT", {}).get("free"))

    if usdt_free <= 5:
        return 0

    max_position_value = usdt_free * LEVERAGE * 0.9
    qty = max_position_value / price
    return round(qty, 4)


def enforce_min_qty(symbol, qty):
    """
    Respecte les minQty Bybit par symbole.
    """
    if "ETH" in symbol:
        return max(qty, 0.01)
    if "BTC" in symbol:
        return max(qty, 0.001)
    return qty


def has_sufficient_margin(symbol, qty, price):
    """
    Vérifie la marge requise AVANT d'envoyer l'ordre
    (garde-fou final anti-110007).
    """
    balance = exchange.fetch_balance()
    usdt_free = safe_float(balance.get("USDT", {}).get("free"))

    # marge estimée (notional / leverage) + buffer sécurité
    notional = qty * price
    required_margin = (notional / LEVERAGE) * 1.1

    return usdt_free >= required_margin


# =========================
# TRADE OPEN
# =========================
def place_trade(signal, qty, entry):
    global in_position, trades_today
    global open_trade_ts, open_trade_side, open_trade_qty, open_trade_entry

    side = "buy" if signal == "long" else "sell"

    if signal == "long":
        sl = entry * (1 - STOP_LOSS_PCT)
        tp = entry + (entry - sl) * RR_MULTIPLIER
    else:
        sl = entry * (1 + STOP_LOSS_PCT)
        tp = entry - (sl - entry) * RR_MULTIPLIER

    exchange.create_market_order(
        SYMBOL,
        side,
        qty,
        params={
            "stopLoss": sl,
            "takeProfit": tp,
            "slTriggerBy": "LastPrice",
            "tpTriggerBy": "LastPrice",
        },
    )

    in_position = True
    trades_today += 1

    open_trade_ts = exchange.milliseconds()
    open_trade_side = side
    open_trade_qty = qty
    open_trade_entry = entry

    msg = (
        f"📈 TRADE OUVERT\n"
        f"Pair: {SYMBOL}\n"
        f"Direction: {signal.upper()}\n"
        f"Qty: {qty}\n"
        f"Entry: {round(entry, 2)}\n"
        f"SL: {round(sl, 2)}\n"
        f"TP: {round(tp, 2)}\n"
        f"RR: {RR_MULTIPLIER}"
    )
    send_telegram(msg)
    print(msg, flush=True)


# =========================
# TRADE CLOSE (PRO V5)
# =========================
def check_trade_closed():
    global in_position, daily_loss, last_trade_time
    global open_trade_ts, open_trade_side, open_trade_qty, open_trade_entry

    if not in_position:
        return

    trades = exchange.fetch_my_trades(SYMBOL, since=open_trade_ts)
    if not trades:
        return

    close_trades = [t for t in trades if t["side"] != open_trade_side]
    if not close_trades:
        return

    close_price = safe_float(close_trades[-1]["price"])
    fee = sum(safe_float(t.get("fee", {}).get("cost")) for t in close_trades)

    if open_trade_side == "buy":
        pnl = (close_price - open_trade_entry) * open_trade_qty
    else:
        pnl = (open_trade_entry - close_price) * open_trade_qty

    pnl -= fee
    result = "WIN" if pnl > 0 else "LOSS"

    log_trade(
        symbol=SYMBOL,
        side=open_trade_side,
        qty=open_trade_qty,
        entry=open_trade_entry,
        exit_price=close_price,
        pnl=pnl,
        result=result,
    )

    if pnl < 0:
        daily_loss += abs(pnl)

    send_telegram(
        f"📊 TRADE FERMÉ\n"
        f"Pair: {SYMBOL}\n"
        f"Résultat: {result}\n"
        f"PnL: {round(pnl, 2)} USDT"
    )

    in_position = False
    last_trade_time = time.time()

    open_trade_ts = None
    open_trade_side = None
    open_trade_qty = None
    open_trade_entry = None


# =========================
# MAIN LOOP
# =========================
def run():
    global daily_loss

    print("🤖 Bot lancé (BYBIT MAINNET – PRO V5.2)", flush=True)
    send_telegram("🤖 Bot Bybit PRO V5.2 démarré")

    init_logger()

    try:
        exchange.set_leverage(LEVERAGE, SYMBOL)
    except Exception:
        pass

    while True:
        try:
            reset_daily()

            # Kill switch journalier
            if daily_loss >= CAPITAL * MAX_DAILY_LOSS_PCT:
                send_telegram("🛑 Kill switch journalier activé")
                time.sleep(3600)
                continue

            # Cooldown après clôture uniquement
            if last_trade_time and time.time() - last_trade_time < COOLDOWN_SECONDS:
                time.sleep(30)
                continue

            if trades_today >= MAX_TRADES_PER_DAY:
                time.sleep(1800)
                continue

            df = fetch_data()
            df = apply_indicators(df)
            signal = check_signal(df)

            print("⏳ Analyse marché...", flush=True)

            if signal and not in_position:
                price = df.iloc[-1].close

                theoretical_qty = calculate_position_size(
                    CAPITAL,
                    RISK_PER_TRADE,
                    STOP_LOSS_PCT,
                    price,
                    LEVERAGE,
                )

                safe_qty = get_max_safe_qty(price)
                qty = min(theoretical_qty, safe_qty)
                qty = enforce_min_qty(SYMBOL, qty)

                # Garde-fous finaux
                if qty <= 0:
                    print("⚠️ Capital insuffisant → trade ignoré", flush=True)
                    time.sleep(300)
                    continue

                if not has_sufficient_margin(SYMBOL, qty, price):
                    print("⚠️ Marge insuffisante → trade ignoré", flush=True)
                    send_telegram("⚠️ Bot1: marge insuffisante → attente")
                    time.sleep(300)
                    continue

                place_trade(signal, qty, price)

            check_trade_closed()
            time.sleep(300)

        except Exception as e:
            if "110007" in str(e):
                send_telegram("⚠️ Bot1: marge/capital insuffisant → attente")
                time.sleep(300)
            else:
                print("❌ Erreur bot:", e, flush=True)
                send_telegram(f"❌ Erreur bot: {e}")
                time.sleep(60)


run()
