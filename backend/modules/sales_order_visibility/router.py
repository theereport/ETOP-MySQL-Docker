from __future__ import annotations

from fastapi import APIRouter, HTTPException, Path, Query, status

from .schemas import (
    InvoiceEvidenceResponse,
    OrderNoteCreate,
    OrderNoteHistoryResponse,
    OrderNoteRecord,
    InvoiceSearchResponse,
    SalesSummaryResponse,
)
from .service import (
    InvoiceNotFound,
    SalesOrderVisibilityService,
    sales_order_visibility_service,
)


router = APIRouter(
    prefix="/api/v1/sales-order-visibility",
    tags=["Sales Order Visibility"],
)


def _invoice_number_path() -> int:
    return Path(ge=1)


@router.get("/health")
def get_health() -> dict:
    return {"status": "ok", "module": "sales_order_visibility"}


@router.get("/invoices/search", response_model=InvoiceSearchResponse)
def search_invoices(
    q: str = Query(default="", max_length=100),
    customer_number: int | None = Query(default=None, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> InvoiceSearchResponse:
    return sales_order_visibility_service.search_invoices(
        search=q,
        customer_number=customer_number,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/invoices/{invoice_number}",
    response_model=InvoiceEvidenceResponse,
)
def get_invoice_evidence(
    invoice_number: int = _invoice_number_path(),
) -> InvoiceEvidenceResponse:
    try:
        return sales_order_visibility_service.get_invoice_evidence(
            invoice_number
        )
    except InvoiceNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "invoice_not_found",
                "message": str(exc),
            },
        ) from exc


@router.get(
    "/invoices/{invoice_number}/notes",
    response_model=OrderNoteHistoryResponse,
)
def get_invoice_notes(
    invoice_number: int = _invoice_number_path(),
) -> OrderNoteHistoryResponse:
    return sales_order_visibility_service.list_notes(invoice_number)


@router.post(
    "/invoices/{invoice_number}/notes",
    response_model=OrderNoteRecord,
    status_code=status.HTTP_201_CREATED,
)
def create_invoice_note(
    payload: OrderNoteCreate,
    invoice_number: int = _invoice_number_path(),
) -> OrderNoteRecord:
    try:
        return sales_order_visibility_service.create_note(
            invoice_number, payload
        )
    except InvoiceNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "invoice_not_found",
                "message": str(exc),
            },
        ) from exc


@router.get("/sales-summary", response_model=SalesSummaryResponse)
def get_sales_summary(
    customer_number: int | None = Query(default=None, ge=1),
    product_number: str | None = Query(default=None, max_length=15),
    limit: int = Query(default=200, ge=1, le=1000),
) -> SalesSummaryResponse:
    return sales_order_visibility_service.get_sales_summary(
        customer_number=customer_number,
        product_number=product_number,
        limit=limit,
    )
