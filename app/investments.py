import httpx
from typing import Dict, Any, List
from decimal import Decimal
from app.utils import format_currency, to_cents

MOCK_STOCK_QUOTES = {
    "VOO": {"price": 492.50, "prev_close": 488.00, "name": "Vanguard S&P 500 ETF"},
    "NVDA": {"price": 128.40, "prev_close": 123.20, "name": "NVIDIA Corporation"},
    "AAPL": {"price": 224.50, "prev_close": 221.00, "name": "Apple Inc"},
    "MSFT": {"price": 448.20, "prev_close": 445.00, "name": "Microsoft Corporation"},
    "TSLA": {"price": 212.00, "prev_close": 216.50, "name": "Tesla Inc"},
    "TRP2055": {"price": 164.80, "prev_close": 163.50, "name": "Transamerica Target 2055"},
}

def fetch_stock_quote(ticker: str) -> Dict[str, Any]:
    """
    Fetch stock quote for ticker via Yahoo Finance API with realistic mock fallback.
    """
    ticker_upper = ticker.upper()
    
    # Try fetching live quote from Yahoo Finance API
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker_upper}"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        response = httpx.get(url, headers=headers, timeout=5.0)
        if response.status_code == 200:
            meta = response.json()["chart"]["result"][0]["meta"]
            price = float(meta.get("regularMarketPrice", 0))
            prev_close = float(meta.get("chartPreviousClose", price))
            if price > 0:
                change = price - prev_close
                pct_change = round((change / prev_close) * 100, 2) if prev_close > 0 else 0.0
                return {
                    "ticker": ticker_upper,
                    "price": price,
                    "prev_close": prev_close,
                    "change": round(change, 2),
                    "change_pct": pct_change,
                    "is_live": True
                }
    except Exception:
        pass

    # Fallback mock quotes
    mock = MOCK_STOCK_QUOTES.get(ticker_upper, {"price": 100.0, "prev_close": 100.0})
    price = mock["price"]
    prev_close = mock["prev_close"]
    change = round(price - prev_close, 2)
    pct_change = round((change / prev_close) * 100, 2) if prev_close > 0 else 0.0

    return {
        "ticker": ticker_upper,
        "price": price,
        "prev_close": prev_close,
        "change": change,
        "change_pct": pct_change,
        "is_live": False
    }

def get_portfolio_market_quotes(holdings: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Process list of portfolio holdings, fetch quotes, and compute Top Gainer & Top Loser.
    """
    enriched_holdings = []
    top_gainer = None
    top_loser = None

    for h in holdings:
        ticker = h["ticker"]
        quote = fetch_stock_quote(ticker)
        
        shares = float(h["shares"])
        price = quote["price"]
        mkt_val = round(shares * price, 2)
        mkt_val_cents = to_cents(mkt_val)

        cost_basis_cents = h["cost_basis_cents"]
        gain_loss_cents = mkt_val_cents - cost_basis_cents
        gain_loss_pct = round((gain_loss_cents / cost_basis_cents) * 100, 2) if cost_basis_cents > 0 else 0.0

        item = {
            "id": h["id"],
            "account_id": h["account_id"],
            "account_name": h["account_name"],
            "ticker": ticker,
            "name": h["name"],
            "asset_type": h["asset_type"],
            "shares": shares,
            "price": price,
            "formatted_price": f"${price:,.2f}",
            "market_value_cents": mkt_val_cents,
            "formatted_market_value": format_currency(mkt_val_cents),
            "cost_basis_cents": cost_basis_cents,
            "formatted_cost_basis": format_currency(cost_basis_cents),
            "gain_loss_cents": gain_loss_cents,
            "formatted_gain_loss": format_currency(gain_loss_cents),
            "gain_loss_pct": gain_loss_pct,
            "day_change": quote["change"],
            "day_change_pct": quote["change_pct"]
        }
        enriched_holdings.append(item)

        # Track Top Gainer and Top Loser
        if top_gainer is None or item["day_change_pct"] > top_gainer["day_change_pct"]:
            top_gainer = item
        if top_loser is None or item["day_change_pct"] < top_loser["day_change_pct"]:
            top_loser = item

    return {
        "holdings": enriched_holdings,
        "top_gainer": top_gainer,
        "top_loser": top_loser
    }
