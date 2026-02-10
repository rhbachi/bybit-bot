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
COOLDOWN_SECONDS = 600

# =========================
# ÉTAT
# =========================
in_position = False
trades_today = 0
last_trade_time = None
current_day = datetime.now(timezone.utc).date()

# =========================
# UTILS
# =========================
def safe_float(v, default=0.0):
    try:
        return float(v) if v is not None else default
    except Exception:
        return default


def reset_daily():
    global trades_today, current_day
    today = datetime.now(timezone.utc).date()
    if today != current_day:
        trades_today = 0
        current_day = today
        print("🔄 Nouveau jour", flush=True)
        send_telegram("🔄 Nouveau jour – compteurs réinitialisés")


def fetch_data():
    ohlcv = exchange.fetch_ohlcv(SYMBOL, TIMEFRAME, limit=120)
    return pd.DataFrame(
        ohlcv,
        columns=["time", "open", "high", "low", "close", "volume"],
    )


def get_min_notional(symbol):
    """
    Bybit / ccxt peut retourner None → fallback obligatoire
    """
    try:
        market = exchange.market(symbol)
        min_notional = market.get("limits", {}).get("cost", {}).get("min")

        if min_notional is None or min_notional <= 0:
            return 5.0

        return float(min_notional)

    except Exception as e:
        print("⚠️ Erreur get_min_notional:", e, flush=True)
        return 5.0


def adjust_qty_to_min_notional(symbol, qty, price):
    min_notional = get_min_notional(symbol)
    notional = qty * price

    if notional >= min_notional:
        return qty

    min_qty = min_notional / price

    print(
        f"⚠️ Ajustement qty → minNotional | "
        f"Old notional={round(notional,2)} | "
        f"MinNotional={min_notional} | "
        f"New qty={round(min_qty,6)}",
        flush=True,
    )

    return round(min_qty, 6)


# =========================
# MAIN
# =========================
def run():
    global in_position, trades_today, last_trade_time

    print("🤖 Bot Bybit V5.2.5 démarré", flush=True)
    send_telegram("🤖 Bot Bybit V5.2.5 démarré")

    init_logger()

    try:
        exchange.set_leverage(LEVERAGE, SYMBOL)
    except Exception:
        pass

    while True:
        try:
            print("⏳ Analyse marché...", flush=True)

            reset_daily()

            if trades_today >= MAX_TRADES_PER_DAY:
                print("🛑 Max trades atteints", flush=True)
                time.sleep(300)
                continue

            if last_trade_time and time.time() - last_trade_time < COOLDOWN_SECONDS:
                print("⏸ Cooldown actif", flush=True)
                time.sleep(60)
                continue

            df = fetch_data()
            df = apply_indicators(df)
            signal = check_signal(df)

            if signal and not in_position:
                price = df.iloc[-1].close

                qty = calculate_position_size(
                    CAPITAL,
                    RISK_PER_TRADE,
                    STOP_LOSS_PCT,
                    price,
                    LEVERAGE,
                )

                # 🔑 Correctif minNotional (SEUL garde-fou)
                qty = adjust_qty_to_min_notional(SYMBOL, qty, price)

                if qty <= 0:
                    print("⚠️ Qty invalide → trade ignoré", flush=True)
                    time.sleep(300)
                    continue

                exchange.create_market_order(
                    SYMBOL,
                    "buy" if signal == "long" else "sell",
                    qty,
                )

                in_position = True
                trades_today += 1
                last_trade_time = time.time()

                msg = f"📈 TRADE OUVERT | {signal.upper()} | {SYMBOL} | Qty={qty}"
                print(msg, flush=True)
                send_telegram(msg)

            # ===== Vérifier clôture =====
            positions = exchange.fetch_positions([SYMBOL])
            pos = next((p for p in positions if p.get("symbol") == SYMBOL), None)

            if in_position and pos and safe_float(pos.get("contracts")) == 0:
                pnl = safe_float(pos.get("realizedPnl"))
                result = "WIN" if pnl > 0 else "LOSS"

                log_trade(SYMBOL, result, 0, 0, 0, pnl, result)

                msg = f"📊 TRADE FERMÉ | {result} | PnL={round(pnl,2)} USDT"
                print(msg, flush=True)
                send_telegram(msg)

                in_position = False

            time.sleep(300)

        except Exception as e:
            print("❌ Erreur bot:", e, flush=True)
            send_telegram(f"❌ Erreur bot: {e}")
            time.sleep(60)


run()
