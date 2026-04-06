"""
Strategy: Crypto Scalping 5M
Translated from Pine Script (Simo / Claude Analysis) to Python for Bybit bot.

Logic:
  Trend  : EMA8 > EMA21 (bull) / EMA8 < EMA21 (bear)
  VWAP   : long above VWAP, short below VWAP
  RSI(7) : long 45-70 | short 30-55
  Volume : volume > 1.2× SMA(20)
  Entry  : EMA8 bounce — prev bar touched EMA8, current bar closes past it
  SL/TP  : 1.0× ATR / 2.0× ATR  →  R:R 2:1
"""

import pandas as pd
import numpy as np

# ── Parameters (mirror Pine Script defaults) ─────────────────────────────────
EMA_FAST_LEN  = 8
EMA_SLOW_LEN  = 21
RSI_LEN       = 7
RSI_LONG_MIN  = 45
RSI_LONG_MAX  = 70
RSI_SHORT_MIN = 30
RSI_SHORT_MAX = 55
VOL_MA_LEN    = 20
VOL_MULTI     = 1.2
ATR_LEN       = 14
VWAP_LEN      = 100   # rolling-window VWAP approximation

# Trailing stop parameters (from Pine Script)
TRAIL_ACTIVE_PCT = 80.0   # activate when price moves 80% toward TP
TRAIL_LOCK_PCT   = 10.0   # trail is placed at 10% of TP range above entry


# ── Indicator computation ────────────────────────────────────────────────────

def apply_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # Fast / Slow EMA
    df["ema_fast"] = df["close"].ewm(span=EMA_FAST_LEN, adjust=False).mean()
    df["ema_slow"] = df["close"].ewm(span=EMA_SLOW_LEN, adjust=False).mean()

    # RSI (Wilder smoothing via ewm com)
    delta     = df["close"].diff()
    gain      = delta.clip(lower=0)
    loss      = (-delta).clip(lower=0)
    avg_gain  = gain.ewm(com=RSI_LEN - 1, adjust=False).mean()
    avg_loss  = loss.ewm(com=RSI_LEN - 1, adjust=False).mean()
    rs        = avg_gain / avg_loss.replace(0, np.nan)
    df["rsi"] = 100 - (100 / (1 + rs))

    # ATR (Wilder smoothing)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - df["close"].shift()).abs(),
        (df["low"]  - df["close"].shift()).abs(),
    ], axis=1).max(axis=1)
    df["atr"] = tr.ewm(span=ATR_LEN, adjust=False).mean()

    # VWAP (rolling window — approximates intraday VWAP on short timeframes)
    df["hlc3"] = (df["high"] + df["low"] + df["close"]) / 3
    pv         = df["hlc3"] * df["volume"]
    df["vwap"] = (
        pv.rolling(VWAP_LEN).sum() /
        df["volume"].rolling(VWAP_LEN).sum()
    )

    # Volume MA
    df["vol_ma"] = df["volume"].rolling(VOL_MA_LEN).mean()

    return df


# ── Signal check ─────────────────────────────────────────────────────────────

def check_signal(df: pd.DataFrame):
    """
    Returns (signal, score, atr)
      signal : 'long' | 'short' | None
      score  : 3 if valid (compatible with bot threshold system)
      atr    : current ATR value
    """
    min_bars = max(EMA_SLOW_LEN, ATR_LEN, VWAP_LEN) + 5
    if len(df) < min_bars:
        return None, 0, 0

    last = df.iloc[-1]
    prev = df.iloc[-2]

    atr = last["atr"]
    if pd.isna(atr) or atr == 0:
        return None, 0, 0

    # ── Filters ──────────────────────────────────────────────────────────────
    bull_stack = last["ema_fast"] > last["ema_slow"]
    bear_stack = last["ema_fast"] < last["ema_slow"]

    above_vwap = last["close"] > last["vwap"]
    below_vwap = last["close"] < last["vwap"]

    rsi      = last["rsi"]
    rsi_bull = RSI_LONG_MIN  <= rsi <= RSI_LONG_MAX
    rsi_bear = RSI_SHORT_MIN <= rsi <= RSI_SHORT_MAX

    vol_ok = (
        not pd.isna(last["vol_ma"]) and
        last["volume"] > last["vol_ma"] * VOL_MULTI
    )

    # ── EMA8 bounce entry ─────────────────────────────────────────────────────
    # Long  : previous bar's low tagged EMA8, current close breaks above EMA8
    ema_bounce_up   = (prev["low"]  <= prev["ema_fast"]) and (last["close"] > last["ema_fast"])
    # Short : previous bar's high tagged EMA8, current close breaks below EMA8
    ema_bounce_down = (prev["high"] >= prev["ema_fast"]) and (last["close"] < last["ema_fast"])

    # ── Decision ─────────────────────────────────────────────────────────────
    if bull_stack and rsi_bull and above_vwap and vol_ok and ema_bounce_up:
        return "long", 3, atr

    if bear_stack and rsi_bear and below_vwap and vol_ok and ema_bounce_down:
        return "short", 3, atr

    return None, 0, atr


# ── Trailing stop parameters (consumed by the bot) ───────────────────────────

def get_trail_params(tp_dist: float):
    """
    Returns (activation_dist, trailing_distance) for Bybit's set_trailing_stop.

    activation_dist  : price must move this much from entry before trail activates
    trailing_distance: fixed offset the trailing stop trails behind the extreme price
    """
    activation_dist   = tp_dist * (TRAIL_ACTIVE_PCT / 100.0)   # 80% of TP
    lock_dist         = tp_dist * (TRAIL_LOCK_PCT   / 100.0)   # 10% of TP
    trailing_distance = activation_dist - lock_dist             # 70% of TP
    return activation_dist, trailing_distance
