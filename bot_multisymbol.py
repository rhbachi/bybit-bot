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
# PARAMÈTRES
# =========================
STOP_LOSS_PCT = 0.006
RR_MULTIPLIER = 2.3
MAX_TRADES_PER_DAY = 10
COOLDOWN_SECONDS = 600

# =========================
# ÉTAT GLOBAL PAR SYMBOLE
# =========================
state = {}
current_day = datetime.now(timezone.utc).date()


def safe_float(v, default=0.0):
    try:
        return float(v) if v is not None else default
    except:
        return default


def init_symbol_state(symbol):
    state[symbol] = {
        "in_position": False,
        "trades_today": 0,
        "last_trade_time": None,
    }


def reset_daily():
    global current_day
    today = datetime.now(timezone.utc).date()
    if today != current_day:
        print("🔄 Nouveau jour", flush=True)
        current_day = today
        for s in state.values():
            s["trades_today"] = 0


def fetch_data(symbol):
    ohlcv = exchange.fetch_ohlcv(symbol, TIMEFRAME, limit=120)
    return pd.DataFrame(
        ohlcv,
        columns=["time", "open", "high", "low", "close", "volume"],
    )


def get_min_notional(symbol):
    try:
        market = exchange.market(symbol)
        min_notional = market.get("limits", {}).get("cost", {}).get("min")
        if not min_notional:
            return 5.0
        return float(min_notional)
    except:
        return 5.0


def adjust_qty_to_min_notional(symbol, qty, price):
    min_notional = get_min_notional(symbol)
    notional = qty * price

    if notional >= min_notional:
        return qty

    min_qty = min_notional / price

    print(
        f"⚠️ {symbol} Ajustement qty | "
        f"Old notional={round(notional,2)} | "
        f"New qty={round(min_qty,6)}",
        flush=True,
    )

    return round(min_qty, 6)


def run():
    print("🤖 MultiSymbol Bot démarré", flush=True)
    send_telegram("🤖 MultiSymbol Bot démarré")

    init_logger()

    for symbol in SYMBOLS:
        init_symbol_state(symbol)

    while True:
        try:
            reset_daily()

            for symbol in SYMBOLS:
                s = state[symbol]

                print(f"\n⏳ Analyse {symbol}", flush=True)
                print(f"📊 in_position={s['in_position']}", flush=True)

                if s["trades_today"] >= MAX_TRADES_PER_DAY:
                    continue

                if s["last_trade_time"] and time.time() - s["last_trade_time"] < COOLDOWN_SECONDS:
                    continue

                df = fetch_data(symbol)
                df = apply_indicators(df)

                signal = check_signal(df)
                print(f"🚦 Signal {symbol} = {signal}", flush=True)

                if signal and not s["in_position"]:
                    price = df.iloc[-1].close

                    qty = calculate_position_size(
                        CAPITAL,
                        RISK_PER_TRADE,
                        STOP_LOSS_PCT,
                        price,
                        LEVERAGE,
                    )

                    qty = adjust_qty_to_min_notional(symbol, qty, price)

                    if qty <= 0:
                        continue

                    # ===== CALCUL SL / TP =====
                    if signal == "long":
                        stop_loss = price * (1 - STOP_LOSS_PCT)
                        sl_distance = price - stop_loss
                        take_profit = price + sl_distance * RR_MULTIPLIER
                    else:
                        stop_loss = price * (1 + STOP_LOSS_PCT)
                        sl_distance = stop_loss - price
                        take_profit = price - sl_distance * RR_MULTIPLIER

                    market = exchange.market(symbol)
                    precision = market["precision"]["price"]

                    stop_loss = round(stop_loss, precision)
                    take_profit = round(take_profit, precision)

                    exchange.create_market_order(
                        symbol,
                        "buy" if signal == "long" else "sell",
                        qty,
                        params={
                            "stopLoss": stop_loss,
                            "takeProfit": take_profit,
                            "slTriggerBy": "LastPrice",
                            "tpTriggerBy": "LastPrice",
                        },
                    )

                    s["in_position"] = True
                    s["trades_today"] += 1
                    s["last_trade_time"] = time.time()

                    print(
                        f"📈 TRADE OUVERT | {symbol} | {signal.upper()} | "
                        f"Entry={round(price,2)} | SL={stop_loss} | TP={take_profit} | Qty={qty}",
                        flush=True,
                    )

                    send_telegram(
                        f"📈 TRADE OUVERT\n"
                        f"Pair: {symbol}\n"
                        f"Direction: {signal.upper()}\n"
                        f"Entry: {round(price,2)}\n"
                        f"SL: {stop_loss}\n"
                        f"TP: {take_profit}\n"
                        f"Qty: {qty}"
                    )

                # ===== Vérifier clôture =====
                positions = exchange.fetch_positions([symbol])
                pos = next((p for p in positions if p.get("symbol") == symbol), None)

                if s["in_position"] and pos and safe_float(pos.get("contracts")) == 0:
                    pnl = safe_float(pos.get("realizedPnl"))
                    result = "WIN" if pnl > 0 else "LOSS"

                    log_trade(symbol, result, 0, 0, 0, pnl, result)

                    print(
                        f"📊 TRADE FERMÉ | {symbol} | {result} | PnL={round(pnl,2)}",
                        flush=True,
                    )

                    send_telegram(
                        f"📊 TRADE FERMÉ\nPair: {symbol}\nRésultat: {result}\nPnL: {round(pnl,2)}"
                    )

                    s["in_position"] = False

            time.sleep(300)

        except Exception as e:
            print("❌ Erreur MultiSymbol:", e, flush=True)
            send_telegram(f"❌ Erreur MultiSymbol: {e}")
            time.sleep(60)


run()