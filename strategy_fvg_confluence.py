# strategy_fvg_confluence.py

import pandas as pd
import numpy as np


# =========================
# ATR
# =========================
def calculate_atr(df, period=14):
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = ranges.max(axis=1)
    return true_range.rolling(period).mean()


# =========================
# IMPULSE DETECTION (5m)
# =========================
def detect_impulse(df):
    if len(df) < 20:
        return False

    atr = calculate_atr(df)
    last = df.iloc[-1]

    range_candle = last['high'] - last['low']
    body = abs(last['close'] - last['open'])
    body_ratio = body / range_candle if range_candle > 0 else 0

    avg_volume = df['volume'].rolling(20).mean().iloc[-1]

    if (
        range_candle >= 1.8 * atr.iloc[-1] and
        body_ratio >= 0.75 and
        last['volume'] >= 1.7 * avg_volume
    ):
        return True

    return False


# =========================
# FAIR VALUE GAP
# =========================
def detect_fvg(df):
    if len(df) < 3:
        return None

    c1 = df.iloc[-3]
    c3 = df.iloc[-1]

    # Bullish FVG
    if c3['low'] > c1['high']:
        return ("long", c1['high'], c3['low'])

    # Bearish FVG
    if c3['high'] < c1['low']:
        return ("short", c3['high'], c1['low'])

    return None


# =========================
# FIBONACCI ZONE
# =========================
def fib_zone(df, lookback=20):
    if len(df) < lookback:
        return None, None

    swing_high = df['high'].iloc[-lookback:].max()
    swing_low = df['low'].iloc[-lookback:].min()

    fib_50 = swing_high - 0.5 * (swing_high - swing_low)
    fib_618 = swing_high - 0.618 * (swing_high - swing_low)

    return min(fib_50, fib_618), max(fib_50, fib_618)


# =========================
# CONFLUENCE CHECK
# =========================
def validate_fvg_confluence(df, ai_signal):
    """
    ai_signal: 'long' or 'short'
    """

    impulse_ok = detect_impulse(df)
    if not impulse_ok:
        return False

    fvg_data = detect_fvg(df)
    if not fvg_data:
        return False

    direction, fvg_low, fvg_high = fvg_data

    if direction != ai_signal:
        return False

    fib_low, fib_high = fib_zone(df)
    if fib_low is None:
        return False

    price = df['close'].iloc[-1]

    in_fvg = fvg_low <= price <= fvg_high
    in_fib = fib_low <= price <= fib_high

    return in_fvg and in_fib