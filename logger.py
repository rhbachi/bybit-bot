import csv
import os
from datetime import datetime, timezone

FILE = "trades.csv"

HEADER = [
    "timestamp",
    "symbol",
    "side",
    "qty",
    "entry_price",
    "exit_price",
    "pnl_usdt",
    "result"
]

def init_logger():
    """
    Initialise le fichier CSV s'il n'existe pas.
    """
    if not os.path.exists(FILE):
        with open(FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(HEADER)


def log_trade(symbol, side, qty, entry_price, exit_price, pnl_usdt, result):
    """
    Ajoute une ligne de trade au CSV.
    """
    with open(FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            datetime.now(timezone.utc).isoformat(),
            symbol,
            side,
            round(float(qty), 6),
            round(float(entry_price), 4),
            round(float(exit_price), 4),
            round(float(pnl_usdt), 4),
            result
        ])
