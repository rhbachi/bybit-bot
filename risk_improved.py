"""
Module de gestion du risque amélioré
Calcul de position size avec validations de sécurité
"""


def calculate_position_size(capital, risk_pct, stop_loss_pct, price, leverage):
    """
    Calcule la taille de position optimale en fonction du risque
    
    Args:
        capital: Capital total disponible (USDT)
        risk_pct: Pourcentage du capital à risquer par trade (ex: 0.05 = 5%)
        stop_loss_pct: Pourcentage de stop loss (ex: 0.006 = 0.6%)
        price: Prix actuel de l'asset
        leverage: Levier utilisé (ex: 2 = 2x)
    
    Returns:
        float: Quantité à trader (arrondie à 4 décimales)
    
    Exemple:
        Capital = 30 USDT
        Risk = 5% = 1.5 USDT
        Stop Loss = 0.6%
        
        Position value = 1.5 / 0.006 = 250 USDT
        Avec leverage 2x → Quantity = (250 * 2) / price
    """
    # Validations d'entrée
    if capital <= 0:
        print("⚠️ Capital invalide:", capital, flush=True)
        return 0
    
    if risk_pct <= 0 or risk_pct > 1:
        print("⚠️ Risk percentage invalide:", risk_pct, flush=True)
        return 0
    
    if stop_loss_pct <= 0 or stop_loss_pct > 1:
        print("⚠️ Stop loss percentage invalide:", stop_loss_pct, flush=True)
        return 0
    
    if price <= 0:
        print("⚠️ Prix invalide:", price, flush=True)
        return 0
    
    if leverage < 1 or leverage > 100:
        print("⚠️ Leverage invalide:", leverage, flush=True)
        return 0
    
    # Calcul du montant à risquer
    risk_amount = capital * risk_pct
    
    # Calcul de la valeur de position nécessaire
    # Pour perdre risk_amount avec un SL de stop_loss_pct, il faut:
    # position_value * stop_loss_pct = risk_amount
    position_value = risk_amount / stop_loss_pct
    
    # Avec leverage, on peut contrôler une position plus grande
    # Quantity = (position_value * leverage) / price
    quantity = (position_value * leverage) / price
    
    # Arrondir à 4 décimales (standard crypto)
    quantity = round(quantity, 4)
    
    # Validation finale
    if quantity <= 0:
        print("⚠️ Quantité calculée invalide:", quantity, flush=True)
        return 0
    
    # Vérification que la position ne dépasse pas le capital
    # La marge requise = (quantity * price) / leverage
    required_margin = (quantity * price) / leverage
    
    if required_margin > capital:
        print(
            f"⚠️ Position trop grande! "
            f"Marge requise: {round(required_margin, 2)} USDT > "
            f"Capital: {capital} USDT",
            flush=True
        )
        # Ajuster la quantité pour correspondre au capital disponible
        quantity = (capital * 0.95 * leverage) / price  # 95% pour marge de sécurité
        quantity = round(quantity, 4)
    
    print(
        f"📊 Position calculée: "
        f"Qty={quantity} | "
        f"Valeur={round(quantity * price, 2)} USDT | "
        f"Marge={round(required_margin, 2)} USDT | "
        f"Risque={round(risk_amount, 2)} USDT ({round(risk_pct*100, 1)}%)",
        flush=True
    )
    
    return quantity


def validate_position_size(qty, price, capital, leverage, min_notional=5.0):
    """
    Valide qu'une taille de position respecte toutes les contraintes
    
    Args:
        qty: Quantité à trader
        price: Prix actuel
        capital: Capital disponible
        leverage: Levier
        min_notional: Valeur minimale de trade (Bybit = 5 USDT)
    
    Returns:
        tuple: (is_valid: bool, error_message: str)
    """
    # Vérifier notionnel minimum
    notional = qty * price
    if notional < min_notional:
        return False, f"Notionnel trop faible: {round(notional, 2)} < {min_notional} USDT"
    
    # Vérifier marge disponible
    required_margin = (qty * price) / leverage
    if required_margin > capital:
        return False, f"Marge insuffisante: {round(required_margin, 2)} > {capital} USDT"
    
    # Vérifier quantité positive
    if qty <= 0:
        return False, "Quantité invalide (<= 0)"
    
    return True, "OK"


def calculate_sl_tp_prices(entry_price, side, stop_loss_pct, rr_multiplier):
    """
    Calcule les prix de Stop Loss et Take Profit
    
    Args:
        entry_price: Prix d'entrée
        side: 'long' ou 'short'
        stop_loss_pct: Pourcentage de stop loss (ex: 0.006 = 0.6%)
        rr_multiplier: Ratio Risk/Reward (ex: 2.3 = 1:2.3)
    
    Returns:
        tuple: (sl_price: float, tp_price: float)
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
        float: Ratio R:R (ex: 2.5 pour 1:2.5)
    """
    if side == "long":
        risk = entry_price - sl_price
        reward = tp_price - entry_price
    else:
        risk = sl_price - entry_price
        reward = entry_price - tp_price
    
    if risk <= 0:
        return 0
    
    rr_ratio = reward / risk
    return round(rr_ratio, 2)
