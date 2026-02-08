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

from strategy_zone2 import apply_indicators, detect_zone_1, detect_zone_2
from risk import calculate_position_size
from notifier import send_telegram
from logger import init_logger, log_trade


# =========================
# PARAMÈTRES STRATÉGIE (ALIGNÉS BOT1)
# =========================
RR_MULTIPLIER = 2.0          # TP = RR x SL
MAX_TRADES_PER_DAY = 3
SLEEP_SECONDS = 300          # 5 minutes


# =========================
# ÉTAT GLOBAL
# =========================
in_position = False
trades_today = 0
current_day = datetime.now(timezone.utc).date()


def reset_daily_counters():
    global trades_today, current_day
    today = datetime.now(timezone.utc).date()
    if today != current_day:
        trades_today = 0
        current_day = today
        send_telegram("🔄 Zone2 – Nouveau jour → compteurs réinitialisés")


def fetch_data():
    ohlcv = exchange.fetch_ohlcv(SYMBOL, TIMEFRAME, limit=100)
    return pd.DataFrame(
        ohlcv,
        columns=["time", "open", "high", "low", "close", "volume"]
    )


def run():
    global in_position, trades_today

    print("🤖 Zone 2 Bot démarré", flush=True)
    send_telegram("🤖 Zone 2 Bot démarré")

    init_logger()

    try:
        exchange.set_leverage(LEVERAGE, SYMBOL)
    except Exception:
        pass

    while True:
        try:
            reset_daily_counters()

            if trades_today >= MAX_TRADES_PER_DAY:
                time.sleep(1800)
                continue

            df = fetch_data()
            df = apply_indicators(df)
            print("⏳ Analyse marché (Zone2)...", flush=True)

            # Zone 1 : observation
            detect_zone_1(df)

            # Zone 2 : exécution
            signal = detect_zone_2(df)

            if signal and not in_position:
                last = df.iloc[-1]
                price = last.close

                if signal == "long":
                    sl = last.low
                    tp = price + (price - sl) * RR_MULTIPLIER
                    side = "buy"
                else:
                    sl = last.high
                    tp = price - (sl - price) * RR_MULTIPLIER
                    side = "sell"

                # 🔑 Alignement avec Bot1
                sl_pct = abs(price - sl) / price if price > 0 else 0

                qty = calculate_position_size(
                    CAPITAL,
                    RISK_PER_TRADE,
                    sl_pct,
                    price,
                    LEVERAGE
                )

                if qty > 0:
                    exchange.create_market_order(
                        symbol=SYMBOL,
                        side=side,
                        amount=qty,
                        params={
                            "stopLoss": sl,
                            "takeProfit": tp,
                            "slTriggerBy": "LastPrice",
                            "tpTriggerBy": "LastPrice"
                        }
                    )

                    in_position = True
                    trades_today += 1

                    msg = (
                        f"📈 *ZONE 2 TRADE OUVERT*\n"
                        f"Pair: {SYMBOL}\n"
                        f"Direction: {signal.upper()}\n"
                        f"Entry: {round(price,2)}\n"
                        f"SL: {round(sl,2)}\n"
                        f"TP: {round(tp,2)}\n"
                        f"RR: {RR_MULTIPLIER}"
                    )
                    print(msg, flush=True)
                    send_telegram(msg)

            # Détection clôture position
            positions = exchange.fetch_positions([SYMBOL])
            pos = next((p for p in positions if p.get("symbol") == SYMBOL), None)

            if in_position and pos and float(pos.get("contracts", 0) or 0) == 0:
                pnl = float(pos.get("realizedPnl", 0) or 0)
                result = "WIN ✅" if pnl > 0 else "LOSS ❌"

                log_trade(SYMBOL, "ZONE2", 0, 0, 0, pnl, result)

                msg = (
                    f"📊 *ZONE 2 TRADE FERMÉ*\n"
                    f"Pair: {SYMBOL}\n"
                    f"Résultat: {result}\n"
                    f"PnL: {round(pnl,2)} USDT"
                )
                print(msg, flush=True)
                send_telegram(msg)

                in_position = False

            time.sleep(SLEEP_SECONDS)

        except Exception as e:
            print("❌ Zone2 Bot error:", e, flush=True)
            send_telegram(f"❌ Zone2 Bot error: {e}")
            time.sleep(60)


# =========================
# ENTRY POINT
# =========================
run()
