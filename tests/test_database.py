import sqlite3
import pytest
from app.database import init_db

@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    db_file = tmp_path / "test_finance.db"
    monkeypatch.setattr("app.config.settings.DATABASE_URL", f"sqlite:///{db_file}")
    init_db()
    conn = sqlite3.connect(db_file)
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()

def test_database_initialization(temp_db):
    cursor = temp_db.cursor()
    
    # Check tables exist
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = {row[0] for row in cursor.fetchall()}
    assert "accounts" in tables
    assert "transactions" in tables
    assert "categories" in tables
    assert "rules" in tables
    assert "balance_snapshots" in tables

    # Check categories seeded
    cursor.execute("SELECT COUNT(*) FROM categories;")
    assert cursor.fetchone()[0] > 0

    # Check rules seeded
    cursor.execute("SELECT COUNT(*) FROM rules;")
    assert cursor.fetchone()[0] > 0

def test_purge_demo_data(temp_db):
    from app.database import purge_demo_data
    stats = purge_demo_data(conn=temp_db)
    assert stats["accounts_deleted"] >= 0
    
    cursor = temp_db.cursor()
    cursor.execute("SELECT COUNT(*) FROM accounts WHERE id IN ('acc_schwab_01', 'acc_transamerica_01', 'acc_checking_01', 'acc_credit_01');")
    assert cursor.fetchone()[0] == 0

