from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field


class HistoricalPaymentGroup(BaseModel):
    customer_number: str
    payment_reference: str
    invoice_count: int
    invoice_numbers: list[str] = Field(default_factory=list)
    original_invoice_total: Decimal = Decimal("0.00")
    remaining_open_amount: Decimal = Decimal("0.00")


class HistoryRepository:
    """
    Reads historical payment groupings from TMAROP.

    A historical payment group consists of fully paid invoices that share
    the same nonblank TAROGLREF value.

    TAROGLREF is treated as a grouping reference. This supports historical
    confidence scoring but does not independently prove the precise payment
    posting sequence.
    """

    def __init__(self, database: Any) -> None:
        self.database = database

    def get_historical_payment_groups(
        self,
        customer_number: str,
        limit: int = 500,
    ) -> list[HistoricalPaymentGroup]:

        safe_limit = max(1, min(2000, int(limit)))

        sql = f"""
            SELECT
                CAST(TARONUMCST AS CHAR) AS customer_number,

                TRIM(
                    CAST(TAROGLREF AS CHAR)
                ) AS payment_reference,

                COUNT(
                    DISTINCT TARONUMINV
                ) AS invoice_count,

                GROUP_CONCAT(
                    DISTINCT CAST(TARONUMINV AS CHAR)
                    ORDER BY TARONUMINV
                    SEPARATOR ','
                ) AS invoice_numbers,

                SUM(
                    COALESCE(TAROAMTORG, 0)
                ) AS original_invoice_total,

                SUM(
                    COALESCE(TAROAMTOPN, 0)
                ) AS remaining_open_amount

            FROM DTA273.TMAROP

            WHERE TARONUMCST = %(customer_number)s

              AND COALESCE(TAROAMTOPN, 0) = 0

              AND TAROGLREF IS NOT NULL

              AND TRIM(
                    CAST(TAROGLREF AS CHAR)
                  ) NOT IN ('', '0')

            GROUP BY
                TARONUMCST,
                TAROGLREF

            ORDER BY
                invoice_count DESC,
                TAROGLREF DESC

            LIMIT {safe_limit}
        """

        rows = self.database.fetch_all(
            sql,
            {
                "customer_number": int(customer_number),
            },
        )

        payment_groups: list[HistoricalPaymentGroup] = []

        for row in rows:
            raw_invoice_numbers = row.get("invoice_numbers") or ""

            invoice_numbers = [
                invoice_number.strip()
                for invoice_number in str(raw_invoice_numbers).split(",")
                if invoice_number.strip()
            ]

            payment_groups.append(
                HistoricalPaymentGroup(
                    customer_number=str(row["customer_number"]).strip(),
                    payment_reference=str(
                        row["payment_reference"]
                    ).strip(),
                    invoice_count=int(row["invoice_count"] or 0),
                    invoice_numbers=invoice_numbers,
                    original_invoice_total=Decimal(
                        str(row["original_invoice_total"] or 0)
                    ),
                    remaining_open_amount=Decimal(
                        str(row["remaining_open_amount"] or 0)
                    ),
                )
            )

        return payment_groups