from __future__ import annotations

from fastapi import APIRouter, HTTPException, Path, Query, status

from .schemas import (
    CustomerExemptionCheckBatchRequest,
    CustomerExemptionCheckBatchResponse,
    CustomerExemptionCheckResponse,
    TaxAuthorityRecord,
    TaxAuthoritySearchResponse,
    TaxComplianceNoteCreate,
    TaxComplianceNoteHistoryResponse,
    TaxComplianceNoteRecord,
    TaxExemptionCodeRecord,
    TaxExemptionCodeSearchResponse,
)
from .service import (
    CustomerNotFound,
    ExemptionCodeNotFound,
    TaxAuthorityNotFound,
    tax_compliance_service,
)


router = APIRouter(
    prefix="/api/v1/tax-compliance",
    tags=["Tax Compliance"],
)


def _customer_number_path() -> int:
    return Path(ge=1)


@router.get("/health")
def get_health() -> dict:
    return {"status": "ok", "module": "tax_compliance"}


@router.get("/tax-authorities", response_model=TaxAuthoritySearchResponse)
def search_tax_authorities(
    state: str = Query(default="", max_length=2),
    tax_type: str = Query(default="", max_length=2),
    active_only: bool = Query(default=True),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> TaxAuthoritySearchResponse:
    return tax_compliance_service.search_tax_authorities(
        state_abbreviation=state,
        tax_type_code=tax_type,
        active_only=active_only,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/tax-authorities/{tax_authority}/{state_code}",
    response_model=TaxAuthorityRecord,
)
def get_tax_authority(
    tax_authority: int = Path(ge=0),
    state_code: int = Path(ge=0),
) -> TaxAuthorityRecord:
    try:
        return tax_compliance_service.get_tax_authority(
            tax_authority, state_code
        )
    except TaxAuthorityNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "tax_authority_not_found", "message": str(exc)},
        ) from exc


@router.get(
    "/exemption-codes", response_model=TaxExemptionCodeSearchResponse
)
def search_exemption_codes(
    state_code: int | None = Query(default=None, ge=0),
    tax_type: str = Query(default="", max_length=2),
    active_only: bool = Query(default=True),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> TaxExemptionCodeSearchResponse:
    return tax_compliance_service.search_exemption_codes(
        state_code=state_code,
        tax_type_code=tax_type,
        active_only=active_only,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/exemption-codes/{exempt_code}",
    response_model=list[TaxExemptionCodeRecord],
)
def get_exemption_code(
    exempt_code: str = Path(min_length=1, max_length=2),
) -> list[TaxExemptionCodeRecord]:
    try:
        return tax_compliance_service.get_exemption_code(exempt_code)
    except ExemptionCodeNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "exemption_code_not_found", "message": str(exc)},
        ) from exc


@router.get(
    "/customers/{customer_number}/exemption-check",
    response_model=CustomerExemptionCheckResponse,
)
def check_customer_exemption(
    customer_number: int = _customer_number_path(),
) -> CustomerExemptionCheckResponse:
    try:
        return tax_compliance_service.check_customer_exemption(
            customer_number
        )
    except CustomerNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "customer_not_found", "message": str(exc)},
        ) from exc


@router.post(
    "/customers/exemption-check/batch",
    response_model=CustomerExemptionCheckBatchResponse,
)
def check_customers_exemption_batch(
    payload: CustomerExemptionCheckBatchRequest,
) -> CustomerExemptionCheckBatchResponse:
    return tax_compliance_service.check_customers_exemption(
        payload.customer_numbers
    )


@router.get(
    "/customers/{customer_number}/notes",
    response_model=TaxComplianceNoteHistoryResponse,
)
def get_customer_notes(
    customer_number: int = _customer_number_path(),
) -> TaxComplianceNoteHistoryResponse:
    return tax_compliance_service.list_notes(customer_number)


@router.post(
    "/customers/{customer_number}/notes",
    response_model=TaxComplianceNoteRecord,
    status_code=status.HTTP_201_CREATED,
)
def create_customer_note(
    payload: TaxComplianceNoteCreate,
    customer_number: int = _customer_number_path(),
) -> TaxComplianceNoteRecord:
    try:
        return tax_compliance_service.create_note(customer_number, payload)
    except CustomerNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "customer_not_found", "message": str(exc)},
        ) from exc
