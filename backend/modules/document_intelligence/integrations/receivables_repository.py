from __future__ import annotations

from datetime import date, datetime, timedelta
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

    # Same shape as GET_OPEN_INVOICES_SQL, but for invoices MaddenCo still
    # carries on TMAROP with a zero open balance - these are excluded from
    # the normal open-invoice list above and shown separately, since a $0
    # balance can be reopened (given a manual balance again) and reviewers
    # need to find them without them cluttering the list of invoices that
    # actually have money outstanding today.
    #
    # MaddenCo does not purge $0 TMAROP rows - a real customer can carry
    # thousands of them going back decades - so this is filtered to
    # TARODTECHG (date of last change) within the last few days in Python
    # (see get_zero_balance_open_invoices), the same way
    # GET_CLOSED_INVOICE_HISTORY_SQL's TIHHDTECHG cutoff works. The LIMIT
    # here is just a defensive bound on top of that, not the real filter.
    GET_ZERO_BALANCE_OPEN_INVOICES_ROW_LIMIT = 2000
    GET_ZERO_BALANCE_OPEN_INVOICES_SQL = """
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
            TAROADJRSN AS adjustment_reason,
            TARODTECHG AS changed_date

        FROM TMAROP
        WHERE TARONUMCST = %(customer_number)s
          AND TAROAMTOPN = 0

        ORDER BY TARODTECHG DESC

        LIMIT {row_limit}
    """.format(row_limit=GET_ZERO_BALANCE_OPEN_INVOICES_ROW_LIMIT)

    # Every TMAROP invoice number for this customer (any balance), used to
    # exclude invoices from the TMIHSH closed-invoice list below that are
    # still carried on TMAROP - avoids showing the same invoice in both
    # lists.
    GET_ALL_TMAROP_INVOICE_NUMBERS_SQL = """
        SELECT DISTINCT TARONUMINV AS invoice_number
        FROM TMAROP
        WHERE TARONUMCST = %(customer_number)s
    """

    # TMIHSH ("Invoice history headers") holds invoices MaddenCo has fully
    # closed out of TMAROP. It has no open-balance/debit-credit columns -
    # TIHHCODTYP ('I' or 'C') is its closest analog to TARODBCR, and
    # TIHHDTECHG (date of last change) is used as the "closed" date, since a
    # history row's last change is effectively when it moved into history.
    # Bounded and ordered most-recent-first so a LIMIT still captures every
    # invoice that could fall inside the last 60 days.
    GET_CLOSED_INVOICE_HISTORY_ROW_LIMIT = 500
    GET_CLOSED_INVOICE_HISTORY_SQL = """
        SELECT
            TIHHNUMCST AS customer_number,
            TIHHNUMINV AS invoice_number,
            TIHHNUMCNT AS invoice_count,
            TIHHDTEINV AS invoice_date,
            TIHHDTEDUE AS due_date,
            TIHHTOTINV AS original_amount,
            TIHHCODTYP AS type_code,
            TIHHDTECHG AS changed_date

        FROM TMIHSH
        WHERE TIHHNUMCST = %(customer_number)s

        ORDER BY TIHHDTECHG DESC
        LIMIT {row_limit}
    """.format(row_limit=GET_CLOSED_INVOICE_HISTORY_ROW_LIMIT)

    def __init__(self, database, *, invoice_owner_cache=None):
        self.database = database
        self.aging_calculator = InvoiceAgingCalculator()
        self._invoice_owner_cache = invoice_owner_cache

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
        return self._map_open_invoice_rows(rows, aging_as_of_date)

    def get_zero_balance_open_invoices(
        self,
        customer_number: str,
        aging_as_of_date: date,
        *,
        days: int = 5,
    ) -> list[OpenInvoice]:
        rows = self.database.fetch_all(
            self.GET_ZERO_BALANCE_OPEN_INVOICES_SQL,
            {
                "customer_number": customer_number,
            },
        )
        cutoff = aging_as_of_date - timedelta(days=days)
        recent_rows = [
            row
            for row in rows
            if (changed_date := self._to_date(row.get("changed_date")))
            is not None
            and changed_date >= cutoff
        ]
        return self._map_open_invoice_rows(recent_rows, aging_as_of_date)

    def get_recently_closed_invoices(
        self,
        customer_number: str,
        as_of_date: date,
        *,
        days: int = 60,
    ) -> list[OpenInvoice]:
        tmarop_rows = self.database.fetch_all(
            self.GET_ALL_TMAROP_INVOICE_NUMBERS_SQL,
            {"customer_number": customer_number},
        )
        tmarop_invoice_numbers = {
            normalize_erp_invoice(row.get("invoice_number"))
            for row in tmarop_rows
        }

        history_rows = self.database.fetch_all(
            self.GET_CLOSED_INVOICE_HISTORY_SQL,
            {"customer_number": customer_number},
        )

        cutoff = as_of_date - timedelta(days=days)
        invoices: list[OpenInvoice] = []
        for row in history_rows:
            invoice_number = normalize_erp_invoice(row.get("invoice_number"))
            if invoice_number and invoice_number in tmarop_invoice_numbers:
                continue

            changed_date = self._to_date(row.get("changed_date"))
            if changed_date is None or changed_date < cutoff:
                continue

            type_code = str(row.get("type_code") or "").strip().upper()
            invoices.append(
                OpenInvoice(
                    customer_number=str(row["customer_number"]),
                    invoice_number=str(row["invoice_number"]),
                    invoice_count=(
                        int(row["invoice_count"])
                        if row.get("invoice_count") is not None
                        else None
                    ),
                    invoice_date=self._to_date(row.get("invoice_date")),
                    due_date=self._to_date(row.get("due_date")),
                    original_amount=self._to_decimal(
                        row.get("original_amount")
                    ),
                    open_amount=Decimal("0.00"),
                    debit_credit="C" if type_code == "C" else "D",
                    aging_bucket="Closed",
                )
            )

        return invoices

    def _map_open_invoice_rows(
        self,
        rows: list[dict[str, Any]],
        aging_as_of_date: date,
    ) -> list[OpenInvoice]:
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

        if self._invoice_owner_cache is not None:
            cached = self._invoice_owner_cache.get_owners(normalized)
            if cached is not None:
                return cached

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
                  AND TARONUMINV IN ({placeholders})
                LIMIT {self.CURRENT_INVOICE_OWNER_ROW_LIMIT}
                """,
                tuple(int(invoice) for invoice in chunk),
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
