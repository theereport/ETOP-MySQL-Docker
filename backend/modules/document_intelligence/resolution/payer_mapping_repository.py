from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.engine import Engine

from data.mysql import get_engine, metadata, payer_customer_mapping_table


class PayerCustomerMappingRepository:
    def __init__(self, engine: Engine | None = None) -> None:
        self._engine = engine or get_engine()

    def initialize(self):
        metadata.create_all(
            self._engine, checkfirst=True, tables=[payer_customer_mapping_table]
        )

    def upsert(self, routing_number, bank_account_last4, normalized_payer_name, customer_number, confidence, confirmed_by_user=True):
        now = datetime.now(timezone.utc).isoformat()
        self.initialize()
        table = payer_customer_mapping_table
        routing_number = routing_number or ""
        bank_account_last4 = bank_account_last4 or ""
        normalized_payer_name = normalized_payer_name or ""
        with self._engine.begin() as connection:
            existing = connection.execute(
                select(table.c.mapping_id).where(
                    table.c.routing_number == routing_number,
                    table.c.bank_account_last4 == bank_account_last4,
                    table.c.normalized_payer_name == normalized_payer_name,
                )
            ).first()
            if existing is None:
                connection.execute(
                    table.insert().values(
                        routing_number=routing_number,
                        bank_account_last4=bank_account_last4,
                        normalized_payer_name=normalized_payer_name,
                        customer_number=customer_number,
                        confidence=confidence,
                        confirmed_by_user=1 if confirmed_by_user else 0,
                        first_seen_at=now,
                        last_seen_at=now,
                    )
                )
            else:
                connection.execute(
                    table.update()
                    .where(table.c.mapping_id == existing[0])
                    .values(
                        customer_number=customer_number,
                        confidence=confidence,
                        confirmed_by_user=1 if confirmed_by_user else 0,
                        last_seen_at=now,
                    )
                )

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
        table = payer_customer_mapping_table
        with self._engine.connect() as connection:
            rows = connection.execute(
                select(table.c.customer_number)
                .where(
                    table.c.routing_number == routing_number,
                    table.c.bank_account_last4 == bank_account_last4,
                    table.c.confirmed_by_user == 1,
                )
                .distinct()
            ).all()
        return [row[0] for row in rows]
