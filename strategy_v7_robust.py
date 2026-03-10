import pandas as pd
import numpy as np

def apply_indicators(df):
    df = df.copy()
    
    # 1. EMA 100 - Plus réactive que EMA 200 pour entrer plus tôt
    df["ema_trend"] = df.close.ewm(span=100, adjust=False).mean()
    
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
    
    # 4. ADX (14) - Force de la tendance
    # High-Low, High-PrevClose, Low-PrevClose
    tr = pd.concat([
        df.high - df.low,
        (df.high - df.close.shift()).abs(),
        (df.low - df.close.shift()).abs()
    ], axis=1).max(axis=1)
    df["atr"] = tr.rolling(window=14).mean()
    
    up_move = df.high.diff()
    down_move = df.low.diff()
    
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)
    
    atr_smooth = df["atr"].replace(0, np.nan)
    plus_di = 100 * pd.Series(plus_dm, index=df.index).rolling(14).mean() / atr_smooth
    minus_di = 100 * pd.Series(minus_dm, index=df.index).rolling(14).mean() / atr_smooth
    
    denom = (plus_di + minus_di).replace(0, np.nan)
    dx = 100 * (abs(plus_di - minus_di) / denom).fillna(0)
    df["adx"] = dx.rolling(14).mean()
    
    # 5. Volume MA
    df["vol_ma"] = df.volume.rolling(20).mean()
    
    return df

def check_signal(df):
    """
    Stratégie V8 - Entrée Précoce & Filtres d'Épuisement :
    - Tendance : Prix vs EMA 100 (plus rapide)
    - Momentum : MACD Crossover
    - Force : ADX > 20 (tendance établie)
    - Filtre Épuisement : RSI LONG [50-65], RSI SHORT [35-50]
    """
    if len(df) < 100:
        return None, 0, 0
        
    last = df.iloc[-1]
    prev = df.iloc[-2]
    
    signal = None
    score = 0
    
    # S'assurer que l'ADX est calculé
    if pd.isna(last.get('adx', np.nan)) or last.adx < 20:
        return None, 0, last.atr
        
    # --- CONDITION LONG ---
    # 1. Tendance : Prix au-dessus EMA 100
    if last.close > last.ema_trend:
        # 2. Momentum : Croisement MACD haussier
        macd_cross = (prev.macd <= prev.macd_signal and last.macd > last.macd_signal)
        
        # 3. Zone de sécurité RSI (on n'entre pas si déjà en sur-achat > 65)
        rsi_safe = 50 < last.rsi < 65
        
        if macd_cross and rsi_safe:
            signal = "long"
            score = 3
            
    # --- CONDITION SHORT ---
    # 1. Tendance : Prix en-dessous EMA 100
    elif last.close < last.ema_trend:
        # 2. Momentum : Croisement MACD baissier
        macd_cross = (prev.macd >= prev.macd_signal and last.macd < last.macd_signal)
        
        # 3. Zone de sécurité RSI (on n'entre pas si déjà en sur-vente < 35)
        rsi_safe = 35 < last.rsi < 50
        
        if macd_cross and rsi_safe:
            signal = "short"
            score = 3
            
    # Bonus Volume & Trend Strength
    if signal:
        if last.volume > last.vol_ma:
            score += 1
        if last.adx > 30: # Tendance forte
            score += 1
            
    return signal, score, last.atr
