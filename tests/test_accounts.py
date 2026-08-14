import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database import init_db, get_connection
from app.simplefin import clean_merchant_description, infer_account_type
from app.auth import create_user, create_session

def test_clean_merchant_description():
    assert clean_merchant_description("TST* CHIPOTLE MEXICAN GRILL MIAMI FL") == "CHIPOTLE MEXICAN GRILL"
    assert clean_merchant_description("SQ * STARBUCKS COFFEE #1234") == "STARBUCKS COFFEE"
    assert clean_merchant_description("PAYPAL * NETFLIX.COM FL 33101") == "NETFLIX.COM"

def test_infer_account_type():
    assert infer_account_type("Betterment Wealth", "Betterment") == "investment"
    assert infer_account_type("Buildwealth Investment Account", "Buildwealth") == "investment"
    assert infer_account_type("Schwab Brokerage", "Charles Schwab") == "investment"
    assert infer_account_type("401k Retirement Plan", "Transamerica") == "retirement"
    assert infer_account_type("Sapphire Credit Card", "Chase") == "credit_card"
    assert infer_account_type("Everyday Checking", "Chase") == "checking"

def test_accounts_page_and_type_update(tmp_path, monkeypatch):
    db_file = tmp_path / "test_acc.db"
    monkeypatch.setattr("app.config.settings.DATABASE_URL", f"sqlite:///{db_file}")
    init_db()

    conn = get_connection()
    try:
        user = create_user("test_admin", "TestPass123!", conn=conn)
        token = create_session(user["id"], conn=conn)
        cursor = conn.cursor()
        
        # Check new categories exist
        cursor.execute("SELECT name FROM categories WHERE name IN ('Data/Tele', 'Demetrius Income', 'Travel');")
        cats = {r[0] for r in cursor.fetchall()}
        assert "Data/Tele" in cats
        assert "Demetrius Income" in cats
        assert "Travel" in cats

        client = TestClient(app)
        client.cookies.set("myredge_session", token)

        # Check account_type column exists and accounts route renders
        res = client.get("/accounts")
        assert res.status_code == 200
        assert "Accounts & Institutions" in res.text
        assert "account_type" in res.text

        # Update account type for an account
        cursor.execute("SELECT id FROM accounts LIMIT 1;")
        row = cursor.fetchone()
        if row:
            acc_id = row[0]
            update_res = client.post(f"/api/accounts/{acc_id}/type", data={"account_type": "investment"}, follow_redirects=True)
            assert update_res.status_code == 200
            
            cursor.execute("SELECT account_type FROM accounts WHERE id = ?;", (acc_id,))
            assert cursor.fetchone()[0] == "investment"
    finally:
        conn.close()
