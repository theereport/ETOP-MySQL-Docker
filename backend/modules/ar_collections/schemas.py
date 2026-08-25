from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


CONTRACT_VERSION = "ar-collections-foundation.v1"


class SourceEvidence(BaseModel):
    system: str = "MaddenCo ERP (DTA273)"
    access: Literal["read_only"] = "read_only"
    status: Literal["available"] = "available"
    retrieved_at: str


class CustomerIdentityEvidence(BaseModel):
    customer_number: int
    customer_name: str
    dba_name: str = ""
    address_lines: list[str] = Field(default_factory=list)
    zip_code: str = ""
    country: str = ""
    phone: str = ""
    email: str = ""
    route_code: str = ""
    store_number: int | None = None
    salesman_number: int | None = None
    customer_type: str = ""
    customer_class: str = ""
    active: bool
    source: str = "MaddenCo TMCUST through shared Customer 360"


class OpenARItem(BaseModel):
    invoice_number: int
    transaction_type: str
    entry_type: str
    debit_credit: str
    original_amount: float
    open_amount: float
    discountable_amount: float
    cash_discount: float
    terms_code: str
    adjustment_reason: str
    reference_number: str
    transaction_date: str | None
    due_date: str | None
    days_past_due: int | None
    purged_to_history: bool


class OpenAREvidence(BaseModel):
    item_count: int
    total_open_amount: float
    open_items: list[OpenARItem]
    source: str = "MaddenCo TMAROP"
    explanation: str = (
        "Each row is one MaddenCo TMAROP open A/R item for this customer. "
        "total_open_amount is the arithmetic sum of TAROAMTOPN across the "
        "returned rows. days_past_due is today's date minus TARODTEDUE, in "
        "days; a positive value means the item is past due, a negative "
        "value means it is not yet due. It is not a collections priority "
        "score."
    )


class AROpenItemHistoryEvidence(BaseModel):
    item_count: int
    items: list[OpenARItem]
    source: str = "MaddenCo TMAROP (TAROHISTYN='Y')"
    explanation: str = (
        "MaddenCo does not purge TMAROP once an item closes — it retains "
        "the row and sets TAROHISTYN='Y'. These are this customer's closed "
        "(fully paid or applied) items, most recent first: the same "
        "columns as open_ar, filtered to history instead of currently "
        "open. This is the customer's real AR item history; the "
        "'transactions' section below (TTNARH/TTNARD) is a separate, "
        "narrower adjustment sub-ledger that is commonly sparse or empty."
    )


class ARTransaction(BaseModel):
    sequence: int
    invoice_number: int
    transaction_date: str | None
    due_date: str | None
    original_amount: float
    debit_credit: str
    entry_type: str
    transaction_type: str
    reference_number: str
    status: str
    period: int | None
    year: int | None
    cash_discount: float


class ARTransactionApplication(BaseModel):
    header_sequence: int
    detail_sequence: int
    header_invoice_number: int
    header_reference_number: str
    header_transaction_date: str | None
    applied_invoice_number: int
    amount_applied: float
    discount_applied: float
    gl_account: int | None
    gl_division: int | None
    gl_department: int | None
    created_date: str | None


class ARTransactionHistoryEvidence(BaseModel):
    transaction_count: int
    application_count: int
    transactions: list[ARTransaction]
    applications: list[ARTransactionApplication]
    source: str = "MaddenCo TTNARH (header) / TTNARD (application detail)"
    explanation: str = (
        "Transactions are MaddenCo TTNARH rows for this customer. "
        "Applications are MaddenCo TTNARD rows joined to TTNARH on the "
        "shared TNARSEQ transaction sequence, showing which invoice(s) each "
        "payment or credit was applied against. Verified against live "
        "data: TTNARH/TTNARD are scoped to a narrow adjustment workflow "
        "(TNARTYPTRN) and are commonly sparse or entirely empty — they are "
        "not this customer's primary transaction ledger. See "
        "item_history above for the customer's real closed-item history, "
        "which TMAROP retains directly. This is not a cash-application "
        "recommendation."
    )


class GLDistributionLine(BaseModel):
    gl_account: int | None
    gl_division: int | None
    gl_department: int | None
    debit_amount: float
    credit_amount: float
    quantity: float
    description: str
    created_date: str | None


class GLDistributionEvidence(BaseModel):
    line_count: int
    total_debit_amount: float
    total_credit_amount: float
    lines: list[GLDistributionLine]
    source: str = "MaddenCo TTNGL"
    explanation: str = (
        "Each row is one MaddenCo TTNGL GL distribution line recorded "
        "against this customer (TNGLNBCST). total_debit_amount and "
        "total_credit_amount are arithmetic sums of TNGLAMTDB and "
        "TNGLAMTCR across the returned rows. This is read-only GL "
        "reference evidence; ETOP performs no GL posting."
    )


class ERPCollectionNote(BaseModel):
    note_text: str
    created_at: str | None
    created_by: str
    changed_at: str | None
    changed_by: str


class ERPCollectionNotesEvidence(BaseModel):
    count: int
    notes: list[ERPCollectionNote]
    source: str = "MaddenCo CCROLNOTE"
    explanation: str = (
        "These are MaddenCo's own existing collection notes, entered "
        "directly in the ERP. ETOP surfaces them read-only; they are "
        "separate from the append-only collections note below."
    )


class ERPCreditManagementNote(BaseModel):
    header_key: int
    regarding: str
    date_to_do: str | None
    date_done: str | None
    created_at: str | None
    created_by: str
    changed_at: str | None
    changed_by: str
    detail_lines: list[str]


class ERPCreditManagementNotesEvidence(BaseModel):
    count: int
    notes: list[ERPCreditManagementNote]
    source: str = "MaddenCo TMCRMH (header) / TMCRMD (detail)"
    explanation: str = (
        "These are MaddenCo's own existing credit-management notes. "
        "detail_lines are TMCRMD rows for the header, ordered by "
        "TCMODNBSEQ. ETOP surfaces them read-only."
    )


class AgingSnapshot(BaseModel):
    snapshot_date: str | None
    aging_future: float
    aging_current: float
    aging_30: float
    aging_60: float
    aging_90: float
    aging_120: float
    balance: float
    balance_high: float
    discount_month_to_date: float
    credit_limit: float
    date_last_paid: str | None
    date_last_statement: str | None
    amount_last_paid: float
    salesman_number: int | None
    sales_month_to_date: float


class AgingHistoryEvidence(BaseModel):
    snapshot_count: int
    snapshots: list[AgingSnapshot]
    source: str = "MaddenCo TMCCH"
    explanation: str = (
        "Each row is one MaddenCo TMCCH periodic aging/credit snapshot for "
        "this customer, most recent first. TMCCH is a periodic snapshot "
        "table, not a real-time balance; compare it against the open-A/R "
        "list above for current standing."
    )


class ARCollectionsEvidenceGap(BaseModel):
    code: Literal[
        "collections_priority_ranking",
        "dunning_cadence_policy",
        "erp_disposition_write_back",
    ]
    label: str
    status: Literal["unavailable"] = "unavailable"
    explanation: str


class ARCollectionsGovernance(BaseModel):
    assessment_type: Literal["evidence_only"] = "evidence_only"
    automatic_score: bool = False
    decision_effect: Literal["none"] = "none"
    erp_write: bool = False


class CustomerARCollectionsResponse(BaseModel):
    contract_version: str = CONTRACT_VERSION
    generated_at: str
    source: SourceEvidence
    customer: CustomerIdentityEvidence
    open_ar: OpenAREvidence
    item_history: AROpenItemHistoryEvidence
    transactions: ARTransactionHistoryEvidence
    gl_distributions: GLDistributionEvidence
    erp_collection_notes: ERPCollectionNotesEvidence
    erp_credit_management_notes: ERPCreditManagementNotesEvidence
    aging_history: AgingHistoryEvidence
    gaps: list[ARCollectionsEvidenceGap]
    governance: ARCollectionsGovernance = Field(
        default_factory=ARCollectionsGovernance
    )


class ARCollectionsNoteCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    author_identity: str = Field(min_length=1, max_length=200)
    note: str = Field(min_length=1, max_length=5000)

    @field_validator("author_identity", "note")
    @classmethod
    def require_non_whitespace(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Value must contain non-whitespace text.")
        return cleaned


class ARCollectionsNoteRecord(BaseModel):
    note_id: str
    customer_number: int
    customer_name: str
    author_identity: str
    note: str
    created_at: str
    source_as_of: str
    actor_identity_source: Literal["operator_supplied"] = "operator_supplied"
    actor_authority_status: Literal[
        "not_independently_verified"
    ] = "not_independently_verified"
    note_classification: Literal[
        "professional_workflow_metadata"
    ] = "professional_workflow_metadata"
    decision_effect: Literal["none"] = "none"
    erp_write: Literal[False] = False
    evidence_snapshot: dict[str, Any]
    evidence_snapshot_sha256: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )


class ARCollectionsNoteHistoryResponse(BaseModel):
    customer_number: int
    count: int
    notes: list[ARCollectionsNoteRecord]
