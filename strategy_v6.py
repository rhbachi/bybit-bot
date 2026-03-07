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
    - Long: EMA21 croise au-dessus de Bollinger Mid (ou l'a fait récemment)
    - Short: EMA21 croise en-dessous de Bollinger Mid (ou l'a fait récemment)
    """
    if len(df) < 25:
        return None, 0, 0
        
    # On regarde les dernières bougies pour ne pas rater le signal
    last = df.iloc[-1]
    prev1 = df.iloc[-2]
    prev2 = df.iloc[-3]

    score = 0
    signal = None

    # Détection du croisement avec tolérance sur 2 bougies
    # Long : EMA passe au-dessus maintenant OU l'a fait à la bougie précédente
    is_cross_long = (prev1.ema21 <= prev1.boll_mid and last.ema21 > last.boll_mid) or \
                    (prev2.ema21 <= prev2.boll_mid and prev1.ema21 > prev1.boll_mid and last.ema21 > last.boll_mid)
    
    # Short : EMA passe en-dessous maintenant OU l'a fait à la bougie précédente
    is_cross_short = (prev1.ema21 >= prev1.boll_mid and last.ema21 < last.boll_mid) or \
                     (prev2.ema21 >= prev2.boll_mid and prev1.ema21 < prev1.boll_mid and last.ema21 < last.boll_mid)

    if is_cross_long:
        signal = "long"
        score += 3 # Score max immédiat pour le croisement

    elif is_cross_short:
        signal = "short"
        score += 3

    # Filtre de volume (optionnel, ajoute du score)
    if signal and last.volume > last.vol_ma:
        score += 1

    atr = last.atr
    return signal, score, atr