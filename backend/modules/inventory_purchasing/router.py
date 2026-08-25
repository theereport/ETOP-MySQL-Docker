from __future__ import annotations

from fastapi import APIRouter, HTTPException, Path, Query, status

from .schemas import (
    InventoryNoteCreate,
    InventoryNoteHistoryResponse,
    InventoryNoteRecord,
    ProductEvidenceResponse,
    ProductSearchResponse,
)
from .service import (
    InventoryPurchasingService,
    ProductNotFound,
    inventory_purchasing_service,
)


router = APIRouter(
    prefix="/api/v1/inventory-purchasing",
    tags=["Inventory & Purchasing"],
)


def _product_number_path() -> str:
    return Path(min_length=1, max_length=15)


@router.get("/health")
def get_health() -> dict:
    return {"status": "ok", "module": "inventory_purchasing"}


@router.get("/products/search", response_model=ProductSearchResponse)
def search_products(
    q: str = Query(default="", max_length=100),
    active_only: bool = Query(default=True),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> ProductSearchResponse:
    return inventory_purchasing_service.search_products(
        search=q,
        active_only=active_only,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/products/{product_number}",
    response_model=ProductEvidenceResponse,
)
def get_product_evidence(
    product_number: str = _product_number_path(),
) -> ProductEvidenceResponse:
    try:
        return inventory_purchasing_service.get_product_evidence(
            product_number
        )
    except ProductNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "product_not_found",
                "message": str(exc),
            },
        ) from exc


@router.get(
    "/products/{product_number}/notes",
    response_model=InventoryNoteHistoryResponse,
)
def get_product_notes(
    product_number: str = _product_number_path(),
) -> InventoryNoteHistoryResponse:
    return inventory_purchasing_service.list_notes(product_number)


@router.post(
    "/products/{product_number}/notes",
    response_model=InventoryNoteRecord,
    status_code=status.HTTP_201_CREATED,
)
def create_product_note(
    payload: InventoryNoteCreate,
    product_number: str = _product_number_path(),
) -> InventoryNoteRecord:
    try:
        return inventory_purchasing_service.create_note(
            product_number, payload
        )
    except ProductNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "product_not_found",
                "message": str(exc),
            },
        ) from exc
