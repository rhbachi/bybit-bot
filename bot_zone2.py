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
# PARAMÈTRES ZONE 2
# =========================
RR_MULTIPLIER = 2.3
MAX_TRADES_PER_DAY = 10
COOLDOWN_SECONDS = 600  # 10 min après clôture

# =========================
# ÉTAT GLOBAL
# =========================
in_position = False
trades_today = 0
current_day = datetime.now(timezone.utc).date()
last_trade_time = None


# =========================
# UTILITAIRES
# =========================
def safe_float(v, default=0.0):
    try:
        return float(v) if v is not None else default
    except Exception:
        return default


def fetch_data():
    ohlcv = exchange.fetch_ohlcv(SYMBOL, TIMEFRAME, limit=120)
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
        send_telegram("🔄 Zone2 – Nouveau jour, compteur réinitialisé")


def get_max_safe_qty(price):
    balance = exchange.fetch_balance()
    usdt_free = safe_float(balance.get("USDT", {}).get("free"))

    if usdt_free <= 5:
        return 0

    max_position_value = usdt_free * LEVERAGE * 0.9
    qty = max_position_value / price
    return round(qty, 4)


def enforce_min_qty(symbol, qty):
    if "ETH" in symbol:
        return max(qty, 0.01)
    if "BTC" in symbol:
        return max(qty, 0.001)
    return qty


# =========================
# VÉRIFICATION CLÔTURE
# =========================
def check_trade_closed():
    global in_position, last_trade_time

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

    log_trade(SYMBOL, "ZONE2", 0, 0, 0, pnl, result)

    send_telegram(
        f"📊 *TRADE FERMÉ (ZONE2)*\n"
        f"Pair: {SYMBOL}\n"
        f"Résultat: {result}\n"
        f"PnL: {round(pnl,2)} USDT"
    )

    in_position = False
    last_trade_time = time.time()


# =========================
# MAIN LOOP
# =========================
def run():
    global in_position, trades_today

    print("🤖 Zone 2 Bot démarré (V5.1)", flush=True)
    send_telegram("🤖 Zone 2 Bot V5.1 démarré")

    init_logger()

    try:
        exchange.set_leverage(LEVERAGE, SYMBOL)
    except Exception:
        pass

    while True:
        try:
            reset_daily()

            # Cooldown après clôture
            if last_trade_time:
                if time.time() - last_trade_time < COOLDOWN_SECONDS:
                    time.sleep(30)
                    continue

            if trades_today >= MAX_TRADES_PER_DAY:
                time.sleep(900)
                continue

            print("⏳ Analyse marché (Zone2)...", flush=True)

            df = fetch_data()
            df = apply_indicators(df)

            # Zone 1 : observation
            detect_zone_1(df)

            # Zone 2 : exécution
            signal = detect_zone_2(df)

            if signal and not in_position:
                last = df.iloc[-1]
                price = last.close

                if signal == "long":
                    sl = last.low
                    sl_distance = price - sl
                    tp = price + sl_distance * RR_MULTIPLIER
                    side = "buy"
                else:
                    sl = last.high
                    sl_distance = sl - price
                    tp = price - sl_distance * RR_MULTIPLIER
                    side = "sell"

                theoretical_qty = calculate_position_size(
                    CAPITAL,
                    RISK_PER_TRADE,
                    sl_distance,
                    price,
                    LEVERAGE
                )

                safe_qty = get_max_safe_qty(price)
                qty = min(theoretical_qty, safe_qty)
                qty = enforce_min_qty(SYMBOL, qty)

                if qty <= 0:
                    send_telegram("⚠️ Zone2: quantité invalide → trade ignoré")
                    time.sleep(300)
                    continue

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

                send_telegram(
                    f"📈 *TRADE OUVERT (ZONE2)*\n"
                    f"Pair: {SYMBOL}\n"
                    f"Direction: {signal.upper()}\n"
                    f"Qty: {qty}\n"
                    f"Entry: {round(price,2)}\n"
                    f"SL: {round(sl,2)}\n"
                    f"TP: {round(tp,2)}\n"
                    f"RR: {RR_MULTIPLIER}"
                )

            check_trade_closed()
            time.sleep(300)

        except Exception as e:
            print("❌ Zone2 Bot error:", e, flush=True)
            send_telegram(f"❌ Zone2 Bot error: {e}")
            time.sleep(60)


# =========================
# ENTRY POINT
# =========================
run()
