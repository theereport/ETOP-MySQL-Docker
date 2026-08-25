from __future__ import annotations

from fastapi import APIRouter, HTTPException, Path, status

from .schemas import (
    ARCollectionsNoteCreate,
    ARCollectionsNoteHistoryResponse,
    ARCollectionsNoteRecord,
    CustomerARCollectionsResponse,
)
from .service import (
    ARCollectionsCustomerNotFound,
    ARCollectionsService,
    ar_collections_service,
)


router = APIRouter(
    prefix="/api/v1/ar-collections",
    tags=["AR Collections"],
)


def _customer_number_path() -> int:
    return Path(ge=1)


@router.get("/health")
def get_health() -> dict:
    return {"status": "ok", "module": "ar_collections"}


@router.get(
    "/customers/{customer_number}",
    response_model=CustomerARCollectionsResponse,
)
def get_customer_collections(
    customer_number: int = _customer_number_path(),
) -> CustomerARCollectionsResponse:
    try:
        return ar_collections_service.get_customer_collections(
            customer_number
        )
    except ARCollectionsCustomerNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "customer_not_found",
                "message": str(exc),
            },
        ) from exc


@router.get(
    "/customers/{customer_number}/notes",
    response_model=ARCollectionsNoteHistoryResponse,
)
def get_customer_notes(
    customer_number: int = _customer_number_path(),
) -> ARCollectionsNoteHistoryResponse:
    return ar_collections_service.list_notes(customer_number)


@router.post(
    "/customers/{customer_number}/notes",
    response_model=ARCollectionsNoteRecord,
    status_code=status.HTTP_201_CREATED,
)
def create_customer_note(
    payload: ARCollectionsNoteCreate,
    customer_number: int = _customer_number_path(),
) -> ARCollectionsNoteRecord:
    try:
        return ar_collections_service.create_note(customer_number, payload)
    except ARCollectionsCustomerNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "customer_not_found",
                "message": str(exc),
            },
        ) from exc
