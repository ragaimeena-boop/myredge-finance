import sqlite3
import pytest
from app.database import init_db
from app.models import SimpleFINResponse
from app.simplefin import ingest_simplefin_data
from app.reports import generate_weekly_report, generate_monthly_report, generate_yearly_report, calculate_net_worth
from pathlib import Path
import json

FIXTURES_DIR = Path(__file__).parent / "fixtures"

@pytest.fixture
def populated_db(tmp_path, monkeypatch):
    db_file = tmp_path / "test_reports.db"
    monkeypatch.setattr("app.config.settings.DATABASE_URL", f"sqlite:///{db_file}")
    init_db()
    conn = sqlite3.connect(db_file)
    conn.row_factory = sqlite3.Row

    fixture_path = FIXTURES_DIR / "simplefin_sample.json"
    with open(fixture_path, "r") as f:
        raw_json = json.load(f)

    response = SimpleFINResponse.model_validate(raw_json)
    ingest_simplefin_data(response, conn=conn)

    yield conn
    conn.close()

def test_net_worth_calculation(populated_db):
    res = calculate_net_worth(conn=populated_db)
    assert res["net_worth_cents"] == 12051975
    assert res["formatted_net_worth"] == "$120,519.75"
    assert len(res["accounts"]) == 4

def test_reports_generation(populated_db):
    # Test weekly report query
    w_report = generate_weekly_report("2023-08-07", "2023-08-13", conn=populated_db)
    assert w_report["expense_cents"] == 16570  # 45.20 (Chipotle) + 120.50 (FPL)
    assert w_report["income_cents"] == 320000  # 3200.00 (Salary)

    # Test monthly report query
    m_report = generate_monthly_report(2023, 8, conn=populated_db)
    assert m_report["expense_cents"] == 16570
    assert m_report["income_cents"] == 320000
    assert m_report["savings_rate_pct"] > 0
    assert "rolling_6_months" in m_report
    assert len(m_report["rolling_6_months"]) == 6
    curr_m = [m for m in m_report["rolling_6_months"] if m["is_current"]][0]
    assert curr_m["income_cents"] == 320000
    assert curr_m["total_expense_cents"] == 16570
    assert curr_m["bills_cents"] + curr_m["spending_cents"] == curr_m["total_expense_cents"]

    # Test yearly report query
    y_report = generate_yearly_report(2023, conn=populated_db)
    assert y_report["expense_cents"] == 16570
    assert len(y_report["monthly_trends"]) == 12
