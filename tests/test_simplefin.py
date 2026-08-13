import json
import sqlite3
from pathlib import Path
import pytest
from app.database import init_db
from app.models import SimpleFINResponse
from app.simplefin import ingest_simplefin_data

FIXTURES_DIR = Path(__file__).parent / "fixtures"

@pytest.fixture
def test_db(tmp_path, monkeypatch):
    db_file = tmp_path / "test_finance.db"
    monkeypatch.setattr("app.config.settings.DATABASE_URL", f"sqlite:///{db_file}")
    init_db()
    conn = sqlite3.connect(db_file)
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()

def test_ingest_simplefin_sample_fixture(test_db):
    fixture_path = FIXTURES_DIR / "simplefin_sample.json"
    with open(fixture_path, "r") as f:
        raw_json = json.load(f)

    response = SimpleFINResponse.model_validate(raw_json)
    stats = ingest_simplefin_data(response, conn=test_db)

    assert stats["accounts_synced"] == 2
    assert stats["transactions_synced"] == 5
    assert stats["snapshots_created"] == 2

    cursor = test_db.cursor()

    # Verify Account details
    cursor.execute("SELECT * FROM accounts WHERE id = 'acc_checking_01';")
    checking = cursor.fetchone()
    assert checking["name"] == "Everyday Checking"
    assert checking["balance_cents"] == 452050

    # Verify Transaction details & Cents math
    cursor.execute("SELECT * FROM transactions WHERE id = 'tx_001';")
    tx1 = cursor.fetchone()
    assert tx1["amount_cents"] == -4520
    assert tx1["description"] == "TST* CHIPOTLE MEXICAN GRILL MIAMI FL"
    
    # Check auto-categorization rule assigned category to Restaurants & Dining
    cursor.execute("SELECT name FROM categories WHERE id = ?;", (tx1["category_id"],))
    cat_row = cursor.fetchone()
    assert cat_row["name"] == "Restaurants & Dining"

    # Verify Credit Card Payment transfer detection
    cursor.execute("SELECT * FROM transactions WHERE id = 'tx_003';")
    tx3 = cursor.fetchone()
    assert tx3["is_transfer"] == 1

def test_idempotent_ingestion(test_db):
    fixture_path = FIXTURES_DIR / "simplefin_sample.json"
    with open(fixture_path, "r") as f:
        raw_json = json.load(f)

    response = SimpleFINResponse.model_validate(raw_json)

    # First ingestion
    ingest_simplefin_data(response, conn=test_db)
    
    # Second ingestion with same data
    ingest_simplefin_data(response, conn=test_db)

    cursor = test_db.cursor()
    cursor.execute("SELECT COUNT(*) FROM accounts;")
    assert cursor.fetchone()[0] == 4

    cursor.execute("SELECT COUNT(*) FROM transactions;")
    assert cursor.fetchone()[0] == 8
