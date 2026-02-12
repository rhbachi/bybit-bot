import pandas as pd

"""
STRATÉGIE ZONE2 - BOT 2
Logique classique : Trade CONTRE la tendance (mean reversion)
Zone 1: Détection de rejet (wicks importants)
Zone 2: Confirmation de retournement
"""

EMA_PERIOD = 20
MIN_EMA_SLOPE = 0.0005

# Variables d'état séparées pour cette stratégie
_zone2_level = None
_zone2_direction = None


def apply_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Applique les indicateurs techniques au DataFrame"""
    df["ema20"] = df["close"].ewm(span=EMA_PERIOD).mean()
    df["ema_slope"] = df["ema20"].diff()
    return df


def crypto_doji(row):
    """
    Détecte les dojis crypto classiques avec mèches importantes
    Indique un rejet potentiel du prix
    """
    body = abs(row.close - row.open)
    candle_range = row.high - row.low
    if candle_range == 0:
        return None

    upper_wick = row.high - max(row.open, row.close)
    lower_wick = min(row.open, row.close) - row.low

    # On cherche des PETITS corps avec de GRANDES mèches
    if body > candle_range * 0.25:
        return None

    # Mèche haute importante = rejet à la hausse
    if upper_wick > candle_range * 0.6:
        return "wick_top"

    # Mèche basse importante = rejet à la baisse
    if lower_wick > candle_range * 0.6:
        return "wick_bottom"

    return None


def detect_zone_1(df: pd.DataFrame):
    """
    Détecte la Zone 1 - Mean Reversion
    Trade CONTRE la tendance quand on détecte un rejet
    """
    global _zone2_level, _zone2_direction

    last = df.iloc[-1]
    doji = crypto_doji(last)

    if doji is None:
        return None

    # Prix au-dessus EMA + rejet haut = préparer SHORT
    if last.close > last.ema20 and doji == "wick_top":
        _zone2_level = last.high
        _zone2_direction = "short"
        return "zone_1_short"

    # Prix en-dessous EMA + rejet bas = préparer LONG
    if last.close < last.ema20 and doji == "wick_bottom":
        _zone2_level = last.low
        _zone2_direction = "long"
        return "zone_1_long"

    return None


def detect_zone_2(df: pd.DataFrame):
    """
    Détecte la Zone 2 - Confirmation du retournement
    On entre quand le prix commence à revenir vers l'EMA
    """
    global _zone2_level, _zone2_direction

    if _zone2_level is None:
        return None

    last = df.iloc[-1]
    prev = df.iloc[-2]

    # Vérifier que l'EMA bouge suffisamment
    if abs(df.ema_slope.iloc[-1]) < MIN_EMA_SLOPE:
        return None

    # Pour SHORT: on attend que le prix commence à baisser
    if _zone2_direction == "short" and last.high < prev.high:
        return "short"

    # Pour LONG: on attend que le prix commence à monter
    if _zone2_direction == "long" and last.low > prev.low:
        return "long"

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
    Réinitialise l'état de la stratégie Zone2
    """
    global _zone2_level, _zone2_direction
    _zone2_level = None
    _zone2_direction = None
    print("🔄 État stratégie Zone2 réinitialisé", flush=True)


def get_state():
    """
    Retourne l'état actuel de la stratégie Zone2
    """
    return {
        "zone_2_level": _zone2_level,
        "zone_2_direction": _zone2_direction,
    }
