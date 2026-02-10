import pandas as pd

"""
STRATÉGIE PRINCIPALE - BOT 1
Logique "inversée" : Trade AVEC la tendance
Zone 1: Détection de momentum fort
Zone 2: Confirmation de continuation
"""

# Paramètres inversés - utiliser une EMA plus courte pour plus de réactivité
EMA_PERIOD = 10
# Seuil de pente plus élevé pour filtrer les faux signaux
MIN_EMA_SLOPE = 0.001

# Variables d'état pour cette stratégie
_zone_1_level = None
_zone_1_direction = None


def apply_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Applique les indicateurs techniques au DataFrame"""
    df["ema10"] = df["close"].ewm(span=EMA_PERIOD).mean()
    df["ema_slope"] = df["ema10"].diff()
    return df


def crypto_doji(row):
    """
    Détecte les dojis crypto - INVERSÉ
    Au lieu de chercher des petits corps, on cherche des GROS corps avec peu de mèches
    """
    body = abs(row.close - row.open)
    candle_range = row.high - row.low
    if candle_range == 0:
        return None

    upper_wick = row.high - max(row.open, row.close)
    lower_wick = min(row.open, row.close) - row.low

    # INVERSÉ: On cherche des corps LARGES (>60% de la bougie)
    if body < candle_range * 0.6:
        return None

    # Bougie haussière forte (corps vert, peu de mèche haute)
    if row.close > row.open and upper_wick < candle_range * 0.2:
        return "strong_bullish"

    # Bougie baissière forte (corps rouge, peu de mèche basse)
    if row.close < row.open and lower_wick < candle_range * 0.2:
        return "strong_bearish"

    return None


def detect_zone_1(df: pd.DataFrame):
    """
    Détecte la Zone 1 - LOGIQUE INVERSÉE
    Au lieu de trader contre la tendance, on trade AVEC la tendance
    """
    global _zone_1_level, _zone_1_direction

    last = df.iloc[-1]
    pattern = crypto_doji(last)

    if pattern is None:
        return None

    # INVERSÉ: Si prix > EMA ET bougie haussière forte → on va LONG
    if last.close > last.ema10 and pattern == "strong_bullish":
        _zone_1_level = last.low
        _zone_1_direction = "long"
        return "zone_1_long"

    # INVERSÉ: Si prix < EMA ET bougie baissière forte → on va SHORT
    if last.close < last.ema10 and pattern == "strong_bearish":
        _zone_1_level = last.high
        _zone_1_direction = "short"
        return "zone_1_short"

    return None


def detect_zone_2(df: pd.DataFrame):
    """
    Détecte la Zone 2 - LOGIQUE INVERSÉE
    On entre quand le momentum continue dans la même direction
    """
    global _zone_1_level, _zone_1_direction

    if _zone_1_level is None:
        return None

    last = df.iloc[-1]
    prev = df.iloc[-2]

    # Vérifier que la pente de l'EMA est significative
    if abs(df.ema_slope.iloc[-1]) < MIN_EMA_SLOPE:
        return None

    # INVERSÉ: Pour un signal LONG, on attend que le prix continue à monter
    if _zone_1_direction == "long" and last.low > prev.low:
        return "long"

    # INVERSÉ: Pour un signal SHORT, on attend que le prix continue à baisser
    if _zone_1_direction == "short" and last.high < prev.high:
        return "short"

    return None


def check_signal(df: pd.DataFrame):
    """
    Point d'entrée principal pour la détection de signal
    Retourne 'long', 'short' ou None
    """
    # D'abord vérifier Zone 1
    zone_1 = detect_zone_1(df)
    
    # Ensuite vérifier Zone 2 (qui dépend de Zone 1)
    zone_2 = detect_zone_2(df)
    
    # Retourner le signal de Zone 2 s'il existe, sinon None
    return zone_2


def reset_state():
    """
    Réinitialise l'état de la stratégie
    Utile pour éviter les conflits entre sessions
    """
    global _zone_1_level, _zone_1_direction
    _zone_1_level = None
    _zone_1_direction = None
    print("🔄 État stratégie principale réinitialisé", flush=True)


def get_state():
    """
    Retourne l'état actuel de la stratégie
    Utile pour le debugging
    """
    return {
        "zone_1_level": _zone_1_level,
        "zone_1_direction": _zone_1_direction,
    }
