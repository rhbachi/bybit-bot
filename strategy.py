import pandas as pd
import numpy as np

"""
STRATÉGIE PRINCIPALE - BOT 1 (VERSION MULTI-FACTEURS)

Structure:
Zone 1 → détection momentum
Zone 2 → continuation
Score multi-facteurs → validation trade
"""

EMA_FAST = 20
EMA_SLOW = 50
RSI_PERIOD = 14
VOLUME_PERIOD = 20
MIN_EMA_SLOPE = 0.0005

_zone_1_level = None
_zone_1_direction = None


def apply_indicators(df: pd.DataFrame) -> pd.DataFrame:

    df["ema20"] = df["close"].ewm(span=EMA_FAST).mean()
    df["ema50"] = df["close"].ewm(span=EMA_SLOW).mean()

    df["ema_slope"] = df["ema20"].diff()

    # RSI
    delta = df["close"].diff()

    gain = np.where(delta > 0, delta, 0)
    loss = np.where(delta < 0, abs(delta), 0)

    avg_gain = pd.Series(gain).rolling(RSI_PERIOD).mean()
    avg_loss = pd.Series(loss).rolling(RSI_PERIOD).mean()

    rs = avg_gain / avg_loss
    df["rsi"] = 100 - (100 / (1 + rs))

    # volume average
    df["volume_avg"] = df["volume"].rolling(VOLUME_PERIOD).mean()

    return df


def crypto_doji(row):

    body = abs(row.close - row.open)
    candle_range = row.high - row.low

    if candle_range == 0:
        return None

    upper_wick = row.high - max(row.open, row.close)
    lower_wick = min(row.open, row.close) - row.low

    if body < candle_range * 0.6:
        return None

    if row.close > row.open and upper_wick < candle_range * 0.2:
        return "strong_bullish"

    if row.close < row.open and lower_wick < candle_range * 0.2:
        return "strong_bearish"

    return None


def detect_zone_1(df):

    global _zone_1_level, _zone_1_direction

    last = df.iloc[-1]
    pattern = crypto_doji(last)

    if pattern is None:
        return None

    if last.close > last.ema20 and pattern == "strong_bullish":
        _zone_1_level = last.low
        _zone_1_direction = "long"
        return "zone_1_long"

    if last.close < last.ema20 and pattern == "strong_bearish":
        _zone_1_level = last.high
        _zone_1_direction = "short"
        return "zone_1_short"

    return None


def detect_zone_2(df):

    global _zone_1_level, _zone_1_direction

    if _zone_1_level is None:
        return None

    last = df.iloc[-1]
    prev = df.iloc[-2]

    if abs(df.ema_slope.iloc[-1]) < MIN_EMA_SLOPE:
        return None

    if _zone_1_direction == "long" and last.low > prev.low:
        return "long"

    if _zone_1_direction == "short" and last.high < prev.high:
        return "short"

    return None


def compute_score(df, signal):

    score = 0
    last = df.iloc[-1]

    # trend
    if last.ema20 > last.ema50 and signal == "long":
        score += 1

    if last.ema20 < last.ema50 and signal == "short":
        score += 1

    # RSI momentum
    if last.rsi > 55 and signal == "long":
        score += 1

    if last.rsi < 45 and signal == "short":
        score += 1

    # volume confirmation
    if last.volume > last.volume_avg:
        score += 1

    # breakout structure
    if signal == "long":
        if last.close > df.high.iloc[-5:-1].max():
            score += 1

    if signal == "short":
        if last.close < df.low.iloc[-5:-1].min():
            score += 1

    return score


def check_signal(df):

    detect_zone_1(df)
    signal = detect_zone_2(df)

    if signal is None:
        return None, 0

    score = compute_score(df, signal)

    return signal, score


def reset_state():

    global _zone_1_level, _zone_1_direction

    _zone_1_level = None
    _zone_1_direction = None

    print("🔄 État stratégie réinitialisé", flush=True)


def get_state():

    return {
        "zone_1_level": _zone_1_level,
        "zone_1_direction": _zone_1_direction,
    }