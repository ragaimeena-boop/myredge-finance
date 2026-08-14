import pytest
from app.investments import fetch_stock_quote, get_portfolio_market_quotes
from app.reports import get_investments_summary

def test_fetch_stock_quote_mock_fallback():
    quote = fetch_stock_quote("NVDA")
    assert quote["ticker"] == "NVDA"
    assert quote["price"] > 0
    assert "change_pct" in quote

def test_portfolio_market_quotes_calculation():
    holdings = [
        {"id": 1, "account_id": "acc_01", "account_name": "Schwab", "ticker": "NVDA", "name": "Nvidia", "asset_type": "Stock", "shares": 10.0, "cost_basis_cents": 100000},
        {"id": 2, "account_id": "acc_01", "account_name": "Schwab", "ticker": "TSLA", "name": "Tesla", "asset_type": "Stock", "shares": 5.0, "cost_basis_cents": 100000}
    ]
    summary = get_portfolio_market_quotes(holdings)
    assert len(summary["holdings"]) == 2
    assert summary["top_gainer"] is not None
    assert summary["top_loser"] is not None

def test_investments_report_summary(auth_client):
    summary = get_investments_summary()
    assert "formatted_portfolio_value" in summary
    assert "holdings" in summary
    assert "asset_allocation" in summary

def test_investments_route(auth_client):
    response = auth_client.get("/investments")
    assert response.status_code == 200
    assert "Investments & Portfolio" in response.text
