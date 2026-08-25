from __future__ import annotations

from decimal import Decimal
from typing import Iterable

from pydantic import BaseModel, Field

from invoice_number_rules import normalize_erp_invoice

from ..business_objects.models import OpenInvoice


class InvoiceMatchCandidate(BaseModel):
    """
    One possible invoice match for a payment.
    """

    customer_number: str
    invoice_number: str
    invoice_count: int | None = None

    open_amount: Decimal
    due_date: str | None = None
    aging_bucket: str | None = None
    days_past_due: int | None = None

    confidence_score: int = Field(
        ge=0,
        le=100,
    )

    match_type: str
    reasons: list[str] = Field(
        default_factory=list
    )


class InvoiceMatchResult(BaseModel):
    """
    Complete deterministic matching result for one payment.
    """

    customer_number: str
    payment_amount: Decimal

    supplied_invoice_numbers: list[str] = Field(
        default_factory=list
    )

    status: str
    confidence_score: int = Field(
        ge=0,
        le=100,
    )

    recommended_invoice_numbers: list[str] = Field(
        default_factory=list
    )

    candidates: list[InvoiceMatchCandidate] = Field(
        default_factory=list
    )

    reasons: list[str] = Field(
        default_factory=list
    )


class InvoiceMatcher:
    """
    Performs deterministic invoice matching.

    Current phases:
    1. Exact invoice-number matching
    2. Exact open-amount matching

    Combination matching will be handled by a separate service.
    """

    def match(
        self,
        customer_number: str,
        payment_amount: Decimal,
        open_invoices: Iterable[OpenInvoice],
        supplied_invoice_numbers: list[str] | None = None,
    ) -> InvoiceMatchResult:
        normalized_payment_amount = self._to_decimal(
            payment_amount
        )

        invoices = list(open_invoices)

        normalized_invoice_numbers = (
            self._normalize_invoice_numbers(
                supplied_invoice_numbers or []
            )
        )

        if not invoices:
            return InvoiceMatchResult(
                customer_number=customer_number,
                payment_amount=normalized_payment_amount,
                supplied_invoice_numbers=(
                    normalized_invoice_numbers
                ),
                status="no_open_invoices",
                confidence_score=0,
                reasons=[
                    (
                        "No open invoices were found for the "
                        "customer."
                    )
                ],
            )

        if normalized_invoice_numbers:
            invoice_number_result = (
                self._match_by_invoice_number(
                    customer_number=customer_number,
                    payment_amount=normalized_payment_amount,
                    invoices=invoices,
                    supplied_invoice_numbers=(
                        normalized_invoice_numbers
                    ),
                )
            )

            if invoice_number_result is not None:
                return invoice_number_result

        return self._match_by_exact_amount(
            customer_number=customer_number,
            payment_amount=normalized_payment_amount,
            invoices=invoices,
            supplied_invoice_numbers=(
                normalized_invoice_numbers
            ),
        )

    def _match_by_invoice_number(
        self,
        customer_number: str,
        payment_amount: Decimal,
        invoices: list[OpenInvoice],
        supplied_invoice_numbers: list[str],
    ) -> InvoiceMatchResult | None:
        supplied_number_set = set(
            supplied_invoice_numbers
        )

        matched_invoices = [
            invoice
            for invoice in invoices
            if self._normalize_invoice_number(
                invoice.invoice_number
            )
            in supplied_number_set
        ]

        if not matched_invoices:
            return None

        matched_total = sum(
            (
                self._to_decimal(
                    invoice.open_amount
                )
                for invoice in matched_invoices
            ),
            Decimal("0.00"),
        )

        candidates = [
            self._build_candidate(
                invoice=invoice,
                confidence_score=100,
                match_type="exact_invoice_number",
                reasons=[
                    (
                        "The invoice number was supplied on "
                        "the remittance."
                    ),
                    (
                        "The invoice belongs to the identified "
                        "customer."
                    ),
                ],
            )
            for invoice in matched_invoices
        ]

        matched_invoice_numbers = [
            str(invoice.invoice_number)
            for invoice in matched_invoices
        ]

        if matched_total == payment_amount:
            return InvoiceMatchResult(
                customer_number=customer_number,
                payment_amount=payment_amount,
                supplied_invoice_numbers=(
                    supplied_invoice_numbers
                ),
                status="exact_match",
                confidence_score=100,
                recommended_invoice_numbers=(
                    matched_invoice_numbers
                ),
                candidates=candidates,
                reasons=[
                    (
                        "The supplied invoice number or numbers "
                        "were found in TMAROP."
                    ),
                    (
                        "The combined open invoice amount exactly "
                        "matches the payment amount."
                    ),
                ],
            )

        if len(matched_invoices) == 1:
            confidence_score = 90
            status = "invoice_number_amount_mismatch"
        else:
            confidence_score = 85
            status = "invoice_numbers_amount_mismatch"

        adjusted_candidates = [
            candidate.model_copy(
                update={
                    "confidence_score": confidence_score,
                    "reasons": [
                        *candidate.reasons,
                        (
                            "The invoice amount does not exactly "
                            "match the payment amount."
                        ),
                    ],
                }
            )
            for candidate in candidates
        ]

        return InvoiceMatchResult(
            customer_number=customer_number,
            payment_amount=payment_amount,
            supplied_invoice_numbers=(
                supplied_invoice_numbers
            ),
            status=status,
            confidence_score=confidence_score,
            recommended_invoice_numbers=(
                matched_invoice_numbers
            ),
            candidates=adjusted_candidates,
            reasons=[
                (
                    "The supplied invoice number or numbers were "
                    "found for the customer."
                ),
                (
                    f"Matched open amount: {matched_total}."
                ),
                (
                    f"Payment amount: {payment_amount}."
                ),
                (
                    "Manual review is required because the "
                    "amounts differ."
                ),
            ],
        )

    def _match_by_exact_amount(
        self,
        customer_number: str,
        payment_amount: Decimal,
        invoices: list[OpenInvoice],
        supplied_invoice_numbers: list[str],
    ) -> InvoiceMatchResult:
        amount_matches = [
            invoice
            for invoice in invoices
            if self._to_decimal(
                invoice.open_amount
            )
            == payment_amount
        ]

        if len(amount_matches) == 1:
            invoice = amount_matches[0]

            candidate = self._build_candidate(
                invoice=invoice,
                confidence_score=98,
                match_type="exact_amount",
                reasons=[
                    (
                        "The invoice open amount exactly matches "
                        "the payment amount."
                    ),
                    (
                        "No other open invoice for this customer "
                        "has the same open amount."
                    ),
                ],
            )

            return InvoiceMatchResult(
                customer_number=customer_number,
                payment_amount=payment_amount,
                supplied_invoice_numbers=(
                    supplied_invoice_numbers
                ),
                status="exact_amount_match",
                confidence_score=98,
                recommended_invoice_numbers=[
                    str(invoice.invoice_number)
                ],
                candidates=[candidate],
                reasons=[
                    (
                        "One open invoice has an exact amount "
                        "match."
                    ),
                    (
                        "The result should still be reviewed when "
                        "no invoice number was supplied."
                    ),
                ],
            )

        if len(amount_matches) > 1:
            candidates = [
                self._build_candidate(
                    invoice=invoice,
                    confidence_score=65,
                    match_type="duplicate_exact_amount",
                    reasons=[
                        (
                            "The invoice open amount exactly "
                            "matches the payment amount."
                        ),
                        (
                            "Another open invoice has the same "
                            "open amount."
                        ),
                    ],
                )
                for invoice in amount_matches
            ]

            return InvoiceMatchResult(
                customer_number=customer_number,
                payment_amount=payment_amount,
                supplied_invoice_numbers=(
                    supplied_invoice_numbers
                ),
                status="ambiguous_exact_amount",
                confidence_score=65,
                candidates=candidates,
                reasons=[
                    (
                        "Multiple open invoices have the same "
                        "amount as the payment."
                    ),
                    (
                        "The engine will not automatically select "
                        "one of these invoices."
                    ),
                ],
            )

        return InvoiceMatchResult(
            customer_number=customer_number,
            payment_amount=payment_amount,
            supplied_invoice_numbers=(
                supplied_invoice_numbers
            ),
            status="no_single_invoice_match",
            confidence_score=0,
            reasons=[
                (
                    "No single open invoice exactly matches the "
                    "payment amount."
                ),
                (
                    "Combination matching should be attempted "
                    "next."
                ),
            ],
        )

    def _build_candidate(
        self,
        invoice: OpenInvoice,
        confidence_score: int,
        match_type: str,
        reasons: list[str],
    ) -> InvoiceMatchCandidate:
        due_date = getattr(
            invoice,
            "due_date",
            None,
        )

        return InvoiceMatchCandidate(
            customer_number=str(
                invoice.customer_number
            ),
            invoice_number=str(
                invoice.invoice_number
            ),
            invoice_count=getattr(
                invoice,
                "invoice_count",
                None,
            ),
            open_amount=self._to_decimal(
                invoice.open_amount
            ),
            due_date=(
                due_date.isoformat()
                if due_date is not None
                else None
            ),
            aging_bucket=getattr(
                invoice,
                "aging_bucket",
                None,
            ),
            days_past_due=getattr(
                invoice,
                "days_past_due",
                None,
            ),
            confidence_score=confidence_score,
            match_type=match_type,
            reasons=reasons,
        )

    @staticmethod
    def _normalize_invoice_numbers(
        invoice_numbers: list[str],
    ) -> list[str]:
        normalized: list[str] = []

        for invoice_number in invoice_numbers:
            cleaned = InvoiceMatcher._normalize_invoice_number(
                invoice_number
            )

            if cleaned and cleaned not in normalized:
                normalized.append(cleaned)

        return normalized

    @staticmethod
    def _normalize_invoice_number(
        invoice_number: object,
    ) -> str:
        return normalize_erp_invoice(invoice_number)

    @staticmethod
    def _to_decimal(
        value: object,
    ) -> Decimal:
        return Decimal(
            str(value or 0)
        ).quantize(
            Decimal("0.01")
        )
