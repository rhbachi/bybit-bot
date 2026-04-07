import time
import threading
import pandas as pd
import math
import os
import json
import pytz
from datetime import datetime

from config import *
from flask import Flask, jsonify
from notifier import send_telegram
from strategy_v9_scalper import apply_indicators as apply_v9, check_signal as check_v9
from strategy_v7_robust import apply_indicators as apply_v7, check_signal as check_v7
from strategy_v6 import apply_indicators as apply_v6, check_signal as check_v6
from strategy_sniper_ote import check_signal as check_sniper, RR_TARGET as SNIPER_RR
from strategy_scalping_5m import (
    apply_indicators as apply_scalp5m,
    check_signal as check_scalp5m,
    get_trail_params as scalp5m_trail_params,
)
from auto_tuner import AutoTuner
from logger_enhanced import get_logger

# ── Timezone Paris pour la session américaine (14h30-20h00) ──────────────────
PARIS_TZ = pytz.timezone("Europe/Paris")
SNIPER_SESSION_START = (14, 30)   # 14h30 Paris
SNIPER_SESSION_END   = (20,  0)   # 20h00 Paris

# ================= CONFIGURATION =================
BOT_NAME = "MULTI_SYMBOL_V6_3"
logger = get_logger(BOT_NAME)
signals_cache = []

app = Flask(__name__)

last_trade_time = {}
active_positions = {} # {symbol: trade_data}

# Active Strategy Settings
ACTIVE_STRATEGY = os.getenv("ACTIVE_STRATEGY", "scalping_5m")
CURRENT_SL_MULTI = SL_ATR_MULTIPLIER
CURRENT_TP_MULTI = TP_ATR_MULTIPLIER
CURRENT_THRESHOLD = SCORE_THRESHOLD
LAST_TUNE_TRADES = 0

# Performance stats
daily_pnl = 0.0
total_trades = 0
consecutive_losses = 0
last_state_save = datetime.now().date().isoformat()

STATE_FILE = "data/multisymbol_state.json"

def save_state():
    state = {
        "daily_pnl": daily_pnl,
        "total_trades": total_trades,
        "consecutive_losses": consecutive_losses,
        "last_save_date": last_state_save,
        "signals_cache": signals_cache[-100:] # Persist some history
    }
    try:
        os.makedirs("data", exist_ok=True)
        with open(STATE_FILE, "w") as f:
            json.dump(state, f)
    except Exception as e:
        logger.log_error("Error saving state", e)

def load_state():
    global daily_pnl, total_trades, consecutive_losses, last_state_save, signals_cache
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                state = json.load(f)
                
            # Check if it's a new day
            current_date = datetime.now().date().isoformat()
            if state.get("last_save_date") == current_date:
                daily_pnl = state.get("daily_pnl", 0.0)
                consecutive_losses = state.get("consecutive_losses", 0)
            else:
                daily_pnl = 0.0
                consecutive_losses = 0
                last_state_save = current_date
                
            total_trades = state.get("total_trades", 0)
            signals_cache = state.get("signals_cache", [])
            print(f"📊 State loaded: PnL Today={daily_pnl:.2f}, Trades={total_trades}")
        except Exception as e:
            logger.log_error("Error loading state", e)

# ================= API =================

@app.route("/api/signals")
def signals():
    """Endpoint pour le dashboard"""
    return jsonify(signals_cache[-50:])

@app.route("/api/status")
def status():
    """État du bot"""
    return jsonify({
        "bot": BOT_NAME,
        "symbols": SYMBOLS,
        "active_strategy": ACTIVE_STRATEGY,
        "threshold": CURRENT_THRESHOLD,
        "sl_multi": CURRENT_SL_MULTI,
        "tp_multi": CURRENT_TP_MULTI,
        "capital": CAPITAL,
        "leverage": LEVERAGE,
        "active_count": len(active_positions),
        "daily_pnl": daily_pnl,
        "total_trades": total_trades
    })

@app.route("/api/trades")
def trades():
    """Historique des trades récents"""
    return jsonify(logger.get_recent_trades(50))

@app.route("/api/positions")
def positions():
    """Positions actuellement ouvertes"""
    # On rafraîchit la liste avec Bybit pour être sûr
    return jsonify(list(active_positions.values()))

def start_api():
    print(f"🌐 {BOT_NAME} API server started on port 5001")
    try:
        app.run(host="0.0.0.0", port=5001)
    except Exception as e:
        logger.log_error("API server error", e)

# ================= FETCH DATA =================

def fetch_data(symbol):
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, TIMEFRAME, limit=200)
        df = pd.DataFrame(
            ohlcv,
            columns=["time", "open", "high", "low", "close", "volume"]
        )
        return df
    except Exception as e:
        logger.log_error(f"Fetch data error {symbol}", e)
        return pd.DataFrame()


def fetch_data_m1(symbol):
    """Données M1 pour l'exécution Sniper OTE"""
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, '1m', limit=100)
        return pd.DataFrame(ohlcv, columns=["time", "open", "high", "low", "close", "volume"])
    except Exception as e:
        logger.log_error(f"Fetch M1 error {symbol}", e)
        return pd.DataFrame()


def fetch_data_h4(symbol):
    """Données H4 pour l'analyse macro Dow Theory"""
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, '4h', limit=50)
        return pd.DataFrame(ohlcv, columns=["time", "open", "high", "low", "close", "volume"])
    except Exception as e:
        logger.log_error(f"Fetch H4 error {symbol}", e)
        return pd.DataFrame()


def fetch_data_5m(symbol):
    """Données 5M pour la stratégie Scalping 5M (besoin de 200 bougies)"""
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, '5m', limit=200)
        return pd.DataFrame(ohlcv, columns=["time", "open", "high", "low", "close", "volume"])
    except Exception as e:
        logger.log_error(f"Fetch 5M error {symbol}", e)
        return pd.DataFrame()


def is_sniper_session():
    """
    Retourne True si on est dans la session américaine : Lun-Ven 14h30-20h00 Paris.
    Couvre l'ouverture de Wall Street + pleine session US.
    """
    now = datetime.now(PARIS_TZ)
    if now.weekday() >= 5:  # Samedi=5, Dimanche=6
        return False
    hm = now.hour * 60 + now.minute
    start = SNIPER_SESSION_START[0] * 60 + SNIPER_SESSION_START[1]
    end   = SNIPER_SESSION_END[0]   * 60 + SNIPER_SESSION_END[1]
    return start <= hm < end

# ================= POSITION SIZE =================

def calculate_position_size(price, stop_distance, capital=None):
    if stop_distance <= 0:
        return None

    effective_capital = capital if capital is not None else CAPITAL

    risk_amount = effective_capital * RISK_PER_TRADE
    qty = (risk_amount / stop_distance) * LEVERAGE

    # Sécurité : Max 25% du capital effectif par position
    max_position_value = effective_capital * LEVERAGE * 0.25
    max_qty = max_position_value / price

    if qty > max_qty:
        qty = max_qty

    return qty

# ================= PRECISION FIX =================

def adjust_qty(symbol, qty, price):
    try:
        market = exchange.market(symbol)
        min_amount = market["limits"]["amount"]["min"]
        precision = market["precision"]["amount"]

        if isinstance(precision, float):
            precision = abs(int(round(-math.log10(precision))))

        qty = round(qty, precision)

        if qty < min_amount:
            return None

        # Bybit : minimum order value 5 USDT
        if qty * price < 5:
            return None

        return qty

    except Exception as e:
        logger.log_error(f"Precision error {symbol}", e)
        return None

# ================= COOLDOWN =================

def cooldown_ok(symbol):
    if symbol not in last_trade_time:
        return True
    elapsed = time.time() - last_trade_time[symbol]
    return elapsed > COOLDOWN_SECONDS

def has_open_position(symbol, ignore_cache=False):
    """Vérifie si une position est déjà ouverte pour ce symbole sur Bybit"""
    try:
        # On vérifie d'abord notre cache local pour la rapidité
        if not ignore_cache and symbol in active_positions:
            return True
            
        # Puis on vérifie réellement sur l'échange
        pos = exchange.fetch_position(symbol)
        is_open = pos and float(pos.get('contracts', 0)) > 0
        
        if is_open:
            # On en profite pour remettre à jour notre cache si besoin
            active_positions[symbol] = {
                "symbol": symbol,
                "side": pos.get('side'),
                "entry_price": pos.get('entryPrice'),
                "qty": pos.get('contracts'),
                "pnl_percent": pos.get('percentage'),
                "pnl_usdt": pos.get('unrealizedPnl'),
                "timestamp": datetime.now().isoformat()
            }
            return True
        else:
            # Si pas de position sur l'échange, on s'assure de nettoyer le cache
            if symbol in active_positions:
                print(f"🔄 Detection fmeture position {symbol}")
                handle_position_closed(symbol)
                del active_positions[symbol]
            return False
    except Exception as e:
        logger.log_error(f"Error checking position for {symbol}", e)
def handle_position_closed(symbol):
    global daily_pnl, total_trades, consecutive_losses
    try:
        # Récupérer les infos de la position AVANT suppression du cache
        cached = active_positions.get(symbol, {})
        pos_side       = cached.get('side', 'unknown')
        pos_entry      = cached.get('entry_price', 0)
        pos_qty        = cached.get('qty', 0)
        pos_strategy   = cached.get('strategy', 'unknown')

        # Retry avec délai croissant — Bybit enregistre le PnL avec un léger délai
        # après la fermeture par trailing stop (asynchrone côté serveur)
        clean_symbol = symbol.split(':')[0].replace('/', '')
        pnl = 0.0
        exit_price = 0.0

        for attempt in range(4):                        # 4 tentatives max
            wait = [3, 5, 8, 12][attempt]              # 3s → 5s → 8s → 12s
            print(f"⏳ {symbol} - Attente PnL tentative {attempt+1}/4 ({wait}s)...", flush=True)
            time.sleep(wait)
            try:
                pnl_resp = exchange.private_get_v5_position_closed_pnl({
                    "category": "linear",
                    "symbol":   clean_symbol,
                    "limit":    1
                })
                if pnl_resp.get('result', {}).get('list'):
                    data       = pnl_resp['result']['list'][0]
                    pnl        = float(data.get('closedPnl', 0))
                    exit_price = float(data.get('avgExitPrice') or data.get('avgPrice', 0))
                    if pnl != 0.0:
                        print(f"✅ {symbol} - PnL récupéré à la tentative {attempt+1}: {pnl:.2f} USDT", flush=True)
                        break
            except Exception as e:
                logger.log_error(f"Error fetching closed PnL {symbol} attempt {attempt+1}", e)

        if pnl == 0.0:
            # Fallback : calcul depuis prix d'entrée/sortie si disponible
            if exit_price > 0 and pos_entry > 0 and pos_qty > 0:
                raw = (exit_price - pos_entry) if pos_side == 'long' else (pos_entry - exit_price)
                pnl = round(raw * pos_qty, 4)
                print(f"⚠️ {symbol} - PnL calculé (fallback): {pnl:.2f} USDT", flush=True)
            else:
                print(f"⚠️ {symbol} - PnL indisponible après 4 tentatives", flush=True)

        daily_pnl += pnl
        total_trades += 1
        if pnl < 0:
            consecutive_losses += 1
        else:
            consecutive_losses = 0

        result = "WIN" if pnl > 0 else ("LOSS" if pnl < 0 else "UNKNOWN")
        print(f"💰 {symbol} [{pos_side.upper()}] {result} | PnL: {pnl:.2f} USDT | Jour: {daily_pnl:.2f} USDT")
        save_state()

        trade_data = {
            'timestamp':    datetime.now().isoformat(),
            'bot_name':     BOT_NAME,
            'symbol':       symbol,
            'side':         pos_side,
            'entry_price':  pos_entry,
            'exit_price':   exit_price,
            'quantity':     pos_qty,
            'pnl_usdt':     pnl,
            'result':       result,
            'exit_reason':  'Exchange closed (SL/TP/Trailing)',
            'strategy':     pos_strategy,
        }
        logger.log_trade_detailed(trade_data)

    except Exception as e:
        logger.log_error(f"Error handling closed position for {symbol}", e)

def set_trailing_stop(symbol, distance, activation_price=None):
    """Active le trailing stop via un appel API séparé (Bybit V5)"""
    try:
        # Attendre un court instant que la position soit enregistrée par Bybit
        time.sleep(1.5)
        
        # Formatage du symbole pour l'appel privé
        clean_symbol = symbol.split(':')[0].replace('/', '')
        
        params = {
            "category": "linear",
            "symbol": clean_symbol,
            "trailingStop": str(round(distance, 4)),
            "positionIdx": 0
        }
        
        if activation_price:
            params["activePrice"] = str(round(activation_price, 4))
            print(f"📈 Trailing Stop configuré pour {symbol} (activation: {round(activation_price, 2)})")
        
        exchange.private_post_v5_position_trading_stop(params)
        return True
    except Exception as e:
        logger.log_error(f"Trailing Stop Error {symbol}", e)
        return False

# ================= OPEN TRADE =================

def get_base_currency(symbol):
    """Extrait la devise de base d'un symbole. Ex: BTC/USDT:USDT → BTC"""
    return symbol.split('/')[0]

def get_available_balance():
    """
    Retourne la marge USDT réellement disponible pour de nouveaux ordres.
    Utilise l'endpoint V5 Bybit qui tient compte des positions ouvertes et
    de la marge gelée — plus fiable que fetch_balance() pour les comptes Unified.
    """
    try:
        resp = exchange.private_get_v5_account_wallet_balance({
            "accountType": "UNIFIED"
        })
        coins = resp.get("result", {}).get("list", [{}])[0].get("coin", [])
        for coin in coins:
            if coin.get("coin") == "USDT":
                # availableToWithdraw = solde libre après marge gelée
                avail = coin.get("availableToWithdraw") or coin.get("availableToBorrow")
                if avail is not None:
                    return float(avail)
    except Exception:
        pass

    # Fallback : compte CONTRACT (non-unified)
    try:
        resp = exchange.private_get_v5_account_wallet_balance({
            "accountType": "CONTRACT"
        })
        coins = resp.get("result", {}).get("list", [{}])[0].get("coin", [])
        for coin in coins:
            if coin.get("coin") == "USDT":
                avail = coin.get("availableToWithdraw")
                if avail is not None:
                    return float(avail)
    except Exception:
        pass

    # Dernier fallback : ccxt standard
    try:
        balance = exchange.fetch_balance()
        free = balance.get("USDT", {}).get("free") or balance.get("free", {}).get("USDT")
        if free is not None:
            return float(free)
    except Exception as e:
        logger.log_error("get_available_balance error", e)

    return None


def open_trade(symbol, side, price, atr, score):
    # Sécurité ultime : On ne rentre pas si déjà en position
    if has_open_position(symbol):
        print(f"🚫 {symbol} déjà en position, ouverture annulée.")
        return

    # Limite du nombre de positions simultanées
    if len(active_positions) >= MAX_POSITIONS:
        print(f"🚫 [{symbol}] Limite de {MAX_POSITIONS} positions atteinte ({len(active_positions)} ouvertes), ouverture annulée.")
        return

    # Pas deux positions sur le même actif de base (ex: BTC/USDT et BTC/ETH)
    base = get_base_currency(symbol)
    for open_sym in active_positions:
        if get_base_currency(open_sym) == base:
            print(f"🚫 [{symbol}] Position déjà ouverte sur {open_sym} (même base: {base}), ouverture annulée.")
            return

    # Solde réel disponible sur Bybit — utilisé comme capital effectif pour le sizing
    available = get_available_balance()
    if available is None:
        print(f"⚠️ {symbol} Impossible de récupérer le solde, utilisation de CAPITAL={CAPITAL}")
        effective_capital = CAPITAL
    else:
        # On utilise 90% du solde libre pour garder un tampon de frais
        effective_capital = available * 0.90
        print(f"💰 {symbol} Capital effectif: {effective_capital:.2f} USDT (solde libre: {available:.2f} USDT)")

    # On force le TP à être au moins à 0.50% du prix pour couvrir les frais (0.075%) et faire du profit
    min_tp_dist = price * 0.0050
    # On force le SL à être au moins à 0.30% pour ne pas couper avec le bruit
    min_sl_dist = price * 0.0030

    sl_dist = max(atr * CURRENT_SL_MULTI, min_sl_dist)
    tp_dist = max(atr * CURRENT_TP_MULTI, min_tp_dist)

    qty = calculate_position_size(price, sl_dist, capital=effective_capital)
    if qty is None:
        return

    qty = adjust_qty(symbol, qty, price)
    if qty is None:
        print(f"⚠️ {symbol} Qty too small after adjustment (capital: {effective_capital:.2f} USDT)")
        last_trade_time[symbol] = time.time()
        return

    # Vérification finale : marge requise vs solde réellement disponible
    # (garde-fou contre race condition ou valeur de balance obsolète)
    if available is not None and available > 0:
        required_margin = (qty * price) / LEVERAGE
        if required_margin > available * 0.85:
            print(f"🚫 {symbol} Marge insuffisante: requis {required_margin:.2f} USDT > dispo {available:.2f} USDT, ordre annulé.")
            last_trade_time[symbol] = time.time()
            return

    if side == "long":
        sl = price - sl_dist
        tp = price + tp_dist
        order_side = "buy"
    else:
        sl = price + sl_dist
        tp = price - tp_dist
        order_side = "sell"

    # Calcul du trailing stop selon la stratégie active
    # scalping_5m : logique Pine Script (activation 80% TP, lock à 10% TP)
    if ACTIVE_STRATEGY == "scalping_5m":
        activation_dist, trailing_distance = scalp5m_trail_params(tp_dist)
    else:
        trailing_distance = max(atr * 0.5, price * 0.0010)
        activation_dist   = max(atr * 0.5, price * 0.0015)

    activation_price = price + activation_dist if side == "long" else price - activation_dist

    try:
        # Configuration SL/TP optimisée pour Bybit V5 (Linear)
        # TP en LIMIT pour économiser 64% de frais
        params = {
            "takeProfit": str(round(tp, 4)),
            "stopLoss": str(round(sl, 4)),
            "tpslMode": "Partial",          # Required for Limit TP
            "tpSize": str(qty),             # Required for Partial mode
            "slSize": str(qty),             # Required for Partial mode
            "tpLimitPrice": str(round(tp, 4)), # Required for Limit TP
            "tpOrderType": "Limit",
            "slOrderType": "Market",
            "positionIdx": 0
        }

        order = exchange.create_order(
            symbol,
            "market",
            order_side,
            qty,
            None,
            params
        )

        # Activer le Trailing Stop avec prix d'activation
        set_trailing_stop(symbol, trailing_distance, activation_price)

        last_trade_time[symbol] = time.time()
        
        trade_data = {
            'timestamp':             datetime.now().isoformat(),
            'bot_name':              BOT_NAME,
            'symbol':                symbol,
            'side':                  side,
            'entry_price':           price,
            'quantity':              qty,
            'result':                'OPEN',
            'exit_reason':           'position opened',
            'entry_signal_strength': score,
            'entry_atr_percent':     (atr / price),
        }
        logger.log_trade_detailed(trade_data)
        
        # Ajouter à notre suivi local des positions actives
        active_positions[symbol] = {
            "symbol": symbol,
            "side": side,
            "entry_price": price,
            "qty": qty,
            "timestamp": datetime.now().isoformat()
        }

        msg = f"🟢 TRADE OPEN {BOT_NAME}\n\nSymbol: {symbol}\nSide: {side.upper()}\nScore: {score}/3\nPrice: {price:.2f}\nSL: {sl:.2f}\nTP: {tp:.2f}\nQty: {qty}"
        send_telegram(msg)
        print(f"✅ {msg}")
        save_state()

    except Exception as e:
        logger.log_error(f"Trade error {symbol}", e)
        send_telegram(f"❌ Error opening {symbol}: {str(e)}")
        # Cooldown après échec pour éviter le spam de tentatives
        last_trade_time[symbol] = time.time()

# ================= OPEN TRADE SNIPER ================

def open_trade_sniper(symbol, side, price, sl_distance, score):
    """
    Ouvre un trade Sniper OTE :
      - SL : distance structurelle passée en paramètre (mèches incluses)
      - TP : RR 2.0 (2x SL distance)
      - Trailing stop léger activé après dépassement du TP/2
    """
    if has_open_position(symbol):
        print(f"🚫 {symbol} déjà en position, ouverture annulée.")
        return

    if len(active_positions) >= MAX_POSITIONS:
        print(f"🚫 [{symbol}] Limite {MAX_POSITIONS} positions atteinte.")
        return

    base = get_base_currency(symbol)
    for open_sym in active_positions:
        if get_base_currency(open_sym) == base:
            print(f"🚫 [{symbol}] Position déjà ouverte sur {open_sym} (même base: {base}).")
            return

    # Solde réel disponible sur Bybit — capital effectif pour le sizing
    available = get_available_balance()
    if available is None:
        print(f"⚠️ {symbol} Sniper: impossible de récupérer le solde, utilisation de CAPITAL={CAPITAL}")
        effective_capital = CAPITAL
    else:
        effective_capital = available * 0.90

    # Sécurité minimale sur le SL
    min_sl = price * 0.0005
    sl_dist = max(sl_distance, min_sl)
    tp_dist = sl_dist * SNIPER_RR   # RR 2.0

    qty = calculate_position_size(price, sl_dist, capital=effective_capital)
    if qty is None:
        return

    qty = adjust_qty(symbol, qty, price)
    if qty is None:
        print(f"⚠️ {symbol} Sniper: qty trop petite après ajustement (capital: {effective_capital:.2f} USDT)")
        last_trade_time[symbol] = time.time()
        return

    if side == 'long':
        sl = round(price - sl_dist, 4)
        tp = round(price + tp_dist, 4)
        order_side = 'buy'
    else:
        sl = round(price + sl_dist, 4)
        tp = round(price - tp_dist, 4)
        order_side = 'sell'

    # Trailing stop léger : activation après TP/2, distance = SL/2
    trailing_distance   = round(sl_dist * 0.5, 4)
    activation_dist     = round(tp_dist * 0.5, 4)
    activation_price    = price + activation_dist if side == 'long' else price - activation_dist

    try:
        params = {
            "takeProfit":   str(round(tp, 4)),
            "stopLoss":     str(round(sl, 4)),
            "tpslMode":     "Partial",
            "tpSize":       str(qty),
            "slSize":       str(qty),
            "tpLimitPrice": str(round(tp, 4)),
            "tpOrderType":  "Limit",
            "slOrderType":  "Market",
            "positionIdx":  0,
        }

        order = exchange.create_order(symbol, "market", order_side, qty, None, params)

        set_trailing_stop(symbol, trailing_distance, activation_price)

        last_trade_time[symbol] = time.time()

        active_positions[symbol] = {
            "symbol":      symbol,
            "side":        side,
            "entry_price": price,
            "qty":         qty,
            "timestamp":   datetime.now().isoformat(),
            "strategy":    "sniper_ote",
        }

        trade_data = {
            'timestamp':             datetime.now().isoformat(),
            'bot_name':              BOT_NAME,
            'symbol':                symbol,
            'side':                  side,
            'entry_price':           price,
            'quantity':              qty,
            'result':                'OPEN',
            'exit_reason':           'position opened',
            'entry_signal_strength': score,
            'strategy':              'sniper_ote',
        }
        logger.log_trade_detailed(trade_data)

        msg = (
            f"🎯 SNIPER OTE TRADE\n\n"
            f"Symbol: {symbol}\n"
            f"Side: {side.upper()}\n"
            f"Score: {score}/3\n"
            f"Prix: {price:.4f}\n"
            f"SL: {sl:.4f} (-{sl_dist/price*100:.2f}%)\n"
            f"TP: {tp:.4f} (+{tp_dist/price*100:.2f}%)\n"
            f"R:R = 1:{SNIPER_RR}\n"
            f"Qty: {qty}"
        )
        send_telegram(msg)
        print(f"✅ {msg}")
        save_state()

    except Exception as e:
        logger.log_error(f"Sniper trade error {symbol}", e)
        send_telegram(f"❌ Sniper error {symbol}: {str(e)}")
        last_trade_time[symbol] = time.time()


# ================= RISK GUARDS =================

def check_risk_limits():
    """
    Vérifie les deux gardes de risque journalier.
    Retourne (True, raison) si le bot doit s'arrêter, (False, "") sinon.

    Guards :
      1. MAX_DAILY_LOSS_PCT  : PnL journalier < -(CAPITAL × MAX_DAILY_LOSS_PCT / 100)
      2. MAX_CONSECUTIVE_LOSSES : N pertes consécutives atteint
    """
    max_loss_usdt = CAPITAL * MAX_DAILY_LOSS_PCT / 100

    if daily_pnl <= -max_loss_usdt:
        return True, (
            f"🛑 MAX DAILY LOSS atteint | PnL: {daily_pnl:.2f} USDT | "
            f"Limite: -{max_loss_usdt:.2f} USDT ({MAX_DAILY_LOSS_PCT}%)"
        )

    if consecutive_losses >= MAX_CONSECUTIVE_LOSSES:
        return True, (
            f"🛑 MAX CONSECUTIVE LOSSES atteint | "
            f"{consecutive_losses} pertes consécutives (limite: {MAX_CONSECUTIVE_LOSSES})"
        )

    return False, ""


# ================= BOT LOOP =================

def bot_loop():
    global daily_pnl, consecutive_losses, last_state_save, total_trades, LAST_TUNE_TRADES
    global ACTIVE_STRATEGY, CURRENT_SL_MULTI, CURRENT_TP_MULTI, CURRENT_THRESHOLD
    
    tuner = AutoTuner(exchange, logger)
    LAST_TUNE_TRADES = total_trades
    
    send_telegram(
        f"🚀 {BOT_NAME} STARTED\n"
        f"Stratégie: {ACTIVE_STRATEGY}\n"
        f"Symbols: {len(SYMBOLS)} | TF: {'5m' if ACTIVE_STRATEGY == 'scalping_5m' else TIMEFRAME}\n"
        f"SL: {CURRENT_SL_MULTI}×ATR | TP: {CURRENT_TP_MULTI}×ATR | Threshold: {CURRENT_THRESHOLD}\n"
        f"Risk guards: -{MAX_DAILY_LOSS_PCT}%/jour | {MAX_CONSECUTIVE_LOSSES} pertes consécutives max"
    )
    print(f"🤖 {BOT_NAME} Monitoring {SYMBOLS}")

    _risk_paused = False          # True quand les guards ont coupé le trading
    _risk_pause_reason = ""

    while True:
        # ── Guards de risque journalier ──────────────────────────────────────
        blocked, reason = check_risk_limits()
        if blocked:
            if not _risk_paused:
                _risk_paused = True
                _risk_pause_reason = reason
                print(reason, flush=True)
                send_telegram(f"⛔ {BOT_NAME} TRADING SUSPENDU\n{reason}\nReprise demain à minuit UTC.")
            time.sleep(300)
            continue

        # Reset du flag si on était en pause et que le guard n'est plus actif
        # (peut arriver si le bot redémarre un nouveau jour)
        if _risk_paused:
            _risk_paused = False
            send_telegram(f"✅ {BOT_NAME} - Guards OK, trading repris.")

        for symbol in SYMBOLS:
            try:
                if not cooldown_ok(symbol):
                    continue

                df = fetch_data(symbol)
                if df.empty:
                    continue

                if ACTIVE_STRATEGY == 'sniper_ote':
                    # ── Sniper OTE : session + dual timeframe ────────────────
                    if not is_sniper_session():
                        now_p = datetime.now(PARIS_TZ)
                        print(
                            f"🕐 Sniper hors session | {now_p.strftime('%a %H:%M')} Paris | "
                            f"Trading: Lun-Ven 14h30-20h00",
                            flush=True
                        )
                        time.sleep(0.2)
                        continue

                    df_m1 = fetch_data_m1(symbol)
                    df_h4 = fetch_data_h4(symbol)
                    if df_m1.empty or df_h4.empty:
                        continue

                    signal, score, sl_distance = check_sniper(df_m1, df_h4)
                    price = float(df_m1['close'].iloc[-1])
                    atr   = sl_distance  # pour le logging
                    reason = ""

                    if signal:
                        if score >= CURRENT_THRESHOLD:
                            open_trade_sniper(symbol, signal, price, sl_distance, score)
                            executed = True
                        else:
                            reason = f"Score insuffisant ({score}/{CURRENT_THRESHOLD})"
                            executed = False
                    else:
                        reason = "Hors zone OTE ou tendance Dow absente"
                        executed = False

                elif ACTIVE_STRATEGY == 'scalping_5m':
                    df5m = fetch_data_5m(symbol)
                    if df5m.empty:
                        continue
                    df5m = apply_scalp5m(df5m)
                    signal, score, atr = check_scalp5m(df5m)
                    df = df5m  # use 5m df for price below
                elif ACTIVE_STRATEGY == 'v9_scalper':
                    df = apply_v9(df)
                    signal, score, atr = check_v9(df)
                elif ACTIVE_STRATEGY == 'v6_aggressive':
                    df = apply_v6(df)
                    signal, score, atr = check_v6(df)
                else:  # Default robust v7
                    df = apply_v7(df)
                    signal, score, atr = check_v7(df)

                if ACTIVE_STRATEGY != 'sniper_ote':
                    price = df.close.iloc[-1]
                    reason = ""

                    if signal:
                        if score >= CURRENT_THRESHOLD:
                            open_trade(symbol, signal, price, atr, score)
                            executed = True
                        else:
                            reason = f"Score insuffisant ({score}/{CURRENT_THRESHOLD})"
                            executed = False
                    else:
                        reason = "Pas de signal EMA"
                        executed = False

                # Logging des signaux (même rejetés)
                signal_data = {
                    "symbol": symbol,
                    "signal": signal if signal else "none",
                    "price": price,
                    "signal_strength": score,
                    "executed": executed,
                    "reason_not_executed": reason
                }
                logger.log_signal(signal_data)
                
                # Mise à jour du cache API (format harmonisé avec ZONE2_AI)
                signals_cache.append({
                    "timestamp": datetime.now().isoformat(),
                    "bot": "MULTI_SYMBOL",
                    "symbol": symbol,
                    "signal": signal if signal else "none",
                    "price": price,
                    "strength": f"{score}/3",
                    "executed": executed,
                    "reason": reason
                })
                if len(signals_cache) > 200:
                    signals_cache.pop(0)
                
                # Save state periodically and on signals
                if signal:
                    save_state()

                # Délai minimal pour ne pas saturer l'API
                time.sleep(0.2)

            except Exception as e:
                logger.log_error(f"Loop error on {symbol}", e)
                time.sleep(10)

        # ================= AUTO-TUNING =================
        try:
            # Trigger Auto-Tuner every 10 trades
            if total_trades > 0 and total_trades - LAST_TUNE_TRADES >= 10:
                print("🔄 Lancement de l'Auto-Tuner...", flush=True)
                # On utilise BTC par défaut comme indicateur de marché général
                best_config = tuner.get_best_configuration(SYMBOLS, TIMEFRAME)
                
                if best_config:
                    new_strat = best_config['strategy']
                    p = best_config['params']

                    # Only switch if meaningfully different
                    if new_strat != ACTIVE_STRATEGY or p['sl_multi'] != CURRENT_SL_MULTI or p['threshold'] != CURRENT_THRESHOLD:
                        ACTIVE_STRATEGY = new_strat
                        CURRENT_SL_MULTI = p['sl_multi']
                        CURRENT_TP_MULTI = p['tp_multi']
                        CURRENT_THRESHOLD = p['threshold']

                        msg = (f"🔄 AUTO-TUNER ACTIF 🔄\n"
                               f"Nouvelle Strat: {ACTIVE_STRATEGY}\n"
                               f"SL Multi: {CURRENT_SL_MULTI}x\n"
                               f"TP Multi: {CURRENT_TP_MULTI}x\n"
                               f"Threshold: {CURRENT_THRESHOLD}\n"
                               f"Expected WinRate: {best_config['expected_wr']:.1f}%\n"
                               f"Expected PnL: {best_config['expected_pnl']:.2f} ATR")
                        print(msg, flush=True)
                        send_telegram(msg)
                    else:
                        print("🔍 Auto-Tuner: config actuelle déjà optimale, pas de changement.", flush=True)
                else:
                    print("🔍 Auto-Tuner: aucune meilleure config trouvée, stratégie conservée.", flush=True)
                
                LAST_TUNE_TRADES = total_trades
        except Exception as e:
            logger.log_error("Auto-tuner error", e)

        # Nettoyage périodique du cache des positions actives (vérification réelle sur Bybit)
        try:
            for s in list(active_positions.keys()):
                # On force la vérification sur l'échange pour vider le cache si la position est fermée
                has_open_position(s, ignore_cache=True)
        except Exception as e:
            logger.log_error("Cleanup positions cache error", e)
            
        # Pause très courte entre les cycles pour une réactivité maximale (5s)
        save_state()
        time.sleep(5)

# ================= START =================

if __name__ == "__main__":
    # Correction d'éventuels problèmes de chargement des marchés
    try:
        exchange.load_markets()
    except:
        pass
        
    load_state()
        
    t = threading.Thread(target=start_api)
    t.daemon = True
    t.start()

    bot_loop()
