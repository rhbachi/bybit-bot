MAX_PORTFOLIO_RISK = 0.10


def portfolio_risk(positions, capital):

    total = 0

    for p in positions.values():
        total += p["risk"]

    return total / capital


def can_open_trade(positions, capital, risk):

    current = portfolio_risk(positions, capital)

    if current + risk > MAX_PORTFOLIO_RISK:
        return False

    return True