def calculate_position_size(capital, risk_pct, stop_loss_pct, price, leverage):
    risk_amount = capital * risk_pct
    position_value = risk_amount / stop_loss_pct
    quantity = (position_value * leverage) / price
    return round(quantity, 4)
