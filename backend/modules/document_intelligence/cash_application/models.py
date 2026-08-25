from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from ..business_objects.models import (
    AgingMatchResult,
    AllocationResolutionResult,
    CustomerAgingSnapshot,
    OpenInvoice,
)


class PaymentIntent(BaseModel):
    intent_type: Literal[
        "full_balance",
        "aging_bucket_combination",
        "oldest_first",
        "explicit_invoice",
        "historical_pattern",
        "unknown",
    ]
    confidence: float = 0.0
    matched_bucket_names: list[str] = Field(default_factory=list)
    explanation: list[str] = Field(default_factory=list)


class InvoiceCandidateSet(BaseModel):
    customer_number: str
    intent_type: str
    invoices: list[OpenInvoice] = Field(default_factory=list)
    excluded_invoice_count: int = 0
    total_candidate_amount: Decimal = Decimal("0.00")
    warnings: list[str] = Field(default_factory=list)


class HistoricalPaymentPattern(BaseModel):
    customer_number: str
    pattern_type: str
    pattern_key: str
    observation_count: int
    success_count: int
    confidence: float
    last_observed_at: str


class CashApplicationDecision(BaseModel):
    status: Literal["recommended", "review_required", "not_found"]
    customer_number: str
    check_amount: Decimal
    payment_intent: PaymentIntent
    aging_match: AgingMatchResult | None = None
    candidate_set: InvoiceCandidateSet | None = None
    allocation_result: AllocationResolutionResult | None = None
    historical_pattern: HistoricalPaymentPattern | None = None
    overall_confidence: float = 0.0
    decision_reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ConfirmApplicationRequest(BaseModel):
    customer_number: str
    check_amount: Decimal
    intent_type: str
    pattern_key: str
    was_successful: bool = True


class LockboxCustomerIdentity(BaseModel):
    customer_number: str = ""
    customer_name: str = ""
    customer_phone: str = ""
    customer_address_line_1: str = ""
    customer_address_line_2: str = ""
    customer_city: str = ""
    customer_state: str = ""
    customer_postal_code: str = ""
    aba_routing: str = ""
    account_number: str = ""


class CustomerResolutionMatch(BaseModel):
    customer_number: str
    customer_name: str = ""
    confidence: float = 0.0
    matched_on: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class CashApplicationDataBundle(BaseModel):
    customer_number: str
    aging: CustomerAgingSnapshot
    invoices: list[OpenInvoice] = Field(default_factory=list)


class LockboxRecommendationRequest(BaseModel):
    transaction_id: str
    check_amount: Decimal
    identity: LockboxCustomerIdentity
    extracted_invoice_numbers: list[str] = Field(default_factory=list)


class SuggestedAllocation(BaseModel):
    invoice_number: str
    open_amount: Decimal
    suggested_apply_amount: Decimal
    invoice_date: str | None = None
    due_date: str | None = None
    aging_bucket: str | None = None
    confidence: float = 0.0
    reason: str = ""


class LockboxRecommendationResponse(BaseModel):
    status: Literal[
        "recommended",
        "review_required",
        "customer_not_found",
        "no_invoice_match",
    ]
    transaction_id: str
    customer_match: CustomerResolutionMatch | None = None
    decision: CashApplicationDecision | None = None
    suggested_allocations: list[SuggestedAllocation] = Field(default_factory=list)
    check_amount: Decimal
    suggested_total: Decimal = Decimal("0.00")
    difference: Decimal = Decimal("0.00")
    can_auto_approve: bool = False
    decision_reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
