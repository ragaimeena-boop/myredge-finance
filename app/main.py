import json
from pathlib import Path
from datetime import datetime
from fastapi import FastAPI, Request, BackgroundTasks, Query, Form
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from apscheduler.schedulers.background import BackgroundScheduler
import pytz
from contextlib import asynccontextmanager

from app.config import settings
from app.database import init_db, get_connection, purge_demo_data
from app.utils import get_eastern_tz, current_eastern_time, format_currency
from app.models import SimpleFINResponse
from app.simplefin import SimpleFINClient, ingest_simplefin_data
from app.reports import (
    generate_weekly_report,
    generate_monthly_report,
    generate_yearly_report,
    calculate_net_worth,
    get_subscriptions_summary,
    get_credit_score_summary,
    get_date_bounds_for_week
)
from app.auth import (
    get_user_count, create_user, get_user_by_username, get_user_by_id,
    verify_password, create_session, validate_session, revoke_session,
    get_totp_qr_data_url, verify_totp_code, get_user_settings,
    update_session_timeout, update_user_credentials, update_user_totp_secret
)

BASE_DIR = Path(__file__).resolve().parent
scheduler = BackgroundScheduler(timezone=pytz.timezone(settings.TIMEZONE))

def run_daily_sync():
    """Daily sync task executed by APScheduler in US Eastern Time."""
    conn = get_connection()
    try:
        if settings.SIMPLEFIN_ACCESS_URL:
            purge_demo_data(conn=conn)
            client = SimpleFINClient()
            data = client.fetch_data()
        else:
            # Fallback to fixture data if no Access URL provided yet
            fixture_path = BASE_DIR.parent / "tests" / "fixtures" / "simplefin_sample.json"
            if fixture_path.exists():
                with open(fixture_path, "r") as f:
                    raw_json = json.load(f)
                
                # Dynamically set posted timestamps relative to current month
                now_ts = int(current_eastern_time().timestamp())
                day_sec = 86400
                offset_days = [1, 2, 3, 3, 4]
                idx = 0
                for acc in raw_json.get("accounts", []):
                    for tx in acc.get("transactions", []):
                        d_offset = offset_days[idx % len(offset_days)]
                        tx["posted"] = now_ts - (d_offset * day_sec)
                        idx += 1

                data = SimpleFINResponse.model_validate(raw_json)
            else:
                return

        return ingest_simplefin_data(data, conn=conn)
    finally:
        conn.close()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager: initializes database and starts daily scheduler."""
    try:
        init_db()
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM accounts;")
            if cursor.fetchone()[0] == 0:
                run_daily_sync()
        finally:
            conn.close()

        scheduler.add_job(run_daily_sync, 'cron', hour=6, minute=0, id='daily_simplefin_pull', replace_existing=True)
        scheduler.start()
        print("MYREDGE Finance Engine initialized successfully.")
    except Exception as e:
        print(f"[STARTUP WARNING] Initialization notice: {e}")

    yield

    try:
        scheduler.shutdown()
    except Exception:
        pass

app = FastAPI(title="Personal Finance Dashboard", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")

@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    exempt_prefixes = [
        "/static", "/favicon.ico", "/manifest.json", "/sw.js",
        "/login", "/api/login", "/verify-otp", "/api/verify-otp",
        "/setup-admin", "/api/setup-admin"
    ]
    if any(path.startswith(prefix) for prefix in exempt_prefixes):
        return await call_next(request)

    conn = get_connection()
    try:
        user_cnt = get_user_count(conn=conn)
        if user_cnt == 0:
            return RedirectResponse(url="/setup-admin", status_code=303)

        session_token = request.cookies.get("myredge_session")
        if not session_token:
            return RedirectResponse(url="/login", status_code=303)

        user, is_timed_out = validate_session(session_token, conn=conn)
        if is_timed_out:
            return RedirectResponse(url="/login?timeout=1", status_code=303)
        if not user:
            return RedirectResponse(url="/login", status_code=303)

        request.state.user = user
    finally:
        conn.close()

    response = await call_next(request)
    return response

@app.get("/manifest.json", include_in_schema=False)
def get_manifest():
    return FileResponse(BASE_DIR / "static" / "manifest.json", media_type="application/manifest+json")

@app.get("/sw.js", include_in_schema=False)
def get_service_worker():
    return FileResponse(BASE_DIR / "static" / "sw.js", media_type="application/javascript")

@app.get("/", response_class=HTMLResponse)
def read_dashboard(request: Request):
    """Dashboard Homepage view."""
    now = current_eastern_time()
    conn = get_connection()
    try:
        net_worth = calculate_net_worth(conn=conn)
        monthly_report = generate_monthly_report(now.year, now.month, conn=conn)
        
        # Recent transactions
        cursor = conn.cursor()
        cursor.execute("""
        SELECT t.*, a.name as account_name, c.name as category_name
        FROM transactions t
        LEFT JOIN accounts a ON t.account_id = a.id
        LEFT JOIN categories c ON t.category_id = c.id
        ORDER BY t.posted_at DESC, t.posted_timestamp DESC
        LIMIT 10;
        """)
        recent_txs = []
        for row in cursor.fetchall():
            tx_dict = dict(row)
            tx_dict["formatted_amount"] = format_currency(tx_dict["amount_cents"])
            recent_txs.append(tx_dict)

        cursor.execute("SELECT COUNT(*) FROM accounts WHERE id IN ('acc_checking_01', 'acc_credit_01', 'acc_schwab_01', 'acc_transamerica_01');")
        has_demo_data = (cursor.fetchone()[0] > 0)

        sync_status = request.query_params.get("sync")
        sync_error = request.query_params.get("sync_error")
        demo_purged = request.query_params.get("demo_purged")
        acc_cnt = request.query_params.get("acc_cnt")
        tx_cnt = request.query_params.get("tx_cnt")

        return templates.TemplateResponse(request=request, name="index.html", context={
            "active_page": "dashboard",
            "net_worth": net_worth,
            "monthly_report": monthly_report,
            "recent_transactions": recent_txs,
            "sync_status": sync_status,
            "sync_error": sync_error,
            "has_demo_data": has_demo_data,
            "demo_purged": demo_purged,
            "acc_cnt": acc_cnt,
            "tx_cnt": tx_cnt
        })
    finally:
        conn.close()

@app.get("/reports/weekly", response_class=HTMLResponse)
def read_weekly_report(request: Request):
    """Weekly Digest Report view."""
    now = current_eastern_time().date()
    start_str, end_str = get_date_bounds_for_week(now)
    conn = get_connection()
    try:
        report = generate_weekly_report(start_str, end_str, conn=conn)
        return templates.TemplateResponse(request=request, name="weekly.html", context={
            "active_page": "weekly",
            "report": report
        })
    finally:
        conn.close()

@app.get("/reports/monthly", response_class=HTMLResponse)
def read_monthly_report(request: Request):
    """Monthly Deep-Dive Report view."""
    now = current_eastern_time()
    conn = get_connection()
    try:
        report = generate_monthly_report(now.year, now.month, conn=conn)
        return templates.TemplateResponse(request=request, name="monthly.html", context={
            "active_page": "monthly",
            "report": report
        })
    finally:
        conn.close()

@app.get("/reports/yearly", response_class=HTMLResponse)
def read_yearly_report(request: Request):
    """Yearly Retrospective Report view."""
    now = current_eastern_time()
    conn = get_connection()
    try:
        report = generate_yearly_report(now.year, conn=conn)
        return templates.TemplateResponse(request=request, name="yearly.html", context={
            "active_page": "yearly",
            "report": report
        })
    finally:
        conn.close()

from decimal import Decimal

@app.get("/transactions", response_class=HTMLResponse)
def read_transactions(
    request: Request,
    category_id: str = Query(default=None),
    category_name: str = Query(default=None),
    q: str = Query(default=None)
):
    """Full Transactions Explorer view with category filtering, keyword search, and amount search."""
    conn = get_connection()
    try:
        cursor = conn.cursor()

        # Parse category_id safely if non-empty integer string
        cat_id_int = int(category_id) if (category_id and category_id.strip().isdigit()) else None

        # Fetch category list for dropdown filter & inline reassignment
        cursor.execute("SELECT id, name, group_name FROM categories ORDER BY group_name, name;")
        all_categories = [dict(row) for row in cursor.fetchall()]

        query = """
        SELECT t.*, a.name as account_name, c.name as category_name
        FROM transactions t
        LEFT JOIN accounts a ON t.account_id = a.id
        LEFT JOIN categories c ON t.category_id = c.id
        """
        where_clauses = []
        params = []

        if cat_id_int is not None:
            where_clauses.append("t.category_id = ?")
            params.append(cat_id_int)
        elif category_name:
            where_clauses.append("c.name = ?")
            params.append(category_name)

        if q and q.strip():
            raw_q = q.strip()
            kw = f"%{raw_q}%"
            
            # Check if q is a numeric monetary value (e.g., "$45.20", "45.20", "-120.50", "3200")
            clean_num = raw_q.replace("$", "").replace(",", "")
            amount_search_cents = None
            try:
                d = Decimal(clean_num)
                amount_search_cents = int((d * Decimal(100)).quantize(Decimal("1")))
            except Exception:
                amount_search_cents = None

            if amount_search_cents is not None:
                where_clauses.append("(t.amount_cents = ? OR ABS(t.amount_cents) = ? OR t.description LIKE ? OR t.payee LIKE ? OR t.memo LIKE ? OR c.name LIKE ? OR a.name LIKE ?)")
                params.extend([amount_search_cents, abs(amount_search_cents), kw, kw, kw, kw, kw])
            else:
                where_clauses.append("(t.description LIKE ? OR t.payee LIKE ? OR t.memo LIKE ? OR c.name LIKE ? OR a.name LIKE ?)")
                params.extend([kw, kw, kw, kw, kw])

        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)

        query += " ORDER BY t.posted_at DESC, t.posted_timestamp DESC;"

        cursor.execute(query, params)
        transactions = []
        selected_category = None

        for row in cursor.fetchall():
            tx_dict = dict(row)
            tx_dict["formatted_amount"] = format_currency(tx_dict["amount_cents"])
            transactions.append(tx_dict)
            if not selected_category and tx_dict["category_name"]:
                selected_category = tx_dict["category_name"]

        active_filter_label = category_name or selected_category if (cat_id_int or category_name) else None
        categorized_count = request.query_params.get("categorized_count")

        return templates.TemplateResponse(request=request, name="transactions.html", context={
            "active_page": "transactions",
            "transactions": transactions,
            "categories": all_categories,
            "selected_category_id": cat_id_int,
            "active_filter_label": active_filter_label,
            "search_query": q.strip() if q else "",
            "categorized_count": categorized_count
        })
    finally:
        conn.close()

@app.post("/api/transactions/{tx_id}/category")
def update_transaction_category(tx_id: str, request: Request, category_id: str = Form(default="")):
    """Reassign category or transfer flag for a transaction, learning rules automatically."""
    conn = get_connection()
    now_str = current_eastern_time().isoformat()
    try:
        cursor = conn.cursor()
        
        cursor.execute("SELECT description, payee FROM transactions WHERE id = ?;", (tx_id,))
        tx_row = cursor.fetchone()

        if category_id == "transfer":
            cursor.execute("""
            UPDATE transactions 
            SET category_id = NULL, is_transfer = 1, updated_at = ?
            WHERE id = ?;
            """, (now_str, tx_id))
        elif category_id.isdigit():
            cat_id = int(category_id)
            cursor.execute("""
            UPDATE transactions 
            SET category_id = ?, is_transfer = 0, updated_at = ?
            WHERE id = ?;
            """, (cat_id, now_str, tx_id))

            # Learn rule from user action & bulk categorize matching uncategorized transactions
            if tx_row:
                from app.simplefin import clean_merchant_description
                clean_p = clean_merchant_description(tx_row["description"], tx_row["payee"])
                raw_pattern = clean_p if (clean_p and len(clean_p) >= 3) else (tx_row["payee"] or tx_row["description"] or "").strip().upper()
                if len(raw_pattern) >= 3:
                    cursor.execute("""
                    INSERT OR IGNORE INTO rules (pattern, category_id, clean_payee, is_transfer, priority)
                    VALUES (?, ?, ?, 0, 20);
                    """, (raw_pattern, cat_id, tx_row["payee"] or raw_pattern.title()))
                    
                    cursor.execute("""
                    UPDATE transactions
                    SET category_id = ?, updated_at = ?
                    WHERE (category_id IS NULL OR category_id = (SELECT id FROM categories WHERE name = 'Uncategorized'))
                      AND (UPPER(description) LIKE ? OR UPPER(payee) LIKE ?);
                    """, (cat_id, now_str, f"%{raw_pattern}%", f"%{raw_pattern}%"))
        else:
            cursor.execute("""
            UPDATE transactions 
            SET category_id = NULL, is_transfer = 0, updated_at = ?
            WHERE id = ?;
            """, (now_str, tx_id))

        conn.commit()
        referer = request.headers.get("referer", "/transactions")
        return RedirectResponse(url=referer, status_code=303)
    finally:
        conn.close()

@app.post("/api/transactions/recategorize")
def trigger_recategorize_uncategorized():
    """Run rule engine across all transactions (force_all=True)."""
    from app.simplefin import reapply_rules_to_uncategorized
    conn = get_connection()
    try:
        count = reapply_rules_to_uncategorized(conn=conn, force_all=True)
    finally:
        conn.close()
    return RedirectResponse(url=f"/transactions?categorized_count={count}", status_code=303)

@app.post("/api/transactions/ai-categorize")
def trigger_ai_categorize():
    """Run Gemini AI Auto-Categorizer across transactions."""
    from app.simplefin import ai_autocategorize_transactions
    count = 0
    try:
        conn = get_connection()
        try:
            count = ai_autocategorize_transactions(conn=conn, force_all=True)
        finally:
            conn.close()
    except Exception as e:
        print(f"[AI CATEGORIZE ROUTE WARNING] {e}")
        count = 0
    return RedirectResponse(url=f"/transactions?categorized_count={count}", status_code=303)

@app.get("/subscriptions", response_class=HTMLResponse)
def read_subscriptions(request: Request):
    """Subscriptions & Recurring Bills radar view."""
    conn = get_connection()
    try:
        summary = get_subscriptions_summary(conn=conn)
        return templates.TemplateResponse(request=request, name="subscriptions.html", context={
            "active_page": "subscriptions",
            "summary": summary,
            "report": summary
        })
    finally:
        conn.close()

@app.get("/investments", response_class=HTMLResponse)
def read_investments(request: Request):
    """Investments & Portfolio view."""
    from app.reports import get_investments_summary
    conn = get_connection()
    try:
        report = get_investments_summary(conn=conn)
        return templates.TemplateResponse(request=request, name="investments.html", context={
            "active_page": "investments",
            "report": report
        })
    finally:
        conn.close()

@app.post("/api/sync")
def trigger_manual_sync():
    """Manual sync trigger endpoint."""
    try:
        stats = run_daily_sync()
        acc_cnt = stats.get("accounts_synced", 0) if stats else 0
        tx_cnt = stats.get("transactions_synced", 0) if stats else 0
        return RedirectResponse(url=f"/?sync=success&acc_cnt={acc_cnt}&tx_cnt={tx_cnt}", status_code=303)
    except Exception as e:
        print(f"[SYNC ERROR] Manual sync failed: {e}")
        return RedirectResponse(url=f"/?sync_error={e}", status_code=303)

@app.post("/api/purge-demo")
def trigger_purge_demo():
    """Manually purge initial sample/demo accounts and transactions from the database."""
    conn = get_connection()
    try:
        purge_demo_data(conn=conn)
    finally:
        conn.close()
    return RedirectResponse(url="/?demo_purged=1", status_code=303)

@app.get("/accounts", response_class=HTMLResponse)
def read_accounts(request: Request):
    """Accounts management view listing connected accounts with editable account_type."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM accounts ORDER BY account_type, name;")
        accounts = []
        account_types = [
            ("checking", "Checking"),
            ("savings", "Savings"),
            ("credit_card", "Credit Card"),
            ("investment", "Investment"),
            ("retirement", "Retirement 401(k)/IRA"),
            ("loan", "Loan / Mortgage"),
            ("other", "Other")
        ]
        
        for row in cursor.fetchall():
            acc_dict = dict(row)
            acc_dict["formatted_balance"] = format_currency(acc_dict["balance_cents"])
            acc_dict["formatted_available"] = format_currency(acc_dict["available_balance_cents"]) if acc_dict["available_balance_cents"] is not None else "N/A"
            acc_dict["type_label"] = (acc_dict.get("account_type") or "checking").replace("_", " ").title()
            accounts.append(acc_dict)

        type_updated = request.query_params.get("updated")

        return templates.TemplateResponse(request=request, name="accounts.html", context={
            "active_page": "accounts",
            "accounts": accounts,
            "account_types": account_types,
            "type_updated": type_updated
        })
    finally:
        conn.close()

@app.post("/api/accounts/{account_id}/type")
def update_account_type(account_id: str, request: Request, account_type: str = Form(default="checking")):
    """Update account_type classification for an account."""
    conn = get_connection()
    now_str = current_eastern_time().isoformat()
    try:
        cursor = conn.cursor()
        cursor.execute("""
        UPDATE accounts 
        SET account_type = ?, updated_at = ?
        WHERE id = ?;
        """, (account_type, now_str, account_id))
        conn.commit()

        return RedirectResponse(url="/accounts?updated=1", status_code=303)
    finally:
        conn.close()

@app.get("/credit-score", response_class=HTMLResponse)
def read_credit_score(request: Request):
    """Credit Score & Credit History Dashboard view."""
    conn = get_connection()
    try:
        summary = get_credit_score_summary(conn=conn)
        logged = request.query_params.get("logged")
        return templates.TemplateResponse(request=request, name="credit_score.html", context={
            "active_page": "credit_score",
            "summary": summary,
            "logged": logged
        })
    finally:
        conn.close()

@app.post("/api/credit-score")
def log_credit_score(
    score: int = Form(...),
    bureau: str = Form(default="Experian FICO 8"),
    recorded_date: str = Form(default=""),
    notes: str = Form(default="")
):
    """Log a new credit score check into the history database."""
    conn = get_connection()
    now_str = current_eastern_time().isoformat()
    rec_date = recorded_date.strip() if recorded_date and recorded_date.strip() else current_eastern_time().strftime("%Y-%m-%d")
    try:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO credit_scores (score, bureau, recorded_date, notes, created_at)
        VALUES (?, ?, ?, ?, ?);
        """, (score, bureau, rec_date, notes, now_str))
        conn.commit()

        return RedirectResponse(url="/credit-score?logged=1", status_code=303)
    finally:
        conn.close()

@app.get("/stock-market", response_class=HTMLResponse)
def read_stock_market(request: Request):
    """Stock Market Live Data & Daily AI Deep Research Dashboard view."""
    from app.stock_market import generate_daily_ai_research
    conn = get_connection()
    try:
        refreshed = request.query_params.get("refreshed")
        research = generate_daily_ai_research(conn=conn)
        return templates.TemplateResponse(request=request, name="stock_market.html", context={
            "active_page": "stock_market",
            "research": research,
            "refreshed": refreshed
        })
    finally:
        conn.close()

@app.post("/api/stock-market/refresh")
def trigger_stock_market_refresh():
    """Trigger manual AI deep research refresh."""
    from app.stock_market import generate_daily_ai_research
    conn = get_connection()
    try:
        generate_daily_ai_research(conn=conn, force_refresh=True)
        return RedirectResponse(url="/stock-market?refreshed=1", status_code=303)
    finally:
        conn.close()

@app.get("/api/stock-market/ticker/{ticker}")
def get_ticker_analysis(ticker: str):
    """Get instant AI deep dive report for a given stock ticker."""
    from app.stock_market import get_ticker_ai_deep_dive
    conn = get_connection()
    try:
        return get_ticker_ai_deep_dive(ticker, conn=conn)
    finally:
        conn.close()

# --- Authentication & Settings Endpoints ---

@app.get("/setup-admin", response_class=HTMLResponse)
def get_setup_admin(request: Request):
    """Initial admin master account setup view."""
    conn = get_connection()
    try:
        if get_user_count(conn=conn) > 0:
            return RedirectResponse(url="/login", status_code=303)
        return templates.TemplateResponse(request=request, name="setup_admin.html", context={"error": None})
    finally:
        conn.close()

@app.post("/api/setup-admin")
def post_setup_admin(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...)
):
    """Create initial admin master account."""
    conn = get_connection()
    try:
        if get_user_count(conn=conn) > 0:
            return RedirectResponse(url="/login", status_code=303)

        if password != confirm_password:
            return templates.TemplateResponse(request=request, name="setup_admin.html", context={"error": "Passwords do not match."})

        if len(password) < 6:
            return templates.TemplateResponse(request=request, name="setup_admin.html", context={"error": "Password must be at least 6 characters."})

        user = create_user(username=username, password=password, conn=conn)
        token = create_session(user["id"], conn=conn)
        
        response = RedirectResponse(url="/", status_code=303)
        response.set_cookie(key="myredge_session", value=token, httponly=True, samesite="lax")
        return response
    finally:
        conn.close()

@app.get("/login", response_class=HTMLResponse)
def get_login(request: Request):
    """Login landing page view."""
    conn = get_connection()
    try:
        timeout = request.query_params.get("timeout")
        logged_out = request.query_params.get("logged_out")
        error = request.query_params.get("error")

        return templates.TemplateResponse(request=request, name="login.html", context={
            "timeout": timeout,
            "logged_out": logged_out,
            "error": error
        })
    finally:
        conn.close()

@app.post("/api/login")
def post_login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...)
):
    """Verify credentials and grant session or prompt 2FA."""
    conn = get_connection()
    try:
        user = get_user_by_username(username, conn=conn)
        if not user or not verify_password(password, user["password_hash"]):
            return templates.TemplateResponse(request=request, name="login.html", context={
                "error": "Invalid username or password."
            })

        # Check if 2FA TOTP is enabled for this user
        if user.get("is_totp_enabled"):
            temp_token = create_session(user["id"], conn=conn)
            response = RedirectResponse(url="/verify-otp", status_code=303)
            response.set_cookie(key="myredge_2fa_pending", value=temp_token, httponly=True, samesite="lax")
            return response

        token = create_session(user["id"], conn=conn)
        response = RedirectResponse(url="/", status_code=303)
        response.set_cookie(key="myredge_session", value=token, httponly=True, samesite="lax")
        return response
    finally:
        conn.close()

@app.get("/verify-otp", response_class=HTMLResponse)
def get_verify_otp(request: Request):
    """2FA OTP challenge view."""
    pending_token = request.cookies.get("myredge_2fa_pending")
    if not pending_token:
        return RedirectResponse(url="/login", status_code=303)

    return templates.TemplateResponse(request=request, name="verify_otp.html", context={"error": None})

@app.post("/api/verify-otp")
def post_verify_otp(
    request: Request,
    otp_code: str = Form(...)
):
    """Verify 6-digit TOTP code and grant session."""
    pending_token = request.cookies.get("myredge_2fa_pending")
    if not pending_token:
        return RedirectResponse(url="/login", status_code=303)

    conn = get_connection()
    try:
        user, _ = validate_session(pending_token, conn=conn)
        if not user:
            return RedirectResponse(url="/login", status_code=303)

        if not verify_totp_code(user["totp_secret"], otp_code):
            return templates.TemplateResponse(request=request, name="verify_otp.html", context={
                "error": "Invalid 2FA verification code. Please check your authenticator app."
            })

        revoke_session(pending_token, conn=conn)
        full_token = create_session(user["id"], conn=conn)

        response = RedirectResponse(url="/", status_code=303)
        response.delete_cookie(key="myredge_2fa_pending")
        response.set_cookie(key="myredge_session", value=full_token, httponly=True, samesite="lax")
        return response
    finally:
        conn.close()

@app.post("/api/logout")
def post_logout(request: Request):
    """Revoke active session token and clear cookies."""
    session_token = request.cookies.get("myredge_session")
    if session_token:
        conn = get_connection()
        try:
            revoke_session(session_token, conn=conn)
        finally:
            conn.close()

    response = RedirectResponse(url="/login?logged_out=1", status_code=303)
    response.delete_cookie(key="myredge_session")
    response.delete_cookie(key="myredge_2fa_pending")
    return response

@app.get("/settings", response_class=HTMLResponse)
def read_settings(request: Request):
    """Settings & System Security Dashboard view."""
    conn = get_connection()
    try:
        user = getattr(request.state, "user", None)
        if not user:
            return RedirectResponse(url="/login", status_code=303)

        user_data = get_user_by_id(user["id"], conn=conn)
        settings_data = get_user_settings(conn=conn)
        qr_url = get_totp_qr_data_url(user_data["totp_secret"], user_data["username"])

        success_msg = request.query_params.get("success")
        error_msg = request.query_params.get("error")

        return templates.TemplateResponse(request=request, name="settings.html", context={
            "active_page": "settings",
            "user": user_data,
            "settings": settings_data,
            "qr_data_url": qr_url,
            "success_msg": success_msg,
            "error_msg": error_msg
        })
    finally:
        conn.close()

@app.post("/api/settings/credentials")
def update_credentials(
    request: Request,
    username: str = Form(...),
    current_password: str = Form(...),
    new_password: str = Form(default=""),
    confirm_password: str = Form(default="")
):
    """Update master username or password."""
    user = getattr(request.state, "user", None)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    conn = get_connection()
    try:
        user_db = get_user_by_id(user["id"], conn=conn)
        if not verify_password(current_password, user_db["password_hash"]):
            return RedirectResponse(url="/settings?error=Incorrect+current+password.", status_code=303)

        if new_password and new_password.strip():
            if new_password != confirm_password:
                return RedirectResponse(url="/settings?error=New+passwords+do+not+match.", status_code=303)
            if len(new_password) < 6:
                return RedirectResponse(url="/settings?error=Password+must+be+at+least+6+characters.", status_code=303)

        update_user_credentials(user["id"], new_username=username, new_password=new_password, conn=conn)
        return RedirectResponse(url="/settings?success=Credentials+updated+successfully.", status_code=303)
    finally:
        conn.close()

@app.post("/api/settings/2fa/enable")
def enable_2fa(
    request: Request,
    otp_code: str = Form(...)
):
    """Enable 2FA TOTP after verifying 6-digit code."""
    user = getattr(request.state, "user", None)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    conn = get_connection()
    try:
        user_db = get_user_by_id(user["id"], conn=conn)
        if not verify_totp_code(user_db["totp_secret"], otp_code):
            return RedirectResponse(url="/settings?error=Invalid+6-digit+code.+Please+check+your+authenticator+app.", status_code=303)

        update_user_totp_secret(user["id"], secret=user_db["totp_secret"], is_enabled=True, conn=conn)
        return RedirectResponse(url="/settings?success=Two-Factor+Authentication+enabled+successfully!", status_code=303)
    finally:
        conn.close()

@app.post("/api/settings/2fa/disable")
def disable_2fa(request: Request):
    """Disable 2FA TOTP."""
    user = getattr(request.state, "user", None)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    conn = get_connection()
    try:
        user_db = get_user_by_id(user["id"], conn=conn)
        update_user_totp_secret(user["id"], secret=user_db["totp_secret"], is_enabled=False, conn=conn)
        return RedirectResponse(url="/settings?success=Two-Factor+Authentication+disabled.", status_code=303)
    finally:
        conn.close()

@app.post("/api/settings/timeout")
def update_timeout(
    request: Request,
    timeout_minutes: int = Form(...)
):
    """Update session inactivity timeout."""
    conn = get_connection()
    try:
        update_session_timeout(timeout_minutes, conn=conn)
        return RedirectResponse(url=f"/settings?success=Session+inactivity+timeout+updated+to+{timeout_minutes}+minutes.", status_code=303)
    finally:
        conn.close()





