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
# FAIR VALUE GAP
# =========================
def detect_fvg(df):
    """Détecte un FVG sur les 3 dernières bougies"""
    if len(df) < 3:
        return None

    c1 = df.iloc[-3]
    c3 = df.iloc[-1]

    # Bullish FVG : gap entre le haut de la bougie 1 et le bas de la bougie 3
    if c3['low'] > c1['high']:
        return ("long", c1['high'], c3['low'])

    # Bearish FVG : gap entre le bas de la bougie 1 et le haut de la bougie 3
    if c3['high'] < c1['low']:
        return ("short", c3['high'], c1['low'])

    return None


def detect_recent_fvg(df, lookback=15):
    """
    Scanne les `lookback` dernières bougies pour trouver le FVG le plus récent.
    Retourne (direction, fvg_low, fvg_high) ou None.
    """
    if len(df) < lookback + 3:
        return None

    # Parcourir du plus récent au plus ancien
    for i in range(len(df) - 1, len(df) - lookback - 1, -1):
        if i < 2:
            break
        c1 = df.iloc[i - 2]
        c3 = df.iloc[i]

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
def fib_zone(df, lookback=30):
    """
    Calcule la zone Fibonacci 50%-61.8% sur les `lookback` dernières bougies.
    Retourne (fib_low, fib_high).
    """
    if len(df) < lookback:
        return None, None

    swing_high = df['high'].iloc[-lookback:].max()
    swing_low = df['low'].iloc[-lookback:].min()

    diff = swing_high - swing_low
    if diff == 0:
        return None, None

    fib_50 = swing_high - 0.5 * diff
    fib_618 = swing_high - 0.618 * diff

    return min(fib_50, fib_618), max(fib_50, fib_618)
