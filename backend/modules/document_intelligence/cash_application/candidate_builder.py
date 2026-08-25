from __future__ import annotations

from decimal import Decimal

from .models import InvoiceCandidateSet, PaymentIntent
from ..business_objects.models import OpenInvoice


class InvoiceCandidateBuilder:
    BUCKET_ALIASES = {
        "FUTURE DUE": {"FUTURE", "FUTURE DUE", "FUT"},
        "CURRENT DUE": {"CURRENT", "CURRENT DUE", "CUR"},
        "PAST DUE 30": {"30", "30 DAY", "PAST DUE 30"},
        "PAST DUE 60": {"60", "60 DAY", "PAST DUE 60"},
        "PAST DUE 90": {"90", "90 DAY", "PAST DUE 90"},
        "PAST DUE 120": {"120", "120+", "PAST DUE 120"},
    }

    def build(
        self,
        customer_number: str,
        invoices: list[OpenInvoice],
        intent: PaymentIntent,
        max_candidates: int = 40,
    ) -> InvoiceCandidateSet:
        active = [
            invoice
            for invoice in invoices
            if invoice.open_amount > Decimal("0.00")
        ]

        active.sort(
            key=lambda invoice: (
                invoice.due_date or invoice.invoice_date,
                invoice.invoice_number,
            )
        )

        if intent.intent_type == "full_balance":
            selected = active
        elif intent.intent_type == "aging_bucket_combination":
            allowed = self._expand_bucket_names(intent.matched_bucket_names)
            selected = [
                invoice
                for invoice in active
                if self._normalize_bucket(invoice.aging_bucket) in allowed
            ]
        else:
            selected = active[:max_candidates]

        total = sum(
            (invoice.open_amount for invoice in selected),
            Decimal("0.00"),
        )

        warnings: list[str] = []
        if not selected:
            warnings.append(
                "No open invoices matched the payment intent and aging-bucket filter."
            )

        return InvoiceCandidateSet(
            customer_number=customer_number,
            intent_type=intent.intent_type,
            invoices=selected,
            excluded_invoice_count=max(len(active) - len(selected), 0),
            total_candidate_amount=total,
            warnings=warnings,
        )

    def _expand_bucket_names(self, bucket_names: list[str]) -> set[str]:
        expanded: set[str] = set()
        for bucket_name in bucket_names:
            normalized = self._normalize_bucket(bucket_name)
            expanded.add(normalized)
            for canonical, aliases in self.BUCKET_ALIASES.items():
                normalized_aliases = {
                    self._normalize_bucket(alias) for alias in aliases
                }
                if normalized == self._normalize_bucket(canonical):
                    expanded.update(normalized_aliases)
        return expanded

    @staticmethod
    def _normalize_bucket(value: str | None) -> str:
        return " ".join((value or "").upper().strip().split())
