from datetime import datetime, date, timedelta
from typing import Dict, Any, List
import pytz
from app.config import settings
from app.utils import get_eastern_tz, to_dollars, format_currency
from app.database import get_connection

def get_date_bounds_for_week(target_date: date = None) -> tuple[str, str]:
    """Get ISO date strings (start_of_week Monday, end_of_week Sunday) for target_date."""
    if target_date is None:
        target_date = datetime.now(get_eastern_tz()).date()
    start = target_date - timedelta(days=target_date.weekday())  # Monday
    end = start + timedelta(days=6)  # Sunday
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")

def get_date_bounds_for_month(year: int, month: int) -> tuple[str, str]:
    """Get ISO date strings for first and last day of specified month."""
    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        end = date(year, month + 1, 1) - timedelta(days=1)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")

def get_date_bounds_for_year(year: int) -> tuple[str, str]:
    """Get ISO date strings for entire year."""
    return f"{year}-01-01", f"{year}-12-31"

def generate_weekly_report(start_date: str, end_date: str, conn=None) -> Dict[str, Any]:
    """Generate weekly financial summary and comparison."""
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True

    try:
        cursor = conn.cursor()

        # Expenses (negative amount_cents, non-transfer)
        cursor.execute("""
        SELECT SUM(amount_cents) FROM transactions
        WHERE posted_at >= ? AND posted_at <= ? AND is_transfer = 0 AND amount_cents < 0;
        """, (start_date, end_date))
        total_expense_cents = abs(cursor.fetchone()[0] or 0)

        # Income (positive amount_cents, non-transfer)
        cursor.execute("""
        SELECT SUM(amount_cents) FROM transactions
        WHERE posted_at >= ? AND posted_at <= ? AND is_transfer = 0 AND amount_cents > 0;
        """, (start_date, end_date))
        total_income_cents = cursor.fetchone()[0] or 0

        # Prior week comparison
        start_dt = date.fromisoformat(start_date)
        prev_start = (start_dt - timedelta(days=7)).strftime("%Y-%m-%d")
        prev_end = (start_dt - timedelta(days=1)).strftime("%Y-%m-%d")

        cursor.execute("""
        SELECT SUM(amount_cents) FROM transactions
        WHERE posted_at >= ? AND posted_at <= ? AND is_transfer = 0 AND amount_cents < 0;
        """, (prev_start, prev_end))
        prev_expense_cents = abs(cursor.fetchone()[0] or 0)

        pct_change = 0.0
        if prev_expense_cents > 0:
            pct_change = round(((total_expense_cents - prev_expense_cents) / prev_expense_cents) * 100, 1)

        # Top Categories
        cursor.execute("""
        SELECT c.id as category_id, c.name as category_name, c.color, SUM(ABS(t.amount_cents)) as category_total_cents
        FROM transactions t
        JOIN categories c ON t.category_id = c.id
        WHERE t.posted_at >= ? AND t.posted_at <= ? AND t.is_transfer = 0 AND t.amount_cents < 0
        GROUP BY c.id
        ORDER BY category_total_cents DESC
        LIMIT 5;
        """, (start_date, end_date))
        top_categories = []
        for row in cursor.fetchall():
            top_categories.append({
                "id": row["category_id"],
                "name": row["category_name"],
                "color": row["color"],
                "total_cents": row["category_total_cents"],
                "formatted_total": format_currency(row["category_total_cents"])
            })

        # Top Payees / Merchants
        cursor.execute("""
        SELECT COALESCE(payee, description) as merchant, SUM(ABS(amount_cents)) as merchant_total_cents, COUNT(*) as tx_count
        FROM transactions
        WHERE posted_at >= ? AND posted_at <= ? AND is_transfer = 0 AND amount_cents < 0
        GROUP BY merchant
        ORDER BY merchant_total_cents DESC
        LIMIT 5;
        """, (start_date, end_date))
        top_merchants = []
        for row in cursor.fetchall():
            top_merchants.append({
                "merchant": row["merchant"],
                "total_cents": row["merchant_total_cents"],
                "formatted_total": format_currency(row["merchant_total_cents"]),
                "count": row["tx_count"]
            })

        net_flow_cents = total_income_cents - total_expense_cents

        return {
            "period_type": "weekly",
            "start_date": start_date,
            "end_date": end_date,
            "income_cents": total_income_cents,
            "formatted_income": format_currency(total_income_cents),
            "expense_cents": total_expense_cents,
            "formatted_expense": format_currency(total_expense_cents),
            "net_flow_cents": net_flow_cents,
            "formatted_net_flow": format_currency(net_flow_cents),
            "prev_week_expense_cents": prev_expense_cents,
            "formatted_prev_expense": format_currency(prev_expense_cents),
            "expense_pct_change": pct_change,
            "top_categories": top_categories,
            "top_merchants": top_merchants
        }
    finally:
        if close_conn:
            conn.close()

def generate_monthly_report(year: int, month: int, conn=None) -> Dict[str, Any]:
    """Generate monthly financial report with savings rate and category drill-down."""
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True

    try:
        cursor = conn.cursor()

        # Check if requested month has data; if not, find latest month with transactions
        m_start, m_end = get_date_bounds_for_month(year, month)
        cursor.execute("SELECT COUNT(*) FROM transactions WHERE posted_at >= ? AND posted_at <= ?;", (m_start, m_end))
        if cursor.fetchone()[0] == 0:
            cursor.execute("SELECT posted_at FROM transactions ORDER BY posted_at DESC LIMIT 1;")
            latest_row = cursor.fetchone()
            if latest_row and latest_row["posted_at"]:
                latest_dt = date.fromisoformat(latest_row["posted_at"])
                year = latest_dt.year
                month = latest_dt.month

        start_date, end_date = get_date_bounds_for_month(year, month)

        # Monthly Expenses
        cursor.execute("""
        SELECT SUM(amount_cents) FROM transactions
        WHERE posted_at >= ? AND posted_at <= ? AND is_transfer = 0 AND amount_cents < 0;
        """, (start_date, end_date))
        expense_cents = abs(cursor.fetchone()[0] or 0)

        # Monthly Income
        cursor.execute("""
        SELECT SUM(amount_cents) FROM transactions
        WHERE posted_at >= ? AND posted_at <= ? AND is_transfer = 0 AND amount_cents > 0;
        """, (start_date, end_date))
        income_cents = cursor.fetchone()[0] or 0

        # Savings Rate Calculation
        savings_rate = 0.0
        net_cents = income_cents - expense_cents
        if income_cents > 0:
            savings_rate = round((net_cents / income_cents) * 100, 1)

        # Expense Category Breakdown
        cursor.execute("""
        SELECT c.id as category_id, c.name as category_name, c.group_name, c.color, SUM(ABS(t.amount_cents)) as total_cents
        FROM transactions t
        JOIN categories c ON t.category_id = c.id
        WHERE t.posted_at >= ? AND t.posted_at <= ? AND t.is_transfer = 0 AND t.amount_cents < 0
        GROUP BY c.id
        ORDER BY total_cents DESC;
        """, (start_date, end_date))
        categories = []
        for row in cursor.fetchall():
            cat_total = row["total_cents"]
            pct = round((cat_total / expense_cents) * 100, 1) if expense_cents > 0 else 0.0
            categories.append({
                "id": row["category_id"],
                "name": row["category_name"],
                "group": row["group_name"],
                "color": row["color"],
                "total_cents": cat_total,
                "formatted_total": format_currency(cat_total),
                "percentage": pct
            })

        # Income Category Breakdown
        cursor.execute("""
        SELECT c.id as category_id, c.name as category_name, c.group_name, c.color, SUM(t.amount_cents) as total_cents
        FROM transactions t
        JOIN categories c ON t.category_id = c.id
        WHERE t.posted_at >= ? AND t.posted_at <= ? AND t.is_transfer = 0 AND t.amount_cents > 0
        GROUP BY c.id
        ORDER BY total_cents DESC;
        """, (start_date, end_date))
        income_categories = []
        for row in cursor.fetchall():
            cat_total = row["total_cents"]
            pct = round((cat_total / income_cents) * 100, 1) if income_cents > 0 else 0.0
            income_categories.append({
                "id": row["category_id"],
                "name": row["category_name"],
                "group": row["group_name"],
                "color": row["color"],
                "total_cents": cat_total,
                "formatted_total": format_currency(cat_total),
                "percentage": pct
            })

        # Month string e.g. "August 2026"
        month_name = date(year, month, 1).strftime("%B %Y")

        return {
            "period_type": "monthly",
            "year": year,
            "month": month,
            "month_name": month_name,
            "start_date": start_date,
            "end_date": end_date,
            "income_cents": income_cents,
            "formatted_income": format_currency(income_cents),
            "expense_cents": expense_cents,
            "formatted_expense": format_currency(expense_cents),
            "net_flow_cents": net_cents,
            "formatted_net_flow": format_currency(net_cents),
            "savings_rate_pct": savings_rate,
            "categories": categories,
            "income_categories": income_categories
        }
    finally:
        if close_conn:
            conn.close()

def generate_yearly_report(year: int, conn=None) -> Dict[str, Any]:
    """Generate annual financial report with monthly breakdown and Net Worth trajectory."""
    start_date, end_date = get_date_bounds_for_year(year)
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True

    try:
        cursor = conn.cursor()

        # Annual Expenses
        cursor.execute("""
        SELECT SUM(amount_cents) FROM transactions
        WHERE posted_at >= ? AND posted_at <= ? AND is_transfer = 0 AND amount_cents < 0;
        """, (start_date, end_date))
        expense_cents = abs(cursor.fetchone()[0] or 0)

        # Annual Income
        cursor.execute("""
        SELECT SUM(amount_cents) FROM transactions
        WHERE posted_at >= ? AND posted_at <= ? AND is_transfer = 0 AND amount_cents > 0;
        """, (start_date, end_date))
        income_cents = cursor.fetchone()[0] or 0

        # Month-by-month trajectory
        monthly_trends = []
        for m in range(1, 13):
            m_start, m_end = get_date_bounds_for_month(year, m)
            cursor.execute("""
            SELECT 
                SUM(CASE WHEN amount_cents > 0 AND is_transfer = 0 THEN amount_cents ELSE 0 END) as inc,
                SUM(CASE WHEN amount_cents < 0 AND is_transfer = 0 THEN ABS(amount_cents) ELSE 0 END) as exp
            FROM transactions
            WHERE posted_at >= ? AND posted_at <= ?;
            """, (m_start, m_end))
            row = cursor.fetchone()
            m_inc = row["inc"] or 0
            m_exp = row["exp"] or 0
            monthly_trends.append({
                "month": m,
                "month_short": date(year, m, 1).strftime("%b"),
                "income_cents": m_inc,
                "formatted_income": format_currency(m_inc),
                "expense_cents": m_exp,
                "formatted_expense": format_currency(m_exp),
                "net_cents": m_inc - m_exp,
                "formatted_net": format_currency(m_inc - m_exp)
            })

        net_cents = income_cents - expense_cents
        savings_rate = round((net_cents / income_cents) * 100, 1) if income_cents > 0 else 0.0

        return {
            "period_type": "yearly",
            "year": year,
            "start_date": start_date,
            "end_date": end_date,
            "income_cents": income_cents,
            "formatted_income": format_currency(income_cents),
            "expense_cents": expense_cents,
            "formatted_expense": format_currency(expense_cents),
            "net_flow_cents": net_cents,
            "formatted_net_flow": format_currency(net_cents),
            "savings_rate_pct": savings_rate,
            "monthly_trends": monthly_trends
        }
    finally:
        if close_conn:
            conn.close()

def calculate_net_worth(conn=None) -> Dict[str, Any]:
    """Calculate current Net Worth across all active accounts."""
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True

    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, balance_cents, org_name, org_domain FROM accounts;")
        accounts = cursor.fetchall()

        net_worth_cents = 0
        assets_cents = 0
        liabilities_cents = 0
        account_summaries = []

        for acc in accounts:
            bal = acc["balance_cents"]
            net_worth_cents += bal
            if bal >= 0:
                assets_cents += bal
            else:
                liabilities_cents += abs(bal)
            
            domain = acc["org_domain"] or ""
            if domain and not (domain.startswith("http://") or domain.startswith("https://")):
                inst_url = f"https://{domain}"
            elif domain:
                inst_url = domain
            elif acc["org_name"] and "chase" in acc["org_name"].lower():
                inst_url = "https://chase.com"
            else:
                inst_url = None

            account_summaries.append({
                "id": acc["id"],
                "name": acc["name"],
                "org_name": acc["org_name"],
                "org_domain": domain,
                "institution_url": inst_url,
                "balance_cents": bal,
                "formatted_balance": format_currency(bal)
            })

        return {
            "net_worth_cents": net_worth_cents,
            "formatted_net_worth": format_currency(net_worth_cents),
            "assets_cents": assets_cents,
            "formatted_assets": format_currency(assets_cents),
            "liabilities_cents": liabilities_cents,
            "formatted_liabilities": format_currency(liabilities_cents),
            "accounts": account_summaries
        }
    finally:
        if close_conn:
            conn.close()

def get_subscriptions_summary(conn=None) -> Dict[str, Any]:
    """Detect recurring subscriptions and bills with cancellation links."""
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True

    # Common subscription cancel quick links
    cancel_link_map = {
        "netflix": "https://www.netflix.com/youraccount",
        "spotify": "https://www.spotify.com/account/overview/",
        "apple": "https://support.apple.com/ht202039",
        "icloud": "https://support.apple.com/ht202039",
        "amazon": "https://www.amazon.com/mc/manage",
        "prime": "https://www.amazon.com/mc/manage",
        "hulu": "https://secure.hulu.com/account",
        "disney": "https://www.disneyplus.com/account",
        "hbo": "https://auth.max.com/subscription",
        "max": "https://auth.max.com/subscription",
        "youtube": "https://www.youtube.com/paid_memberships",
        "fpl": "https://www.fpl.com",
        "florida power": "https://www.fpl.com",
        "gym": "https://www.google.com/search?q=cancel+gym+membership",
    }

    try:
        cursor = conn.cursor()
        # Fetch recurring transactions (category Subscriptions, Utilities, or repeated payees)
        cursor.execute("""
        SELECT 
            COALESCE(t.payee, t.description) as merchant,
            t.description,
            ABS(t.amount_cents) as last_amount_cents,
            t.posted_at as last_charge_date,
            c.name as category_name,
            COUNT(*) as charge_count
        FROM transactions t
        LEFT JOIN categories c ON t.category_id = c.id
        WHERE t.is_transfer = 0 AND t.amount_cents < 0 AND (
            c.name IN ('Subscriptions & Recurring', 'Utilities') 
            OR t.description LIKE '%SUBSCRIPTION%'
            OR t.description LIKE '%AUTOPAY%'
            OR t.description LIKE '%UTILITY%'
        )
        GROUP BY merchant
        ORDER BY last_charge_date DESC;
        """)
        
        subscriptions = []
        total_monthly_cents = 0

        for row in cursor.fetchall():
            merchant = row["merchant"]
            merchant_lower = merchant.lower()
            amt_cents = row["last_amount_cents"]
            total_monthly_cents += amt_cents

            # Find quick cancel URL
            cancel_url = None
            for key, url in cancel_link_map.items():
                if key in merchant_lower or key in row["description"].lower():
                    cancel_url = url
                    break
            
            if not cancel_url:
                search_q = merchant.replace(" ", "+")
                cancel_url = f"https://www.google.com/search?q=cancel+{search_q}+subscription"

            subscriptions.append({
                "merchant": merchant,
                "description": row["description"],
                "amount_cents": amt_cents,
                "formatted_amount": format_currency(amt_cents),
                "last_charge_date": row["last_charge_date"],
                "category_name": row["category_name"] or "Subscription",
                "charge_count": row["charge_count"],
                "cancel_url": cancel_url
            })

        total_annual_cents = total_monthly_cents * 12

        return {
            "subscriptions": subscriptions,
            "total_monthly_cents": total_monthly_cents,
            "formatted_monthly_total": format_currency(total_monthly_cents),
            "total_annual_cents": total_annual_cents,
            "formatted_annual_total": format_currency(total_annual_cents),
            "count": len(subscriptions)
        }
    finally:
        if close_conn:
            conn.close()

def get_investments_summary(conn=None) -> Dict[str, Any]:
    """Generate detailed investments dashboard payload with portfolio allocation and holdings quotes."""
    from app.investments import get_portfolio_market_quotes

    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True

    try:
        cursor = conn.cursor()

        # Investment Accounts
        cursor.execute("""
        SELECT * FROM accounts 
        WHERE name LIKE '%Brokerage%' OR name LIKE '%Retirement%' OR name LIKE '%401%' OR name LIKE '%Schwab%' OR name LIKE '%Transamerica%' OR name LIKE '%Investment%'
        ORDER BY balance_cents DESC;
        """)
        inv_accounts = []
        total_balance_cents = 0
        for row in cursor.fetchall():
            acc_dict = dict(row)
            acc_dict["formatted_balance"] = format_currency(acc_dict["balance_cents"])
            total_balance_cents += acc_dict["balance_cents"]
            inv_accounts.append(acc_dict)

        # Holdings
        cursor.execute("""
        SELECT h.*, a.name as account_name
        FROM holdings h
        JOIN accounts a ON h.account_id = a.id
        ORDER BY h.cost_basis_cents DESC;
        """)
        raw_holdings = [dict(row) for row in cursor.fetchall()]
        
        # Enrich holdings with stock quote data
        quotes_summary = get_portfolio_market_quotes(raw_holdings)
        enriched_holdings = quotes_summary["holdings"]
        
        # Calculate Asset Allocation (Retirement vs Stock Brokerage)
        asset_breakdown = {}
        total_market_value_cents = 0
        for item in enriched_holdings:
            atype = item["asset_type"]
            val = item["market_value_cents"]
            total_market_value_cents += val
            asset_breakdown[atype] = asset_breakdown.get(atype, 0) + val

        asset_allocation = []
        colors = ["#38BDF8", "#10B981", "#6366F1", "#F59E0B", "#EC4899"]
        c_idx = 0
        for atype, val_cents in asset_breakdown.items():
            pct = round((val_cents / total_market_value_cents) * 100, 1) if total_market_value_cents > 0 else 0.0
            asset_allocation.append({
                "type": atype,
                "value_cents": val_cents,
                "formatted_value": format_currency(val_cents),
                "percentage": pct,
                "color": colors[c_idx % len(colors)]
            })
            c_idx += 1

        # Investment Transactions
        cursor.execute("""
        SELECT t.*, a.name as account_name, c.name as category_name
        FROM transactions t
        JOIN accounts a ON t.account_id = a.id
        LEFT JOIN categories c ON t.category_id = c.id
        WHERE a.name LIKE '%Brokerage%' OR a.name LIKE '%Retirement%' OR a.name LIKE '%401%' OR a.name LIKE '%Schwab%' OR a.name LIKE '%Transamerica%' OR c.name = 'Investments & Interest'
        ORDER BY t.posted_at DESC, t.posted_timestamp DESC;
        """)
        inv_transactions = []
        for row in cursor.fetchall():
            tx_dict = dict(row)
            tx_dict["formatted_amount"] = format_currency(tx_dict["amount_cents"])
            inv_transactions.append(tx_dict)

        portfolio_value_cents = total_market_value_cents if total_market_value_cents > 0 else total_balance_cents

        return {
            "total_portfolio_value_cents": portfolio_value_cents,
            "formatted_portfolio_value": format_currency(portfolio_value_cents),
            "accounts": inv_accounts,
            "holdings": enriched_holdings,
            "top_gainer": quotes_summary["top_gainer"],
            "top_loser": quotes_summary["top_loser"],
            "asset_allocation": asset_allocation,
            "transactions": inv_transactions
        }
    finally:
        if close_conn:
            conn.close()
