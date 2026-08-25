from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from .schemas import CustomerSearchResponse, CustomerSummaryResponse
from .service import customer_service


router = APIRouter(
    prefix="/api/v1/customers",
    tags=["Customer 360"],
)


@router.get(
    "",
    response_model=CustomerSearchResponse,
)
@router.get(
    "/search",
    response_model=CustomerSearchResponse,
)
def search_customers(
    search: str = Query(default="", max_length=200),
    route_code: str | None = Query(
        default=None,
        max_length=2,
    ),
    store_number: int | None = Query(
        default=None,
        ge=0,
        le=999,
    ),
    active_only: bool = Query(default=True),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> CustomerSearchResponse:
    result = customer_service.search(
        search=search,
        route_code=route_code,
        store_number=store_number,
        active_only=active_only,
        limit=limit,
        offset=offset,
    )

    return CustomerSearchResponse(**result)


@router.get(
    "/{customer_number}",
    response_model=CustomerSummaryResponse,
)
def get_customer_summary(
    customer_number: int,
) -> CustomerSummaryResponse:
    customer = customer_service.summary(customer_number)

    if customer is None:
        raise HTTPException(
            status_code=404,
            detail=f"Customer {customer_number} was not found.",
        )

    return CustomerSummaryResponse(**customer)
