import pandas as pd

EMA_PERIOD = 20
MIN_EMA_SLOPE = 0.0005   # anti-range

# Mémoire Zone 1
zone_1_level = None
zone_1_direction = None


def apply_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df["ema20"] = df["close"].ewm(span=EMA_PERIOD).mean()
    df["ema_slope"] = df["ema20"].diff()
    return df


def crypto_doji(row):
    body = abs(row.close - row.open)
    candle_range = row.high - row.low
    if candle_range == 0:
        return None

    upper_wick = row.high - max(row.open, row.close)
    lower_wick = min(row.open, row.close) - row.low

    # Corps très petit
    if body > candle_range * 0.25:
        return None

    if upper_wick > candle_range * 0.6:
        return "wick_top"      # rejet haussier → short potentiel

    if lower_wick > candle_range * 0.6:
        return "wick_bottom"   # rejet baissier → long potentiel

    return None


def detect_zone_1(df: pd.DataFrame):
    global zone_1_level, zone_1_direction

    last = df.iloc[-1]
    doji = crypto_doji(last)

    if doji is None:
        return None

    # Biais EMA
    if last.close > last.ema20 and doji == "wick_top":
        zone_1_level = last.high
        zone_1_direction = "short"
        return "zone_1_short"

    if last.close < last.ema20 and doji == "wick_bottom":
        zone_1_level = last.low
        zone_1_direction = "long"
        return "zone_1_long"

    return None


def detect_zone_2(df: pd.DataFrame):
    global zone_1_level, zone_1_direction

    if zone_1_level is None:
        return None

    last = df.iloc[-1]
    prev = df.iloc[-2]

    # Anti-range
    if abs(df.ema_slope.iloc[-1]) < MIN_EMA_SLOPE:
        return None

    # Confirmation structure
    if zone_1_direction == "short":
        if last.high < prev.high:
            return "short"

    if zone_1_direction == "long":
        if last.low > prev.low:
            return "long"

    return None
