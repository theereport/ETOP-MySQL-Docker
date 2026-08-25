"""HTTP surface for the R73 Payment Notes evidence workspace."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Path, Query, UploadFile, status
from core.auth import AuthenticationRequired as WorkflowAuthenticationRequired
from core.auth import Token

from .remote_capture import RemoteCaptureError
from .repository import PaymentNotesConflict, PaymentNotesIntegrityError, PaymentNotesNotFound
from .route_reference import RouteReferenceError
from .schemas import (
    Governance, ReviewRequest, ReviewResponse, RouteActivationRequest,
    RouteReferenceList, RouteReferenceStatus, RouteReferenceSummary, RunDetail, RunList,
)
from .service import PaymentNotesPreconditionError, PaymentNotesService, PaymentNotesValidationError

payment_notes_service = PaymentNotesService()

router = APIRouter(prefix="/api/v1/payment-notes", tags=["Payment Notes"])


def _raise(exc: Exception) -> None:
    if isinstance(exc, WorkflowAuthenticationRequired):
        raise HTTPException(status_code=401, detail={"code": "workflow_authentication_required", "message": str(exc)}, headers={"WWW-Authenticate": "Bearer"}) from exc
    if isinstance(exc, PaymentNotesNotFound):
        raise HTTPException(status_code=404, detail={"code": "payment_notes_not_found", "message": str(exc)}) from exc
    if isinstance(exc, PaymentNotesIntegrityError):
        raise HTTPException(status_code=409, detail={"code": "payment_notes_integrity_error", "message": str(exc)}) from exc
    if isinstance(exc, (PaymentNotesConflict, PaymentNotesPreconditionError)):
        raise HTTPException(status_code=409, detail={"code": "payment_notes_conflict", "message": str(exc)}) from exc
    if isinstance(exc, (PaymentNotesValidationError, RemoteCaptureError, RouteReferenceError)):
        raise HTTPException(status_code=422, detail={"code": "payment_notes_validation_error", "message": str(exc)}) from exc
    raise exc


def _actor(token: str) -> str:
    return payment_notes_service.actor_for_token(token)


@router.get("/governance", response_model=Governance)
def governance(token: Token) -> Governance:
    try:
        _actor(token)
        return Governance.model_validate(payment_notes_service.governance())
    except Exception as exc:
        _raise(exc)
        raise AssertionError("unreachable")


@router.post("/route-references/upload", response_model=RouteReferenceSummary, status_code=status.HTTP_201_CREATED)
async def upload_route_reference(
    token: Token,
    file: Annotated[UploadFile, File()],
    version_label: Annotated[str, Form(min_length=1, max_length=120)],
    idempotency_key: Annotated[str, Form(min_length=8, max_length=160)],
) -> RouteReferenceSummary:
    try:
        return RouteReferenceSummary.model_validate(payment_notes_service.import_route_reference(
            await file.read(), file.filename or "route-reference.csv", version_label, idempotency_key, _actor(token)))
    except Exception as exc:
        _raise(exc)
        raise AssertionError("unreachable")


@router.get("/route-references", response_model=RouteReferenceList)
def list_route_references(token: Token) -> RouteReferenceList:
    try:
        _actor(token)
        return RouteReferenceList.model_validate(payment_notes_service.list_route_references())
    except Exception as exc:
        _raise(exc)
        raise AssertionError("unreachable")


@router.get("/route-references/status", response_model=RouteReferenceStatus)
def route_reference_status(token: Token) -> RouteReferenceStatus:
    try:
        _actor(token)
        return RouteReferenceStatus.model_validate(payment_notes_service.route_reference_status())
    except Exception as exc:
        _raise(exc)
        raise AssertionError("unreachable")


@router.post("/route-references/{reference_id}/activate", response_model=RouteReferenceSummary)
def activate_route_reference(
    payload: RouteActivationRequest, token: Token,
    reference_id: Annotated[str, Path(min_length=5, max_length=100)],
) -> RouteReferenceSummary:
    try:
        return RouteReferenceSummary.model_validate(payment_notes_service.activate_route_reference(
            reference_id, payload.idempotency_key, _actor(token)))
    except Exception as exc:
        _raise(exc)
        raise AssertionError("unreachable")


@router.post("/runs", response_model=RunDetail, status_code=status.HTTP_201_CREATED)
async def create_run(
    token: Token,
    file: Annotated[UploadFile, File()],
    date_from: Annotated[str, Form(pattern=r"^\d{4}-\d{2}-\d{2}$")],
    date_to: Annotated[str, Form(pattern=r"^\d{4}-\d{2}-\d{2}$")],
    idempotency_key: Annotated[str, Form(min_length=8, max_length=160)],
) -> RunDetail:
    try:
        return RunDetail.model_validate(payment_notes_service.create_run(
            await file.read(), file.filename or "remote-capture.csv", date_from, date_to,
            idempotency_key, _actor(token)))
    except Exception as exc:
        _raise(exc)
        raise AssertionError("unreachable")


@router.get("/runs", response_model=RunList)
def list_runs(token: Token, limit: Annotated[int, Query(ge=1, le=200)] = 50,
              offset: Annotated[int, Query(ge=0)] = 0) -> RunList:
    try:
        _actor(token)
        return RunList.model_validate(payment_notes_service.list_runs(limit, offset))
    except Exception as exc:
        _raise(exc)
        raise AssertionError("unreachable")


@router.get("/runs/{run_id}", response_model=RunDetail)
def get_run(token: Token, run_id: Annotated[str, Path(min_length=7, max_length=100)]) -> RunDetail:
    try:
        _actor(token)
        return RunDetail.model_validate(payment_notes_service.get_run(run_id))
    except Exception as exc:
        _raise(exc)
        raise AssertionError("unreachable")


@router.post("/runs/{run_id}/items/{item_id}/reviews", response_model=ReviewResponse)
def review_item(
    payload: ReviewRequest, token: Token,
    run_id: Annotated[str, Path(min_length=7, max_length=100)],
    item_id: Annotated[str, Path(min_length=5, max_length=100)],
) -> ReviewResponse:
    try:
        return ReviewResponse.model_validate(payment_notes_service.review_item(
            run_id, item_id, payload, _actor(token)))
    except Exception as exc:
        _raise(exc)
        raise AssertionError("unreachable")


__all__ = ["router"]

