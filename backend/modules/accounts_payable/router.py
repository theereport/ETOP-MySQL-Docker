from __future__ import annotations

from datetime import date
from typing import Literal

from fastapi import APIRouter, HTTPException, Path, Query, status

from .schemas import (
    APControlCaseCreate,
    APControlCaseDetail,
    APControlCaseListResponse,
    APControlReviewCreate,
    APCashScenarioCreate,
    APCashScenarioHistoryResponse,
    APCashScenarioRecord,
    APErpLedgerRefreshResponse,
    APInvoiceDetailResponse,
    APInvoiceListResponse,
    APOverviewResponse,
    APSyncResponse,
    APVendorCashIntelligenceResponse,
    APVendorTermsReferenceListResponse,
    APVendorTermsReferenceUpsert,
    APWarehouseApprovalActionCreate,
    APWarehouseApprovalActionRecord,
    APWarehouseApprovalQueueResponse,
    APExceptionActionCreate,
    APExceptionActionHistoryResponse,
    APExceptionActionRecord,
    APExceptionOperationsResponse,
)
from .service import (
    APControlCaseNotFound,
    APControlConflict,
    APInvoiceNotFound,
    APDocumentJobNotEligible,
    APDocumentReviewConflict,
    accounts_payable_service,
)
from .source import APSourceUnavailable


router = APIRouter(
    prefix="/api/v1/accounts-payable",
    tags=["Accounts Payable Intelligence"],
)


@router.post("/sync", response_model=APSyncResponse)
def sync_accounts_payable_evidence() -> APSyncResponse:
    try:
        return accounts_payable_service.sync()
    except APSourceUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "ap_document_source_unavailable",
                "message": str(exc),
            },
        ) from exc


@router.post(
    "/sync/document-jobs/{job_id}",
    response_model=APSyncResponse,
)
def sync_exact_vendor_invoice_evidence(
    job_id: str = Path(min_length=1, max_length=100),
) -> APSyncResponse:
    try:
        return accounts_payable_service.sync_document_job(job_id)
    except APDocumentJobNotEligible as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "ap_document_job_not_eligible", "message": str(exc)},
        ) from exc
    except APDocumentReviewConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "ap_document_review_conflict", "message": str(exc)},
        ) from exc
    except APSourceUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "ap_document_source_unavailable",
                "message": str(exc),
            },
        ) from exc


@router.get("/overview", response_model=APOverviewResponse)
def get_accounts_payable_overview() -> APOverviewResponse:
    return accounts_payable_service.overview()


@router.post(
    "/erp-ledger/refresh",
    response_model=APErpLedgerRefreshResponse,
)
def refresh_accounts_payable_erp_ledger() -> APErpLedgerRefreshResponse:
    """Scans MaddenCo's open AP ledger (PMHD) and vendor terms codes
    (PMVEND) in the background and returns immediately - the scan takes
    1-2+ minutes, so this never blocks the request the way
    cash_flow_forecasting's equivalent endpoint does. Progress and
    completion surface through the platform job queue."""

    return accounts_payable_service.refresh_erp_ledger()


@router.get(
    "/vendor-terms-reference",
    response_model=APVendorTermsReferenceListResponse,
)
def list_accounts_payable_vendor_terms_reference() -> APVendorTermsReferenceListResponse:
    return APVendorTermsReferenceListResponse(
        items=accounts_payable_service.list_vendor_terms_reference()
    )


@router.put(
    "/vendor-terms-reference/{terms_code}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def upsert_accounts_payable_vendor_terms_reference(
    payload: APVendorTermsReferenceUpsert,
    terms_code: str = Path(min_length=1, max_length=20),
) -> None:
    accounts_payable_service.upsert_vendor_terms_reference(
        terms_code, payload.model_dump()
    )


@router.get(
    "/warehouse-approval-queue",
    response_model=APWarehouseApprovalQueueResponse,
)
def get_accounts_payable_warehouse_approval_queue(
    division: str | None = Query(default=None, max_length=20),
) -> APWarehouseApprovalQueueResponse:
    """Every currently-open ERP invoice (same open-ledger cache the
    dashboard uses), bucketed by warehouse-approval status. This is
    evidence/documentation only - it never gates, blocks, or replaces AP's
    own entry of an invoice, matching the Approval Center's existing
    governance posture."""

    return accounts_payable_service.warehouse_approval_queue(division)


@router.post(
    "/warehouse-approval-queue/actions",
    response_model=APWarehouseApprovalActionRecord,
    status_code=status.HTTP_201_CREATED,
)
def create_accounts_payable_warehouse_approval_action(
    payload: APWarehouseApprovalActionCreate,
) -> APWarehouseApprovalActionRecord:
    return accounts_payable_service.record_warehouse_approval_action(
        vendor_number=payload.vendor_number,
        invoice_number=payload.invoice_number,
        to_status=payload.to_status,
        actor_identity=payload.actor_identity,
        notes=payload.notes,
    )


@router.get(
    "/vendor-cash-intelligence",
    response_model=APVendorCashIntelligenceResponse,
)
def get_accounts_payable_vendor_cash_intelligence(
    as_of_date: date | None = Query(default=None),
) -> APVendorCashIntelligenceResponse:
    return accounts_payable_service.vendor_cash_intelligence(as_of_date)


@router.get(
    "/cash-scenarios",
    response_model=APCashScenarioHistoryResponse,
)
def get_accounts_payable_cash_scenarios() -> APCashScenarioHistoryResponse:
    return accounts_payable_service.list_cash_scenarios()


@router.post(
    "/cash-scenarios",
    response_model=APCashScenarioRecord,
    status_code=status.HTTP_201_CREATED,
)
def create_accounts_payable_cash_scenario(
    payload: APCashScenarioCreate,
) -> APCashScenarioRecord:
    return accounts_payable_service.create_cash_scenario(payload)


@router.get(
    "/exception-operations",
    response_model=APExceptionOperationsResponse,
)
def get_accounts_payable_exception_operations(
    as_of_date: date | None = Query(default=None),
) -> APExceptionOperationsResponse:
    return accounts_payable_service.exception_operations(as_of_date)


@router.get("/invoices", response_model=APInvoiceListResponse)
def list_accounts_payable_invoices(
    query: str | None = Query(default=None, max_length=200),
    status_filter: Literal[
        "review_required",
        "evidence_available",
        "ocr_review",
    ]
    | None = Query(default=None, alias="status"),
    exception: bool | None = Query(default=None),
    duplicate: bool | None = Query(default=None),
    exception_code: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    sort_by: Literal[
        "received_at",
        "invoice_date",
        "due_date",
        "total",
        "vendor_name",
        "ocr_confidence",
    ] = Query(default="received_at"),
    sort_order: Literal["asc", "desc"] = Query(default="desc"),
) -> APInvoiceListResponse:
    return accounts_payable_service.list_invoices(
        query=query,
        status=status_filter,
        exception=exception,
        duplicate=duplicate,
        exception_code=exception_code,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_order=sort_order,
    )


@router.get(
    "/invoices/{ap_invoice_id}",
    response_model=APInvoiceDetailResponse,
)
def get_accounts_payable_invoice(
    ap_invoice_id: str = Path(
        min_length=1,
        max_length=100,
        pattern=r"^ap-invoice-[0-9a-f]{24}$",
    ),
) -> APInvoiceDetailResponse:
    try:
        return accounts_payable_service.get_invoice(ap_invoice_id)
    except APInvoiceNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "ap_invoice_not_found",
                "message": str(exc),
            },
        ) from exc


@router.get(
    "/invoices/{ap_invoice_id}/exception-actions",
    response_model=APExceptionActionHistoryResponse,
)
def get_accounts_payable_exception_actions(
    ap_invoice_id: str = Path(
        min_length=1,
        max_length=100,
        pattern=r"^ap-invoice-[0-9a-f]{24}$",
    ),
) -> APExceptionActionHistoryResponse:
    try:
        return accounts_payable_service.list_exception_actions(ap_invoice_id)
    except APInvoiceNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "ap_invoice_not_found", "message": str(exc)},
        ) from exc


@router.post(
    "/invoices/{ap_invoice_id}/exception-actions",
    response_model=APExceptionActionRecord,
    status_code=status.HTTP_201_CREATED,
)
def create_accounts_payable_exception_action(
    payload: APExceptionActionCreate,
    ap_invoice_id: str = Path(
        min_length=1,
        max_length=100,
        pattern=r"^ap-invoice-[0-9a-f]{24}$",
    ),
) -> APExceptionActionRecord:
    try:
        return accounts_payable_service.create_exception_action(
            ap_invoice_id,
            payload,
        )
    except APInvoiceNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "ap_invoice_not_found", "message": str(exc)},
        ) from exc
    except APControlConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "ap_exception_action_conflict", "message": str(exc)},
        ) from exc


@router.post(
    "/invoices/{ap_invoice_id}/control-cases",
    response_model=APControlCaseDetail,
    status_code=status.HTTP_201_CREATED,
)
def create_accounts_payable_control_case(
    payload: APControlCaseCreate,
    ap_invoice_id: str = Path(
        min_length=1,
        max_length=100,
        pattern=r"^ap-invoice-[0-9a-f]{24}$",
    ),
) -> APControlCaseDetail:
    try:
        return accounts_payable_service.create_control_case(
            ap_invoice_id,
            payload,
        )
    except APInvoiceNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "ap_invoice_not_found", "message": str(exc)},
        ) from exc


@router.get(
    "/control-cases",
    response_model=APControlCaseListResponse,
)
def list_accounts_payable_control_cases(
    intended_action: Literal[
        "approval_review",
        "payment_preparation",
    ]
    | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> APControlCaseListResponse:
    return accounts_payable_service.list_control_cases(
        intended_action=intended_action,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/control-cases/{control_case_id}",
    response_model=APControlCaseDetail,
)
def get_accounts_payable_control_case(
    control_case_id: str = Path(
        min_length=1,
        max_length=120,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$",
    ),
) -> APControlCaseDetail:
    try:
        return accounts_payable_service.get_control_case(control_case_id)
    except APControlCaseNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "ap_control_case_not_found", "message": str(exc)},
        ) from exc


@router.post(
    "/control-cases/{control_case_id}/reviews",
    response_model=APControlCaseDetail,
)
def create_accounts_payable_control_review(
    payload: APControlReviewCreate,
    control_case_id: str = Path(
        min_length=1,
        max_length=120,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$",
    ),
) -> APControlCaseDetail:
    try:
        return accounts_payable_service.create_control_review(
            control_case_id,
            payload,
        )
    except APControlCaseNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "ap_control_case_not_found", "message": str(exc)},
        ) from exc
    except APControlConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "ap_control_conflict", "message": str(exc)},
        ) from exc
