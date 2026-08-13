import pytest
from fastapi.testclient import TestClient
from app.main import app

def test_dashboard_home_route(tmp_path, monkeypatch):
    db_file = tmp_path / "test_web.db"
    monkeypatch.setattr("app.config.settings.DATABASE_URL", f"sqlite:///{db_file}")
    
    with TestClient(app) as client:
        response = client.get("/")
        assert response.status_code == 200
        assert "MYREDGE Dashboard" in response.text
        assert "Net Worth" in response.text

def test_weekly_report_route(tmp_path, monkeypatch):
    db_file = tmp_path / "test_web.db"
    monkeypatch.setattr("app.config.settings.DATABASE_URL", f"sqlite:///{db_file}")

    with TestClient(app) as client:
        response = client.get("/reports/weekly")
        assert response.status_code == 200
        assert "Weekly Digest Report" in response.text

def test_monthly_report_route(tmp_path, monkeypatch):
    db_file = tmp_path / "test_web.db"
    monkeypatch.setattr("app.config.settings.DATABASE_URL", f"sqlite:///{db_file}")

    with TestClient(app) as client:
        response = client.get("/reports/monthly")
        assert response.status_code == 200
        assert "Monthly Deep-Dive Report" in response.text

def test_yearly_report_route(tmp_path, monkeypatch):
    db_file = tmp_path / "test_web.db"
    monkeypatch.setattr("app.config.settings.DATABASE_URL", f"sqlite:///{db_file}")

    with TestClient(app) as client:
        response = client.get("/reports/yearly")
        assert response.status_code == 200
        assert "Yearly Financial Retrospective" in response.text

def test_transactions_route(tmp_path, monkeypatch):
    db_file = tmp_path / "test_web.db"
    monkeypatch.setattr("app.config.settings.DATABASE_URL", f"sqlite:///{db_file}")

    with TestClient(app) as client:
        response = client.get("/transactions")
        assert response.status_code == 200
        assert "Transaction History" in response.text

def test_transactions_search_route(tmp_path, monkeypatch):
    db_file = tmp_path / "test_web.db"
    monkeypatch.setattr("app.config.settings.DATABASE_URL", f"sqlite:///{db_file}")
    from app.database import init_db
    from app.main import run_daily_sync
    init_db()
    run_daily_sync()

    with TestClient(app) as client:
        response = client.get("/transactions?q=chipotle")
        assert response.status_code == 200
        assert "Chipotle" in response.text

def test_transactions_empty_category_query(tmp_path, monkeypatch):
    db_file = tmp_path / "test_web.db"
    monkeypatch.setattr("app.config.settings.DATABASE_URL", f"sqlite:///{db_file}")
    from app.database import init_db
    from app.main import run_daily_sync
    init_db()
    run_daily_sync()

    with TestClient(app) as client:
        response = client.get("/transactions?q=chipotle&category_id=")
        assert response.status_code == 200
        assert "Chipotle" in response.text

def test_transactions_amount_search(tmp_path, monkeypatch):
    db_file = tmp_path / "test_web.db"
    monkeypatch.setattr("app.config.settings.DATABASE_URL", f"sqlite:///{db_file}")
    from app.database import init_db
    from app.main import run_daily_sync
    init_db()
    run_daily_sync()

    with TestClient(app) as client:
        response = client.get("/transactions?q=45.20")
        assert response.status_code == 200
        assert "Chipotle" in response.text

def test_update_transaction_category_api(tmp_path, monkeypatch):
    db_file = tmp_path / "test_web.db"
    monkeypatch.setattr("app.config.settings.DATABASE_URL", f"sqlite:///{db_file}")

    with TestClient(app) as client:
        response = client.post("/api/transactions/tx_001/category", data={"category_id": "1"}, follow_redirects=True)
        assert response.status_code == 200

def test_manual_sync_api(tmp_path, monkeypatch):
    db_file = tmp_path / "test_web.db"
    monkeypatch.setattr("app.config.settings.DATABASE_URL", f"sqlite:///{db_file}")

    with TestClient(app) as client:
        response = client.post("/api/sync", follow_redirects=False)
        assert response.status_code == 303
