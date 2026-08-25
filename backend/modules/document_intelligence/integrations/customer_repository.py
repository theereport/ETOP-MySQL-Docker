from __future__ import annotations

from decimal import Decimal
from typing import Any

from ..business_objects.models import CustomerAgingSnapshot
from .db_protocol import ReadOnlyDatabase


class CustomerRepository:
    GET_BY_NUMBER_SQL = """
        SELECT
            CUNUMBER AS customer_number,
            CUNAME AS customer_name,
            CUADDR1 AS address_line_1,
            CUCITY AS city,
            CUSTATE AS state,
            CUZIP AS postal_code
        FROM TMCUST
        WHERE CUNUMBER = :customer_number
        LIMIT 1
    """

    SEARCH_SQL = """
        SELECT
            CUNUMBER AS customer_number,
            CUNAME AS customer_name,
            CUADDR1 AS address_line_1,
            CUCITY AS city,
            CUSTATE AS state,
            CUZIP AS postal_code
        FROM TMCUST
        WHERE
            (
                :postal_code <> ''
                AND LEFT(REPLACE(CUZIP, '-', ''), 5) = :postal_code
            )
            OR
            (
                :state <> ''
                AND UPPER(TRIM(CUSTATE)) = UPPER(TRIM(:state))
            )
            OR
            (
                :payer_name <> ''
                AND UPPER(CUNAME) LIKE CONCAT(
                    '%',
                    UPPER(:payer_name),
                    '%'
                )
            )
        ORDER BY CUNAME
        LIMIT :limit
    """

    GET_AGING_SQL = """
        SELECT
            CUNUMBER AS customer_number,
            CUNAME AS customer_name,

            CURVCPMFUT AS future_due,
            CURVCPMCUR AS current_due,
            CURVCPM30 AS past_due_30,
            CURVCPM60 AS past_due_60,
            CURVCPM90 AS past_due_90,
            CURVCPM120 AS past_due_120,

            CURVCBLEOM AS total_balance_due,

            CULASPAYDT AS last_payment_date,
            CULASPAYAM AS last_payment_amount

        FROM TMCUST
        WHERE CUNUMBER = :customer_number
        LIMIT 1
    """

    def __init__(self, database: ReadOnlyDatabase):
        self.database = database

    def get_by_customer_number(
        self,
        customer_number: str,
    ) -> dict[str, Any] | None:
        return self.database.fetch_one(
            self.GET_BY_NUMBER_SQL,
            {
                "customer_number": customer_number,
            },
        )

    def search_candidates(
        self,
        payer_name: str | None,
        postal_code: str | None,
        state: str | None,
        limit: int = 25,
    ) -> list[dict[str, Any]]:
        return self.database.fetch_all(
            self.SEARCH_SQL,
            {
                "payer_name": payer_name or "",
                "postal_code": (postal_code or "")[:5],
                "state": state or "",
                "limit": limit,
            },
        )

    def get_aging_snapshot(
        self,
        customer_number: str,
    ) -> CustomerAgingSnapshot | None:
        row = self.database.fetch_one(
            self.GET_AGING_SQL,
            {
                "customer_number": customer_number,
            },
        )

        if not row:
            return None

        return CustomerAgingSnapshot(
            customer_number=str(row["customer_number"]),
            future_due=self._to_decimal(
                row.get("future_due")
            ),
            current_due=self._to_decimal(
                row.get("current_due")
            ),
            past_due_30=self._to_decimal(
                row.get("past_due_30")
            ),
            past_due_60=self._to_decimal(
                row.get("past_due_60")
            ),
            past_due_90=self._to_decimal(
                row.get("past_due_90")
            ),
            past_due_120=self._to_decimal(
                row.get("past_due_120")
            ),
            total_balance_due=self._to_decimal(
                row.get("total_balance_due")
            ),
            last_payment_date=(
                str(row["last_payment_date"])
                if row.get("last_payment_date") is not None
                else None
            ),
            last_payment_amount=self._to_decimal(
                row.get("last_payment_amount")
            ),
        )

    @staticmethod
    def _to_decimal(
        value: Any,
    ) -> Decimal:
        if value is None:
            return Decimal("0.00")

        return Decimal(str(value)).quantize(
            Decimal("0.01")
        )