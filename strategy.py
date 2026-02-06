import pandas_ta as ta

def apply_indicators(df):
    df["ema9"] = ta.ema(df["close"], length=9)
    df["ema21"] = ta.ema(df["close"], length=21)
    df["rsi"] = ta.rsi(df["close"], length=14)
    return df

def check_signal(df):
    prev = df.iloc[-2]
    last = df.iloc[-1]

    if prev.ema9 < prev.ema21 and last.ema9 > last.ema21 and 50 < last.rsi < 70:
        return "long"

    if prev.ema9 > prev.ema21 and last.ema9 < last.ema21 and 30 < last.rsi < 50:
        return "short"

    return None
