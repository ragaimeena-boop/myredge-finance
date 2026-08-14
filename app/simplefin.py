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

def apply_categorization_rules(conn, description: str, payee: str) -> Tuple[int | None, str | None, int]:
    """
    Match transaction description/payee against database rules.
    Returns (category_id, clean_payee, is_transfer).
    """
    cursor = conn.cursor()
    cursor.execute("SELECT id, pattern, category_id, clean_payee, is_transfer FROM rules ORDER BY priority DESC;")
    rules = cursor.fetchall()

    desc_upper = (description or "").upper()
    payee_upper = (payee or "").upper()

    for rule in rules:
        pattern = rule["pattern"].upper()
        if pattern in desc_upper or pattern in payee_upper:
            clean_payee = rule["clean_payee"] if rule["clean_payee"] else payee
            return rule["category_id"], clean_payee, rule["is_transfer"]

    # Fallback to Uncategorized if no rule matches
    cursor.execute("SELECT id FROM categories WHERE name = 'Uncategorized';")
    row = cursor.fetchone()
    cat_id = row["id"] if row else None
    return cat_id, payee, 0

def reapply_rules_to_uncategorized(conn=None) -> int:
    """
    Re-evaluate categorization rules against all currently Uncategorized transactions.
    Preserves user manual category assignments.
    Returns count of transactions categorized.
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

        cursor.execute("""
        SELECT id, description, payee 
        FROM transactions 
        WHERE (category_id = ? OR category_id IS NULL) AND is_transfer = 0;
        """, (uncat_id,))
        txs = cursor.fetchall()

        now_str = current_eastern_time().isoformat()

        for tx in txs:
            cat_id, clean_payee, is_transfer = apply_categorization_rules(conn, tx["description"], tx["payee"])
            if cat_id is not None and cat_id != uncat_id:
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

            # Upsert Account record
            cursor.execute("""
            INSERT INTO accounts (id, name, currency, balance_cents, available_balance_cents, org_name, org_domain, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                currency = excluded.currency,
                balance_cents = excluded.balance_cents,
                available_balance_cents = excluded.available_balance_cents,
                org_name = excluded.org_name,
                org_domain = excluded.org_domain,
                updated_at = excluded.updated_at;
            """, (account.id, account.name, account.currency, bal_cents, avail_cents, org_name, org_domain, now_str))
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
