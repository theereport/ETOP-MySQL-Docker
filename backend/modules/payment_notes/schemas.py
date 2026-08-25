"""Public API contracts for the R73 Payment Notes workspace."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Governance(StrictModel):
    module_id: Literal["payment_notes"] = "payment_notes"
    authority_boundary: Literal["evidence_and_recommendation_only"] = (
        "evidence_and_recommendation_only"
    )
    erp_access: Literal["read_only"] = "read_only"
    erp_writes: Literal[False] = False
    balancing_item_type: Literal["Virtual Credit"] = "Virtual Credit"
    match_rule_version: str
    invoice_extraction_rule_version: str
    remote_capture_parser_version: str
    route_reference_parser_version: str
    erp_contract_version: str
    erp_snapshot_mode: Literal["independent_bounded_read_only_queries"]
    cross_run_reuse_policy: Literal["unresolved_fail_closed"]


class RouteReferenceSummary(StrictModel):
    reference_id: str
    version_label: str
    source_name: str
    source_sha256: str
    source_size: int
    parser_version: str
    mapping_count: int
    input_row_count: int
    blank_row_count: int
    duplicate_mapping_count: int
    conflict_count: int
    warnings: list[str]
    created_by: str
    created_at: str
    is_active: bool = False
    activated_at: str | None = None


class RouteReferenceList(StrictModel):
    items: list[RouteReferenceSummary]
    total: int


class RouteReferenceStatus(StrictModel):
    configured: bool
    active_reference: RouteReferenceSummary | None
    run_creation_allowed: bool
    message: str


class RouteActivationRequest(StrictModel):
    idempotency_key: str = Field(min_length=8, max_length=160)


class SignatureEvidenceModel(StrictModel):
    customer_number: str
    invoice_number: str
    signer_name: str
    filename: str
    created_at: str
    uploaded_at: str
    rrn: str
    evidence_status: str


class MatchCandidateModel(StrictModel):
    payment_id: str
    customer_number: str
    route: str
    payment_type: str
    raw_check_number: str
    normalized_check_number: str
    amount: str
    authorization_number: str
    notes: str
    raw_invoices: str
    invoice_numbers: list[str]
    invoice_reference_status: str
    received: str
    received_at: str
    created_at: str
    matched_factors: list[str]
    conflicting_factors: list[str]
    candidate_tier: str
    signature_lookup_status: str
    signatures: list[SignatureEvidenceModel]


class CrossRunReuseEvidenceModel(StrictModel):
    payment_id: str
    prior_run_ids: list[str]
    prior_item_ids: list[str]
    source_types: list[str]


class MatchDecisionModel(StrictModel):
    disposition: str
    tier: str
    selected_payment_id: str | None
    candidates: list[MatchCandidateModel]
    warnings: list[str]
    rule_version: str
    source_complete: bool
    candidate_total_count: int
    candidate_display_cap: int
    candidate_population_complete: bool
    cross_run_reuse_evidence: list[CrossRunReuseEvidenceModel]


class ExpectedPaymentQueryProvenance(StrictModel):
    source_object: Literal["KMTDTA.WHSIGPAY"]
    store_number: str
    routes: list[str]
    date_from: str
    date_to: str
    retrieved_at: str
    row_limit: int
    returned_count: int
    complete: bool
    canonical_evidence_sha256: str
    error: str | None = None


class SignatureQueryProvenance(StrictModel):
    source_object: Literal["KMTDTA.WHSIGIMG"]
    retrieved_at: str
    row_limit: int
    pair_count: int
    returned_count: int
    complete: bool
    canonical_evidence_sha256: str
    error: str | None = None


class ERPProvenance(StrictModel):
    contract_version: str
    snapshot_mode: Literal["independent_bounded_read_only_queries"]
    expected_payment_queries: list[ExpectedPaymentQueryProvenance]
    signature_queries: list[SignatureQueryProvenance]
    expected_payment_query_count: int
    signature_query_count: int
    complete: bool


class BankItemModel(StrictModel):
    item_id: str
    source_row_number: int
    source_record_sha256: str
    deposit_key: str
    location_key: str
    store_number: str
    location_name: str
    account_name: str
    create_business_date: str
    deposit_number: str
    item_type: str
    amount: str
    raw_amount: str
    raw_check_number: str
    normalized_check_number: str
    warnings: list[str]
    route_resolution: dict[str, Any]
    match: MatchDecisionModel
    current_review: dict[str, Any] | None = None


class DepositModel(StrictModel):
    deposit_key: str
    location_key: str
    store_number: str
    location_name: str
    account_name: str
    create_business_date: str
    deposit_number: str
    physical_item_count: int
    balancing_item_count: int
    quarantined_row_count: int
    physical_total: str
    balancing_total: str
    difference: str
    status: str
    counts_final: bool
    warnings: list[str]


class QuarantinedRowModel(StrictModel):
    source_row_number: int
    source_record_sha256: str
    reason_codes: list[str]
    provisional_deposit_key: str
    provisional_item_type: str
    provisional_amount: str | None
    provisional_is_physical: bool


class RunSummary(StrictModel):
    run_id: str
    source_name: str
    source_sha256: str
    source_size: int
    route_reference_id: str
    date_from: str
    date_to: str
    status: str
    deposit_count: int
    physical_item_count: int
    quarantined_row_count: int
    created_by: str
    created_at: str


class RunList(StrictModel):
    items: list[RunSummary]
    total: int


class RunDetail(StrictModel):
    run_id: str
    status: str
    source: dict[str, Any]
    route_reference: dict[str, Any]
    date_from: str
    date_to: str
    erp_provenance: ERPProvenance
    deposits: list[DepositModel]
    items: list[BankItemModel]
    quarantined_rows: list[QuarantinedRowModel]
    warnings: list[str]
    created_by: str
    created_at: str
    reviews: list[dict[str, Any]]


class ReviewRequest(StrictModel):
    decision: Literal["accept_candidate", "leave_unmatched", "hold"]
    selected_payment_id: str | None = Field(default=None, max_length=120)
    reason: str = Field(min_length=3, max_length=2_000)
    idempotency_key: str = Field(min_length=8, max_length=160)


class ReviewResponse(StrictModel):
    event: dict[str, Any]
    current_review: dict[str, Any]
    item_id: str
    run_id: str


__all__ = [name for name in globals() if not name.startswith("_")]
