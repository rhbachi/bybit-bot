"""
Stratégie V9 Scalper - Optimisée pour le 1m et les frais Bybit
- Filtre de tendance: EMA 50
- Signal: Croisement EMA 9 / EMA 21
- Confirmation: Stochastic (14, 3, 3)
- Volatilité: ADX > 20
"""
import pandas as pd
import numpy as np

def apply_indicators(df):
    df = df.copy()
    
    # 1. EMAs pour tendance et signal
    df["ema9"] = df.close.ewm(span=9, adjust=False).mean()
    df["ema21"] = df.close.ewm(span=21, adjust=False).mean()
    df["ema50"] = df.close.ewm(span=50, adjust=False).mean()
    
    # 2. Stochastic Fast (14, 3)
    low_min = df.low.rolling(window=14).min()
    high_max = df.high.rolling(window=14).max()
    df["stoch_k"] = 100 * (df.close - low_min) / (high_max - low_min)
    df["stoch_d"] = df.stoch_k.rolling(window=3).mean()
    
    # 3. ATR (14) pour SL/TP
    tr = pd.concat([
        df.high - df.low,
        (df.high - df.close.shift()).abs(),
        (df.low - df.close.shift()).abs()
    ], axis=1).max(axis=1)
    df["atr"] = tr.rolling(window=14).mean()
    
    # 4. ADX (14) - Force de la tendance
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
    
    return df

def check_signal(df):
    """
    Conditions d'entrée V9:
    - Long: EMA9 > EMA21, EMA9 > EMA50, Stoch_K > Stoch_D (croisement récent)
    - Short: EMA9 < EMA21, EMA9 < EMA50, Stoch_K < Stoch_D
    - Filtre ADX > 20 pour éviter les marchés rangés
    """
    if len(df) < 50:
        return None, 0, 0
        
    last = df.iloc[-1]
    prev = df.iloc[-2]
    
    # Filtre ADX indispensable pour le scalping
    if pd.isna(last.get('adx', np.nan)) or last.adx < 20:
        return None, 0, last.atr
        
    signal = None
    score = 0
    
    # Croisement EMA 9/21
    ema_cross_up = prev.ema9 <= prev.ema21 and last.ema9 > last.ema21
    ema_cross_down = prev.ema9 >= prev.ema21 and last.ema9 < last.ema21
    
    # --- CONDITION LONG ---
    if ema_cross_up and last.close > last.ema50:
        # Confirmation Stochastic (on veut que le croisement soit récent ou momentum haussier)
        if last.stoch_k > last.stoch_d and last.stoch_k < 80: # Pas encore sur-achat
            signal = "long"
            score = 3
            
    # --- CONDITION SHORT ---
    elif ema_cross_down and last.close < last.ema50:
        if last.stoch_k < last.stoch_d and last.stoch_k > 20: # Pas encore sur-vente
            signal = "short"
            score = 3
            
    if signal:
        if last.adx > 30: # Tendance très forte
            score += 1
            
    return signal, score, last.atr
