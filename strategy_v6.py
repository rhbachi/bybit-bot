import pandas as pd


def apply_indicators(df):

    df["ema20"] = df.close.ewm(span=20).mean()
    df["ema50"] = df.close.ewm(span=50).mean()

    tr1 = df.high - df.low
    tr2 = abs(df.high - df.close.shift())
    tr3 = abs(df.low - df.close.shift())

    tr = pd.concat([tr1,tr2,tr3],axis=1).max(axis=1)

    df["atr"] = tr.rolling(14).mean()

    df["vol_ma"] = df.volume.rolling(20).mean()

    return df


def check_signal(df):

    last = df.iloc[-1]

    score = 0
    signal = None

    if last.ema20 > last.ema50:
        signal = "long"
        score += 2

    if last.ema20 < last.ema50:
        signal = "short"
        score += 2

    if last.volume > last.vol_ma:
        score += 1

    atr = last.atr

    return signal, score, atr