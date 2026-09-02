from __future__ import annotations

from fastapi import APIRouter, HTTPException, Path, Query, status

from .schemas import (
    VendorEvidenceResponse,
    VendorNoteCreate,
    VendorNoteHistoryResponse,
    VendorNoteRecord,
    VendorSearchResponse,
)
from .service import VendorIntelligenceService, VendorNotFound, vendor_intelligence_service


router = APIRouter(
    prefix="/api/v1/vendor-intelligence",
    tags=["Vendor Intelligence"],
)


def _vendor_number_path() -> int:
    return Path(ge=1)


@router.get("/health")
def get_health() -> dict:
    return {"status": "ok", "module": "vendor_intelligence"}


@router.post("/po-fill-rate-cache/refresh")
def refresh_po_fill_rate_cache() -> dict:
    """Full TMPOHD/TMPODT scan across every vendor (minutes) - not part of
    interactive page loads. Call this once, then periodically (e.g. daily),
    to keep each vendor's fill-rate performance summary current."""

    return vendor_intelligence_service.refresh_po_fill_rate_cache()


@router.get("/vendors/search", response_model=VendorSearchResponse)
def search_vendors(
    q: str = Query(default="", max_length=100),
    active_only: bool = Query(default=True),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> VendorSearchResponse:
    return vendor_intelligence_service.search_vendors(
        search=q,
        active_only=active_only,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/vendors/{vendor_number}",
    response_model=VendorEvidenceResponse,
)
def get_vendor_evidence(
    vendor_number: int = _vendor_number_path(),
) -> VendorEvidenceResponse:
    try:
        return vendor_intelligence_service.get_vendor_evidence(vendor_number)
    except VendorNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "vendor_not_found",
                "message": str(exc),
            },
        ) from exc


@router.get(
    "/vendors/{vendor_number}/notes",
    response_model=VendorNoteHistoryResponse,
)
def get_vendor_notes(
    vendor_number: int = _vendor_number_path(),
) -> VendorNoteHistoryResponse:
    return vendor_intelligence_service.list_notes(vendor_number)


@router.post(
    "/vendors/{vendor_number}/notes",
    response_model=VendorNoteRecord,
    status_code=status.HTTP_201_CREATED,
)
def create_vendor_note(
    payload: VendorNoteCreate,
    vendor_number: int = _vendor_number_path(),
) -> VendorNoteRecord:
    try:
        return vendor_intelligence_service.create_note(vendor_number, payload)
    except VendorNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "vendor_not_found",
                "message": str(exc),
            },
        ) from exc
