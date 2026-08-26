import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from core.test_path_override import resolve_test_path_override

class PayerCustomerMappingRepository:
    def __init__(self, db_path=None):
        self.db_path = Path(
            db_path
            if db_path is not None
            else resolve_test_path_override(
                "ETOP_TEST_CASH_PAYER_LEARNING_DB",
                "data/modules/document_intelligence/document_intelligence.db",
            )
        )
    def initialize(self):
        self.db_path.parent.mkdir(parents=True,exist_ok=True)
        c = sqlite3.connect(self.db_path)
        try:
            with c:
                c.execute("""CREATE TABLE IF NOT EXISTS payer_customer_mapping(
                    mapping_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    routing_number TEXT NOT NULL DEFAULT '',
                    bank_account_last4 TEXT NOT NULL DEFAULT '',
                    normalized_payer_name TEXT NOT NULL DEFAULT '',
                    customer_number TEXT NOT NULL, confidence REAL NOT NULL,
                    confirmed_by_user INTEGER NOT NULL DEFAULT 0,
                    first_seen_at TEXT NOT NULL,last_seen_at TEXT NOT NULL,
                    UNIQUE(routing_number,bank_account_last4,normalized_payer_name))""")
        finally:
            c.close()

    def upsert(self,routing_number,bank_account_last4,normalized_payer_name,customer_number,confidence,confirmed_by_user=True):
        now=datetime.now(timezone.utc).isoformat()
        c = sqlite3.connect(self.db_path)
        try:
            with c:
                c.execute("""INSERT INTO payer_customer_mapping
                (routing_number,bank_account_last4,normalized_payer_name,customer_number,confidence,confirmed_by_user,first_seen_at,last_seen_at)
                VALUES(?,?,?,?,?,?,?,?)
                ON CONFLICT(routing_number,bank_account_last4,normalized_payer_name)
                DO UPDATE SET customer_number=excluded.customer_number,confidence=excluded.confidence,
                confirmed_by_user=excluded.confirmed_by_user,last_seen_at=excluded.last_seen_at""",
                (routing_number or "",bank_account_last4 or "",normalized_payer_name or "",customer_number,confidence,1 if confirmed_by_user else 0,now,now))
        finally:
            c.close()

    def find_confirmed_customer_numbers(self, routing_number, bank_account_last4):
        """Distinct human-confirmed customer numbers previously recorded
        for this exact bank account (routing + last 4 of the account
        number), regardless of payer-name text - OCR can render the same
        real payer's name slightly differently across checks, but the
        bank account itself is an exact identifier."""
        routing_number = (routing_number or "").strip()
        bank_account_last4 = (bank_account_last4 or "").strip()
        if not routing_number or not bank_account_last4:
            return []
        self.initialize()
        c = sqlite3.connect(self.db_path)
        try:
            c.row_factory = sqlite3.Row
            rows = c.execute(
                """SELECT DISTINCT customer_number FROM payer_customer_mapping
                WHERE routing_number = ? AND bank_account_last4 = ?
                  AND confirmed_by_user = 1""",
                (routing_number, bank_account_last4),
            ).fetchall()
        finally:
            c.close()
        return [row["customer_number"] for row in rows]
