import sqlite3
import os
from datetime import datetime

DB_PATH = os.getenv("DB_PATH", "data/trades.db")

os.makedirs("data", exist_ok=True)


def get_connection():
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT,
        side TEXT,
        entry REAL,
        exit REAL,
        sl REAL,
        tp REAL,
        qty REAL,
        pnl REAL,
        result TEXT,
        timestamp TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS equity_curve (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        equity REAL,
        timestamp TEXT
    )
    """)

    conn.commit()
    conn.close()


def insert_trade(symbol, side, entry, exit_price, sl, tp, qty, pnl, result):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO trades
        (symbol, side, entry, exit, sl, tp, qty, pnl, result, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        symbol, side, entry, exit_price,
        sl, tp, qty, pnl, result,
        datetime.utcnow().isoformat()
    ))

    conn.commit()
    conn.close()


def get_recent_trades(limit=50):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT symbol, side, entry, exit, sl, tp, qty, pnl, result, timestamp
        FROM trades
        ORDER BY id DESC
        LIMIT ?
    """, (limit,))

    rows = cursor.fetchall()
    conn.close()

    keys = ["symbol", "side", "entry", "exit", "sl", "tp", "qty", "pnl", "result", "timestamp"]

    return [dict(zip(keys, row)) for row in rows]