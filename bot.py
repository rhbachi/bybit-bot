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
COOLDOWN_SECONDS = 600

# =========================
# ÉTAT GLOBAL
# =========================
in_position = False
trades_today = 0
daily_loss = 0.0
current_day = datetime.now(timezone.utc).date()
last_trade_time = None


def safe_float(value, default=0.0):
    try:
        return float(value) if value is not None else default
    except Exception:
        return default


def reset_daily_counters():
    global trades_today, daily_loss, current_day
    today = datetime.now(timezone.utc).date()
    if today != current_day:
        trades_today = 0
        daily_loss = 0.0
        current_day = today
        send_telegram("🔄 Nouveau jour → compteurs réinitialisés")


def fetch_data():
    ohlcv = exchange.fetch_ohlcv(SYMBOL, TIMEFRAME, limit=100)
    return pd.DataFrame(
        ohlcv,
        columns=["time", "open", "high", "low", "close", "volume"]
    )


def get_safe_position_size(price):
    balance = exchange.fetch_balance()
    usdt_free = safe_float(balance.get("USDT", {}).get("free"))
    max_position_value = usdt_free * LEVERAGE * 0.9
    return round(max_position_value / price, 4) if price > 0 else 0


def enforce_min_qty(symbol, qty):
    if "BTC" in symbol:
        return max(qty, 0.001)
    if "ETH" in symbol:
        return max(qty, 0.01)
    return qty


def check_trade_closed():
    global in_position, daily_loss, last_trade_time

    if not in_position:
        return

    positions = exchange.fetch_positions([SYMBOL])
    pos = next((p for p in positions if p.get("symbol") == SYMBOL), None)
    if not pos:
        return

    contracts = safe_float(pos.get("contracts"))
    if contracts > 0:
        return

    pnl = safe_float(pos.get("realizedPnl"))
    result = "WIN ✅" if pnl > 0 else "LOSS ❌"

    log_trade(SYMBOL, result, 0, 0, 0, pnl, result)

    if pnl < 0:
        daily_loss += abs(pnl)

    in_position = False
    last_trade_time = time.time()

    msg = f"📊 *TRADE FERMÉ*\nPair: {SYMBOL}\nRésultat: {result}\nPnL: {round(pnl,2)} USDT"
    print(msg, flush=True)
    send_telegram(msg)


def place_trade(signal, qty, entry_price):
    global in_position, trades_today

    side = "buy" if signal == "long" else "sell"

    if signal == "long":
        stop_loss = entry_price * (1 - STOP_LOSS_PCT)
        tp = entry_price + (entry_price - stop_loss) * RR_MULTIPLIER
    else:
        stop_loss = entry_price * (1 + STOP_LOSS_PCT)
        tp = entry_price - (stop_loss - entry_price) * RR_MULTIPLIER

    exchange.create_market_order(
        symbol=SYMBOL,
        side=side,
        amount=qty,
        params={
            "stopLoss": stop_loss,
            "takeProfit": tp,
            "slTriggerBy": "LastPrice",
            "tpTriggerBy": "LastPrice"
        }
    )

    in_position = True
    trades_today += 1

    msg = (
        f"📈 *TRADE OUVERT*\n"
        f"Pair: {SYMBOL}\n"
        f"Direction: {signal.upper()}\n"
        f"Qty: {qty}\n"
        f"Entry: {round(entry_price,2)}\n"
        f"SL: {round(stop_loss,2)}\n"
        f"TP: {round(tp,2)}\n"
        f"RR: {RR_MULTIPLIER}"
    )
    print(msg, flush=True)
    send_telegram(msg)


def run():
    global in_position, daily_loss

    print("🤖 Bot lancé (BYBIT MAINNET – STABLE)", flush=True)
    send_telegram("🤖 Bot Bybit V5 démarré")
    init_logger()

    try:
        exchange.set_leverage(LEVERAGE, SYMBOL)
    except Exception:
        pass

    while True:
        try:
            reset_daily_counters()

            if daily_loss >= CAPITAL * MAX_DAILY_LOSS_PCT:
                send_telegram("🛑 Kill switch journalier – bot en pause")
                time.sleep(3600)
                continue

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
                    CAPITAL, RISK_PER_TRADE, STOP_LOSS_PCT, price, LEVERAGE
                )
                qty = min(theoretical_qty, get_safe_position_size(price))
                qty = enforce_min_qty(SYMBOL, qty)

                if qty > 0:
                    place_trade(signal, qty, price)

            check_trade_closed()
            time.sleep(300)

        except Exception as e:
            send_telegram(f"❌ Erreur bot: {e}")
            time.sleep(60)


run()
