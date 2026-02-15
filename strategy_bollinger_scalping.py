"""
Stratégie Scalping Bollinger Bands - Multi Timeframe (5m / 1m)

Principe : Rebond sur les bandes de Bollinger
- Long quand prix touche bande inférieure puis rebondit
- Short quand prix touche bande supérieure puis rebondit
- TP : Retour vers la bande moyenne (SMA20)
"""

import pandas as pd

# =========================
# PARAMÈTRES BOLLINGER
# =========================
BB_PERIOD = 20      # Période de la moyenne mobile
BB_STD_DEV = 2.0    # Nombre d'écarts-types
MIN_BODY_PCT = 0.002  # Filtre anti-doji (0.2%)

# Seuils de détection
BAND_TOUCH_THRESHOLD = 0.002  # 0.2% au-delà de la bande


def calculate_bollinger_bands(df, period=20, std_dev=2.0):
    """
    Calcule les bandes de Bollinger
    
    Args:
        df: DataFrame OHLCV
        period: Période pour la moyenne mobile (défaut 20)
        std_dev: Nombre d'écarts-types (défaut 2.0)
    
    Returns:
        DataFrame avec bb_upper, bb_middle, bb_lower
    """
    df = df.copy()
    
    # Moyenne mobile (middle band)
    df['bb_middle'] = df['close'].rolling(window=period).mean()
    
    # Écart-type
    std = df['close'].rolling(window=period).std()
    
    # Bandes supérieure et inférieure
    df['bb_upper'] = df['bb_middle'] + (std_dev * std)
    df['bb_lower'] = df['bb_middle'] - (std_dev * std)
    
    # Largeur des bandes (indicateur de volatilité)
    df['bb_width'] = df['bb_upper'] - df['bb_lower']
    df['bb_width_pct'] = df['bb_width'] / df['bb_middle']
    
    return df


def detect_band_touch_5m(df_5m):
    """
    Détecte si le prix a touché une bande de Bollinger et rebondit
    
    Returns:
        'lower_bounce' : Touche bande inf + rebond (signal LONG)
        'upper_bounce' : Touche bande sup + rebond (signal SHORT)
        None : Pas de signal
    """
    if len(df_5m) < BB_PERIOD + 2:
        return None
    
    current = df_5m.iloc[-1]
    previous = df_5m.iloc[-2]
    
    # Vérifier que les bandes sont calculées
    if pd.isna(current['bb_upper']) or pd.isna(current['bb_lower']):
        return None
    
    # ========== TOUCHE BANDE INFÉRIEURE ==========
    # Condition 1 : Prix précédent touche/casse la bande inférieure
    touched_lower = previous['low'] <= (previous['bb_lower'] * (1 + BAND_TOUCH_THRESHOLD))
    
    # Condition 2 : Prix actuel rebondit (close au-dessus de la bande)
    bounced_from_lower = current['close'] > current['bb_lower']
    
    if touched_lower and bounced_from_lower:
        print(f"📊 Bollinger - Rebond bande INFÉRIEURE détecté", flush=True)
        return 'lower_bounce'
    
    # ========== TOUCHE BANDE SUPÉRIEURE ==========
    # Condition 1 : Prix précédent touche/casse la bande supérieure
    touched_upper = previous['high'] >= (previous['bb_upper'] * (1 - BAND_TOUCH_THRESHOLD))
    
    # Condition 2 : Prix actuel rebondit (close en-dessous de la bande)
    bounced_from_upper = current['close'] < current['bb_upper']
    
    if touched_upper and bounced_from_upper:
        print(f"📊 Bollinger - Rebond bande SUPÉRIEURE détecté", flush=True)
        return 'upper_bounce'
    
    return None


def check_entry_pattern_1m(df_1m, band_signal):
    """
    Vérifie le pattern d'entrée sur le timeframe 1 minute
    
    Pattern MODIFIÉ :
    - 1 bougie dans le sens du rebond (au lieu de 2)
    - PAS de dojis (corps minimum 0.2%)
    
    Args:
        df_1m: DataFrame OHLCV du timeframe 1m
        band_signal: 'lower_bounce' ou 'upper_bounce'
    
    Returns:
        'long', 'short', ou None
    """
    if len(df_1m) < 1 or band_signal is None:
        return None
    
    current = df_1m.iloc[-1]
    
    # Filtre anti-doji sur la bougie actuelle
    current_body_pct = abs(current['close'] - current['open']) / current['open']
    
    if current_body_pct < MIN_BODY_PCT:
        print(f"🔍 Bougie rejetée (doji): corps={current_body_pct:.4f} < {MIN_BODY_PCT}", flush=True)
        return None
    
    # Signal LONG (rebond bande inférieure)
    if band_signal == 'lower_bounce':
        candle_bullish = current['close'] > current['open']
        
        if candle_bullish:
            print(f"✅ Pattern 1m VALIDÉ: 1 bougie haussière (corps={current_body_pct:.4f})", flush=True)
            return 'long'
    
    # Signal SHORT (rebond bande supérieure)
    elif band_signal == 'upper_bounce':
        candle_bearish = current['close'] < current['open']
        
        if candle_bearish:
            print(f"✅ Pattern 1m VALIDÉ: 1 bougie baissière (corps={current_body_pct:.4f})", flush=True)
            return 'short'
    
    return None


def calculate_sl_tp_bollinger(entry_price, side, bb_upper, bb_middle, bb_lower):
    """
    Calcule SL et TP basés sur les bandes de Bollinger
    
    Args:
        entry_price: Prix d'entrée
        side: 'long' ou 'short'
        bb_upper: Bande supérieure actuelle
        bb_middle: Bande moyenne actuelle
        bb_lower: Bande inférieure actuelle
    
    Returns:
        (sl_price, tp_price)
    """
    if side == 'long':
        # SL : Sous la bande inférieure
        sl_price = bb_lower * 0.995  # -0.5% sous la bande
        
        # TP : Bande moyenne (retour à la moyenne)
        tp_price = bb_middle
        
    else:  # short
        # SL : Au-dessus de la bande supérieure
        sl_price = bb_upper * 1.005  # +0.5% au-dessus de la bande
        
        # TP : Bande moyenne (retour à la moyenne)
        tp_price = bb_middle
    
    return sl_price, tp_price


def check_exit_conditions_bollinger(entry_price, current_price, side, bb_middle, candles_in_position):
    """
    Vérifie les conditions de sortie
    
    Sortie si :
    1. Fin de la 3ème bougie (candles_in_position >= 3)
    2. Prix atteint la bande moyenne (TP)
    3. Profit >= 2%
    
    Args:
        entry_price: Prix d'entrée
        current_price: Prix actuel
        side: 'long' ou 'short'
        bb_middle: Bande moyenne actuelle
        candles_in_position: Nombre de bougies depuis l'entrée
    
    Returns:
        bool: True si doit sortir
    """
    # Condition 1 : Fin de la 3ème bougie
    if candles_in_position >= 3:
        return True
    
    # Condition 2 : Prix proche de la bande moyenne (TP atteint)
    if side == 'long':
        if current_price >= bb_middle * 0.998:  # À 0.2% de la moyenne
            return True
    else:  # short
        if current_price <= bb_middle * 1.002:  # À 0.2% de la moyenne
            return True
    
    # Condition 3 : Profit >= 2%
    if side == 'long':
        profit_pct = (current_price - entry_price) / entry_price
    else:  # short
        profit_pct = (entry_price - current_price) / entry_price
    
    if profit_pct >= 0.02:  # 2%
        return True
    
    return False


# Pour compatibilité avec les bots existants
def apply_indicators(df):
    """Applique les indicateurs (Bollinger Bands)"""
    return calculate_bollinger_bands(df)


def check_signal(df):
    """Fonction de compatibilité (non utilisée pour multi-timeframe)"""
    return None


def reset_state():
    """Réinitialise l'état de la stratégie"""
    pass


def get_state():
    """Retourne l'état actuel"""
    return {}
