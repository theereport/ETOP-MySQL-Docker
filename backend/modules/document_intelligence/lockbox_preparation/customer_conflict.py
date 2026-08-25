"""Deterministic customer-conflict assessment using current open AR.

Broad invoice-owner discovery can surface historical or duplicated ERP rows.
This policy does not discard those records.  It permits a customer
recommendation only when every valid remittance invoice is currently open
under one and the same candidate customer.  Missing, unavailable, or split
current-open evidence remains ambiguous and requires professional review.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from .contracts import InvoiceOwnerEvidence, OpenARSnapshot, dataclass_payload
from .policy import normalize_invoice


CUSTOMER_CONFLICT_RULE_VERSION = (
    "lockbox-current-open-ar-customer-resolution@1.1.0"
)


@dataclass(frozen=True)
class CustomerConflictAssessment:
    status: str
    customer_number: str = ""
    candidate_customer_numbers: tuple[str, ...] = ()
    remittance_invoice_numbers: tuple[str, ...] = ()
    broad_invoice_owners: Mapping[str, tuple[str, ...]] = field(
        default_factory=dict
    )
    current_open_invoice_owners: Mapping[str, tuple[str, ...]] = field(
        default_factory=dict
    )
    missing_current_open_invoices: tuple[str, ...] = ()
    unavailable_customer_numbers: tuple[str, ...] = ()
    current_open_ar_sources: Mapping[str, Mapping[str, str]] = field(
        default_factory=dict
    )
    current_open_invoice_sources: Mapping[str, Mapping[str, str]] = field(
        default_factory=dict
    )
    explanation: str = ""
    rule_version: str = CUSTOMER_CONFLICT_RULE_VERSION
    requires_human_review: bool = True
    can_auto_approve: bool = False
    erp_write_performed: bool = False

    def payload(self) -> dict[str, Any]:
        return dataclass_payload(self)


def assess_current_open_invoice_owners(
    *,
    invoice_numbers: Sequence[object],
    broad_invoice_owners: Mapping[str, InvoiceOwnerEvidence],
    current_invoice_owners: Mapping[str, InvoiceOwnerEvidence],
    read_unavailable: bool = False,
) -> CustomerConflictAssessment:
    """Assess a bounded, direct TMAROP owner read for every invoice.

    Unlike the original broad-conflict path, this applies even when broad
    discovery returned zero or one owner candidate.  It may resolve only when
    every admitted invoice is currently open under exactly one same customer.
    """

    valid_invoices = tuple(
        dict.fromkeys(
            invoice
            for value in invoice_numbers
            if (invoice := normalize_invoice(value))
        )
    )
    broad_owners = {
        invoice: tuple(
            sorted(
                {
                    str(value or "").strip().removesuffix(".0")
                    for value in broad_invoice_owners.get(
                        invoice,
                        InvoiceOwnerEvidence(invoice_number=invoice),
                    ).customer_numbers
                    if str(value or "").strip()
                }
            )
        )
        for invoice in valid_invoices
    }
    current_owners = {
        invoice: tuple(
            sorted(
                {
                    str(value or "").strip().removesuffix(".0")
                    for value in current_invoice_owners.get(
                        invoice,
                        InvoiceOwnerEvidence(invoice_number=invoice),
                    ).customer_numbers
                    if str(value or "").strip()
                }
            )
        )
        for invoice in valid_invoices
    }
    candidates = tuple(
        sorted(
            {
                customer
                for owner_map in (broad_owners, current_owners)
                for owners in owner_map.values()
                for customer in owners
            }
        )
    )
    missing = tuple(
        invoice
        for invoice, owners in current_owners.items()
        if not owners
    )
    sources = {
        invoice: {
            "source_reference": str(
                current_invoice_owners.get(
                    invoice,
                    InvoiceOwnerEvidence(invoice_number=invoice),
                ).source_reference
                or ""
            ),
            "as_of_time": str(
                current_invoice_owners.get(
                    invoice,
                    InvoiceOwnerEvidence(invoice_number=invoice),
                ).as_of_time
                or ""
            ),
        }
        for invoice in valid_invoices
    }
    base = {
        "candidate_customer_numbers": candidates,
        "remittance_invoice_numbers": valid_invoices,
        "broad_invoice_owners": broad_owners,
        "current_open_invoice_owners": current_owners,
        "missing_current_open_invoices": missing,
        "current_open_invoice_sources": sources,
    }

    if not valid_invoices:
        return CustomerConflictAssessment(
            status="not_applicable",
            explanation=(
                "No governed remittance invoice was available for a direct "
                "current-open owner lookup."
            ),
            **base,
        )
    if read_unavailable:
        return CustomerConflictAssessment(
            status="evidence_unavailable",
            explanation=(
                "The bounded TMAROP current-open owner lookup was "
                "unavailable; contact evidence cannot replace that read."
            ),
            **base,
        )
    if len(missing) == len(valid_invoices):
        return CustomerConflictAssessment(
            status="not_found",
            explanation=(
                "No admitted remittance invoice is currently open in "
                "TMAROP. Broad owner evidence remains preserved."
            ),
            **base,
        )
    if missing:
        return CustomerConflictAssessment(
            status="incomplete",
            explanation=(
                "At least one admitted remittance invoice has a current "
                "TMAROP owner while another is missing; no customer was "
                "selected."
            ),
            **base,
        )
    if any(len(owners) != 1 for owners in current_owners.values()):
        return CustomerConflictAssessment(
            status="ambiguous",
            explanation=(
                "At least one admitted remittance invoice is currently open "
                "under more than one ERP customer; no customer was selected."
            ),
            **base,
        )
    unique_current_owners = {
        owners[0] for owners in current_owners.values()
    }
    if len(unique_current_owners) != 1:
        return CustomerConflictAssessment(
            status="ambiguous",
            explanation=(
                "Current TMAROP remittance invoices belong to different ERP "
                "customers; cross-customer use requires governed review."
            ),
            **base,
        )

    customer_number = next(iter(unique_current_owners))
    return CustomerConflictAssessment(
        status="resolved",
        customer_number=customer_number,
        explanation=(
            "Every admitted remittance invoice is currently open in TMAROP "
            f"under ERP customer {customer_number}."
        ),
        **base,
    )


def invoice_owner_candidates(
    invoice_numbers: Sequence[object],
    invoice_owners: Mapping[str, InvoiceOwnerEvidence],
) -> tuple[str, ...]:
    """Return every candidate owner for the transaction's valid invoices."""

    valid_invoices = tuple(
        dict.fromkeys(
            invoice
            for value in invoice_numbers
            if (invoice := normalize_invoice(value))
        )
    )
    return tuple(
        sorted(
            {
                str(customer_number or "").strip().removesuffix(".0")
                for invoice in valid_invoices
                for customer_number in invoice_owners.get(
                    invoice,
                    InvoiceOwnerEvidence(invoice_number=invoice),
                ).customer_numbers
                if str(customer_number or "").strip()
            }
        )
    )


def assess_current_open_ar_ownership(
    *,
    invoice_numbers: Sequence[object],
    invoice_owners: Mapping[str, InvoiceOwnerEvidence],
    open_ar_by_customer: Mapping[str, OpenARSnapshot],
    unavailable_customer_numbers: Sequence[str] = (),
) -> CustomerConflictAssessment:
    """Assess whether current open AR removes a broad-owner conflict.

    This deliberately requires complete evidence: every valid remittance
    invoice must be found as currently open under exactly one candidate, and
    that customer must be identical for every invoice.
    """

    valid_invoices = tuple(
        dict.fromkeys(
            invoice
            for value in invoice_numbers
            if (invoice := normalize_invoice(value))
        )
    )
    broad_owners = {
        invoice: tuple(
            sorted(
                {
                    str(value or "").strip().removesuffix(".0")
                    for value in invoice_owners.get(
                        invoice,
                        InvoiceOwnerEvidence(invoice_number=invoice),
                    ).customer_numbers
                    if str(value or "").strip()
                }
            )
        )
        for invoice in valid_invoices
    }
    candidates = tuple(
        sorted(
            {
                customer
                for owners in broad_owners.values()
                for customer in owners
            }
        )
    )
    unavailable = tuple(
        sorted(
            {
                str(value or "").strip().removesuffix(".0")
                for value in unavailable_customer_numbers
                if str(value or "").strip()
            }
        )
    )
    current_owners: dict[str, tuple[str, ...]] = {}
    for invoice in valid_invoices:
        owners: set[str] = set()
        for customer_number, snapshot in open_ar_by_customer.items():
            normalized_customer = str(
                customer_number or ""
            ).strip().removesuffix(".0")
            if not normalized_customer:
                continue
            if any(
                normalize_invoice(row.invoice_number) == invoice
                for row in snapshot.invoices
            ):
                owners.add(normalized_customer)
        current_owners[invoice] = tuple(sorted(owners))

    missing = tuple(
        invoice
        for invoice, owners in current_owners.items()
        if not owners
    )
    source_evidence = {
        str(customer_number): {
            "source_reference": str(snapshot.source_reference or ""),
            "as_of_time": str(snapshot.as_of_time or ""),
        }
        for customer_number, snapshot in sorted(open_ar_by_customer.items())
    }

    base = {
        "candidate_customer_numbers": candidates,
        "remittance_invoice_numbers": valid_invoices,
        "broad_invoice_owners": broad_owners,
        "current_open_invoice_owners": current_owners,
        "missing_current_open_invoices": missing,
        "unavailable_customer_numbers": unavailable,
        "current_open_ar_sources": source_evidence,
    }

    if len(candidates) < 2:
        return CustomerConflictAssessment(
            status="not_applicable",
            explanation=(
                "Current-open conflict resolution was not applied because "
                "the valid invoice evidence did not contain multiple ERP "
                "owner candidates."
            ),
            **base,
        )

    if unavailable:
        return CustomerConflictAssessment(
            status="evidence_unavailable",
            explanation=(
                "Current open AR could not be read for every ERP owner "
                "candidate; no customer was selected."
            ),
            **base,
        )

    if not valid_invoices or missing:
        return CustomerConflictAssessment(
            status="incomplete",
            explanation=(
                "Every valid remittance invoice must be found in current "
                "open AR before broad ERP owner conflicts can be narrowed; "
                "no customer was selected."
            ),
            **base,
        )

    if any(len(owners) != 1 for owners in current_owners.values()):
        return CustomerConflictAssessment(
            status="ambiguous",
            explanation=(
                "At least one remittance invoice remains currently open "
                "under multiple ERP customer candidates; no customer was "
                "selected."
            ),
            **base,
        )

    unique_current_owners = {
        owners[0]
        for owners in current_owners.values()
    }
    if len(unique_current_owners) != 1:
        return CustomerConflictAssessment(
            status="ambiguous",
            explanation=(
                "Current open remittance invoices belong to different ERP "
                "customers; no customer was selected."
            ),
            **base,
        )

    customer_number = next(iter(unique_current_owners))
    return CustomerConflictAssessment(
        status="resolved",
        customer_number=customer_number,
        explanation=(
            "Every valid remittance invoice is currently open under ERP "
            f"customer {customer_number}. Broader invoice-owner candidates "
            "remain preserved as historical/conflicting evidence."
        ),
        **base,
    )
