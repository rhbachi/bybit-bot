import time
import pandas as pd
from datetime import datetime, timezone

from config import exchange, SYMBOL, TIMEFRAME, CAPITAL, RISK_PER_TRADE, LEVERAGE
from strategy_zone2 import apply_indicators, detect_zone_2
from risk import calculate_position_size
from notifier import send_telegram

in_position = False
trades_today = 0
current_day = datetime.now(timezone.utc).date()

def reset_daily():
    global trades_today, current_day
    today = datetime.now(timezone.utc).date()
    if today != current_day:
        trades_today = 0
        current_day = today
        print("🔄 Nouveau jour (Zone2)", flush=True)

def fetch_data():
    ohlcv = exchange.fetch_ohlcv(SYMBOL, TIMEFRAME, limit=100)
    return pd.DataFrame(
        ohlcv,
        columns=["time", "open", "high", "low", "close", "volume"]
    )

def run():
    global in_position, trades_today

    print("🤖 Zone2 Bot V5.2 démarré", flush=True)
    send_telegram("🤖 Zone2 Bot V5.2 démarré")

    while True:
        try:
            print("⏳ Analyse marché (Zone2)...", flush=True)

            reset_daily()

            df = fetch_data()
            df = apply_indicators(df)
            signal = detect_zone_2(df)

            if signal and not in_position:
                price = df.iloc[-1].close
                qty = calculate_position_size(
                    CAPITAL,
                    RISK_PER_TRADE,
                    0.006,
                    price,
                    LEVERAGE
                )

                if qty > 0:
                    exchange.create_market_order(
                        SYMBOL,
                        "buy" if signal == "long" else "sell",
                        qty
                    )

                    in_position = True
                    trades_today += 1

                    msg = f"📈 ZONE2 TRADE | {signal.upper()}"
                    print(msg, flush=True)
                    send_telegram(msg)

            time.sleep(300)

        except Exception as e:
            print("❌ Zone2 error:", e, flush=True)
            send_telegram(f"❌ Zone2 error: {e}")
            time.sleep(60)

run()
