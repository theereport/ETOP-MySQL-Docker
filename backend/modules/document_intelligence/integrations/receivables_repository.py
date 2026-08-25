from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from invoice_number_rules import normalize_erp_invoice

from ..business_objects.models import OpenInvoice
from ..resolution.invoice_aging import InvoiceAgingCalculator


class ReceivablesRepository:
    CURRENT_INVOICE_OWNER_CHUNK_SIZE = 100
    CURRENT_INVOICE_OWNER_ROW_LIMIT = 1001
    GET_OPEN_INVOICES_SQL = """
        SELECT
            TARONUMCST AS customer_number,
            TARONUMINV AS invoice_number,
            TARONUMCNT AS invoice_count,
            TARODTE AS invoice_date,
            TARODTEDUE AS due_date,

            TAROAMTORG AS original_amount,
            TAROAMTOPN AS open_amount,
            TAROAMTMMO AS open_memo_amount,
            TAROAMTDSC AS discountable_amount,
            TAROCSHDSC AS cash_discount,

            TARODBCR AS debit_credit,
            TAROTYPTRN AS transaction_type,
            TAROSTRSEL AS selling_store,
            TARONUMREF AS reference_number,
            TAROADJRSN AS adjustment_reason

        FROM TMAROP
        WHERE TARONUMCST = %(customer_number)s
          AND TAROAMTOPN <> 0

        ORDER BY
            TARODTEDUE,
            TARODTE,
            TARONUMINV,
            TARONUMCNT
    """

    def __init__(self, database):
        self.database = database
        self.aging_calculator = InvoiceAgingCalculator()

    def get_open_invoices(
        self,
        customer_number: str,
        aging_as_of_date: date,
    ) -> list[OpenInvoice]:
        rows = self.database.fetch_all(
            self.GET_OPEN_INVOICES_SQL,
            {
                "customer_number": customer_number,
            },
        )

        invoices: list[OpenInvoice] = []

        for row in rows:
            open_amount = self._signed_amount(
                value=row.get("open_amount"),
                debit_credit=row.get("debit_credit"),
            )

            invoice_date = self._to_date(
                row.get("invoice_date")
            )

            due_date = self._to_date(
                row.get("due_date")
            )

            aging_bucket = self.aging_calculator.get_bucket(
                due_date=due_date,
                aging_as_of_date=aging_as_of_date,
            )

            days_past_due = (
                (aging_as_of_date - due_date).days
                if due_date is not None
                else None
            )

            invoices.append(
                OpenInvoice(
                    customer_number=str(
                        row["customer_number"]
                    ),
                    invoice_number=str(
                        row["invoice_number"]
                    ),
                    invoice_count=(
                        int(row["invoice_count"])
                        if row.get("invoice_count") is not None
                        else None
                    ),
                    invoice_date=invoice_date,
                    due_date=due_date,
                    original_amount=self._to_decimal(
                        row.get("original_amount")
                    ),
                    open_amount=open_amount,
                    open_memo_amount=self._to_decimal(
                        row.get("open_memo_amount")
                    ),
                    discountable_amount=self._to_decimal(
                        row.get("discountable_amount")
                    ),
                    cash_discount=self._to_decimal(
                        row.get("cash_discount")
                    ),
                    debit_credit=str(
                        row.get("debit_credit") or ""
                    ),
                    transaction_type=str(
                        row.get("transaction_type") or ""
                    ),
                    selling_store=(
                        str(row["selling_store"])
                        if row.get("selling_store") is not None
                        else None
                    ),
                    reference_number=str(
                        row.get("reference_number") or ""
                    ),
                    adjustment_reason=str(
                        row.get("adjustment_reason") or ""
                    ),
                    days_past_due=days_past_due,
                    aging_bucket=aging_bucket,
                )
            )

        return invoices

    def get_current_invoice_owners(
        self,
        invoice_numbers: list[str] | tuple[str, ...],
    ) -> dict[str, set[str]]:
        """Read the current TMAROP owner set for governed invoices.

        This is a bounded, read-only lookup.  Returning every requested key,
        including those with no rows, lets the caller distinguish a successful
        missing-owner result from a failed ERP read.
        """

        normalized = list(
            dict.fromkeys(
                invoice
                for value in invoice_numbers
                if (invoice := normalize_erp_invoice(value))
            )
        )
        owners: dict[str, set[str]] = {
            invoice: set() for invoice in normalized
        }
        for start in range(
            0,
            len(normalized),
            self.CURRENT_INVOICE_OWNER_CHUNK_SIZE,
        ):
            chunk = normalized[
                start : start + self.CURRENT_INVOICE_OWNER_CHUNK_SIZE
            ]
            placeholders = ", ".join(["%s"] * len(chunk))
            rows = self.database.fetch_all(
                f"""
                SELECT
                    CAST(TARONUMINV AS CHAR) AS invoice_number,
                    CAST(TARONUMCST AS CHAR) AS customer_number
                FROM TMAROP
                WHERE TAROAMTOPN <> 0
                  AND TRIM(LEADING '0' FROM CAST(TARONUMINV AS CHAR))
                      IN ({placeholders})
                LIMIT {self.CURRENT_INVOICE_OWNER_ROW_LIMIT}
                """,
                tuple(chunk),
            )
            if len(rows) >= self.CURRENT_INVOICE_OWNER_ROW_LIMIT:
                raise RuntimeError(
                    "The bounded TMAROP current-invoice owner lookup was "
                    "incomplete."
                )
            for row in rows:
                invoice = normalize_erp_invoice(row.get("invoice_number"))
                customer_number = str(
                    row.get("customer_number") or ""
                ).strip().removesuffix(".0")
                if invoice in owners and customer_number:
                    owners[invoice].add(customer_number)
        return owners

    @staticmethod
    def _to_decimal(value: Any) -> Decimal:
        return Decimal(
            str(value or 0)
        ).quantize(
            Decimal("0.01")
        )

    def _signed_amount(
        self,
        value: Any,
        debit_credit: Any,
    ) -> Decimal:
        amount = self._to_decimal(value)

        indicator = str(
            debit_credit or ""
        ).strip().upper()

        if indicator in {"C", "CR", "CREDIT"}:
            return -abs(amount)

        return abs(amount)

    @staticmethod
    def _to_date(value: Any) -> date | None:
        if value in (None, "", 0):
            return None

        if isinstance(value, datetime):
            return value.date()

        if isinstance(value, date):
            return value

        text = str(value).strip()

        # Handles values returned as numbers such as 20260722.0.
        if text.endswith(".0"):
            text = text[:-2]

        for date_format in (
            "%Y%m%d",
            "%m%d%Y",
            "%m/%d/%Y",
            "%Y-%m-%d",
        ):
            try:
                return datetime.strptime(
                    text,
                    date_format,
                ).date()
            except ValueError:
                continue

        return None
