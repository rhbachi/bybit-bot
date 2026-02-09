import time
import pandas as pd
from datetime import datetime, timezone

from config import (
    exchange,
    SYMBOLS,
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
state = {}
stats = {
    "trades": 0,
    "wins": 0,
    "losses": 0,
    "pnl": 0.0,
    "dd": 0.0,
}

current_day = datetime.now(timezone.utc).date()


# =========================
# UTILS
# =========================
def safe_float(v, default=0.0):
    try:
        return float(v) if v is not None else default
    except Exception:
        return default


def init_symbol_state(symbol):
    state[symbol] = {
        "in_position": False,
        "trades_today": 0,
        "daily_loss": 0.0,
        "last_trade_time": None,
        "open_trade_ts": None,
        "open_trade_side": None,
        "open_trade_qty": None,
        "open_trade_entry": None,
    }


def reset_daily_if_needed():
    global current_day, stats

    today = datetime.now(timezone.utc).date()
    if today != current_day:
        send_daily_summary()
        current_day = today

        stats = {"trades": 0, "wins": 0, "losses": 0, "pnl": 0.0, "dd": 0.0}
        for s in state.values():
            s["trades_today"] = 0
            s["daily_loss"] = 0.0


def send_daily_summary():
    msg = (
        "📊 *RÉSUMÉ JOURNALIER – BOT 1*\n"
        f"Paires: {', '.join(SYMBOLS)}\n"
        f"Trades: {stats['trades']}\n"
        f"Wins: {stats['wins']} | Losses: {stats['losses']}\n"
        f"PnL: {round(stats['pnl'],2)} USDT\n"
        f"DD journalier: {round(stats['dd'],2)} USDT"
    )
    send_telegram(msg)


def fetch_data(symbol):
    ohlcv = exchange.fetch_ohlcv(symbol, TIMEFRAME, limit=120)
    return pd.DataFrame(
        ohlcv, columns=["time", "open", "high", "low", "close", "volume"]
    )


def get_max_safe_qty(price):
    balance = exchange.fetch_balance()
    usdt_free = safe_float(balance.get("USDT", {}).get("free"))
    if usdt_free <= 5:
        return 0
    return round((usdt_free * LEVERAGE * 0.9) / price, 4)


def enforce_min_qty(symbol, qty):
    if "ETH" in symbol:
        return max(qty, 0.01)
    if "BTC" in symbol:
        return max(qty, 0.001)
    return qty


def has_sufficient_margin(qty, price):
    balance = exchange.fetch_balance()
    usdt_free = safe_float(balance.get("USDT", {}).get("free"))
    required = (qty * price / LEVERAGE) * 1.1
    return usdt_free >= required


# =========================
# TRADE CLOSE
# =========================
def check_trade_closed(symbol):
    s = state[symbol]
    if not s["in_position"]:
        return

    trades = exchange.fetch_my_trades(symbol, since=s["open_trade_ts"])
    if not trades:
        return

    closes = [t for t in trades if t["side"] != s["open_trade_side"]]
    if not closes:
        return

    close_price = safe_float(closes[-1]["price"])
    fee = sum(safe_float(t.get("fee", {}).get("cost")) for t in closes)

    if s["open_trade_side"] == "buy":
        pnl = (close_price - s["open_trade_entry"]) * s["open_trade_qty"]
    else:
        pnl = (s["open_trade_entry"] - close_price) * s["open_trade_qty"]

    pnl -= fee
    result = "WIN" if pnl > 0 else "LOSS"

    stats["trades"] += 1
    stats["pnl"] += pnl
    if pnl > 0:
        stats["wins"] += 1
    else:
        stats["losses"] += 1
        stats["dd"] += abs(pnl)

    log_trade(symbol, s["open_trade_side"], s["open_trade_qty"],
              s["open_trade_entry"], close_price, pnl, result)

    send_telegram(
        f"📊 TRADE FERMÉ\n"
        f"Pair: {symbol}\n"
        f"Résultat: {result}\n"
        f"PnL: {round(pnl,2)} USDT"
    )

    s["in_position"] = False
    s["last_trade_time"] = time.time()


# =========================
# MAIN LOOP
# =========================
def run():
    init_logger()

    for sym in SYMBOLS:
        init_symbol_state(sym)

    send_telegram("🤖 Bot Bybit V5.3 démarré (Multi-paires + Résumé journalier)")

    while True:
        try:
            reset_daily_if_needed()

            for symbol in SYMBOLS:
                s = state[symbol]

                if s["in_position"]:
                    check_trade_closed(symbol)
                    continue

                if s["trades_today"] >= MAX_TRADES_PER_DAY:
                    continue

                if s["last_trade_time"] and time.time() - s["last_trade_time"] < COOLDOWN_SECONDS:
                    continue

                df = fetch_data(symbol)
                df = apply_indicators(df)
                signal = check_signal(df)

                if not signal:
                    continue

                price = df.iloc[-1].close
                theoretical_qty = calculate_position_size(
                    CAPITAL, RISK_PER_TRADE, STOP_LOSS_PCT, price, LEVERAGE
                )

                qty = min(theoretical_qty, get_max_safe_qty(price))
                qty = enforce_min_qty(symbol, qty)

                if qty <= 0 or not has_sufficient_margin(qty, price):
                    continue

                side = "buy" if signal == "long" else "sell"

                sl = price * (1 - STOP_LOSS_PCT) if signal == "long" else price * (1 + STOP_LOSS_PCT)
                tp = price + (price - sl) * RR_MULTIPLIER if signal == "long" else price - (sl - price) * RR_MULTIPLIER

                exchange.create_market_order(
                    symbol, side, qty,
                    params={
                        "stopLoss": sl,
                        "takeProfit": tp,
                        "slTriggerBy": "LastPrice",
                        "tpTriggerBy": "LastPrice",
                    }
                )

                s.update({
                    "in_position": True,
                    "trades_today": s["trades_today"] + 1,
                    "open_trade_ts": exchange.milliseconds(),
                    "open_trade_side": side,
                    "open_trade_qty": qty,
                    "open_trade_entry": price,
                })

                send_telegram(
                    f"📈 TRADE OUVERT\nPair: {symbol}\nDir: {signal.upper()}\nQty: {qty}\nEntry: {round(price,2)}"
                )

            time.sleep(300)

        except Exception as e:
            send_telegram(f"❌ Bot1 erreur: {e}")
            time.sleep(60)


run()
