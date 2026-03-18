"""
Stratégie Sniper OTE (Optimal Trade Entry)
Protocole : Scalping Haute Précision

Règles :
  1. Tendance macro H4 via Théorie de Dow (HH+HL = bull, LH+LL = bear)
  2. Prix en zone OTE Fibonacci (61.8% – 78.6%) sur M1
  3. Alignement M1 avec H4 (pas de contre-tendance forte)
  4. Entrée proche du niveau 0.618 (Golden Zone)
  5. SL : derrière la structure réelle (mèches incluses)
  6. TP : RR fixe de 2.0
"""
import numpy as np

# ─── Paramètres ────────────────────────────────────────────────────────────────
OTE_ENTRY = 0.618    # Niveau idéal d'entrée (bonus score)
OTE_LIMIT = 0.786    # Borne extérieure de la zone OTE
RR_TARGET = 2.0      # Risk/Reward cible

H4_LOOKBACK  = 20    # Nombre de bougies H4 pour Dow Theory
M1_LOOKBACK  = 50    # Nombre de bougies M1 pour trouver le swing
M1_SL_LOOKBACK = 15  # Nombre de bougies M1 pour le SL structurel

MIN_SL_PCT = 0.001   # SL minimum : 0.1% du prix (éviter le bruit)
MAX_SL_PCT = 0.03    # SL maximum : 3% du prix (éviter les SL absurdes)
MIN_SWING_PCT = 0.005  # Swing minimum : 0.5% (sinon trop petit pour tracer fib)


# ─── Théorie de Dow (H4) ───────────────────────────────────────────────────────
def detect_dow_trend(df, lookback=H4_LOOKBACK):
    """
    Détecte la tendance via la Théorie de Dow sur les `lookback` dernières bougies.
    Bullish  : Higher Highs (HH) + Higher Lows (HL)
    Bearish  : Lower Highs  (LH) + Lower Lows  (LL)
    Retourne 'long', 'short', ou None.
    """
    if len(df) < lookback + 2:
        return None

    data  = df.tail(lookback)
    highs = data['high'].values
    lows  = data['low'].values

    pivot_highs = []
    pivot_lows  = []

    for i in range(1, len(data) - 1):
        if highs[i] >= highs[i - 1] and highs[i] >= highs[i + 1]:
            pivot_highs.append(highs[i])
        if lows[i] <= lows[i - 1] and lows[i] <= lows[i + 1]:
            pivot_lows.append(lows[i])

    if len(pivot_highs) < 2 or len(pivot_lows) < 2:
        return None

    hh = pivot_highs[-1] > pivot_highs[-2]
    hl = pivot_lows[-1]  > pivot_lows[-2]
    lh = pivot_highs[-1] < pivot_highs[-2]
    ll = pivot_lows[-1]  < pivot_lows[-2]

    if hh and hl:
        return 'long'
    if lh and ll:
        return 'short'
    return None


# ─── Swing pour Fibonacci ──────────────────────────────────────────────────────
def find_last_swing(df, trend, lookback=M1_LOOKBACK):
    """
    Identifie le dernier swing d'impulsion sur M1 pour tracer Fibonacci.
      Long  → (swing_low, swing_high)  — impulsion haussière
      Short → (swing_high, swing_low)  — impulsion baissière
    Retourne (swing_from, swing_to) ou (None, None).
    """
    if len(df) < lookback:
        return None, None

    recent = df.tail(lookback)
    h = recent['high'].values
    l = recent['low'].values

    if trend == 'long':
        sh_idx = int(np.argmax(h))         # Sommet de l'impulsion
        if sh_idx < 3:
            return None, None
        swing_high = h[sh_idx]
        swing_low  = l[:sh_idx].min()      # Creux AVANT ce sommet
        return swing_low, swing_high

    else:  # short
        sl_idx = int(np.argmin(l))         # Creux de l'impulsion
        if sl_idx < 3:
            return None, None
        swing_low  = l[sl_idx]
        swing_high = h[:sl_idx].max()      # Sommet AVANT ce creux
        return swing_high, swing_low


# ─── Zone OTE (61.8% – 78.6%) ─────────────────────────────────────────────────
def price_in_ote(price, swing_from, swing_to, trend):
    """
    Vérifie que le prix est en zone OTE (retracement 61.8%-78.6% du swing).
    Retourne (bool, fib_618) — fib_618 est le niveau d'entrée idéal.
    """
    diff = abs(swing_to - swing_from)
    if diff == 0:
        return False, 0.0

    if trend == 'long':
        # Retracement depuis le swing_high (swing_to) vers le bas
        fib_618 = swing_to - OTE_ENTRY * diff
        fib_786 = swing_to - OTE_LIMIT  * diff
        ote_low, ote_high = fib_786, fib_618
    else:
        # Retracement depuis le swing_low (swing_to) vers le haut
        fib_618 = swing_to + OTE_ENTRY * diff
        fib_786 = swing_to + OTE_LIMIT  * diff
        ote_low, ote_high = fib_618, fib_786

    return ote_low <= price <= ote_high, fib_618


# ─── SL Structurel ────────────────────────────────────────────────────────────
def get_structural_sl(df, trend, lookback=M1_SL_LOOKBACK):
    """
    SL placé derrière la structure réelle (mèches incluses) :
      Long  → dernier plus bas (low minimum)
      Short → dernier plus haut (high maximum)
    """
    recent = df.tail(lookback)
    if trend == 'long':
        return float(recent['low'].min())
    else:
        return float(recent['high'].max())


# ─── Signal Principal ─────────────────────────────────────────────────────────
def check_signal(df_m1, df_h4):
    """
    Signal Sniper OTE.

    Score :
      1 pt  → Tendance H4 confirmée (Dow Theory)
      +1 pt → Alignement M1 avec H4
      +1 pt → Prix très proche du 0.618 (entrée optimale)
    Score max : 3

    Retourne (signal, score, sl_distance) ou (None, 0, 0).
    """
    if len(df_m1) < 60 or len(df_h4) < 25:
        return None, 0, 0

    # ── 1. Tendance H4 ────────────────────────────────────────────────────
    h4_trend = detect_dow_trend(df_h4)
    if not h4_trend:
        return None, 0, 0

    price = float(df_m1['close'].iloc[-1])
    score = 1  # H4 confirmé

    # ── 2. Swing + Zone OTE ───────────────────────────────────────────────
    swing_from, swing_to = find_last_swing(df_m1, h4_trend)
    if swing_from is None:
        return None, 0, 0

    # Swing trop petit = pas de signal
    if abs(swing_to - swing_from) < price * MIN_SWING_PCT:
        return None, 0, 0

    in_ote, fib_618 = price_in_ote(price, swing_from, swing_to, h4_trend)
    if not in_ote:
        return None, 0, 0

    # ── 3. Alignement M1 (hard filter) ────────────────────────────────────
    last_close = float(df_m1['close'].iloc[-1])
    prev_close = float(df_m1['close'].iloc[-2])
    m1_aligned = (
        (h4_trend == 'long'  and last_close > prev_close) or
        (h4_trend == 'short' and last_close < prev_close)
    )
    if not m1_aligned:
        return None, 0, 0

    score += 1  # M1 aligné

    # ── Bonus : entrée très proche du 0.618 ───────────────────────────────
    tolerance = price * 0.0005
    near_618 = (
        (h4_trend == 'long'  and price <= fib_618 + tolerance) or
        (h4_trend == 'short' and price >= fib_618 - tolerance)
    )
    if near_618:
        score += 1

    # ── 4. SL structurel ──────────────────────────────────────────────────
    sl_price = get_structural_sl(df_m1, h4_trend)

    sl_distance = price - sl_price if h4_trend == 'long' else sl_price - price

    # Clamp SL dans des limites raisonnables
    if sl_distance < price * MIN_SL_PCT:
        sl_distance = price * MIN_SL_PCT
    elif sl_distance > price * MAX_SL_PCT:
        return None, 0, 0

    return h4_trend, score, sl_distance
