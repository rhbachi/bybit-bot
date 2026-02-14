"""
Stratégie Scalping 3 Bougies - Multi Timeframe (5m / 1m)

Détection tendance sur 5m, exécution sur 1m
Sortie : fin 3ème bougie OU profit >= 2%
"""

import pandas as pd
import pandas_ta as ta

# =========================
# ÉTAT GLOBAL
# =========================
_trend_direction = None  # 'bullish', 'bearish', ou None
_candles_count = 0  # Compteur de bougies dans la position
_position_entry_time = None  # Timestamp d'entrée

def reset_state():
    """Réinitialise l'état de la stratégie"""
    global _trend_direction, _candles_count, _position_entry_time
    _trend_direction = None
    _candles_count = 0
    _position_entry_time = None


def get_state():
    """Retourne l'état actuel (pour debug)"""
    return {
        'trend': _trend_direction,
        'candles': _candles_count,
        'entry_time': _position_entry_time
    }


def apply_indicators_5m(df_5m):
    """
    Applique les indicateurs sur le timeframe 5 minutes
    
    Args:
        df_5m: DataFrame OHLCV du timeframe 5m
    
    Returns:
        DataFrame avec EMA20 et EMA50
    """
    df = df_5m.copy()
    
    # EMA20 et EMA50
    df['ema20'] = ta.ema(df['close'], length=20)
    df['ema50'] = ta.ema(df['close'], length=50)
    
    return df


def detect_trend_5m(df_5m):
    """
    Détecte la tendance sur le timeframe 5 minutes
    
    Conditions HAUSSIÈRE :
    - EMA20 > EMA50
    - Close > EMA20
    - 2 dernières bougies haussières
    
    Conditions BAISSIÈRE :
    - EMA20 < EMA50
    - Close < EMA20
    - 2 dernières bougies baissières
    
    Returns:
        'bullish', 'bearish', ou None
    """
    if len(df_5m) < 50:
        return None
    
    last = df_5m.iloc[-1]
    prev = df_5m.iloc[-2]
    
    # Vérifier que les EMA sont calculées
    if pd.isna(last['ema20']) or pd.isna(last['ema50']):
        return None
    
    # Tendance HAUSSIÈRE
    bullish_ema = last['ema20'] > last['ema50']
    bullish_close = last['close'] > last['ema20']
    bullish_candle_1 = prev['close'] > prev['open']
    bullish_candle_2 = last['close'] > last['open']
    
    if bullish_ema and bullish_close and bullish_candle_1 and bullish_candle_2:
        return 'bullish'
    
    # Tendance BAISSIÈRE
    bearish_ema = last['ema20'] < last['ema50']
    bearish_close = last['close'] < last['ema20']
    bearish_candle_1 = prev['close'] < prev['open']
    bearish_candle_2 = last['close'] < last['open']
    
    if bearish_ema and bearish_close and bearish_candle_1 and bearish_candle_2:
        return 'bearish'
    
    return None


def check_entry_pattern_1m(df_1m, trend):
    """
    Vérifie le pattern d'entrée sur le timeframe 1 minute
    
    Pattern :
    - 2 bougies consécutives dans le sens de la tendance
    - Entrée à l'ouverture de la 3ème bougie
    
    Args:
        df_1m: DataFrame OHLCV du timeframe 1m
        trend: 'bullish' ou 'bearish'
    
    Returns:
        'long', 'short', ou None
    """
    if len(df_1m) < 2 or trend is None:
        return None
    
    prev_2 = df_1m.iloc[-2]
    prev_1 = df_1m.iloc[-1]
    
    if trend == 'bullish':
        # 2 bougies haussières consécutives
        candle_1_bullish = prev_2['close'] > prev_2['open']
        candle_2_bullish = prev_1['close'] > prev_1['open']
        
        if candle_1_bullish and candle_2_bullish:
            return 'long'
    
    elif trend == 'bearish':
        # 2 bougies baissières consécutives
        candle_1_bearish = prev_2['close'] < prev_2['open']
        candle_2_bearish = prev_1['close'] < prev_1['open']
        
        if candle_1_bearish and candle_2_bearish:
            return 'short'
    
    return None


def check_exit_conditions(entry_price, current_price, side, candles_in_position):
    """
    Vérifie les conditions de sortie
    
    Sortie si :
    1. Fin de la 3ème bougie (candles_in_position >= 3)
    2. Profit >= 2%
    
    Args:
        entry_price: Prix d'entrée
        current_price: Prix actuel
        side: 'long' ou 'short'
        candles_in_position: Nombre de bougies depuis l'entrée
    
    Returns:
        bool: True si doit sortir
    """
    # Condition 1 : Fin de la 3ème bougie
    if candles_in_position >= 3:
        return True
    
    # Condition 2 : Profit >= 2%
    if side == 'long':
        profit_pct = (current_price - entry_price) / entry_price
    else:  # short
        profit_pct = (entry_price - current_price) / entry_price
    
    if profit_pct >= 0.02:  # 2%
        return True
    
    return False


# Pour compatibilité avec les bots existants
def apply_indicators(df):
    """Fonction de compatibilité (non utilisée pour cette stratégie)"""
    return df


def check_signal(df):
    """Fonction de compatibilité (non utilisée pour cette stratégie)"""
    return None
