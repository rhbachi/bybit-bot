def adjust_quantity(exchange, symbol, qty, price):

    market = exchange.market(symbol)

    min_amount = market["limits"]["amount"]["min"]
    precision = market["precision"]["amount"]

    step_size = 10 ** (-precision)

    qty = max(qty, min_amount)

    qty = round(qty / step_size) * step_size

    min_notional = 5

    if qty * price < min_notional:
        return None

    return float(qty)