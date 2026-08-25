"""Pure-Python contracts for durable Lockbox preparation.

The read provider deliberately exposes query verbs only. It has no method for
approval, posting, application, correction, or another ERP write.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Literal, Mapping, Protocol, Sequence


JsonObject = dict[str, Any]


@dataclass(frozen=True)
class SourceTransaction:
    transaction_id: str
    ordinal: int
    check_amount: Decimal
    extracted_invoice_numbers: tuple[str, ...] = ()
    original_source: Mapping[str, Any] = field(default_factory=dict)
    extraction_version: str = "unknown"
    source_reference: str = ""
    source_hash: str = ""
    payment_date: date | None = None
    remittance_evidence_complete: bool = False
    projection_evidence: Mapping[str, Any] = field(default_factory=dict)
    preexisting_human_disposition: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class StartPreparationRequest:
    source_job_id: str
    source_file_hash: str
    transactions: tuple[SourceTransaction, ...]
    correlation_id: str = ""
    idempotency_key: str = ""
    job_id: str = ""
    source_reference: str = ""


@dataclass(frozen=True)
class InvoiceOwnerEvidence:
    invoice_number: str
    customer_numbers: tuple[str, ...] = ()
    source_reference: str = ""
    as_of_time: str = ""


@dataclass(frozen=True)
class CustomerResolution:
    status: Literal["resolved", "ambiguous", "not_found", "unavailable"]
    customer_number: str = ""
    customer_snapshot: Mapping[str, Any] = field(default_factory=dict)
    candidates: tuple[str, ...] = ()
    matched_on: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    source_reference: str = ""
    as_of_time: str = ""
    selection_basis: str = ""
    matching_evidence: Mapping[str, Any] = field(default_factory=dict)
    selected_confidence: float = 0.0
    confidence_basis: str = ""


@dataclass(frozen=True)
class CustomerSnapshot:
    customer_number: str
    fields: Mapping[str, Any] = field(default_factory=dict)
    source_reference: str = ""
    as_of_time: str = ""


@dataclass(frozen=True)
class CustomerGroupSnapshot:
    """Read-only TMCUST relationship context for one matched account."""

    matched_customer_number: str
    enterprise_number: str = ""
    accounts: tuple[CustomerSnapshot, ...] = ()
    source_reference: str = ""
    as_of_time: str = ""
    complete: bool = True
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class OpenInvoice:
    customer_number: str
    invoice_number: str
    open_amount: Decimal
    due_date: date | None = None
    invoice_date: date | None = None
    raw_transaction_type: str = ""
    signed_source_amount: Decimal | None = None
    aging_bucket: str = ""
    source_reference: str = ""
    invoice_count: int | None = None
    open_item_key: str = ""


@dataclass(frozen=True)
class OpenARSnapshot:
    customer_number: str
    invoices: tuple[OpenInvoice, ...]
    as_of_time: str
    source_reference: str = ""
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class EffectiveInvoice:
    customer_number: str
    invoice_number: str
    open_amount: Decimal
    effective_amount: Decimal
    due_date: date | None
    invoice_date: date | None
    raw_transaction_type: str
    business_type: Literal["Debit", "Credit"]
    negative_debit_credit: bool
    aging_bucket: str
    source_reference: str
    normalized_invoice_number: str = ""
    invoice_count: int | None = None
    open_item_key: str = ""
    allocation_kind: Literal["invoice", "service_charge"] = "invoice"


@dataclass(frozen=True)
class AllocationLine:
    customer_number: str
    invoice_number: str
    open_amount: Decimal
    apply_amount: Decimal
    due_date: date | None
    invoice_date: date | None
    raw_transaction_type: str
    business_type: Literal["Debit", "Credit"]
    negative_debit_credit: bool
    aging_bucket: str
    source_reference: str
    reason: str
    normalized_invoice_number: str = ""
    invoice_count: int | None = None
    open_item_key: str = ""
    allocation_kind: Literal["invoice", "service_charge"] = "invoice"


@dataclass(frozen=True)
class AllocationRecommendation:
    status: Literal["recommended", "review_required"]
    method: str
    allocations: tuple[AllocationLine, ...]
    check_amount: Decimal
    suggested_total: Decimal
    difference: Decimal
    reasons: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    can_auto_approve: bool = False


class ReadOnlyPreparationProvider(Protocol):
    """Adapter seam for active ERP/customer/open-AR read services."""

    def resolve_invoice_owners(
        self,
        invoice_numbers: Sequence[str],
    ) -> Mapping[str, InvoiceOwnerEvidence]:
        ...

    def resolve_current_invoice_owners(
        self,
        invoice_numbers: Sequence[str],
    ) -> Mapping[str, InvoiceOwnerEvidence]:
        ...

    def resolve_customer(
        self,
        transaction: SourceTransaction,
        invoice_owners: Mapping[str, InvoiceOwnerEvidence],
    ) -> CustomerResolution:
        ...

    def load_customer(
        self,
        customer_number: str,
    ) -> CustomerSnapshot:
        ...

    def load_customer_group(
        self,
        customer: CustomerSnapshot,
    ) -> CustomerGroupSnapshot:
        ...

    def load_open_ar(
        self,
        customer_number: str,
        as_of_date: date,
    ) -> OpenARSnapshot:
        ...


class UnconfiguredReadOnlyPreparationProvider:
    """Safe default used until Agent 4 binds the active read-only services."""

    _MESSAGE = (
        "Durable Lockbox preparation is not connected to the active read-only "
        "ERP/customer/open-AR services."
    )

    def resolve_invoice_owners(
        self,
        invoice_numbers: Sequence[str],
    ) -> Mapping[str, InvoiceOwnerEvidence]:
        raise RuntimeError(self._MESSAGE)

    def resolve_current_invoice_owners(
        self,
        invoice_numbers: Sequence[str],
    ) -> Mapping[str, InvoiceOwnerEvidence]:
        raise RuntimeError(self._MESSAGE)

    def resolve_customer(
        self,
        transaction: SourceTransaction,
        invoice_owners: Mapping[str, InvoiceOwnerEvidence],
    ) -> CustomerResolution:
        raise RuntimeError(self._MESSAGE)

    def load_customer(
        self,
        customer_number: str,
    ) -> CustomerSnapshot:
        raise RuntimeError(self._MESSAGE)

    def load_customer_group(
        self,
        customer: CustomerSnapshot,
    ) -> CustomerGroupSnapshot:
        raise RuntimeError(self._MESSAGE)

    def load_open_ar(
        self,
        customer_number: str,
        as_of_date: date,
    ) -> OpenARSnapshot:
        raise RuntimeError(self._MESSAGE)


def dataclass_payload(value: Any) -> Any:
    """Convert nested contracts to JSON-compatible values."""

    if hasattr(value, "__dataclass_fields__"):
        return dataclass_payload(asdict(value))
    if isinstance(value, Mapping):
        return {
            str(key): dataclass_payload(item)
            for key, item in value.items()
        }
    if isinstance(value, (tuple, list)):
        return [dataclass_payload(item) for item in value]
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    return value
