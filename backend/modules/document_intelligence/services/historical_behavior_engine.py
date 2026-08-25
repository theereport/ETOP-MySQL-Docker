from __future__ import annotations

from pydantic import BaseModel, Field

from ..integrations.history_repository import HistoricalPaymentGroup


class HistoricalBehaviorProfile(BaseModel):
    customer_number: str
    sample_size: int
    confidence_level: str

    multiple_payment_ratio: float | None = None
    average_invoice_group_size: float | None = None
    commonly_combines_invoices: bool | None = None

    single_invoice_group_count: int = 0
    multi_invoice_group_count: int = 0
    largest_invoice_group_size: int | None = None

    notes: list[str] = Field(default_factory=list)


class HistoricalBehaviorEngine:
    """
    Converts verified TMAROP payment groupings into conservative
    customer-payment behavior signals.
    """

    def analyze(
        self,
        customer_number: str,
        payment_groups: list[HistoricalPaymentGroup],
    ) -> HistoricalBehaviorProfile:

        valid_groups = [
            group
            for group in payment_groups
            if group.invoice_count > 0
            and group.payment_reference.strip() not in ("", "0")
        ]

        sample_size = len(valid_groups)

        if sample_size == 0:
            return HistoricalBehaviorProfile(
                customer_number=customer_number,
                sample_size=0,
                confidence_level="none",
                notes=[
                    "No usable fully paid TMAROP payment groups were returned."
                ],
            )

        group_sizes = [
            group.invoice_count
            for group in valid_groups
        ]

        single_invoice_group_count = sum(
            group_size == 1
            for group_size in group_sizes
        )

        multi_invoice_group_count = sum(
            group_size > 1
            for group_size in group_sizes
        )

        multiple_payment_ratio = round(
            multi_invoice_group_count / sample_size,
            4,
        )

        average_invoice_group_size = round(
            sum(group_sizes) / sample_size,
            2,
        )

        largest_invoice_group_size = max(group_sizes)

        commonly_combines_invoices = (
            multiple_payment_ratio >= 0.50
        )

        confidence_level = (
            "high"
            if sample_size >= 30
            else "medium"
            if sample_size >= 10
            else "low"
        )

        notes = [
            (
                "Behavior is based on fully paid TMAROP invoices grouped "
                "by matching TAROGLREF values."
            ),
            (
                "Single-invoice and multi-invoice groups are both included "
                "when calculating the multi-invoice payment ratio."
            ),
            (
                "Historical behavior adjusts recommendation confidence only "
                "and never overrides an ambiguous deterministic match."
            ),
            (
                "Oldest-first versus newest-first behavior is not inferred "
                "from TAROGLREF grouping alone."
            ),
        ]

        if commonly_combines_invoices:
            notes.append(
                "At least half of the sampled historical payment groups "
                "contained more than one invoice."
            )
        else:
            notes.append(
                "Fewer than half of the sampled historical payment groups "
                "contained more than one invoice."
            )

        return HistoricalBehaviorProfile(
            customer_number=customer_number,
            sample_size=sample_size,
            confidence_level=confidence_level,
            multiple_payment_ratio=multiple_payment_ratio,
            average_invoice_group_size=average_invoice_group_size,
            commonly_combines_invoices=commonly_combines_invoices,
            single_invoice_group_count=single_invoice_group_count,
            multi_invoice_group_count=multi_invoice_group_count,
            largest_invoice_group_size=largest_invoice_group_size,
            notes=notes,
        )