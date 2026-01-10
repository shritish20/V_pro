import sqlite3
from datetime import datetime

class DatabaseManager:
    def __init__(self, db_path="volguard_trades.db"):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.create_tables()

    def create_tables(self):
        cursor = self.conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                strategy_type TEXT, expiry DATE, status TEXT DEFAULT 'OPEN',
                entry_premium REAL DEFAULT 0.0, realized_pnl REAL DEFAULT 0.0,
                exit_reason TEXT
            )
        ''')
        self.conn.commit()

    def log_trade(self, strategy_type, expiry, entry_premium):
        cursor = self.conn.cursor()
        cursor.execute("INSERT INTO trades (strategy_type, expiry, entry_premium) VALUES (?, ?, ?)", 
                      (strategy_type, str(expiry), entry_premium))
        self.conn.commit()
