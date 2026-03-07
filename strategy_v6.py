import pandas as pd

def apply_indicators(df):
    # EMA 21
    df["ema21"] = df.close.ewm(span=21, adjust=False).mean()
    
    # Bollinger Bands (20, 2) - On utilise la ligne du milieu (SMA 20)
    df["boll_mid"] = df.close.rolling(window=20).mean()
    df["std"] = df.close.rolling(window=20).std()
    df["boll_upper"] = df["boll_mid"] + (df["std"] * 2)
    df["boll_lower"] = df["boll_mid"] - (df["std"] * 2)

    # ATR pour le calcul du SL/TP
    tr1 = df.high - df.low
    tr2 = abs(df.high - df.close.shift())
    tr3 = abs(df.low - df.close.shift())
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df["atr"] = tr.rolling(window=14).mean()

    # Volume filter
    df["vol_ma"] = df.volume.rolling(20).mean()

    return df

def check_signal(df):
    """
    Détecte le croisement entre EMA21 et Bollinger Mid
    - Long: EMA21 croise au-dessus de Bollinger Mid
    - Short: EMA21 croise en-dessous de Bollinger Mid
    """
    if len(df) < 22:
        return None, 0, 0
        
    last = df.iloc[-1]
    prev = df.iloc[-2]

    score = 0
    signal = None

    # Détection du croisement (Crossover/Crossunder)
    # Long: EMA était sous BollMid et passe au-dessus
    if prev.ema21 <= prev.boll_mid and last.ema21 > last.boll_mid:
        signal = "long"
        score += 2

    # Short: EMA était au-dessus BollMid et passe en-dessous
    elif prev.ema21 >= prev.boll_mid and last.ema21 < last.boll_mid:
        signal = "short"
        score += 2

    # Filtre de volume supplémentaire
    if signal and last.volume > last.vol_ma:
        score += 1

    atr = last.atr
    return signal, score, atr