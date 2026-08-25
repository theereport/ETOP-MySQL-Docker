from __future__ import annotations

from datetime import date
from decimal import Decimal

from .data_provider import CashApplicationDataProvider
from .models import (
    CashApplicationDataBundle,
    CustomerResolutionMatch,
    LockboxCustomerIdentity,
)
from ..business_objects.models import CustomerAgingSnapshot


class ExistingCashApplicationProvider(CashApplicationDataProvider):
    """
    Run-ready adapter for ETOP's existing ReceivablesRepository.

    Current behavior:
    - Uses the customer number already present on the lockbox transaction.
    - Loads open invoices through ReceivablesRepository.
    - Builds the customer aging snapshot directly from those invoices.

    Name/address-only customer matching can be added later without changing
    the cash-application endpoint.
    """

    def __init__(self, receivables_repository):
        self.receivables_repository = receivables_repository

    def resolve_customer(
        self,
        identity: LockboxCustomerIdentity,
    ) -> CustomerResolutionMatch | None:
        customer_number = (identity.customer_number or "").strip()

        if not customer_number:
            return None

        return CustomerResolutionMatch(
            customer_number=customer_number,
            customer_name=(identity.customer_name or "").strip(),
            confidence=1.0,
            matched_on=["customer number supplied by lockbox transaction"],
        )

    def load_customer_data(
        self,
        customer_number: str,
    ) -> CashApplicationDataBundle:
        aging_as_of_date = date.today()

        invoices = self.receivables_repository.get_open_invoices(
            customer_number=customer_number,
            aging_as_of_date=aging_as_of_date,
        )

        aging = self._build_aging_snapshot(
            customer_number=customer_number,
            invoices=invoices,
        )

        return CashApplicationDataBundle(
            customer_number=customer_number,
            aging=aging,
            invoices=invoices,
        )

    @staticmethod
    def _build_aging_snapshot(
        customer_number: str,
        invoices: list,
    ) -> CustomerAgingSnapshot:
        totals = {
            "future_due": Decimal("0.00"),
            "current_due": Decimal("0.00"),
            "past_due_30": Decimal("0.00"),
            "past_due_60": Decimal("0.00"),
            "past_due_90": Decimal("0.00"),
            "past_due_120": Decimal("0.00"),
        }

        for invoice in invoices:
            amount = Decimal(str(invoice.open_amount or 0))
            bucket = " ".join(
                str(invoice.aging_bucket or "").upper().split()
            )

            if bucket in {"FUTURE", "FUTURE DUE"}:
                totals["future_due"] += amount
            elif bucket in {"CURRENT", "CURRENT DUE"}:
                totals["current_due"] += amount
            elif "120" in bucket:
                totals["past_due_120"] += amount
            elif "90" in bucket:
                totals["past_due_90"] += amount
            elif "60" in bucket:
                totals["past_due_60"] += amount
            elif "30" in bucket:
                totals["past_due_30"] += amount
            else:
                days_past_due = invoice.days_past_due
                if days_past_due is None or days_past_due <= 0:
                    totals["current_due"] += amount
                elif days_past_due <= 30:
                    totals["past_due_30"] += amount
                elif days_past_due <= 60:
                    totals["past_due_60"] += amount
                elif days_past_due <= 90:
                    totals["past_due_90"] += amount
                else:
                    totals["past_due_120"] += amount

        total_balance_due = sum(
            totals.values(),
            Decimal("0.00"),
        )

        return CustomerAgingSnapshot(
            customer_number=customer_number,
            future_due=totals["future_due"],
            current_due=totals["current_due"],
            past_due_30=totals["past_due_30"],
            past_due_60=totals["past_due_60"],
            past_due_90=totals["past_due_90"],
            past_due_120=totals["past_due_120"],
            total_balance_due=total_balance_due,
        )
