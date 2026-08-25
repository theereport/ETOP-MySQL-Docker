from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from .schemas import (
    CustomerClassResponse,
    DiscountEvidenceResponse,
    DiscountSearchResponse,
    PricingNoteCreate,
    PricingNoteHistoryResponse,
    PricingNoteRecord,
)
from .service import (
    DiscountNotFound,
    PricingContractsService,
    pricing_contracts_service,
)


router = APIRouter(
    prefix="/api/v1/pricing-contracts",
    tags=["Pricing & Contracts"],
)


@router.get("/health")
def get_health() -> dict:
    return {"status": "ok", "module": "pricing_contracts"}


@router.get("/discounts/search", response_model=DiscountSearchResponse)
def search_discounts(
    customer_number: int | None = Query(default=None, ge=0),
    product_number: str = Query(default="", max_length=15),
    product_class: str = Query(default="", max_length=2),
    vendor_code: str = Query(default="", max_length=3),
    active_only: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> DiscountSearchResponse:
    return pricing_contracts_service.search_discounts(
        customer_number=customer_number,
        product_number=product_number,
        product_class=product_class,
        vendor_code=vendor_code,
        active_only=active_only,
        limit=limit,
        offset=offset,
    )


@router.get("/discounts/lookup", response_model=DiscountEvidenceResponse)
def get_discount(
    customer_number: int = Query(ge=0),
    vendor_code: str = Query(min_length=1, max_length=3),
    product_class: str = Query(min_length=1, max_length=2),
    product_number: str = Query(min_length=1, max_length=15),
    product_type: str = Query(min_length=1, max_length=3),
) -> DiscountEvidenceResponse:
    try:
        return pricing_contracts_service.get_discount(
            customer_number=customer_number,
            vendor_code=vendor_code,
            product_class=product_class,
            product_number=product_number,
            product_type=product_type,
        )
    except DiscountNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "discount_not_found",
                "message": str(exc),
            },
        ) from exc


@router.get("/customer-classes/search", response_model=CustomerClassResponse)
def search_customer_classes(
    q: str = Query(default="", max_length=100),
    active_only: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> CustomerClassResponse:
    return pricing_contracts_service.list_customer_classes(
        search=q,
        active_only=active_only,
        limit=limit,
        offset=offset,
    )


@router.get("/notes", response_model=PricingNoteHistoryResponse)
def get_notes(
    customer_number: int = Query(ge=0),
    vendor_code: str | None = Query(default=None, max_length=3),
    product_class: str | None = Query(default=None, max_length=2),
    product_number: str | None = Query(default=None, max_length=15),
    product_type: str | None = Query(default=None, max_length=3),
) -> PricingNoteHistoryResponse:
    return pricing_contracts_service.list_notes(
        customer_number,
        vendor_code=vendor_code,
        product_class=product_class,
        product_number=product_number,
        product_type=product_type,
    )


@router.post(
    "/notes",
    response_model=PricingNoteRecord,
    status_code=status.HTTP_201_CREATED,
)
def create_note(payload: PricingNoteCreate) -> PricingNoteRecord:
    return pricing_contracts_service.create_note(payload)
