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
# STRATEGY PARAMETERS
# =========================
STOP_LOSS_PCT = 0.006
RR_MULTIPLIER = 2.3
MAX_TRADES_PER_DAY = 10
COOLDOWN_SECONDS = 600

# ===== PORTFOLIO PROTECTION =====
MAX_OPEN_POSITIONS = 2
MAX_PORTFOLIO_RISK = 0.06          # 6% total risk max
MAX_TOTAL_EXPOSURE_MULT = 1.2      # 120% capital exposure max


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
        current_day = today
        for s in state.values():
            s["trades_today"] = 0
        print("🔄 Nouveau jour", flush=True)


def fetch_data(symbol):
    ohlcv = exchange.fetch_ohlcv(symbol, TIMEFRAME, limit=120)
    return pd.DataFrame(
        ohlcv,
        columns=["time", "open", "high", "low", "close", "volume"],
    )


# ===== PORTFOLIO HELPERS =====

def get_open_positions():
    positions = exchange.fetch_positions()
    return [
        p for p in positions
        if safe_float(p.get("contracts")) > 0
    ]


def get_portfolio_risk():
    positions = get_open_positions()
    return len(positions) * RISK_PER_TRADE


def get_total_exposure():
    positions = get_open_positions()
    exposure = 0.0
    for p in positions:
        entry = safe_float(p.get("entryPrice"))
        contracts = safe_float(p.get("contracts"))
        exposure += entry * contracts
    return exposure


def run():
    print("🤖 MultiSymbol Bot démarré (Portfolio Safe V1)", flush=True)
    send_telegram("🤖 MultiSymbol Bot démarré (Portfolio Safe V1)")
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

                    # ===== PORTFOLIO PROTECTION =====
                    open_positions = get_open_positions()

                    if len(open_positions) >= MAX_OPEN_POSITIONS:
                        print("🔒 Max positions atteintes", flush=True)
                        continue

                    if get_portfolio_risk() + RISK_PER_TRADE > MAX_PORTFOLIO_RISK:
                        print("🔒 Risque portefeuille max atteint", flush=True)
                        continue

                    price = df.iloc[-1].close

                    qty = calculate_position_size(
                        CAPITAL,
                        RISK_PER_TRADE,
                        STOP_LOSS_PCT,
                        price,
                        LEVERAGE,
                    )

                    if qty <= 0:
                        continue

                    # ===== SL / TP =====
                    if signal == "long":
                        stop_loss = price * (1 - STOP_LOSS_PCT)
                        sl_distance = price - stop_loss
                        take_profit = price + sl_distance * RR_MULTIPLIER
                    else:
                        stop_loss = price * (1 + STOP_LOSS_PCT)
                        sl_distance = stop_loss - price
                        take_profit = price - sl_distance * RR_MULTIPLIER

                    stop_loss = float(exchange.price_to_precision(symbol, stop_loss))
                    take_profit = float(exchange.price_to_precision(symbol, take_profit))
                    qty = float(exchange.amount_to_precision(symbol, qty))

                    # ===== Exposure Check =====
                    new_exposure = get_total_exposure() + (price * qty)
                    if new_exposure > CAPITAL * MAX_TOTAL_EXPOSURE_MULT:
                        print("🔒 Exposition totale trop élevée", flush=True)
                        continue

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
                        f"SL={stop_loss} | TP={take_profit} | Qty={qty}",
                        flush=True,
                    )

                    send_telegram(
                        f"📈 TRADE OUVERT\n"
                        f"Pair: {symbol}\n"
                        f"Direction: {signal.upper()}\n"
                        f"SL: {stop_loss}\n"
                        f"TP: {take_profit}\n"
                        f"Qty: {qty}"
                    )

                # ===== CHECK CLOSE =====
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