from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


CONTRACT_VERSION = "general-ledger-foundation.v1"


class SourceEvidence(BaseModel):
    system: str = "MaddenCo ERP (DTA273)"
    access: Literal["read_only"] = "read_only"
    status: Literal["available"] = "available"
    retrieved_at: str


class AccountSearchResult(BaseModel):
    account_number: int
    division: int
    department: int
    description: str = ""
    short_name: str = ""
    debit_or_credit: str = ""
    account_type: str = ""
    active: bool


class AccountSearchResponse(BaseModel):
    contract_version: str = CONTRACT_VERSION
    source: SourceEvidence
    count: int
    accounts: list[AccountSearchResult]


class AccountIdentityEvidence(BaseModel):
    account_number: int
    division: int
    department: int
    company_number: int | None
    description: str = ""
    short_name: str = ""
    debit_or_credit: str = ""
    account_type: str = ""
    active: bool
    requires_customer: bool
    requires_employee: bool
    requires_job: bool
    requires_po: bool
    date_created: str | None
    date_changed: str | None
    created_by: str = ""
    changed_by: str = ""


class AccountEvidenceGap(BaseModel):
    code: Literal[
        "reconciliation_tolerance_threshold",
        "close_period_lock_authority",
        "automatic_balance_verdict",
        "unposted_je_line_retention",
    ]
    label: str
    status: Literal["unavailable"] = "unavailable"
    explanation: str


class GeneralLedgerGovernance(BaseModel):
    assessment_type: Literal["evidence_only"] = "evidence_only"
    automatic_score: bool = False
    decision_effect: Literal["none"] = "none"
    erp_write: bool = False


class AccountEvidenceResponse(BaseModel):
    contract_version: str = CONTRACT_VERSION
    generated_at: str
    source: SourceEvidence
    identity: AccountIdentityEvidence
    gaps: list[AccountEvidenceGap]
    governance: GeneralLedgerGovernance = Field(
        default_factory=GeneralLedgerGovernance
    )


class AccountPeriodBalance(BaseModel):
    year: int
    period: int
    net_balance: float


class AccountBalanceEvidence(BaseModel):
    account_number: int
    division: int
    department: int
    balances: list[AccountPeriodBalance]
    source: str = "MaddenCo GMBL"
    explanation: str = (
        "Each row is GMBL's own recorded GBAMT (G/L Net Balance) for the "
        "account/division/department/period/year. ETOP does not recompute "
        "or adjust this value."
    )


class JournalEntryHeaderReference(BaseModel):
    reference_number: int
    period: int
    year: int
    company_number: int | None
    total_debit: float
    total_credit: float
    flag: str = ""


class PostedTransaction(BaseModel):
    sequence: int
    year: int
    period: int
    amount: float
    debit_or_credit: str
    description: str = ""
    system_source: str = ""
    date_created: str | None
    date_posted: str | None
    je_created_date: str | None
    je_created_time: str = ""
    je_created_by: str = ""
    je_created_workstation: str = ""
    customer_number: int | None
    employee_number: int | None
    job_number: int | None
    po_number: int | None
    reference_number: int | None
    reconcile_reference_number: int | None
    memo_id: int | None
    matched_journal_entry: JournalEntryHeaderReference | None


class UnpostedJournalEntryLine(BaseModel):
    reference_number: int
    sequence: int
    account_number: int
    division: int
    department: int
    debit_amount: float
    credit_amount: float
    description: str = ""
    customer_number: int | None
    employee_number: int | None
    job_number: int | None
    po_number: int | None


class ReconciliationCheck(BaseModel):
    year: int
    period: int
    posted_debit_total: float
    posted_credit_total: float
    posted_net_total: float
    period_balance: float | None
    difference: float | None
    formula: str = (
        "posted_net_total = SUM(GMAD.GAAMT WHERE GACDDBCR='DB') - "
        "SUM(GMAD.GAAMT WHERE GACDDBCR='CR'); difference = "
        "posted_net_total - GMBL.GBAMT for the same account/division/"
        "department/period/year. This is a literal arithmetic comparison, "
        "not an approved reconciliation or an automatic in-balance verdict."
    )


class TransactionEvidence(BaseModel):
    account_number: int
    division: int
    department: int
    year: int
    period: int
    count: int
    transactions: list[PostedTransaction]
    reconciliation: ReconciliationCheck
    unposted_journal_entry_lines: list[UnpostedJournalEntryLine]
    unposted_explanation: str = (
        "MaddenCo purges GTJD (journal entry detail) once an entry posts to "
        "GMAD; GTJD holds only line items for a journal entry currently "
        "being entered and not yet posted for this account/division/"
        "department. It is not a historical journal entry line archive."
    )
    source: str = (
        "MaddenCo GMAD (posted detail), left joined to GTJT (actual journal "
        "entry totals) on GANBREF=GJHNBREF and matching period/year; GTJD "
        "(unposted journal entry detail) queried separately by account/"
        "division/department."
    )


class StandardJournalEntryTemplateSummary(BaseModel):
    name: str
    description: str = ""
    je_description: str = ""
    status_code: str = ""


class StandardJournalEntryTemplateResponse(BaseModel):
    contract_version: str = CONTRACT_VERSION
    source: SourceEvidence
    count: int
    templates: list[StandardJournalEntryTemplateSummary]
    explanation: str = (
        "MaddenCo GMSH standard/recurring journal entry templates. These "
        "are reference templates only, not actual postings."
    )


class StandardJournalEntryTemplateLine(BaseModel):
    sequence: int
    account_number: int
    division: int
    department: int
    debit_amount: float
    credit_amount: float
    description: str = ""
    customer_number: int | None
    employee_number: int | None
    job_number: int | None
    po_number: int | None


class StandardJournalEntryTemplateDetail(BaseModel):
    name: str
    description: str = ""
    je_description: str = ""
    status_code: str = ""
    next_sequence_number: int | None
    created_by: str = ""
    last_changed_by: str = ""
    lines: list[StandardJournalEntryTemplateLine]
    line_debit_total: float
    line_credit_total: float
    source: str = "MaddenCo GMSH / GMSD"
    explanation: str = (
        "This is a standard/recurring journal entry template (GMSH header, "
        "GMSD lines) kept for reference. It is not an actual posting and "
        "has no GMAD or GTJT evidence of its own. Debit/credit totals are "
        "the sum of this template's own GSJD lines."
    )


class GLNoteCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    author_identity: str = Field(min_length=1, max_length=200)
    note: str = Field(min_length=1, max_length=5000)
    division: int = Field(default=0, ge=0)
    department: int = Field(default=0, ge=0)
    period: int | None = Field(default=None, ge=0, le=13)
    year: int | None = Field(default=None, ge=1900, le=2999)

    @field_validator("author_identity", "note")
    @classmethod
    def require_non_whitespace(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Value must contain non-whitespace text.")
        return cleaned


class GLNoteRecord(BaseModel):
    note_id: str
    account_number: int
    division: int
    department: int
    period: int | None
    year: int | None
    account_description: str
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


class GLNoteHistoryResponse(BaseModel):
    account_number: int
    count: int
    notes: list[GLNoteRecord]
