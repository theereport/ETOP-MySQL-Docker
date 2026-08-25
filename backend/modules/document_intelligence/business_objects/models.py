from __future__ import annotations
from datetime import date
from decimal import Decimal
from typing import Any, Literal
from pydantic import BaseModel, Field

class OcrPageResult(BaseModel):
    page_number: int
    text: str = ""
    confidence: float = 0.0
    engine: str
    image_path: str | None = None
    warnings: list[str] = Field(default_factory=list)

class PayerIdentity(BaseModel):
    payer_name: str | None = None
    address_line_1: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    printed_customer_number: str | None = None
    routing_number: str | None = None
    bank_account_last4: str | None = None
    check_number: str | None = None
    memo_text: str | None = None
    source_pages: list[int] = Field(default_factory=list)

class CustomerCandidate(BaseModel):
    customer_number: str
    customer_name: str
    address_line_1: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    score: float
    match_reasons: list[str] = Field(default_factory=list)

class CustomerResolutionResult(BaseModel):
    status: Literal["matched","review_required","not_found"]
    selected_customer: CustomerCandidate | None = None
    candidates: list[CustomerCandidate] = Field(default_factory=list)
    confidence: float = 0.0
    warnings: list[str] = Field(default_factory=list)

class OpenInvoice(BaseModel):
    customer_number: str
    invoice_number: str
    invoice_count: int | None = None

    invoice_date: date | None = None
    due_date: date | None = None

    original_amount: Decimal = Decimal("0.00")
    open_amount: Decimal = Decimal("0.00")
    open_memo_amount: Decimal = Decimal("0.00")
    discountable_amount: Decimal = Decimal("0.00")
    cash_discount: Decimal = Decimal("0.00")

    debit_credit: str = ""
    transaction_type: str = ""
    selling_store: str | None = None
    reference_number: str = ""
    adjustment_reason: str = ""

    days_past_due: int | None = None
    aging_bucket: str | None = None

class AllocationProposal(BaseModel):
    invoice_number: str
    proposed_amount: Decimal
    open_amount: Decimal
    aging_bucket: str | None = None

class AllocationResolutionResult(BaseModel):
    status: Literal["exact","review_required","not_found"]
    method: str
    check_amount: Decimal
    matched_total: Decimal = Decimal("0.00")
    difference: Decimal = Decimal("0.00")
    confidence: float = 0.0
    proposals: list[AllocationProposal] = Field(default_factory=list)
    alternate_matches: int = 0
    warnings: list[str] = Field(default_factory=list)

class CustomerAgingSnapshot(BaseModel):
    customer_number: str
    future_due: Decimal = Decimal("0.00")
    current_due: Decimal = Decimal("0.00")
    past_due_30: Decimal = Decimal("0.00")
    past_due_60: Decimal = Decimal("0.00")
    past_due_90: Decimal = Decimal("0.00")
    past_due_120: Decimal = Decimal("0.00")
    total_balance_due: Decimal = Decimal("0.00")
    last_payment_date: str | None = None
    last_payment_amount: Decimal = Decimal("0.00")


class AgingBucketMatch(BaseModel):
    bucket_name: str
    amount: Decimal


class AgingMatchResult(BaseModel):
    status: Literal["exact", "review_required", "not_found"]
    method: str
    check_amount: Decimal
    matched_total: Decimal = Decimal("0.00")
    difference: Decimal = Decimal("0.00")
    matched_buckets: list[AgingBucketMatch] = Field(default_factory=list)
    alternate_matches: int = 0
    confidence: float = 0.0
    warnings: list[str] = Field(default_factory=list)