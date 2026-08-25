from __future__ import annotations

from fastapi import APIRouter, HTTPException, Path, Query, status

from .schemas import (
    RouteEvidenceResponse,
    RouteNoteCreate,
    RouteNoteHistoryResponse,
    RouteNoteRecord,
    RouteSearchResponse,
)
from .service import (
    FreightLogisticsService,
    RouteNotFound,
    freight_logistics_service,
)


router = APIRouter(
    prefix="/api/v1/freight-logistics",
    tags=["Freight & Logistics"],
)


def _route_code_path() -> str:
    return Path(min_length=1, max_length=8)


@router.get("/health")
def get_health() -> dict:
    return {"status": "ok", "module": "freight_logistics"}


@router.get("/routes/search", response_model=RouteSearchResponse)
def search_routes(
    q: str = Query(default="", max_length=100),
    active_only: bool = Query(default=True),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> RouteSearchResponse:
    return freight_logistics_service.search_routes(
        search=q,
        active_only=active_only,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/routes/{route_code}",
    response_model=RouteEvidenceResponse,
)
def get_route_evidence(
    route_code: str = _route_code_path(),
) -> RouteEvidenceResponse:
    try:
        return freight_logistics_service.get_route_evidence(route_code)
    except RouteNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "route_not_found",
                "message": str(exc),
            },
        ) from exc


@router.get(
    "/routes/{route_code}/notes",
    response_model=RouteNoteHistoryResponse,
)
def get_route_notes(
    route_code: str = _route_code_path(),
) -> RouteNoteHistoryResponse:
    return freight_logistics_service.list_notes(route_code)


@router.post(
    "/routes/{route_code}/notes",
    response_model=RouteNoteRecord,
    status_code=status.HTTP_201_CREATED,
)
def create_route_note(
    payload: RouteNoteCreate,
    route_code: str = _route_code_path(),
) -> RouteNoteRecord:
    try:
        return freight_logistics_service.create_note(route_code, payload)
    except RouteNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "route_not_found",
                "message": str(exc),
            },
        ) from exc
