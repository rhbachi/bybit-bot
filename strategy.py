import pandas as pd


def apply_indicators(df):

    df["ema20"] = df.close.ewm(span=20).mean()
    df["ema50"] = df.close.ewm(span=50).mean()

    tr1 = df.high - df.low
    tr2 = abs(df.high - df.close.shift())
    tr3 = abs(df.low - df.close.shift())

    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    df["atr"] = tr.rolling(14).mean()

    delta = df.close.diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()

    rs = avg_gain / avg_loss

    df["rsi"] = 100 - (100 / (1 + rs))

    df["vol_ma"] = df.volume.rolling(20).mean()

    return df


def market_regime(df):

    ema20 = df.ema20.iloc[-1]
    ema50 = df.ema50.iloc[-1]

    if ema20 > ema50:
        return "bull"

    if ema20 < ema50:
        return "bear"

    return "range"


def check_signal(df):

    last = df.iloc[-1]

    regime = market_regime(df)

    score = 0
    signal = None

    if regime == "bull" and last.close > last.ema20:
        signal = "long"
        score += 2

    if regime == "bear" and last.close < last.ema20:
        signal = "short"
        score += 2

    if last.rsi < 35:
        score += 1

    if last.rsi > 65:
        score += 1

    if last.volume > last.vol_ma:
        score += 1

    atr = last.atr

    return signal, score, atr