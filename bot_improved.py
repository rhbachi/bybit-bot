import time
import pandas as pd
from datetime import datetime, timezone

from config import (
    exchange,
    SYMBOL,
    TIMEFRAME,
    CAPITAL,
    RISK_PER_TRADE,
    LEVERAGE,
)

from strategy_main import apply_indicators, check_signal
from risk import calculate_position_size
from notifier import send_telegram
from logger import init_logger, log_trade

# =========================
# PARAMÈTRES STRATÉGIE
# =========================
STOP_LOSS_PCT = 0.006
RR_MULTIPLIER = 2.3
MAX_TRADES_PER_DAY = 10
COOLDOWN_SECONDS = 600

# =========================
# ÉTAT
# =========================
in_position = False
trades_today = 0
last_trade_time = None
current_day = datetime.now(timezone.utc).date()

# Variables pour tracker le trade en cours
current_trade = {
    "entry_price": 0,
    "side": None,
    "qty": 0,
    "sl_price": 0,
    "tp_price": 0,
}

# =========================
# UTILS
# =========================
def safe_float(v, default=0.0):
    try:
        return float(v) if v is not None else default
    except Exception:
        return default


def reset_daily():
    global trades_today, current_day
    today = datetime.now(timezone.utc).date()
    if today != current_day:
        trades_today = 0
        current_day = today
        print("🔄 Nouveau jour", flush=True)
        send_telegram("🔄 Nouveau jour — compteurs réinitialisés")


def fetch_data():
    ohlcv = exchange.fetch_ohlcv(SYMBOL, TIMEFRAME, limit=120)
    return pd.DataFrame(
        ohlcv,
        columns=["time", "open", "high", "low", "close", "volume"],
    )


def get_available_balance():
    """
    Récupère le solde USDT disponible
    """
    try:
        balance = exchange.fetch_balance()
        usdt_balance = balance.get('USDT', {})
        available = safe_float(usdt_balance.get('free', 0))
        
        print(f"💰 Solde disponible: {available} USDT", flush=True)
        return available
    
    except Exception as e:
        print(f"⚠️ Erreur get_available_balance: {e}", flush=True)
        return 0


def get_min_notional(symbol):
    """
    Bybit / ccxt peut retourner None → fallback obligatoire
    """
    try:
        market = exchange.market(symbol)
        min_notional = market.get("limits", {}).get("cost", {}).get("min")

        if min_notional is None or min_notional <= 0:
            return 5.0

        return float(min_notional)

    except Exception as e:
        print("⚠️ Erreur get_min_notional:", e, flush=True)
        return 5.0


def adjust_qty_to_min_notional(symbol, qty, price):
    min_notional = get_min_notional(symbol)
    notional = qty * price

    if notional >= min_notional:
        return qty

    min_qty = min_notional / price

    print(
        f"⚠️ Ajustement qty → minNotional | "
        f"Old notional={round(notional,2)} | "
        f"MinNotional={min_notional} | "
        f"New qty={round(min_qty,6)}",
        flush=True,
    )

    return round(min_qty, 6)


def place_sl_tp_orders(symbol, side, qty, entry_price, sl_price, tp_price):
    """
    Place les ordres Stop Loss et Take Profit conditionnels sur Bybit V5
    
    Args:
        symbol: Symbole de trading (ex: ETH/USDT:USDT)
        side: 'long' ou 'short'
        qty: Quantité
        entry_price: Prix d'entrée
        sl_price: Prix du Stop Loss
        tp_price: Prix du Take Profit
    
    Returns:
        bool: True si SL/TP placés avec succès, False sinon
    """
    try:
        # Bybit V5 nécessite triggerDirection pour les ordres conditionnels
        if side == "long":
            # Stop Loss pour LONG : vendre si prix descend
            sl_params = {
                'stopLoss': sl_price,
                'triggerDirection': 'descending',  # Prix descend
                'triggerBy': 'LastPrice',
                'reduceOnly': True,
            }
            
            # Take Profit pour LONG : vendre si prix monte
            tp_params = {
                'takeProfit': tp_price,
                'triggerDirection': 'ascending',  # Prix monte
                'triggerBy': 'LastPrice',
                'reduceOnly': True,
            }
            
        else:  # short
            # Stop Loss pour SHORT : acheter si prix monte
            sl_params = {
                'stopLoss': sl_price,
                'triggerDirection': 'ascending',  # Prix monte
                'triggerBy': 'LastPrice',
                'reduceOnly': True,
            }
            
            # Take Profit pour SHORT : acheter si prix descend
            tp_params = {
                'takeProfit': tp_price,
                'triggerDirection': 'descending',  # Prix descend
                'triggerBy': 'LastPrice',
                'reduceOnly': True,
            }
        
        # Méthode 1 : Utiliser set_trading_stop (recommandé pour Bybit V5)
        try:
            exchange.private_post_v5_position_trading_stop({
                'category': 'linear',
                'symbol': symbol.replace('/', '').replace(':USDT', ''),
                'stopLoss': str(sl_price),
                'takeProfit': str(tp_price),
                'tpTriggerBy': 'LastPrice',
                'slTriggerBy': 'LastPrice',
                'positionIdx': 0,  # One-way mode
            })
            
            print(f"✅ SL/TP placés (méthode 1): SL={round(sl_price, 2)} | TP={round(tp_price, 2)}", flush=True)
            return True
            
        except Exception as e1:
            print(f"⚠️ Méthode 1 échouée: {e1}", flush=True)
            
            # Méthode 2 : Ordres conditionnels séparés
            try:
                order_side_close = 'sell' if side == 'long' else 'buy'
                
                # Placer Stop Loss
                sl_order = exchange.create_order(
                    symbol,
                    'market',
                    order_side_close,
                    qty,
                    None,
                    params={
                        'stopLoss': sl_price,
                        'triggerDirection': 'descending' if side == 'long' else 'ascending',
                        'triggerBy': 'LastPrice',
                        'reduceOnly': True,
                        'orderType': 'Market',
                        'triggerPrice': sl_price,
                    }
                )
                
                print(f"✅ Stop Loss placé: {round(sl_price, 2)}", flush=True)
                
                # Placer Take Profit
                tp_order = exchange.create_order(
                    symbol,
                    'market',
                    order_side_close,
                    qty,
                    None,
                    params={
                        'takeProfit': tp_price,
                        'triggerDirection': 'ascending' if side == 'long' else 'descending',
                        'triggerBy': 'LastPrice',
                        'reduceOnly': True,
                        'orderType': 'Market',
                        'triggerPrice': tp_price,
                    }
                )
                
                print(f"✅ Take Profit placé: {round(tp_price, 2)}", flush=True)
                return True
                
            except Exception as e2:
                print(f"❌ Méthode 2 échouée: {e2}", flush=True)
                return False
        
    except Exception as e:
        print(f"❌ Erreur générale placement SL/TP: {e}", flush=True)
        return False


def close_position_immediately(symbol, side, qty):
    """
    Ferme immédiatement une position si SL/TP n'ont pas pu être placés
    """
    try:
        close_side = 'sell' if side == 'long' else 'buy'
        exchange.create_market_order(symbol, close_side, qty, params={'reduceOnly': True})
        print(f"🛑 Position fermée immédiatement (pas de SL/TP)", flush=True)
        send_telegram(f"🛑 Position fermée par sécurité - SL/TP impossible à placer")
        return True
    except Exception as e:
        print(f"❌ Impossible de fermer la position: {e}", flush=True)
        return False


# =========================
# MAIN
# =========================
def run():
    global in_position, trades_today, last_trade_time, current_trade

    print("🤖 Bot Bybit V6.1 FIXED démarré", flush=True)
    send_telegram("🤖 Bot Bybit V6.1 FIXED démarré\n✅ SL/TP obligatoires activés")

    init_logger()

    try:
        exchange.set_leverage(LEVERAGE, SYMBOL)
        print(f"⚙️ Leverage configuré: {LEVERAGE}x", flush=True)
    except Exception as e:
        if "110043" not in str(e):
            print(f"⚠️ Erreur set_leverage: {e}", flush=True)
        else:
            print(f"⚙️ Leverage déjà à {LEVERAGE}x", flush=True)

    while True:
        try:
            print("⏳ Analyse marché...", flush=True)

            reset_daily()

            if trades_today >= MAX_TRADES_PER_DAY:
                print("🛑 Max trades atteints", flush=True)
                time.sleep(300)
                continue

            if last_trade_time and time.time() - last_trade_time < COOLDOWN_SECONDS:
                print("⏸ Cooldown actif", flush=True)
                time.sleep(60)
                continue

            df = fetch_data()
            df = apply_indicators(df)
            signal = check_signal(df)

            # ===== OUVERTURE DE POSITION =====
            if signal and not in_position:
                # 1️⃣ Vérifier le solde disponible
                available_balance = get_available_balance()
                
                if available_balance < 5:  # Minimum 5 USDT
                    print("❌ Solde insuffisant pour trader", flush=True)
                    send_telegram(f"⚠️ Solde insuffisant: {available_balance} USDT")
                    time.sleep(300)
                    continue
                
                # 2️⃣ Utiliser le minimum entre CAPITAL configuré et solde disponible
                effective_capital = min(CAPITAL, available_balance * 0.95)  # 95% du solde dispo
                
                print(f"📊 Capital effectif: {round(effective_capital, 2)} USDT (config: {CAPITAL}, dispo: {round(available_balance, 2)})", flush=True)
                
                # 3️⃣ Calculer la position
                price = df.iloc[-1].close

                qty = calculate_position_size(
                    effective_capital,  # Utiliser le capital effectif
                    RISK_PER_TRADE,
                    STOP_LOSS_PCT,
                    price,
                    LEVERAGE,
                )

                # Ajuster pour minNotional
                qty = adjust_qty_to_min_notional(SYMBOL, qty, price)

                if qty <= 0:
                    print("⚠️ Qty invalide → trade ignoré", flush=True)
                    time.sleep(300)
                    continue

                # 4️⃣ Calculer SL et TP
                if signal == "long":
                    sl_price = price * (1 - STOP_LOSS_PCT)
                    tp_price = price * (1 + (STOP_LOSS_PCT * RR_MULTIPLIER))
                    order_side = "buy"
                else:  # short
                    sl_price = price * (1 + STOP_LOSS_PCT)
                    tp_price = price * (1 - (STOP_LOSS_PCT * RR_MULTIPLIER))
                    order_side = "sell"

                # 5️⃣ Passer l'ordre d'entrée
                print(f"📊 Ouverture {signal.upper()} | Qty={qty} | Prix={round(price, 2)}", flush=True)
                
                order = exchange.create_market_order(
                    SYMBOL,
                    order_side,
                    qty,
                )

                # 6️⃣ Placer les ordres SL/TP (OBLIGATOIRE)
                print("🔒 Placement SL/TP...", flush=True)
                sl_tp_success = place_sl_tp_orders(SYMBOL, signal, qty, price, sl_price, tp_price)

                # 7️⃣ SI SL/TP ÉCHOUENT → FERMER LA POSITION IMMÉDIATEMENT
                if not sl_tp_success:
                    print("🚨 SL/TP non placés → Fermeture immédiate de la position", flush=True)
                    send_telegram(f"🚨 ALERTE CRITIQUE\nSL/TP impossible à placer\nPosition fermée par sécurité")
                    
                    close_position_immediately(SYMBOL, signal, qty)
                    
                    # Ne pas compter ce trade
                    time.sleep(300)
                    continue

                # 8️⃣ Mettre à jour l'état (seulement si SL/TP OK)
                in_position = True
                trades_today += 1
                last_trade_time = time.time()

                current_trade = {
                    "entry_price": price,
                    "side": signal,
                    "qty": qty,
                    "sl_price": sl_price,
                    "tp_price": tp_price,
                    "entry_time": datetime.now(timezone.utc),
                }

                # 9️⃣ Notification
                msg = (
                    f"🚀 TRADE OUVERT\n"
                    f"Direction: {signal.upper()}\n"
                    f"Prix: {round(price, 2)} USDT\n"
                    f"Quantité: {qty}\n"
                    f"SL: {round(sl_price, 2)} (-{STOP_LOSS_PCT*100}%)\n"
                    f"TP: {round(tp_price, 2)} (+{STOP_LOSS_PCT*RR_MULTIPLIER*100}%)\n"
                    f"Risk/Reward: 1:{RR_MULTIPLIER}\n"
                    f"SL/TP: ✅ PLACÉS ET CONFIRMÉS"
                )
                print(msg, flush=True)
                send_telegram(msg)

            # ===== VÉRIFIER CLÔTURE =====
            if in_position:
                positions = exchange.fetch_positions([SYMBOL])
                pos = next((p for p in positions if p.get("symbol") == SYMBOL), None)

                # Position fermée
                if pos and safe_float(pos.get("contracts")) == 0:
                    pnl = safe_float(pos.get("unrealizedPnl"))
                    
                    # Déterminer si c'est un WIN ou LOSS
                    result = "WIN" if pnl > 0 else "LOSS"
                    
                    # Estimer le prix de sortie
                    exit_price = current_trade["tp_price"] if pnl > 0 else current_trade["sl_price"]

                    # Logger avec les vraies données
                    log_trade(
                        SYMBOL,
                        current_trade["side"],
                        current_trade["qty"],
                        current_trade["entry_price"],
                        exit_price,
                        pnl,
                        result
                    )

                    # Calculer la durée du trade
                    duration = datetime.now(timezone.utc) - current_trade["entry_time"]
                    duration_minutes = int(duration.total_seconds() / 60)

                    # Notification détaillée
                    msg = (
                        f"{'🟢 WIN' if pnl > 0 else '🔴 LOSS'} - TRADE FERMÉ\n"
                        f"Direction: {current_trade['side'].upper()}\n"
                        f"Entrée: {round(current_trade['entry_price'], 2)} USDT\n"
                        f"Sortie: {round(exit_price, 2)} USDT\n"
                        f"PnL: {round(pnl, 2)} USDT ({round((pnl/effective_capital)*100, 2)}%)\n"
                        f"Durée: {duration_minutes} min\n"
                        f"Trades aujourd'hui: {trades_today}/{MAX_TRADES_PER_DAY}"
                    )
                    print(msg, flush=True)
                    send_telegram(msg)

                    # Reset état
                    in_position = False
                    current_trade = {
                        "entry_price": 0,
                        "side": None,
                        "qty": 0,
                        "sl_price": 0,
                        "tp_price": 0,
                    }

            time.sleep(300)

        except Exception as e:
            print("❌ Erreur bot:", e, flush=True)
            send_telegram(f"❌ Erreur bot: {e}")
            time.sleep(60)


if __name__ == "__main__":
    run()
