"""Bounded read-only access to Payment Notes and signature evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any, Sequence

from .matching import (
    ExpectedPayment,
    SignatureEvidence,
    extract_invoice_references,
    money,
    normalize_check_number,
)
from .route_reference import normalize_route


ERP_CONTRACT_VERSION = "payment-notes-erp-evidence@1.0.0"


class PaymentNotesERPError(RuntimeError):
    """The bounded ERP evidence request could not be completed safely."""


@dataclass(frozen=True)
class ExpectedPaymentResult:
    payments: tuple[ExpectedPayment, ...]
    complete: bool
    row_limit: int
    route_count: int
    retrieved_at: str


@dataclass(frozen=True)
class SignatureResult:
    evidence: dict[tuple[str, str], tuple[SignatureEvidence, ...]]
    complete: bool
    row_limit: int
    pair_count: int
    retrieved_at: str


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, Decimal) and value == value.to_integral_value():
        return str(int(value))
    text = str(value).strip()
    if text.endswith(".0") and text[:-2].isdigit():
        return text[:-2]
    return text


def _timestamp(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value).strip()


class PaymentNotesERPRepository:
    """Fixed-projection ERP queries; no mutation method is provided."""

    MAX_ROUTES = 250
    EXPECTED_PAYMENT_ROW_LIMIT = 5_000
    MAX_SIGNATURE_PAIRS = 250
    SIGNATURE_ROW_LIMIT = 2_000

    def __init__(self, database=None, clock=None) -> None:
        if database is None:
            # Keep pure parsing/matching imports runnable without the ERP/web
            # dependency stack. The real connector is resolved only when this
            # read-only repository is actually constructed.
            from core.database import madden_database

            database = madden_database
        self.database = database
        self.clock = clock or (lambda: datetime.now().astimezone().isoformat())

    def get_expected_payments(
        self,
        routes: Sequence[str],
        date_from: date,
        date_to: date,
    ) -> ExpectedPaymentResult:
        if date_to < date_from:
            raise PaymentNotesERPError("Payment Notes date_to precedes date_from.")
        normalized_routes = tuple(
            sorted(
                dict.fromkeys(
                    route
                    for value in routes
                    if (route := normalize_route(value))
                )
            )
        )
        if not normalized_routes:
            return ExpectedPaymentResult((), True, self.EXPECTED_PAYMENT_ROW_LIMIT, 0, self.clock())
        if len(normalized_routes) > self.MAX_ROUTES:
            raise PaymentNotesERPError(
                f"Route set exceeds the {self.MAX_ROUTES}-route query bound."
            )
        placeholders = ", ".join(["%s"] * len(normalized_routes))
        start = datetime.combine(date_from, time.min)
        end_exclusive = datetime.combine(date_to + timedelta(days=1), time.min)
        try:
            rows = self.database.fetch_all(
                f"""
                SELECT
                    ID,
                    CUSTNUM,
                    TRIM(ROUTE) AS ROUTE,
                    TRIM(TYPE) AS TYPE,
                    CAST(CHECKNUM AS CHAR) AS CHECKNUM,
                    CAST(AUTHNUM AS CHAR) AS AUTHNUM,
                    AMOUNT,
                    NOTES,
                    INVOICES,
                    RECEIVED,
                    RECSTAMP,
                    CRTSTAMP
                FROM KMTDTA.WHSIGPAY
                WHERE TRIM(ROUTE) IN ({placeholders})
                  AND UPPER(TRIM(TYPE)) = 'CHECK'
                  AND CRTSTAMP >= %s
                  AND CRTSTAMP < %s
                ORDER BY CRTSTAMP, ID
                LIMIT {self.EXPECTED_PAYMENT_ROW_LIMIT + 1}
                """,
                (*normalized_routes, start, end_exclusive),
            )
        except Exception as exc:
            raise PaymentNotesERPError(
                "The read-only WHSIGPAY evidence query failed."
            ) from exc
        complete = len(rows) <= self.EXPECTED_PAYMENT_ROW_LIMIT
        payments: list[ExpectedPayment] = []
        for row in rows[: self.EXPECTED_PAYMENT_ROW_LIMIT]:
            raw_invoices = _text(row.get("INVOICES"))
            invoice_numbers, invoice_status = extract_invoice_references(raw_invoices)
            raw_check = _text(row.get("CHECKNUM"))
            payments.append(
                ExpectedPayment(
                    payment_id=_text(row.get("ID")),
                    customer_number=_text(row.get("CUSTNUM")),
                    route=normalize_route(row.get("ROUTE")),
                    payment_type=_text(row.get("TYPE")),
                    raw_check_number=raw_check,
                    normalized_check_number=normalize_check_number(raw_check),
                    amount=money(row.get("AMOUNT")),
                    authorization_number=_text(row.get("AUTHNUM")),
                    notes=_text(row.get("NOTES")),
                    raw_invoices=raw_invoices,
                    invoice_numbers=invoice_numbers,
                    invoice_reference_status=invoice_status,
                    received=_text(row.get("RECEIVED")),
                    received_at=_timestamp(row.get("RECSTAMP")),
                    created_at=_timestamp(row.get("CRTSTAMP")),
                )
            )
        return ExpectedPaymentResult(
            payments=tuple(payments),
            complete=complete,
            row_limit=self.EXPECTED_PAYMENT_ROW_LIMIT,
            route_count=len(normalized_routes),
            retrieved_at=self.clock(),
        )

    def get_signature_evidence(
        self,
        customer_invoice_pairs: Sequence[tuple[str, str]],
    ) -> SignatureResult:
        pairs = tuple(
            sorted(
                dict.fromkeys(
                    (_text(customer), _text(invoice))
                    for customer, invoice in customer_invoice_pairs
                    if _text(customer) and _text(invoice)
                )
            )
        )
        if not pairs:
            return SignatureResult({}, True, self.SIGNATURE_ROW_LIMIT, 0, self.clock())
        if len(pairs) > self.MAX_SIGNATURE_PAIRS:
            raise PaymentNotesERPError(
                f"Signature pair set exceeds the {self.MAX_SIGNATURE_PAIRS}-pair bound."
            )
        predicates = " OR ".join(["(CUSTNUM = %s AND INVNUM = %s)"] * len(pairs))
        parameters = tuple(value for pair in pairs for value in pair)
        try:
            rows = self.database.fetch_all(
                f"""
                SELECT
                    CUSTNUM,
                    INVNUM,
                    SIGNAME,
                    FILENAME,
                    CRTSTAMP,
                    UPLDSTAMP,
                    RRN
                FROM KMTDTA.WHSIGIMG
                WHERE {predicates}
                ORDER BY CUSTNUM, INVNUM, RRN, FILENAME
                LIMIT {self.SIGNATURE_ROW_LIMIT + 1}
                """,
                parameters,
            )
        except Exception as exc:
            raise PaymentNotesERPError(
                "The read-only WHSIGIMG evidence query failed."
            ) from exc
        complete = len(rows) <= self.SIGNATURE_ROW_LIMIT
        grouped: dict[tuple[str, str], list[SignatureEvidence]] = {}
        allowed = set(pairs)
        for row in rows[: self.SIGNATURE_ROW_LIMIT]:
            pair = (_text(row.get("CUSTNUM")), _text(row.get("INVNUM")))
            if pair not in allowed:
                continue
            grouped.setdefault(pair, []).append(
                SignatureEvidence(
                    customer_number=pair[0],
                    invoice_number=pair[1],
                    signer_name=_text(row.get("SIGNAME")),
                    filename=_text(row.get("FILENAME")),
                    created_at=_timestamp(row.get("CRTSTAMP")),
                    uploaded_at=_timestamp(row.get("UPLDSTAMP")),
                    rrn=_text(row.get("RRN")),
                )
            )
        return SignatureResult(
            evidence={key: tuple(value) for key, value in grouped.items()},
            complete=complete,
            row_limit=self.SIGNATURE_ROW_LIMIT,
            pair_count=len(pairs),
            retrieved_at=self.clock(),
        )


__all__ = [
    "ERP_CONTRACT_VERSION",
    "ExpectedPaymentResult",
    "PaymentNotesERPError",
    "PaymentNotesERPRepository",
    "SignatureResult",
]

