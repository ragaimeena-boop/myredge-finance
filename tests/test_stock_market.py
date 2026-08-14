import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from app.main import app
from app.database import get_connection, init_db
from app.stock_market import (
    get_live_market_indices,
    get_top_market_movers,
    generate_daily_ai_research,
    get_ticker_ai_deep_dive
)

@pytest.fixture(autouse=True)
def setup_test_db(tmp_path, monkeypatch):
    """Set up temporary SQLite database for testing stock market module."""
    db_file = tmp_path / "test_stock_market.db"
    monkeypatch.setattr("app.config.settings.DATABASE_URL", f"sqlite:///{db_file}")
    init_db()
    return db_file

@pytest.fixture(autouse=True)
def mock_yfinance(monkeypatch):
    """Mock yfinance calls to ensure fast, deterministic tests without hitting live APIs."""
    class FakeFastInfo:
        last_price = 150.00
        regular_market_price = 150.00
        previous_close = 145.00
        regular_market_previous_close = 145.00
        last_volume = 1000000
        regular_market_volume = 1000000

    class FakeTicker:
        def __init__(self, symbol):
            self.symbol = symbol
            self.fast_info = FakeFastInfo()
            self.info = {
                "longName": f"{symbol} Corporation",
                "forwardPE": 24.5,
                "marketCap": 1500000000000
            }

    try:
        import yfinance as yf
        monkeypatch.setattr("yfinance.Ticker", FakeTicker)
    except Exception:
        pass

def test_get_live_market_indices():
    indices = get_live_market_indices()
    assert isinstance(indices, list)
    assert len(indices) >= 4
    for idx in indices:
        assert "symbol" in idx
        assert "name" in idx
        assert "price" in idx
        assert "status" in idx

def test_get_top_market_movers():
    movers = get_top_market_movers()
    assert "gainers" in movers
    assert "losers" in movers
    assert "active" in movers
    assert isinstance(movers["gainers"], list)

def test_generate_daily_ai_research():
    conn = get_connection()
    try:
        research = generate_daily_ai_research(conn=conn, force_refresh=True)
        assert "market_sentiment" in research
        assert "macro_summary" in research
        assert "opportunities" in research
        assert len(research["opportunities"]) > 0

        # Test caching
        cached_research = generate_daily_ai_research(conn=conn, force_refresh=False)
        assert cached_research["cached"] is True
    finally:
        conn.close()

def test_get_ticker_ai_deep_dive():
    conn = get_connection()
    try:
        data = get_ticker_ai_deep_dive("NVDA", conn=conn)
        assert data["ticker"] == "NVDA"
        assert "thesis" in data
        assert "bull_case" in data
        assert "articles" in data
    finally:
        conn.close()

def test_stock_market_web_routes():
    client = TestClient(app)
    
    # Test GET /stock-market
    res = client.get("/stock-market")
    assert res.status_code == 200
    assert "Stock Market" in res.text
    assert "AI Opportunities" in res.text

    # Test POST /api/stock-market/refresh
    res_post = client.post("/api/stock-market/refresh", follow_redirects=True)
    assert res_post.status_code == 200

    # Test GET /api/stock-market/ticker/NVDA
    res_ticker = client.get("/api/stock-market/ticker/NVDA")
    assert res_ticker.status_code == 200
    json_data = res_ticker.json()
    assert json_data["ticker"] == "NVDA"
