"""
Stratégie FVG + Fibonacci + Momentum léger
- Détecte un FVG récent (sur les 15 dernières bougies)
- Vérifie si le prix est dans la zone Fibonacci (50%-61.8%)
- Confirme avec MACD ou RSI (au moins 1 sur 2)
"""
import pandas as pd
import numpy as np
from datetime import datetime
import os
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

from strategy_fvg_confluence import detect_recent_fvg, fib_zone, calculate_atr


# =========================
# INDICATEURS
# =========================
def calculate_ema(df, period):
    return df['close'].ewm(span=period, adjust=False).mean()


def calculate_macd(df, fast=12, slow=26, signal=9):
    ema_fast = calculate_ema(df, fast)
    ema_slow = calculate_ema(df, slow)
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def calculate_rsi(df, period=14):
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


def calculate_stochastic(df, k_period=14, d_period=3):
    low_min = df['low'].rolling(window=k_period).min()
    high_max = df['high'].rolling(window=k_period).max()
    k = 100 * ((df['close'] - low_min) / (high_max - low_min))
    d = k.rolling(window=d_period).mean()
    return k, d


def calculate_bollinger_bands(df, period=20, std_dev=2):
    sma = df['close'].rolling(window=period).mean()
    std = df['close'].rolling(window=period).std()
    return sma + (std * std_dev), sma, sma - (std * std_dev)


def apply_indicators(df):
    """Applique tous les indicateurs techniques"""
    df = df.copy()
    df['ema20'] = calculate_ema(df, 20)
    df['ema50'] = calculate_ema(df, 50)
    df['macd'], df['macd_signal'], df['macd_hist'] = calculate_macd(df)
    df['rsi'] = calculate_rsi(df)
    df['stoch_k'], df['stoch_d'] = calculate_stochastic(df)
    df['bb_upper'], df['bb_middle'], df['bb_lower'] = calculate_bollinger_bands(df)
    df['atr'] = calculate_atr(df)
    return df


def detect_trend(df):
    """Tendance EMA20/50 pour information (non bloquant)"""
    last = df.iloc[-1]
    if pd.isna(last.get('ema20')) or pd.isna(last.get('ema50')):
        return None
    if last['ema20'] > last['ema50'] and last['close'] > last['ema20']:
        return 'bullish'
    if last['ema20'] < last['ema50'] and last['close'] < last['ema20']:
        return 'bearish'
    return None


# =========================
# SIGNAL PRINCIPAL
# =========================
def check_signal(df):
    """
    Stratégie FVG + Fibonacci + Momentum léger.
    Retourne 'long', 'short' ou None.
    """
    if len(df) < 50:
        logger.info("Pas assez de données: %d/50", len(df))
        return None

    df = apply_indicators(df)
    last = df.iloc[-1]
    price = last['close']

    # Étape 1 : FVG récent
    fvg = detect_recent_fvg(df, lookback=15)
    if not fvg:
        logger.info("Pas de FVG récent détecté")
        return None

    direction, fvg_low, fvg_high = fvg
    logger.info("FVG %s détecté: [%.2f - %.2f]", direction, fvg_low, fvg_high)

    # Étape 2 : Prix dans zone Fibonacci 50%-61.8%
    fib_low, fib_high = fib_zone(df, lookback=30)
    if fib_low is None:
        logger.info("Impossible de calculer la zone Fibonacci")
        return None

    if not (fib_low <= price <= fib_high):
        logger.info("Prix %.2f hors zone Fibonacci [%.2f - %.2f]", price, fib_low, fib_high)
        return None

    logger.info("Prix dans zone Fibonacci [%.2f - %.2f]", fib_low, fib_high)

    # Étape 3 : Confirmation momentum (MACD ou RSI)
    if direction == 'long':
        macd_ok = last['macd'] > last['macd_signal']
        rsi_ok = 40 < last['rsi'] < 70
    else:
        macd_ok = last['macd'] < last['macd_signal']
        rsi_ok = 30 < last['rsi'] < 60

    if not (macd_ok or rsi_ok):
        logger.info("Momentum insuffisant (MACD=%s, RSI=%.1f)", macd_ok, last['rsi'])
        return None

    logger.info("SIGNAL %s | Prix: %.2f | RSI: %.1f | MACD ok: %s", direction, price, last['rsi'], macd_ok)
    return direction


# Alias pour compatibilité avec les imports existants
debug_check_signal = check_signal


def get_state():
    """Stub pour compatibilité — plus d'état global"""
    return {'ote_active': False, 'bios_level': None}


def reset_state():
    """Stub pour compatibilité — plus d'état global"""
    pass


# =========================
# SL/TP ADAPTATIF
# =========================
def calculate_sl_tp_adaptive(entry_price, side, df):
    """SL/TP basés sur ATR"""
    atr = df['atr'].iloc[-1]
    atr_pct = atr / entry_price

    sl_multiplier = float(os.getenv('SL_ATR_MULTIPLIER', '1.2'))
    tp_multiplier = float(os.getenv('TP_ATR_MULTIPLIER', '1.8'))

    sl_distance = atr * sl_multiplier
    tp_distance = atr * tp_multiplier

    if side == 'long':
        sl_price = entry_price - sl_distance
        tp_price = entry_price + tp_distance
    else:
        sl_price = entry_price + sl_distance
        tp_price = entry_price - tp_distance

    return round(sl_price, 2), round(tp_price, 2), atr_pct


# =========================
# FORCE DU SIGNAL
# =========================
def calculate_signal_strength(df, signal):
    """Force du signal (0-3) : MACD + RSI + Stochastic"""
    if not signal:
        return 0
    last = df.iloc[-1]
    strength = 0
    if (signal == 'long' and last['macd'] > last['macd_signal']) or \
       (signal == 'short' and last['macd'] < last['macd_signal']):
        strength += 1
    if (signal == 'long' and 50 < last['rsi'] < 70) or \
       (signal == 'short' and 30 < last['rsi'] < 50):
        strength += 1
    if (signal == 'long' and last['stoch_k'] > last['stoch_d']) or \
       (signal == 'short' and last['stoch_k'] < last['stoch_d']):
        strength += 1
    return strength
