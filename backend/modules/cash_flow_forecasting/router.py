from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Query

from .schemas import (
    CashFlowAccuracyHistoryResponse,
    CashFlowForecastResponse,
    CashFlowSnapshotHistoryResponse,
)
from .service import cash_flow_forecasting_service


router = APIRouter(
    prefix="/api/v1/cash-flow-forecasting",
    tags=["Cash Flow Forecasting"],
)


@router.get("/health")
def get_health() -> dict:
    return {"status": "ok", "module": "cash_flow_forecasting"}


@router.get("/current", response_model=CashFlowForecastResponse)
def get_current_forecast(
    as_of: date | None = Query(default=None),
) -> CashFlowForecastResponse:
    return cash_flow_forecasting_service.get_current_forecast(as_of)


@router.post("/snapshots", status_code=201)
def create_snapshot(as_of: date | None = Query(default=None)) -> dict:
    snapshot_id = cash_flow_forecasting_service.create_snapshot(as_of)
    return {"snapshot_id": snapshot_id}


@router.get("/snapshots", response_model=CashFlowSnapshotHistoryResponse)
def list_snapshots(
    limit: int = Query(default=50, ge=1, le=200)
) -> CashFlowSnapshotHistoryResponse:
    return cash_flow_forecasting_service.list_snapshots(limit)


@router.post("/ap-cache/refresh")
def refresh_ap_cache() -> dict:
    """Full PMHD scan (~2-3 minutes) - not part of interactive page loads.
    Call this once, then periodically (e.g. daily), to keep the AP
    due-date projection current."""

    return cash_flow_forecasting_service.refresh_ap_due_date_cache()


@router.post("/accuracy/record-closed-weeks")
def record_closed_weeks(as_of: date | None = Query(default=None)) -> dict:
    return cash_flow_forecasting_service.record_closed_weeks(as_of)


@router.get("/accuracy-history", response_model=CashFlowAccuracyHistoryResponse)
def get_accuracy_history(
    limit: int = Query(default=200, ge=1, le=1000)
) -> CashFlowAccuracyHistoryResponse:
    return cash_flow_forecasting_service.get_accuracy_history(limit)
