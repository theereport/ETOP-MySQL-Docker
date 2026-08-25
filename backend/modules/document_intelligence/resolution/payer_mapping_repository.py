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
        with sqlite3.connect(self.db_path) as c:
            c.execute("""CREATE TABLE IF NOT EXISTS payer_customer_mapping(
                mapping_id INTEGER PRIMARY KEY AUTOINCREMENT,
                routing_number TEXT NOT NULL DEFAULT '',
                bank_account_last4 TEXT NOT NULL DEFAULT '',
                normalized_payer_name TEXT NOT NULL DEFAULT '',
                customer_number TEXT NOT NULL, confidence REAL NOT NULL,
                confirmed_by_user INTEGER NOT NULL DEFAULT 0,
                first_seen_at TEXT NOT NULL,last_seen_at TEXT NOT NULL,
                UNIQUE(routing_number,bank_account_last4,normalized_payer_name))""")
    def upsert(self,routing_number,bank_account_last4,normalized_payer_name,customer_number,confidence,confirmed_by_user=True):
        now=datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.db_path) as c:
            c.execute("""INSERT INTO payer_customer_mapping
            (routing_number,bank_account_last4,normalized_payer_name,customer_number,confidence,confirmed_by_user,first_seen_at,last_seen_at)
            VALUES(?,?,?,?,?,?,?,?)
            ON CONFLICT(routing_number,bank_account_last4,normalized_payer_name)
            DO UPDATE SET customer_number=excluded.customer_number,confidence=excluded.confidence,
            confirmed_by_user=excluded.confirmed_by_user,last_seen_at=excluded.last_seen_at""",
            (routing_number or "",bank_account_last4 or "",normalized_payer_name or "",customer_number,confidence,1 if confirmed_by_user else 0,now,now))
