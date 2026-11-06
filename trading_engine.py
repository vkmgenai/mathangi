import sqlite3
import logging
import math
import threading
from datetime import datetime, time, timedelta

DB_PATH = "market_data.db"
_market_doc_sync_thread = None
_market_doc_sync_lock = threading.Lock()


def _run_market_doc_sync_daily():
    while True:
        try:
            from sync_market_docs import overwrite_market_vector_store

            overwrite_market_vector_store()
        except Exception:
            logging.exception("Daily market document sync failed")

        now = datetime.now()
        next_run = datetime.combine(now.date(), time.min)
        if next_run <= now:
            next_run += timedelta(days=1)

        threading.Event().wait((next_run - now).total_seconds())


def _start_market_doc_sync_scheduler():
    global _market_doc_sync_thread

    with _market_doc_sync_lock:
        if _market_doc_sync_thread is None or not _market_doc_sync_thread.is_alive():
            _market_doc_sync_thread = threading.Thread(
                target=_run_market_doc_sync_daily,
                name="market-doc-sync",
                daemon=True,
            )
            _market_doc_sync_thread.start()

def init_trading_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Account Cash Balance Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS account (
            id INTEGER PRIMARY KEY,
            cash_balance REAL
        )
    ''')
    
    # Portfolio Positions Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS positions (
            symbol TEXT PRIMARY KEY,
            name TEXT,
            quantity INTEGER,
            average_price REAL
        )
    ''')
    
    # Trade Audit Trail Log
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS trade_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            action TEXT,
            symbol TEXT,
            quantity INTEGER,
            price REAL,
            total_amount REAL
        )
    ''')
    
    # Initialize default balance if empty
    cursor.execute("SELECT COUNT(*) FROM account")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO account (id, cash_balance) VALUES (1, 1000.0)")
        
    conn.commit()
    conn.close()
    _start_market_doc_sync_scheduler()

def get_account_summary():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT cash_balance FROM account WHERE id = 1")
    cash = cursor.fetchone()[0]
    
    cursor.execute("SELECT symbol, name, quantity, average_price FROM positions")
    positions = [{"symbol": r[0], "name": r[1], "quantity": r[2], "average_price": r[3]} for r in cursor.fetchall()]
    conn.close()
    
    return {"cash_balance": cash, "positions": positions}

def set_account_cash_balance(cash_balance: float):
    if not math.isfinite(cash_balance) or cash_balance < 0:
        raise ValueError("Cash balance must be a finite, non-negative number.")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE account SET cash_balance = ? WHERE id = 1", (cash_balance,))
    conn.commit()
    conn.close()
    return cash_balance

def execute_trade(action: str, symbol: str, name: str, quantity: int, price: float):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT cash_balance FROM account WHERE id = 1")
    cash = cursor.fetchone()[0]
    total_cost = quantity * price

    if action.upper() == "BUY":
        if cash < total_cost:
            conn.close()
            return {"success": False, "error": "Insufficient mock cash balance."}
        
        # Deduct cash & add position
        new_cash = cash - total_cost
        cursor.execute("UPDATE account SET cash_balance = ? WHERE id = 1", (new_cash,))
        
        cursor.execute("SELECT quantity, average_price FROM positions WHERE symbol = ?", (symbol,))
        row = cursor.fetchone()
        if row:
            old_qty, old_avg = row
            new_qty = old_qty + quantity
            new_avg = ((old_qty * old_avg) + total_cost) / new_qty
            cursor.execute("UPDATE positions SET quantity = ?, average_price = ? WHERE symbol = ?", (new_qty, new_avg, symbol))
        else:
            cursor.execute("INSERT INTO positions (symbol, name, quantity, average_price) VALUES (?, ?, ?, ?)", (symbol, name, quantity, price))

    elif action.upper() == "SELL":
        cursor.execute("SELECT quantity FROM positions WHERE symbol = ?", (symbol,))
        row = cursor.fetchone()
        if not row or row[0] < quantity:
            conn.close()
            return {"success": False, "error": "Not enough units owned to sell."}
        
        new_qty = row[0] - quantity
        new_cash = cash + total_cost
        cursor.execute("UPDATE account SET cash_balance = ? WHERE id = 1", (new_cash,))
        
        if new_qty == 0:
            cursor.execute("DELETE FROM positions WHERE symbol = ?", (symbol,))
        else:
            cursor.execute("UPDATE positions SET quantity = ? WHERE symbol = ?", (new_qty, symbol))

    # Log trade
    cursor.execute("INSERT INTO trade_logs (action, symbol, quantity, price, total_amount) VALUES (?, ?, ?, ?, ?)",
                   (action.upper(), symbol, quantity, price, total_cost))
    conn.commit()
    conn.close()
    return {"success": True, "message": f"Successfully executed {action} for {quantity} units of {symbol}."}

if __name__ == "__main__":
    init_trading_db()