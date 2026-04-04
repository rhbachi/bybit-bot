"""
Stratégie avancée avec EMA, MACD, RSI, Stochastic, Bollinger Bands
et OTE (Optimal Trade Entry) sur retracements Fibonacci
Version avec logs de débogage et export CSV pour dashboard
"""
import pandas as pd
import numpy as np
from datetime import datetime
import os
import logging
import csv

# Configuration des logs
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

# =========================
# ÉTAT GLOBAL
# =========================
_last_bios_level = None  # Dernier Break of Structure
_last_bios_direction = None
_ote_active = False
_ote_entry_zone = None  # (zone_basse, zone_haute)

def reset_state():
    """Réinitialise l'état de la stratégie"""
    global _last_bios_level, _last_bios_direction, _ote_active, _ote_entry_zone
    _last_bios_level = None
    _last_bios_direction = None
    _ote_active = False
    _ote_entry_zone = None

def get_state():
    """Retourne l'état actuel pour debug"""
    return {
        'bios_level': _last_bios_level,
        'bios_direction': _last_bios_direction,
        'ote_active': _ote_active,
        'ote_zone': _ote_entry_zone
    }

def log_signal_to_file(signal_data):
    """Enregistre un signal dans le fichier CSV du dashboard"""
    try:
        signal_file = "logs/signals_log.csv"

        # S'assurer que le dossier logs existe
        os.makedirs("logs", exist_ok=True)

        # Créer le fichier avec en-tête s'il n'existe pas
        if not os.path.exists(signal_file):
            with open(signal_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'timestamp', 'bot_name', 'symbol', 'signal', 'price',
                    'trend', 'rsi', 'macd', 'stoch_k', 'stoch_d',
                    'bb_position', 'ote_zone', 'bios_detected',
                    'signal_strength', 'executed', 'reason_not_executed'
                ])

        # Ajouter le signal
        with open(signal_file, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                signal_data.get('timestamp', datetime.now().isoformat()),
                signal_data.get('bot_name', 'ZONE2_AI'),
                signal_data.get('symbol', 'UNKNOWN'),
                signal_data.get('signal', 'none'),
                signal_data.get('price', 0),
                signal_data.get('trend', 'unknown'),
                signal_data.get('rsi', 0),
                signal_data.get('macd', 0),
                signal_data.get('stoch_k', 0),
                signal_data.get('stoch_d', 0),
                signal_data.get('bb_position', 0),
                signal_data.get('ote_zone', False),
                signal_data.get('bios_detected', False),
                signal_data.get('signal_strength', 0),
                signal_data.get('executed', False),
                signal_data.get('reason_not_executed', '')
            ])
    except Exception as e:
        logger.error(f"Erreur lors du log du signal: {e}")

def calculate_atr(df, period=14):
    """Calcule l'ATR (Average True Range) pour la volatilité adaptative"""
    high = df['high']
    low = df['low']
    close = df['close'].shift(1)

    tr1 = high - low
    tr2 = abs(high - close)
    tr3 = abs(low - close)

    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean()

    return atr

def calculate_ema(df, period):
    """Calcule EMA avec pandas"""
    return df['close'].ewm(span=period, adjust=False).mean()

def calculate_macd(df, fast=12, slow=26, signal=9):
    """Calcule MACD"""
    ema_fast = calculate_ema(df, fast)
    ema_slow = calculate_ema(df, slow)

    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line

    return macd_line, signal_line, histogram

def calculate_rsi(df, period=14):
    """Calcule RSI"""
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))

    return rsi

def calculate_stochastic(df, k_period=14, d_period=3):
    """Calcule Stochastic Oscillator"""
    low_min = df['low'].rolling(window=k_period).min()
    high_max = df['high'].rolling(window=k_period).max()

    k = 100 * ((df['close'] - low_min) / (high_max - low_min))
    d = k.rolling(window=d_period).mean()

    return k, d

def calculate_bollinger_bands(df, period=20, std_dev=2):
    """Calcule Bollinger Bands"""
    sma = df['close'].rolling(window=period).mean()
    std = df['close'].rolling(window=period).std()

    upper_band = sma + (std * std_dev)
    lower_band = sma - (std * std_dev)

    return upper_band, sma, lower_band

def detect_bios(df):
    """
    Détecte Break of Structure (BIOS) - Logique corrigée
    """
    if len(df) < 20:
        return None

    # On cherche les plus hauts/bas sur les bougies PRECEDENTES (période -10 à -2)
    # pour exclure la bougie actuelle et comparer correctement son Close
    past_high = df['high'].iloc[-10:-1].max()
    past_low = df['low'].iloc[-10:-1].min()
    current_close = df['close'].iloc[-1]

    # Dépassement léger pour confirmer la cassure (0.05%)
    if current_close > past_high * 1.0005:
        return {'direction': 'bullish', 'level': past_high}

    if current_close < past_low * 0.9995:
        return {'direction': 'bearish', 'level': past_low}

    return None

def calculate_fibonacci_retracement(swing_low, swing_high):
    """
    Calcule les niveaux Fibonacci avec niveaux configurables
    """
    diff = swing_high - swing_low

    # Niveaux Fibonacci depuis variables d'env
    fib_382 = float(os.getenv('FIB_382', '0.382'))
    fib_500 = float(os.getenv('FIB_500', '0.5'))
    fib_618 = float(os.getenv('FIB_618', '0.618'))
    fib_786 = float(os.getenv('FIB_786', '0.786'))

    return {
        '0.0': swing_low,
        '0.382': swing_low + diff * fib_382,
        '0.5': swing_low + diff * fib_500,
        '0.618': swing_low + diff * fib_618,
        '0.786': swing_low + diff * fib_786,
        '1.0': swing_high
    }

def detect_ote_zone(df, bios_direction, bios_level):
    """
    Détecte la zone OTE (Optimal Trade Entry) sur retracement Fibonacci
    OTE = zone entre 0.618 et 0.786 du dernier mouvement
    """
    if len(df) < 30:
        return None

    # Récupérer les niveaux Fibonacci depuis variables d'env
    fib_entry_min = float(os.getenv('FIB_ENTRY_MIN', '0.618'))
    fib_entry_max = float(os.getenv('FIB_ENTRY_MAX', '0.786'))

    if bios_direction == 'bullish':
        # Trouver le dernier swing low avant le BIOS
        swings = df['low'].rolling(window=5, center=True).min()
        swing_low = swings[swings == swings].iloc[-10:-2].min()

        if pd.isna(swing_low):
            return None

        fibs = calculate_fibonacci_retracement(swing_low, bios_level)
        ote_low = fibs[str(fib_entry_min)]
        ote_high = fibs[str(fib_entry_max)]

        return {
            'direction': 'long',
            'entry_zone': (ote_low, ote_high),
            'fibs': fibs
        }

    elif bios_direction == 'bearish':
        # Trouver le dernier swing high avant le BIOS
        swings = df['high'].rolling(window=5, center=True).max()
        swing_high = swings[swings == swings].iloc[-10:-2].max()

        if pd.isna(swing_high):
            return None

        fibs = calculate_fibonacci_retracement(bios_level, swing_high)
        ote_low = fibs[str(fib_entry_min)]
        ote_high = fibs[str(fib_entry_max)]

        return {
            'direction': 'short',
            'entry_zone': (ote_low, ote_high),
            'fibs': fibs
        }

    return None

def calculate_adaptive_thresholds(df):
    """
    Calcule des seuils adaptatifs basés sur la volatilité (ATR)
    """
    atr = calculate_atr(df)
    current_atr = atr.iloc[-1]
    current_price = df['close'].iloc[-1]
    atr_pct = current_atr / current_price

    # Seuils de base depuis variables d'env
    rsi_ob_base = float(os.getenv('RSI_OVERBOUGHT_BASE', '70'))
    rsi_os_base = float(os.getenv('RSI_OVERSOLD_BASE', '30'))
    stoch_ob_base = float(os.getenv('STOCH_OVERBOUGHT_BASE', '80'))
    stoch_os_base = float(os.getenv('STOCH_OVERSOLD_BASE', '20'))

    # Ajuster les seuils selon la volatilité
    if atr_pct > 0.02:  # Forte volatilité (>2%)
        rsi_overbought = rsi_ob_base + 5
        rsi_oversold = rsi_os_base - 5
        stoch_overbought = stoch_ob_base + 5
        stoch_oversold = stoch_os_base - 5
    elif atr_pct > 0.01:  # Volatilité moyenne (1-2%)
        rsi_overbought = rsi_ob_base
        rsi_oversold = rsi_os_base
        stoch_overbought = stoch_ob_base
        stoch_oversold = stoch_os_base
    else:  # Faible volatilité (<1%)
        rsi_overbought = rsi_ob_base - 5
        rsi_oversold = rsi_os_base + 5
        stoch_overbought = stoch_ob_base - 5
        stoch_oversold = stoch_os_base + 5

    return {
        'rsi_ob': rsi_overbought,
        'rsi_os': rsi_oversold,
        'stoch_ob': stoch_overbought,
        'stoch_os': stoch_oversold,
        'atr_pct': atr_pct
    }

def apply_indicators(df):
    """
    Applique tous les indicateurs techniques
    """
    df = df.copy()

    # EMAs
    df['ema20'] = calculate_ema(df, 20)
    df['ema50'] = calculate_ema(df, 50)
    df['ema200'] = calculate_ema(df, 200)

    # MACD
    df['macd'], df['macd_signal'], df['macd_hist'] = calculate_macd(df)

    # RSI
    df['rsi'] = calculate_rsi(df)

    # Stochastic
    df['stoch_k'], df['stoch_d'] = calculate_stochastic(df)

    # Bollinger Bands
    df['bb_upper'], df['bb_middle'], df['bb_lower'] = calculate_bollinger_bands(df)

    # ATR
    df['atr'] = calculate_atr(df)

    return df

def detect_trend(df):
    """
    Détecte la tendance principale avec EMA 20/50
    """
    last = df.iloc[-1]

    if pd.isna(last['ema20']) or pd.isna(last['ema50']):
        return None

    # Tendance haussière (Golden Cross / Alignement)
    if last['ema20'] > last['ema50'] and last['close'] > last['ema20']:
        return 'bullish'

    # Tendance baissière (Death Cross / Alignement)
    if last['ema20'] < last['ema50'] and last['close'] < last['ema20']:
        return 'bearish'

    return None

def detect_momentum_signal(df, trend):
    """
    Détecte les signaux de momentum (MACD, RSI, Stochastic)
    """
    last = df.iloc[-1]
    prev = df.iloc[-2]

    # Seuils adaptatifs selon volatilité
    thresholds = calculate_adaptive_thresholds(df)

    signals = []

    # MACD Crossover
    if last['macd'] > last['macd_signal'] and prev['macd'] <= prev['macd_signal']:
        signals.append('macd_bullish')
    elif last['macd'] < last['macd_signal'] and prev['macd'] >= prev['macd_signal']:
        signals.append('macd_bearish')

    # RSI
    if trend == 'bullish' and last['rsi'] > 50 and last['rsi'] < thresholds['rsi_ob']:
        signals.append('rsi_healthy_bull')
    elif trend == 'bearish' and last['rsi'] < 50 and last['rsi'] > thresholds['rsi_os']:
        signals.append('rsi_healthy_bear')

    # Stochastic
    if last['stoch_k'] > last['stoch_d'] and last['stoch_k'] < thresholds['stoch_ob']:
        signals.append('stoch_bullish')
    elif last['stoch_k'] < last['stoch_d'] and last['stoch_k'] > thresholds['stoch_os']:
        signals.append('stoch_bearish')

    # Bollinger Bands (zones d'exhaustion)
    if last['close'] < last['bb_lower']:
        signals.append('bb_oversold')
    elif last['close'] > last['bb_upper']:
        signals.append('bb_overbought')

    return signals

def calculate_signal_strength(df, signal):
    """
    Calcule la force du signal (0-3)
    """
    if not signal:
        return 0

    last = df.iloc[-1]
    strength = 0

    # MACD
    if (signal == 'long' and last['macd'] > last['macd_signal']) or \
       (signal == 'short' and last['macd'] < last['macd_signal']):
        strength += 1

    # RSI
    if (signal == 'long' and 50 < last['rsi'] < 70) or \
       (signal == 'short' and 30 < last['rsi'] < 50):
        strength += 1

    # Stochastic
    if (signal == 'long' and last['stoch_k'] > last['stoch_d']) or \
       (signal == 'short' and last['stoch_k'] < last['stoch_d']):
        strength += 1

    return strength

def calculate_sl_tp_adaptive(entry_price, side, df):
    """
    Calcule SL/TP adaptatifs basés sur ATR avec ratios configurables
    """
    atr = df['atr'].iloc[-1]
    atr_pct = atr / entry_price

    # Ratios depuis variables d'env
    sl_atr_multiplier = float(os.getenv('SL_ATR_MULTIPLIER', '1.5'))
    tp_atr_multiplier = float(os.getenv('TP_ATR_MULTIPLIER', '3.0'))

    # SL et TP basés sur ATR
    sl_distance = atr * sl_atr_multiplier
    tp_distance = atr * tp_atr_multiplier

    if side == 'long':
        sl_price = entry_price - sl_distance
        tp_price = entry_price + tp_distance
    else:
        sl_price = entry_price + sl_distance
        tp_price = entry_price - tp_distance

    return round(sl_price, 2), round(tp_price, 2), atr_pct

def debug_check_signal(df):
    """Version debug de check_signal qui explique pourquoi pas de signal"""

    # Créer les données de base pour le signal
    signal_data = {
        'bot_name': 'ZONE2_AI',
        'symbol': os.getenv('SYMBOL', 'UNKNOWN'),
        'timestamp': datetime.now().isoformat(),
        'price': df['close'].iloc[-1] if not df.empty else 0,
        'trend': 'unknown',
        'rsi': 0,
        'macd': 0,
        'stoch_k': 0,
        'stoch_d': 0,
        'bb_position': 0,
        'ote_zone': False,
        'bios_detected': False,
        'signal_strength': 0,
        'executed': False,
        'reason_not_executed': ''
    }

    if len(df) < 50:
        logger.info("❌ Pas assez de données: %d/50 bougies", len(df))
        signal_data['reason_not_executed'] = 'Pas assez de données'
        log_signal_to_file(signal_data)
        return None

    # Appliquer indicateurs
    df = apply_indicators(df)

    # Mettre à jour les valeurs des indicateurs
    last = df.iloc[-1]
    signal_data['rsi'] = last.get('rsi', 0)
    signal_data['macd'] = last.get('macd', 0)
    signal_data['stoch_k'] = last.get('stoch_k', 0)
    signal_data['stoch_d'] = last.get('stoch_d', 0)

    # Calculer position BB
    if 'bb_upper' in last and 'bb_lower' in last:
        bb_range = last['bb_upper'] - last['bb_lower']
        if bb_range > 0:
            signal_data['bb_position'] = (last['close'] - last['bb_lower']) / bb_range

    # Vérifier tendance
    trend = detect_trend(df)
    signal_data['trend'] = trend if trend else 'unknown'

    if not trend:
        logger.info("❌ Pas de tendance claire (EMA20/50)")
        logger.info("   EMA20: %.2f, EMA50: %.2f, Close: %.2f",
                   last.get('ema20',0), last.get('ema50',0), last['close'])
        signal_data['reason_not_executed'] = 'Pas de tendance claire'
        log_signal_to_file(signal_data)
        reset_state()
        return None

    logger.info(f"✅ Tendance détectée: {trend}")

    # MACHINE À ÉTATS : BIOS -> OTE -> MOMENTUM
    global _last_bios_level, _last_bios_direction, _ote_active, _ote_entry_zone

    # Étape 1 : Détecter un nouveau Break of Structure (BIOS)
    bios = detect_bios(df)

    if bios and bios['direction'] == trend:
        # Nouveau BIOS détecté dans le sens de la tendance
        _last_bios_level = bios['level']
        _last_bios_direction = bios['direction']

        # Calcul de la zone OTE associée
        ote = detect_ote_zone(df, bios['direction'], bios['level'])
        if ote:
            _ote_entry_zone = ote['entry_zone']
            _ote_active = False  # On attend maintenant le pullback
            logger.info(f"✅ Nouveau BIOS détecté à {_last_bios_level:.2f}. Zone OTE calculée: {_ote_entry_zone[0]:.2f}-{_ote_entry_zone[1]:.2f}")

    signal_data['bios_detected'] = _last_bios_level is not None

    # Étape 2 : Vérifier si on piste un setup
    if not _last_bios_level or not _ote_entry_zone:
        logger.info("❌ En attente d'un Break of Structure (BIOS)")
        signal_data['reason_not_executed'] = 'Pas de BIOS / Attente breakout'
        log_signal_to_file(signal_data)
        return None

    # Invalidation si la tendance se retourne pendant qu'on attend
    if trend != _last_bios_direction:
        logger.info("❌ Tendance inversée, annulation du setup BIOS en cours")
        reset_state()
        signal_data['reason_not_executed'] = 'Tendance inversée'
        log_signal_to_file(signal_data)
        return None

    # Étape 3 : Vérifier le Pullback dans la zone OTE
    current_price = df['close'].iloc[-1]
    zone_low, zone_high = _ote_entry_zone

    # On regarde si le prix "touche" ou est "dans" la zone
    in_zone = zone_low <= current_price <= zone_high

    if not _ote_active:
        if in_zone:
            _ote_active = True  # Le prix a touché la zone, elle est active pour un rebond
            logger.info("✅ Le prix est entré dans la zone OTE ! Attente du momentum...")
        else:
            # On est toujours en attente du pullback
            logger.info(f"❌ Attente du pullback dans l'OTE ({zone_low:.2f}-{zone_high:.2f}). Prix: {current_price:.2f}")
            signal_data['reason_not_executed'] = 'Attente du Pullback (OTE)'
            log_signal_to_file(signal_data)
            return None

    # Si on arrive ici, la zone OTE est "active" (le pullback a eu lieu)
    signal_data['ote_zone'] = True

    # Étape 4 : Vérifier la confirmation par le Momentum pour le rebond
    signals = detect_momentum_signal(df, trend)
    logger.info(f"   Signaux momentum: {signals}")

    required = []
    score = 0
    if trend == 'bullish':
        required = ['macd_bullish', 'rsi_healthy_bull', 'stoch_bullish']
        score = sum(1 for s in required if s in signals)
    else:
        required = ['macd_bearish', 'rsi_healthy_bear', 'stoch_bearish']
        score = sum(1 for s in required if s in signals)

    logger.info(f"   Score momentum: {score}/3")
    signal_data['signal_strength'] = score

    # On autorise l'entrée avec un score de 2/3 (assouplissement)
    if score < 2:
        logger.info("❌ Pullback effectué mais Momentum insuffisant pour valider le rebond")
        signal_data['reason_not_executed'] = f'Momentum insuffisant ({score}/3)'
        log_signal_to_file(signal_data)
        return None

    # SIGNAL TROUVÉ - retourne 'long' ou 'short' (Fix: was incorrectly returning 'bullish'/'bearish')
    result = 'long' if trend == 'bullish' else 'short'
    logger.info(f"🎉 SIGNAL TROUVÉ: {result}")

    # On réinitialise l'état pour chercher le prochain setup après une entrée
    reset_state()

    signal_data['signal'] = result
    signal_data['executed'] = True
    signal_data['reason_not_executed'] = ''
    log_signal_to_file(signal_data)

    return result

# Garder l'ancien nom pour la compatibilité
check_signal = debug_check_signal
