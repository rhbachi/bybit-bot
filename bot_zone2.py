import time
import pandas as pd
from datetime import datetime, timezone

from config import (
    exchange,
    SYMBOL,
    TIMEFRAME,
    CAPITAL,
    RISK_PER_TRADE,
    RR,
    MAX_TRADES_PER_DAY,
    LEVERAGE,
)

from strategy_zone2 import apply_indicators, detect_zone_1, detect_zone_2
from risk import calculate_position_size
from notifier import send_telegram
from logger import init_logger, log_trade


in_position = False
trades_today = 0
current_day = datetime.now(timezone.utc).date()


def fetch_data():
    ohlcv = exchange.fetch_ohlcv(SYMBOL, TIMEFRAME, limit=100)
    return pd.DataFrame(
        ohlcv,
        columns=["time", "open", "high", "low", "close", "volume"]
    )


def reset_daily():
    global trades_today, current_day
    today = datetime.now(timezone.utc).date()
    if today != current_day:
        trades_today = 0
        current_day = today
        send_telegram("🔄 Zone2 Bot – Nouveau jour")


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
            reset_daily()

            if trades_today >= MAX_TRADES_PER_DAY:
                time.sleep(900)
                continue

            df = fetch_data()
            df = apply_indicators(df)

            # Étape 1 : détecter Zone 1 (observation)
            detect_zone_1(df)

            # Étape 2 : détecter Zone 2 (exécution)
            signal = detect_zone_2(df)

            if signal and not in_position:
                last = df.iloc[-1]
                price = last.close

                if signal == "long":
                    sl = last.low
                    tp = price + (price - sl) * RR
                    side = "buy"
                else:
                    sl = last.high
                    tp = price - (sl - price) * RR
                    side = "sell"

                sl_distance = abs(price - sl)
                qty = calculate_position_size(
                    CAPITAL,
                    RISK_PER_TRADE,
                    sl_distance,
                    price
                )

                if qty > 0:
                    exchange.create_market_order(
                        SYMBOL,
                        side,
                        qty,
                        params={
                            "stopLoss": sl,
                            "takeProfit": tp,
                            "slTriggerBy": "LastPrice",
                            "tpTriggerBy": "LastPrice"
                        }
                    )

                    in_position = True
                    trades_today += 1

                    msg = f"✅ ZONE 2 TRADE {signal.upper()} | {SYMBOL}"
                    print(msg, flush=True)
                    send_telegram(msg)

            # Vérifier clôture
            positions = exchange.fetch_positions([SYMBOL])
            pos = next((p for p in positions if p.get("symbol") == SYMBOL), None)

            if in_position and pos and float(pos.get("contracts", 0)) == 0:
                pnl = float(pos.get("realizedPnl", 0) or 0)
                log_trade(SYMBOL, "ZONE2", 0, 0, 0, pnl, "CLOSED")
                in_position = False

            time.sleep(300)

        except Exception as e:
            print("❌ Zone2 Bot error:", e, flush=True)
            send_telegram(f"❌ Zone2 Bot error: {e}")
            time.sleep(60)


run()
