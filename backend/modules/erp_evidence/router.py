from __future__ import annotations

from fastapi import APIRouter, HTTPException, Path, Query

from modules.accounts_payable.service import APInvoiceNotFound

from .ap_spend_schemas import APSpendQuestionResponse, APSpendReadinessResponse
from .ap_spend_service import ap_vendor_spend_service
from .schemas import (
    APERPEvidenceResponse,
    APInvoiceSearchResponse,
    APMappingReadinessResponse,
    CreditERPEvidenceResponse,
    ERPEvidenceGatewayStatus,
)
from .service import erp_evidence_service


router = APIRouter(
    prefix="/api/v1/erp-evidence",
    tags=["Read-Only ERP Evidence"],
)


@router.get("/status", response_model=ERPEvidenceGatewayStatus)
def gateway_status() -> ERPEvidenceGatewayStatus:
    return erp_evidence_service.status()


@router.get(
    "/credit/customers/{customer_number}",
    response_model=CreditERPEvidenceResponse,
)
def credit_customer_evidence(
    customer_number: int,
    open_item_limit: int = Query(default=200, ge=1, le=500),
) -> CreditERPEvidenceResponse:
    response = erp_evidence_service.credit_customer(
        customer_number,
        open_item_limit=open_item_limit,
    )
    if response is None:
        raise HTTPException(
            status_code=404,
            detail=f"Customer {customer_number} was not found in current ERP evidence.",
        )
    return response


@router.get(
    "/accounts-payable/mapping-readiness",
    response_model=APMappingReadinessResponse,
)
def accounts_payable_mapping_readiness() -> APMappingReadinessResponse:
    return erp_evidence_service.ap_mapping_readiness()


@router.get(
    "/accounts-payable/vendor-spend-readiness",
    response_model=APSpendReadinessResponse,
)
def accounts_payable_vendor_spend_readiness() -> APSpendReadinessResponse:
    return ap_vendor_spend_service.readiness()


@router.get(
    "/accounts-payable/vendor-spend-question",
    response_model=APSpendQuestionResponse,
)
def accounts_payable_vendor_spend_question(
    question: str = Query(min_length=3, max_length=300),
) -> APSpendQuestionResponse:
    return ap_vendor_spend_service.answer(question)


@router.get(
    "/accounts-payable/invoice-search",
    response_model=APInvoiceSearchResponse,
)
def accounts_payable_invoice_search(
    vendor_query: str | None = Query(default=None, max_length=100),
    invoice_number: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=50, ge=1, le=50),
) -> APInvoiceSearchResponse:
    try:
        return erp_evidence_service.search_ap_invoices(
            vendor_query=vendor_query,
            invoice_number=invoice_number,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get(
    "/accounts-payable/invoice-evidence",
    response_model=APERPEvidenceResponse,
)
def accounts_payable_direct_invoice_evidence(
    vendor_number: int = Query(ge=1),
    invoice_number: str = Query(min_length=1, max_length=100),
) -> APERPEvidenceResponse:
    try:
        return erp_evidence_service.ap_invoice_by_erp_identity(
            vendor_number=vendor_number,
            invoice_number=invoice_number,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get(
    "/accounts-payable/invoices/{ap_invoice_id}",
    response_model=APERPEvidenceResponse,
)
def accounts_payable_invoice_evidence(
    ap_invoice_id: str = Path(
        min_length=1,
        max_length=100,
        pattern=r"^ap-invoice-[0-9a-f]{24}$",
    ),
) -> APERPEvidenceResponse:
    try:
        return erp_evidence_service.ap_invoice(ap_invoice_id)
    except APInvoiceNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
