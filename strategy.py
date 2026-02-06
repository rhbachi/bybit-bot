def apply_indicators(df):
    # EMA
    df["ema9"] = df["close"].ewm(span=9, adjust=False).mean()
    df["ema21"] = df["close"].ewm(span=21, adjust=False).mean()

    # RSI
    delta = df["close"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df["rsi"] = 100 - (100 / (1 + rs))

    return df


def check_signal(df):
    if len(df) < 30:
        return None

    prev = df.iloc[-2]
    last = df.iloc[-1]

    # LONG
    if prev.ema9 < prev.ema21 and last.ema9 > last.ema21:
        if 50 < last.rsi < 70:
            return "long"

    # SHORT
    if prev.ema9 > prev.ema21 and last.ema9 < last.ema21:
        if 30 < last.rsi < 50:
            return "short"

    return None
