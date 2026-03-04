positions = {}


def add_position(symbol, data):

    positions[symbol] = data


def remove_position(symbol):

    if symbol in positions:
        del positions[symbol]


def get_positions():

    return positions


def lowest_score():

    if not positions:
        return None

    return min(positions.items(), key=lambda x: x[1]["score"])