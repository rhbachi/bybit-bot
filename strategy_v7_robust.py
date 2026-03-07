import pandas as pd
import numpy as np

def apply_indicators(df):
    df = df.copy()
    
    # 1. EMA 200 - Filtre de tendance long terme
    df["ema200"] = df.close.ewm(span=200, adjust=False).mean()
    
    # 2. MACD (12, 26, 9)
    ema_fast = df.close.ewm(span=12, adjust=False).mean()
    ema_slow = df.close.ewm(span=26, adjust=False).mean()
    df["macd"] = ema_fast - ema_slow
    df["macd_signal"] = df.macd.ewm(span=9, adjust=False).mean()
    
    # 3. RSI (14)
    delta = df.close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df["rsi"] = 100 - (100 / (1 + rs))
    
    # 4. ATR (14) pour SL/TP
    tr1 = df.high - df.low
    tr2 = abs(df.high - df.close.shift())
    tr3 = abs(df.low - df.close.shift())
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df["atr"] = tr.rolling(window=14).mean()
    
    # 5. Volume MA
    df["vol_ma"] = df.volume.rolling(20).mean()
    
    return df

def check_signal(df):
    """
    Stratégie Robuste Triple Confirmation :
    - Tendance : Prix vs EMA 200
    - Momentum : MACD Crossover
    - Force : RSI > 50 (Long) ou RSI < 50 (Short)
    """
    if len(df) < 200: # Besoin de 200 bougies pour l'EMA200
        return None, 0, 0
        
    last = df.iloc[-1]
    prev = df.iloc[-2]
    
    signal = None
    score = 0
    
    # --- CONDITION LONG ---
    # 1. Tendance : Prix au-dessus EMA 200
    if last.close > last.ema200:
        # 2. Momentum : Croisement MACD haussier (sur les 2 dernières bougies)
        macd_cross = (prev.macd <= prev.macd_signal and last.macd > last.macd_signal)
        
        # 3. Force : RSI > 50
        rsi_bullish = last.rsi > 50
        
        if macd_cross and rsi_bullish:
            signal = "long"
            score = 3
            
    # --- CONDITION SHORT ---
    # 1. Tendance : Prix en-dessous EMA 200
    elif last.close < last.ema200:
        # 2. Momentum : Croisement MACD baissier
        macd_cross = (prev.macd >= prev.macd_signal and last.macd < last.macd_signal)
        
        # 3. Force : RSI < 50
        rsi_bearish = last.rsi < 50
        
        if macd_cross and rsi_bearish:
            signal = "short"
            score = 3
            
    # Bonus Volume
    if signal and last.volume > last.vol_ma:
        score += 1
        
    return signal, score, last.atr
