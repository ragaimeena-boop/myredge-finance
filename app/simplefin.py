import time
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Tuple
import httpx
from app.config import settings
from app.utils import to_cents, current_eastern_time, timestamp_to_eastern_date
from app.models import SimpleFINResponse
from app.database import get_connection

def calculate_sync_range(days: int = settings.INITIAL_SYNC_DAYS) -> Tuple[int, int]:
    """Calculate start and end Unix timestamps for SimpleFIN sync (max 90 days)."""
    days = min(days, settings.INITIAL_SYNC_DAYS)
    end_dt = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(days=days)
    return int(start_dt.timestamp()), int(end_dt.timestamp())

class SimpleFINClient:
    def __init__(self, access_url: str = ""):
        self.access_url = access_url or settings.SIMPLEFIN_ACCESS_URL

    def fetch_data(self, start_ts: int = None, end_ts: int = None) -> SimpleFINResponse:
        """Fetch account and transaction JSON payload from SimpleFIN API."""
        if not self.access_url:
            raise ValueError("SIMPLEFIN_ACCESS_URL is not configured.")

        if start_ts is None or end_ts is None:
            start_ts, end_ts = calculate_sync_range()

        params = {
            "start-date": start_ts,
            "end-date": end_ts
        }

        # SimpleFIN Access URL contains Basic Auth embedded in the URL
        response = httpx.get(self.access_url, params=params, timeout=30.0)
        response.raise_for_status()
        
        payload = response.json()
        return SimpleFINResponse.model_validate(payload)

import re
from difflib import SequenceMatcher

def clean_merchant_description(desc: str, payee: str = "") -> str:
    """
    Normalize raw bank text into a clean merchant string.
    Strips payment processor prefixes (FAWRY*, PAYMOB*, TST*, SQ *, PAYPAL *), store numbers (#1234),
    locations (MIAMI FL), trailing symbols, phone numbers, zip codes, and transaction codes.
    """
    raw = payee if (payee and len(payee.strip()) >= 3) else (desc or "")
    s = raw.upper()

    prefixes = [
        r"^FAWRY\s*\*\s*", r"^FAWRYPF\s*\*\s*", r"^PAYMOB\s*-\s*\*\s*", r"^PAYMOB\s*\*\s*",
        r"^TST\*\s*", r"^SQ\s*\*\s*", r"^PAYPAL\s*\*\s*", r"^POS\s+PURCH\s*",
        r"^DBT\s+CRD\s*", r"^APLY\s+PAY\s*", r"^CHECKCARD\s*", r"^COLLEGEBOARD\*\s*"
    ]
    for p in prefixes:
        s = re.sub(p, "", s)

    s = re.sub(r"#\d+", "", s)
    s = re.sub(r"\bSTORE\s*\d+\b", "", s)
    s = re.sub(r"\b\d{5}(-\d{4})?\b", "", s)
    s = re.sub(r"\b[A-Z]+\s+(FL|CA|NY|TX|GA|NC|SC|TN|OH|PA|IL|MA|NJ|VA|WA)\b$", "", s)
    s = re.sub(r"\b(FL|CA|NY|TX|GA|NC|SC|TN|OH|PA|IL|MA|NJ|VA|WA)\b", "", s)
    s = re.sub(r"[>|\*]+$", "", s)
    s = re.sub(r"\s+", " ", s).strip()

    return s

def infer_account_type(name: str, org_name: str = "") -> str:
    """Infer account type (checking, savings, credit_card, investment, retirement) from name & org."""
    combined = f"{name} {org_name}".upper()
    if any(k in combined for k in ["BETTERMENT", "BUILDWEALTH", "SCHWAB", "FIDELITY", "VANGUARD", "E*TRADE", "MERRILL", "BROKERAGE"]):
        return "investment"
    elif any(k in combined for k in ["401K", "401(K)", "IRA", "RETIREMENT", "PENSION", "TRANSAMERICA"]):
        return "retirement"
    elif any(k in combined for k in ["CREDIT", "CARD", "VISA", "MASTERCARD", "AMEX", "DISCOVER"]):
        return "credit_card"
    elif "SAVINGS" in combined or "MONEY MARKET" in combined:
        return "savings"
    return "checking"

HEURISTIC_KEYWORDS = [
    # Taxes & Revenue
    (["FLA DEPT REVENUE", "DEPT REVENUE", "DEPT OF REVENUE", "DEPT REV", "FL DEPT", "FLA DEPT", "REVENUE", "IRS", "US TREAS", "TREASURY", "INTERNAL REVENUE", "TAX PAY", "PROPERTY TAX", "TAX COLLECTOR", "STATE TAX", "TURBOTAX", "H&R BLOCK", "TAXACT"], "IRS/Taxes", 0),
    
    # Education & Learning
    (["COLLEGEBOARD", "COLLEGE BOARD", "SAT ONLN", "ACT TEST", "UNIVERSITY", "COLLEGE", "TUITION", "COURSERA", "UDEMY", "EDX", "SCHOOL", "ACADEMY", "LEARNING", "EDUCATION"], "Education & Learning", 0),
    
    # Office
    (["STAPLES", "OFFICE DEPOT", "OFFICEMAX", "FEDEX OFFICE", "UPS STORE", "PAPER", "INK", "DESK", "WORKPLACE", "OFFICE"], "Office", 0),
    
    # Entertainment
    (["NEVERLAND", "PAYMOB-*NEVERLAND", "PARK", "RESORT", "CINEMA", "THEATER", "THEATRE", "MOVIE", "STREAM", "PLAYSTATION", "XBOX", "NINTENDO", "GAME", "STEAM", "TICKETMASTER", "EVENTBRITE", "STUBHUB", "GOLF", "BOWLING", "MUSEUM", "DISNEY", "UNIVERSAL", "ENTERTAINMENT"], "Entertainment", 0),

    # Auto & Transportation
    (["TYREPRO", "TYRE", "TIRE", "AUTO REPAIR", "AUTOMOTIVE", "MECHANIC", "GAS", "OIL", "FUEL", "CHEVRON", "SHELL", "EXXON", "MOBIL", "BP", "WAWA", "SPEEDWAY", "VALERO"], "Auto Payment & Insurance", 0),
    
    # Rent & Housing
    (["RES MANAGEMENT", "RAGHAEB RES", "RESIDENTIAL MANAGEMENT", "PROPERTY MANAGEMENT", "REALTY", "RENT", "MORTGAGE", "APARTMENTS", "LEASE"], "Mortgage & Rent", 0),

    # Groceries & Specialty
    (["STAR K", "KOSHER", "MARKET", "GROCERY", "SUPERMARKET", "WHOLE FOODS", "TRADER JOE", "PUBLIX", "COSTCO", "ALDI", "KROGER"], "Groceries", 0),

    # Medical & Healthcare
    (["CVS", "WALGREENS", "RITE AID", "PHARMACY", "CLINIC", "HOSPITAL", "DOCTOR", "DENTAL", "DENTIST", "QUEST DIAGNOSTICS", "LABCORP", "OPTICAL", "VISION", "HEALTHCARE"], "Medical & Healthcare", 0),
    
    # Restaurants & Dining
    (["CAFE", "BISTRO", "GRILL", "DINER", "BURGER", "PIZZA", "SUSHI", "TACO", "BAKERY", "BAR", "PUB", "RESTAURANT", "KITCHEN"], "Restaurants & Dining", 0),
    
    # Shopping & Retail
    (["FAWRY", "LEATHER", "CLOTHING", "BOUTIQUE", "RETAIL", "AMAZON", "TARGET", "WALMART", "BEST BUY", "HOME DEPOT", "LOWES"], "Shopping & Retail", 0),

    # Transfers
    (["ATM WITHDRAWAL", "CASH WITHDRAWAL", "WIRE TRANSFER", "ACH TRANSFER", "ZELLE", "VENMO", "PAYPAL"], "Internal Transfer", 1),
]

def apply_categorization_rules(conn, description: str, payee: str) -> Tuple[int | None, str | None, int]:
    """
    Match transaction description/payee against database rules using 4-tier robust intelligence engine.
    Returns (category_id, clean_payee, is_transfer).
    """
    cursor = conn.cursor()
    cursor.execute("SELECT id, pattern, category_id, clean_payee, is_transfer FROM rules ORDER BY priority DESC;")
    rules = cursor.fetchall()

    raw_desc = (description or "").upper()
    raw_payee = (payee or "").upper()
    combined_text = f"{raw_desc} {raw_payee}"
    clean_merchant = clean_merchant_description(description, payee)

    # Tier 1: Exact Substring / Token Match against database rules
    for rule in rules:
        pattern = rule["pattern"].upper()
        if pattern in clean_merchant or pattern in raw_desc or pattern in raw_payee:
            final_payee = rule["clean_payee"] if rule["clean_payee"] else (payee or clean_merchant.title())
            return rule["category_id"], final_payee, rule["is_transfer"]

    # Tier 2: Word Boundary / Regex Token Match
    for rule in rules:
        pattern = rule["pattern"].upper()
        if len(pattern) >= 3 and re.search(r'\b' + re.escape(pattern) + r'\b', combined_text):
            final_payee = rule["clean_payee"] if rule["clean_payee"] else (payee or clean_merchant.title())
            return rule["category_id"], final_payee, rule["is_transfer"]

    # Tier 3: Heuristic Domain Keyword Fallback Engine
    for keywords, category_name, is_transfer in HEURISTIC_KEYWORDS:
        for kw in keywords:
            if re.search(r'\b' + re.escape(kw) + r'\b', combined_text) or re.search(r'\b' + re.escape(kw) + r'\b', clean_merchant):
                cursor.execute("SELECT id, is_transfer FROM categories WHERE name = ?;", (category_name,))
                cat_row = cursor.fetchone()
                if cat_row:
                    cat_id = cat_row["id"]
                    cat_is_trans = cat_row["is_transfer"] if cat_row["is_transfer"] is not None else is_transfer
                    final_payee = payee or clean_merchant.title()
                    # Auto-persist rule so future syncs match in Tier 1 instantly
                    try:
                        cursor.execute("""
                        INSERT OR IGNORE INTO rules (pattern, category_id, clean_payee, is_transfer, priority)
                        VALUES (?, ?, ?, ?, 5);
                        """, (kw, cat_id, final_payee, cat_is_trans))
                        conn.commit()
                    except Exception:
                        pass
                    return cat_id, final_payee, cat_is_trans

    # Tier 4: Fuzzy Similarity Match against rule pattern keywords
    best_match = None
    highest_score = 0.0
    for rule in rules:
        pattern = rule["pattern"].upper()
        if len(pattern) >= 4 and len(clean_merchant) >= 4:
            ratio = SequenceMatcher(None, pattern, clean_merchant).ratio()
            if ratio >= 0.80 and ratio > highest_score:
                highest_score = ratio
                best_match = rule

    if best_match:
        final_payee = best_match["clean_payee"] if best_match["clean_payee"] else (payee or clean_merchant.title())
        return best_match["category_id"], final_payee, best_match["is_transfer"]

    # Fallback to Uncategorized if no rule matches
    cursor.execute("SELECT id FROM categories WHERE name = 'Uncategorized';")
    row = cursor.fetchone()
    cat_id = row["id"] if row else None
    return cat_id, (payee or clean_merchant.title() or "Unknown Merchant"), 0

def reapply_rules_to_uncategorized(conn=None, force_all: bool = False) -> int:
    """
    Re-evaluate categorization rules against Uncategorized transactions (or ALL transactions if force_all=True).
    Preserves user manual category assignments when force_all=False.
    Returns count of transactions categorized or updated.
    """
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True

    categorized_count = 0
    try:
        cursor = conn.cursor()
        
        cursor.execute("SELECT id FROM categories WHERE name = 'Uncategorized';")
        row = cursor.fetchone()
        uncat_id = row["id"] if row else None

        if force_all:
            cursor.execute("""
            SELECT id, description, payee 
            FROM transactions 
            WHERE is_transfer = 0;
            """)
        else:
            cursor.execute("""
            SELECT id, description, payee 
            FROM transactions 
            WHERE (category_id = ? OR category_id IS NULL) AND is_transfer = 0;
            """, (uncat_id,))

        txs = cursor.fetchall()
        now_str = current_eastern_time().isoformat()

        for tx in txs:
            cat_id, clean_payee, is_transfer = apply_categorization_rules(conn, tx["description"], tx["payee"])
            if cat_id is not None and (force_all or cat_id != uncat_id):
                cursor.execute("""
                UPDATE transactions
                SET category_id = ?, payee = ?, is_transfer = ?, updated_at = ?
                WHERE id = ?;
                """, (cat_id, clean_payee, is_transfer, now_str, tx["id"]))
                categorized_count += 1

        conn.commit()
    finally:
        if close_conn:
            conn.close()

    return categorized_count

def ai_autocategorize_transactions(conn=None, force_all: bool = False) -> int:
    """
    Use Gemini AI API to analyze and auto-categorize bank transactions.
    Auto-persists learned rules into SQLite database and updates transaction records.
    """
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True

    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name FROM categories ORDER BY id ASC;")
        cat_rows = cursor.fetchall()
        categories_map = {row["name"].upper(): row["id"] for row in cat_rows}
        categories_list = [row["name"] for row in cat_rows]

        cursor.execute("SELECT id FROM categories WHERE name = 'Uncategorized';")
        uncat_row = cursor.fetchone()
        uncat_id = uncat_row["id"] if uncat_row else None

        if force_all:
            cursor.execute("""
            SELECT id, description, payee, amount_cents 
            FROM transactions 
            WHERE is_transfer = 0;
            """)
        else:
            cursor.execute("""
            SELECT id, description, payee, amount_cents 
            FROM transactions 
            WHERE (category_id = ? OR category_id IS NULL) AND is_transfer = 0;
            """, (uncat_id,))
            
        txs = cursor.fetchall()
        if not txs:
            return 0

        api_key = os.getenv("GEMINI_API_KEY") or getattr(settings, "GEMINI_API_KEY", "")

        tx_items = []
        for tx in txs:
            tx_items.append({
                "id": str(tx["id"]),
                "description": tx["description"] or "",
                "payee": tx["payee"] or "",
                "amount": str(tx["amount_cents"] / 100.0)
            })

        ai_results = []
        if api_key:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
            prompt = f"""
            You are an expert personal finance transaction classifier.
            Classify each bank transaction into EXACTLY ONE category from this allowed list:
            {json.dumps(categories_list)}

            Important domain hints:
            - UF Health, Hospitals, Clinics, Doctors, Dental, CVS, Walgreens -> "Medical & Healthcare"
            - Tag Asmt, FL License, DMV, Vehicle registration, Auto Repair, Geico -> "Auto Payment & Insurance"
            - State of Florida Dept Revenue, IRS, Tax Collector, US Treasury -> "IRS/Taxes"
            - Collegeboard, SAT, ACT, University, Tuition, Schools -> "Education & Learning"
            - Circle K, Wawa, Speedway, Chevron, Shell -> "Fuel & Gas"
            - Neverland, AMC, Steam, PlayStation, Resorts, Theme Parks -> "Entertainment"
            - Staples, Office Depot, FedEx Office -> "Office"
            - Fawry, Leather, Retail stores -> "Shopping & Retail"
            - Raghaeb Res Management, Rent, Mortgage -> "Mortgage & Rent"

            Input transactions:
            {json.dumps(tx_items[:50])}

            Return ONLY valid JSON array with objects matching:
            [
              {{
                "id": "transaction_id",
                "category_name": "Exact Category Name",
                "clean_payee": "Clean Human Payee Name",
                "is_transfer": 0
              }}
            ]
            """
            try:
                res = httpx.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=25.0)
                if res.status_code == 200:
                    resp_json = res.json()
                    text_content = resp_json['candidates'][0]['content']['parts'][0]['text']
                    clean_json_str = re.sub(r"```json|```", "", text_content).strip()
                    ai_results = json.loads(clean_json_str)
            except Exception as e:
                print(f"[AI CATEGORIZATION WARNING] Gemini API call fallback: {e}")

        now_str = current_eastern_time().isoformat()
        updated_count = 0

        for item in (ai_results if ai_results else []):
            tx_id = item.get("id")
            cat_name = item.get("category_name", "").strip()
            clean_payee = item.get("clean_payee", "").strip()
            is_trans = 1 if item.get("is_transfer") else 0

            cat_id = categories_map.get(cat_name.upper())
            if tx_id and cat_id:
                cursor.execute("""
                UPDATE transactions
                SET category_id = ?, payee = ?, is_transfer = ?, updated_at = ?
                WHERE id = ?;
                """, (cat_id, clean_payee, is_trans, now_str, tx_id))
                updated_count += 1

                if clean_payee and len(clean_payee) >= 3:
                    cursor.execute("""
                    INSERT OR IGNORE INTO rules (pattern, category_id, clean_payee, is_transfer, priority)
                    VALUES (?, ?, ?, ?, 15);
                    """, (clean_payee.upper(), cat_id, clean_payee, is_trans))

        # Fallback heuristic pass
        heuristic_count = reapply_rules_to_uncategorized(conn=conn, force_all=force_all)
        conn.commit()

        return updated_count + heuristic_count
    finally:
        if close_conn:
            conn.close()

def ingest_simplefin_data(data: SimpleFINResponse, conn=None) -> Dict[str, int]:
    """
    Idempotent upsert of SimpleFIN account and transaction records into SQLite database.
    Stores money strictly in integer cents.
    """
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True

    stats = {"accounts_synced": 0, "transactions_synced": 0, "snapshots_created": 0}
    now_str = current_eastern_time().isoformat()
    today_str = current_eastern_time().strftime("%Y-%m-%d")

    try:
        cursor = conn.cursor()

        for account in data.accounts:
            bal_cents = to_cents(account.balance)
            avail_cents = to_cents(account.available_balance) if account.available_balance is not None else None
            org_name = account.org.name if account.org else None
            org_domain = account.org.domain if account.org else None

            acc_type = infer_account_type(account.name, org_name or "")

            # Upsert Account record
            cursor.execute("""
            INSERT INTO accounts (id, name, currency, balance_cents, available_balance_cents, org_name, org_domain, account_type, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                currency = excluded.currency,
                balance_cents = excluded.balance_cents,
                available_balance_cents = excluded.available_balance_cents,
                org_name = excluded.org_name,
                org_domain = excluded.org_domain,
                account_type = COALESCE(accounts.account_type, excluded.account_type),
                updated_at = excluded.updated_at;
            """, (account.id, account.name, account.currency, bal_cents, avail_cents, org_name, org_domain, acc_type, now_str))
            stats["accounts_synced"] += 1

            # Daily Balance Snapshot
            cursor.execute("""
            INSERT INTO balance_snapshots (account_id, snapshot_date, balance_cents, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(account_id, snapshot_date) DO UPDATE SET
                balance_cents = excluded.balance_cents,
                created_at = excluded.created_at;
            """, (account.id, today_str, bal_cents, now_str))
            stats["snapshots_created"] += 1

            # Process Transactions
            for tx in account.transactions:
                amt_cents = to_cents(tx.amount)
                posted_dt = timestamp_to_eastern_date(tx.posted).isoformat()
                pending_int = 1 if tx.pending else 0

                # Check if transaction already has user category assignment
                cursor.execute("SELECT category_id, is_transfer, user_notes FROM transactions WHERE id = ?;", (tx.id,))
                existing = cursor.fetchone()

                if existing and existing["category_id"] is not None:
                    cat_id = existing["category_id"]
                    is_transfer = existing["is_transfer"]
                    clean_payee = tx.payee
                else:
                    cat_id, clean_payee, is_transfer = apply_categorization_rules(conn, tx.description, tx.payee)

                cursor.execute("""
                INSERT INTO transactions (
                    id, account_id, posted_at, posted_timestamp, amount_cents,
                    description, payee, memo, pending, category_id, is_transfer,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    account_id = excluded.account_id,
                    posted_at = excluded.posted_at,
                    posted_timestamp = excluded.posted_timestamp,
                    amount_cents = excluded.amount_cents,
                    description = excluded.description,
                    payee = COALESCE(excluded.payee, transactions.payee),
                    memo = excluded.memo,
                    pending = excluded.pending,
                    updated_at = excluded.updated_at;
                """, (
                    tx.id, account.id, posted_dt, tx.posted, amt_cents,
                    tx.description, clean_payee, tx.memo, pending_int, cat_id, is_transfer,
                    now_str, now_str
                ))
                stats["transactions_synced"] += 1

        conn.commit()
    finally:
        if close_conn:
            conn.close()

    return stats
