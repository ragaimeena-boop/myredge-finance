import sqlite3
from pathlib import Path
from typing import Generator
from app.config import settings

def get_db_path() -> Path:
    db_file = settings.db_path
    db_file.parent.mkdir(parents=True, exist_ok=True)
    return db_file

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def get_db() -> Generator[sqlite3.Connection, None, None]:
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()

def init_db():
    """Initialize database tables and seed default categories."""
    conn = get_connection()
    cursor = conn.cursor()

    # Accounts table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS accounts (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        currency TEXT DEFAULT 'USD',
        balance_cents INTEGER NOT NULL,
        available_balance_cents INTEGER,
        org_name TEXT,
        org_domain TEXT,
        updated_at TEXT NOT NULL
    );
    """)

    # Categories table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        group_name TEXT NOT NULL,
        icon TEXT DEFAULT 'tag',
        color TEXT DEFAULT '#94A3B8',
        is_income INTEGER DEFAULT 0,
        is_transfer INTEGER DEFAULT 0
    );
    """)

    # Rules table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS rules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pattern TEXT NOT NULL UNIQUE,
        category_id INTEGER NOT NULL,
        clean_payee TEXT,
        is_transfer INTEGER DEFAULT 0,
        priority INTEGER DEFAULT 0,
        FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE CASCADE
    );
    """)

    # Transactions table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS transactions (
        id TEXT PRIMARY KEY,
        account_id TEXT NOT NULL,
        posted_at TEXT NOT NULL,
        posted_timestamp INTEGER NOT NULL,
        amount_cents INTEGER NOT NULL,
        description TEXT NOT NULL,
        payee TEXT,
        memo TEXT,
        pending INTEGER DEFAULT 0,
        category_id INTEGER,
        is_transfer INTEGER DEFAULT 0,
        user_notes TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE,
        FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE SET NULL
    );
    """)

    # Balance Snapshots table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS balance_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id TEXT NOT NULL,
        snapshot_date TEXT NOT NULL,
        balance_cents INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(account_id, snapshot_date),
        FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE
    );
    """)

    # Holdings table for investment accounts
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS holdings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id TEXT NOT NULL,
        ticker TEXT NOT NULL,
        name TEXT NOT NULL,
        asset_type TEXT NOT NULL,
        shares REAL NOT NULL,
        cost_basis_cents INTEGER NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE(account_id, ticker),
        FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE
    );
    """)

    # Seed Default Categories if empty
    cursor.execute("SELECT COUNT(*) FROM categories;")
    if cursor.fetchone()[0] == 0:
        default_categories = [
            # Income
            ("Salary & Wages", "Income", "briefcase", "#10B981", 1, 0),
            ("Investments & Interest", "Income", "trending-up", "#059669", 1, 0),
            ("Other Income", "Income", "dollar-sign", "#34D399", 1, 0),
            
            # Housing
            ("Mortgage & Rent", "Housing", "home", "#6366F1", 0, 0),
            ("Utilities", "Housing", "zap", "#818CF8", 0, 0),
            ("Home Maintenance", "Housing", "tool", "#A5B4FC", 0, 0),

            # Food & Dining
            ("Groceries", "Food & Dining", "shopping-bag", "#F59E0B", 0, 0),
            ("Restaurants & Dining", "Food & Dining", "coffee", "#FBBF24", 0, 0),

            # Transportation
            ("Fuel & Gas", "Transportation", "truck", "#EF4444", 0, 0),
            ("Auto Payment & Insurance", "Transportation", "shield", "#F87171", 0, 0),
            ("Transit & Rideshare", "Transportation", "navigation", "#FCA5A5", 0, 0),

            # Lifestyle & Bills
            ("Shopping & Retail", "Lifestyle", "shopping-cart", "#EC4899", 0, 0),
            ("Subscriptions & Recurring", "Lifestyle", "repeat", "#F472B6", 0, 0),
            ("Medical & Healthcare", "Healthcare", "heart", "#06B6D4", 0, 0),

            # Transfers & Financial
            ("Credit Card Payment", "Transfers", "credit-card", "#64748B", 0, 1),
            ("Internal Transfer", "Transfers", "repeat", "#94A3B8", 0, 1),
            ("Uncategorized", "Other", "help-circle", "#64748B", 0, 0),
        ]

        cursor.executemany("""
        INSERT INTO categories (name, group_name, icon, color, is_income, is_transfer)
        VALUES (?, ?, ?, ?, ?, ?);
        """, default_categories)

    # Seed Default Categorization Rules if empty
    cursor.execute("SELECT COUNT(*) FROM rules;")
    if cursor.fetchone()[0] == 0:
        default_rules = [
            ("CHIPOTLE", "Restaurants & Dining", "Chipotle", 0),
            ("FLORIDA POWER", "Utilities", "Florida Power & Light", 0),
            ("CREDIT CARD PAYMENT", "Credit Card Payment", None, 1),
            ("PAYMENT THANK YOU", "Credit Card Payment", None, 1),
            ("AUTOPAY CREDIT CARD", "Credit Card Payment", None, 1),
            ("PAYROLL DIRECT DEPOSIT", "Salary & Wages", None, 0),
            ("DIVIDEND", "Investments & Interest", None, 0),
            ("SCHWAB", "Investments & Interest", "Charles Schwab", 0),
        ]
        
        for pattern, cat_name, clean_payee, is_trans in default_rules:
            cursor.execute("SELECT id FROM categories WHERE name = ?;", (cat_name,))
            row = cursor.fetchone()
            if row:
                cursor.execute("""
                INSERT OR IGNORE INTO rules (pattern, category_id, clean_payee, is_transfer, priority)
                VALUES (?, ?, ?, ?, 10);
                """, (pattern, row["id"], clean_payee, is_trans))

    # Seed Sample Investment Accounts & Holdings if empty
    cursor.execute("SELECT COUNT(*) FROM accounts WHERE id IN ('acc_schwab_01', 'acc_transamerica_01');")
    if cursor.fetchone()[0] == 0:
        now_str = "2026-08-13T00:00:00-04:00"
        inv_accounts = [
            ("acc_schwab_01", "Charles Schwab Brokerage", "USD", 3485000, 3485000, "Charles Schwab", "schwab.com", now_str),
            ("acc_transamerica_01", "Transamerica 401(k) Retirement", "USD", 8240000, 8240000, "Transamerica", "transamerica.com", now_str),
        ]
        cursor.executemany("""
        INSERT OR IGNORE INTO accounts (id, name, currency, balance_cents, available_balance_cents, org_name, org_domain, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?);
        """, inv_accounts)

        schwab_holdings = [
            ("acc_schwab_01", "VOO", "Vanguard S&P 500 ETF", "ETF", 25.0, 1150000, now_str),
            ("acc_schwab_01", "NVDA", "NVIDIA Corporation", "Stock", 30.0, 320000, now_str),
            ("acc_schwab_01", "AAPL", "Apple Inc", "Stock", 25.0, 420000, now_str),
            ("acc_schwab_01", "MSFT", "Microsoft Corporation", "Stock", 15.0, 580000, now_str),
            ("acc_schwab_01", "TSLA", "Tesla Inc", "Stock", 20.0, 410000, now_str),
            ("acc_transamerica_01", "TRP2055", "Transamerica Target 2055 Retirement Fund", "Retirement 401(k)", 500.0, 8240000, now_str),
        ]
        cursor.executemany("""
        INSERT OR IGNORE INTO holdings (account_id, ticker, name, asset_type, shares, cost_basis_cents, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?);
        """, schwab_holdings)

        # Seed sample investment transactions
        inv_txs = [
            ("tx_inv_01", "acc_schwab_01", "2026-08-05", 1785936000, 12550, "QUALIFIED DIVIDEND VANGUARD S&P 500 ETF", "Vanguard", "Quarterly dividend payout", 0, 2, 0, now_str, now_str),
            ("tx_inv_02", "acc_transamerica_01", "2026-08-01", 1785590400, 75000, "EMPLOYER MATCH 401K CONTRIBUTION", "Transamerica", "Biweekly 401k match", 0, 1, 0, now_str, now_str),
            ("tx_inv_03", "acc_schwab_01", "2026-07-28", 1785244800, -45000, "BUY 1.0 SHARE NVDA AT 450.00", "Charles Schwab", "Stock purchase", 0, 2, 0, now_str, now_str),
        ]
        cursor.executemany("""
        INSERT OR IGNORE INTO transactions (id, account_id, posted_at, posted_timestamp, amount_cents, description, payee, memo, pending, category_id, is_transfer, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, inv_txs)

    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print("Database schema successfully initialized.")
