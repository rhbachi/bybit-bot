"""
Module de gestion du risque avec calcul correct du leverage
"""

def calculate_position_size(capital, risk_pct, stop_loss_pct, price, leverage):
    """
    Calcule la taille de position en tenant compte du leverage
    
    Args:
        capital: Capital alloué au bot (USDT)
        risk_pct: Pourcentage de risque par trade (ex: 0.03 = 3%)
        stop_loss_pct: Distance du stop loss en % (ex: 0.006 = 0.6%)
        price: Prix actuel de l'asset
        leverage: Leverage utilisé (ex: 2, 5, 10)
    
    Returns:
        float: Quantité à trader (en coins)
    
    Exemple:
        capital = 15 USDT
        risk_pct = 0.03 (3%)
        stop_loss_pct = 0.006 (0.6%)
        price = 1947 USDT
        leverage = 2
        
        → Position max (capital × leverage) = 30 USDT
        → Risque accepté = 0.45 USDT (3% de 15)
        → Position basée sur risque = 75 USDT (trop grand!)
        → Position finale = MIN(30, 75) = 30 USDT
        → Qty = 30 / 1947 = 0.0154 ETH
    """
    
    # Montant qu'on est prêt à risquer
    risk_amount = capital * risk_pct
    
    # Position maximale avec le leverage
    max_position_usdt = capital * leverage
    
    # Position basée sur le risque et le stop loss
    # Si on risque 0.45 USDT avec un SL de 0.6%, notre position peut être :
    risk_based_position = risk_amount / stop_loss_pct
    
    # Prendre le MINIMUM entre les deux pour ne jamais dépasser le capital
    actual_position_usdt = min(max_position_usdt, risk_based_position)
    
    # Convertir en quantité de coins
    qty = actual_position_usdt / price
    
    # Arrondir à 4 décimales
    qty = round(qty, 4)
    
    print(
        f"📊 Calcul position: "
        f"Capital={capital} | "
        f"Risk={risk_pct*100}% ({round(risk_amount,2)} USDT) | "
        f"Leverage={leverage}x | "
        f"Max position={round(max_position_usdt,2)} USDT | "
        f"Risk-based position={round(risk_based_position,2)} USDT | "
        f"Actual position={round(actual_position_usdt,2)} USDT | "
        f"Qty={qty}",
        flush=True
    )
    
    return qty


def validate_position_size(symbol, qty, price, capital, leverage):
    """
    Valide qu'une position ne dépasse pas le capital disponible
    
    Args:
        symbol: Symbole du trade
        qty: Quantité calculée
        price: Prix actuel
        capital: Capital disponible
        leverage: Leverage utilisé
    
    Returns:
        bool: True si la position est valide
    """
    notional = qty * price
    margin_required = notional / leverage
    
    if margin_required > capital:
        print(
            f"⚠️ Position invalide: "
            f"Marge requise={round(margin_required,2)} > "
            f"Capital={capital}",
            flush=True
        )
        return False
    
    print(
        f"✅ Position valide: "
        f"Notional={round(notional,2)} | "
        f"Marge={round(margin_required,2)} | "
        f"Capital={capital}",
        flush=True
    )
    
    return True


def calculate_sl_tp_prices(entry_price, side, stop_loss_pct, rr_multiplier):
    """
    Calcule les prix de Stop Loss et Take Profit
    
    Args:
        entry_price: Prix d'entrée
        side: 'long' ou 'short'
        stop_loss_pct: Distance du SL en % (ex: 0.006 = 0.6%)
        rr_multiplier: Ratio Risk/Reward (ex: 2.3)
    
    Returns:
        tuple: (sl_price, tp_price)
    """
    if side == "long":
        sl_price = entry_price * (1 - stop_loss_pct)
        tp_price = entry_price * (1 + (stop_loss_pct * rr_multiplier))
    else:  # short
        sl_price = entry_price * (1 + stop_loss_pct)
        tp_price = entry_price * (1 - (stop_loss_pct * rr_multiplier))
    
    return round(sl_price, 2), round(tp_price, 2)


def calculate_risk_reward_ratio(entry_price, sl_price, tp_price, side):
    """
    Calcule le ratio Risk/Reward réel
    
    Args:
        entry_price: Prix d'entrée
        sl_price: Prix du Stop Loss
        tp_price: Prix du Take Profit
        side: 'long' ou 'short'
    
    Returns:
        float: Ratio R:R
    """
    if side == "long":
        risk = entry_price - sl_price
        reward = tp_price - entry_price
    else:  # short
        risk = sl_price - entry_price
        reward = entry_price - tp_price
    
    if risk == 0:
        return 0
    
    rr_ratio = reward / risk
    return round(rr_ratio, 2)
