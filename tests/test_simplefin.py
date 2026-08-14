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

def test_reapply_rules_to_uncategorized(test_db):
    from app.simplefin import reapply_rules_to_uncategorized
    cursor = test_db.cursor()

    # Insert an uncategorized Publix transaction
    cursor.execute("SELECT id FROM categories WHERE name = 'Uncategorized';")
    uncat_id = cursor.fetchone()["id"]

    cursor.execute("""
    INSERT INTO transactions (id, account_id, posted_at, posted_timestamp, amount_cents, description, payee, pending, category_id, created_at, updated_at)
    VALUES ('tx_publix_test', 'acc_checking_01', '2026-08-14', 1786665600, -6540, 'PUBLIX SUPER MARKETS #1234', 'Publix', 0, ?, '2026-08-14', '2026-08-14');
    """, (uncat_id,))
    test_db.commit()

    count = reapply_rules_to_uncategorized(conn=test_db)
    assert count >= 1

    cursor.execute("SELECT c.name FROM transactions t JOIN categories c ON t.category_id = c.id WHERE t.id = 'tx_publix_test';")
    row = cursor.fetchone()
    assert row["name"] == "Groceries"

def test_robust_categorization_engine(test_db):
    from app.simplefin import apply_categorization_rules

    # Test IRS/Taxes matching
    cat_id_tax, payee_tax, is_trans_tax = apply_categorization_rules(test_db, "ACH WITHDRAWAL IRS DES:US TREAS TAX REF ID:99203", "IRS")
    cursor = test_db.cursor()
    cursor.execute("SELECT name FROM categories WHERE id = ?;", (cat_id_tax,))
    assert cursor.fetchone()["name"] == "IRS/Taxes"

    # Test Office matching
    cat_id_off, payee_off, _ = apply_categorization_rules(test_db, "STAPLES #0482 MIAMI FL", "Staples")
    cursor.execute("SELECT name FROM categories WHERE id = ?;", (cat_id_off,))
    assert cursor.fetchone()["name"] == "Office"

    # Test Entertainment matching
    cat_id_ent, payee_ent, _ = apply_categorization_rules(test_db, "SQ *CINEMARK THEATRES #381", "Cinemark")
    cursor.execute("SELECT name FROM categories WHERE id = ?;", (cat_id_ent,))
    assert cursor.fetchone()["name"] == "Entertainment"


