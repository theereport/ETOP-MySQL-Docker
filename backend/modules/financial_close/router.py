from __future__ import annotations

from fastapi import APIRouter, HTTPException, Path, status

from core.auth import AuthenticationRequired as WorkflowAuthenticationRequired
from core.auth import Token

from .repository import (
    FinancialCloseConflict,
    FinancialCloseIntegrityError,
    FinancialCloseNotFound,
)
from .schemas import (
    CloseControlCreate,
    CloseControlEventList,
    CloseControlSummary,
    CloseCycleCreate,
    CloseCycleDetail,
    CloseCycleListResponse,
    ClosePreparationCreate,
    CloseReviewCreate,
    CloseTemplateCreate,
    CloseTemplateDetail,
    CloseTemplateInstantiate,
    CloseTemplateListResponse,
    CloseTemplateVersionCreate,
    FinancialCloseGovernance,
)
from .service import (
    FinancialClosePermissionDenied,
    FinancialCloseValidationError,
    financial_close_service,
)


router = APIRouter(
    prefix="/api/v1/financial-close",
    tags=["Financial Close and Controller Intelligence"],
)


def _raise_financial_close_error(exc: Exception) -> None:
    if isinstance(exc, WorkflowAuthenticationRequired):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "workflow_authentication_required",
                "message": str(exc),
            },
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    if isinstance(exc, FinancialClosePermissionDenied):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "financial_close_permission_denied",
                "message": str(exc),
            },
        ) from exc
    if isinstance(exc, FinancialCloseNotFound):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "financial_close_record_not_found",
                "message": str(exc),
            },
        ) from exc
    if isinstance(exc, (FinancialCloseConflict, FinancialCloseIntegrityError)):
        code = (
            "financial_close_evidence_integrity_error"
            if isinstance(exc, FinancialCloseIntegrityError)
            else "financial_close_conflict"
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": code, "message": str(exc)},
        ) from exc
    if isinstance(exc, FinancialCloseValidationError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "financial_close_validation_error",
                "message": str(exc),
            },
        ) from exc
    raise exc


CycleId = Path(
    min_length=5,
    max_length=80,
    pattern=r"^FCC-[A-Za-z0-9-]+$",
)
ControlId = Path(
    min_length=5,
    max_length=80,
    pattern=r"^FCT-[A-Za-z0-9-]+$",
)
TemplateId = Path(
    min_length=5,
    max_length=80,
    pattern=r"^FCP-[A-Za-z0-9-]+$",
)
TemplateVersion = Path(ge=1, le=1_000_000)


@router.get("/governance", response_model=FinancialCloseGovernance)
def get_financial_close_governance(token: Token) -> FinancialCloseGovernance:
    try:
        return financial_close_service.governance_for_token(token)
    except WorkflowAuthenticationRequired as exc:
        _raise_financial_close_error(exc)
        raise AssertionError("unreachable")


@router.get("/templates", response_model=CloseTemplateListResponse)
def list_financial_close_templates(token: Token) -> CloseTemplateListResponse:
    try:
        return financial_close_service.list_templates(token)
    except (
        WorkflowAuthenticationRequired,
        FinancialCloseIntegrityError,
    ) as exc:
        _raise_financial_close_error(exc)
        raise AssertionError("unreachable")


@router.post(
    "/templates",
    response_model=CloseTemplateDetail,
    status_code=status.HTTP_201_CREATED,
)
def create_financial_close_template(
    payload: CloseTemplateCreate,
    token: Token,
) -> CloseTemplateDetail:
    try:
        return financial_close_service.create_template(token, payload)
    except (
        WorkflowAuthenticationRequired,
        FinancialCloseConflict,
        FinancialCloseIntegrityError,
        FinancialCloseNotFound,
        FinancialClosePermissionDenied,
        FinancialCloseValidationError,
    ) as exc:
        _raise_financial_close_error(exc)
        raise AssertionError("unreachable")


@router.get("/templates/{template_id}", response_model=CloseTemplateDetail)
def get_financial_close_template(
    token: Token,
    template_id: str = TemplateId,
) -> CloseTemplateDetail:
    try:
        return financial_close_service.get_template(token, template_id)
    except (
        WorkflowAuthenticationRequired,
        FinancialCloseIntegrityError,
        FinancialCloseNotFound,
    ) as exc:
        _raise_financial_close_error(exc)
        raise AssertionError("unreachable")


@router.post(
    "/templates/{template_id}/versions",
    response_model=CloseTemplateDetail,
    status_code=status.HTTP_201_CREATED,
)
def create_financial_close_template_version(
    payload: CloseTemplateVersionCreate,
    token: Token,
    template_id: str = TemplateId,
) -> CloseTemplateDetail:
    try:
        return financial_close_service.create_template_version(
            token,
            template_id,
            payload,
        )
    except (
        WorkflowAuthenticationRequired,
        FinancialCloseConflict,
        FinancialCloseIntegrityError,
        FinancialCloseNotFound,
        FinancialClosePermissionDenied,
        FinancialCloseValidationError,
    ) as exc:
        _raise_financial_close_error(exc)
        raise AssertionError("unreachable")


@router.post(
    "/templates/{template_id}/versions/{template_version}/instantiate",
    response_model=CloseCycleDetail,
    status_code=status.HTTP_201_CREATED,
)
def instantiate_financial_close_template(
    payload: CloseTemplateInstantiate,
    token: Token,
    template_id: str = TemplateId,
    template_version: int = TemplateVersion,
) -> CloseCycleDetail:
    try:
        return financial_close_service.instantiate_template(
            token,
            template_id,
            template_version,
            payload,
        )
    except (
        WorkflowAuthenticationRequired,
        FinancialCloseConflict,
        FinancialCloseIntegrityError,
        FinancialCloseNotFound,
        FinancialClosePermissionDenied,
        FinancialCloseValidationError,
    ) as exc:
        _raise_financial_close_error(exc)
        raise AssertionError("unreachable")


@router.get("/cycles", response_model=CloseCycleListResponse)
def list_financial_close_cycles(token: Token) -> CloseCycleListResponse:
    try:
        return financial_close_service.list_cycles(token)
    except (
        WorkflowAuthenticationRequired,
        FinancialCloseIntegrityError,
    ) as exc:
        _raise_financial_close_error(exc)
        raise AssertionError("unreachable")


@router.post(
    "/cycles",
    response_model=CloseCycleDetail,
    status_code=status.HTTP_201_CREATED,
)
def create_financial_close_cycle(
    payload: CloseCycleCreate,
    token: Token,
) -> CloseCycleDetail:
    try:
        return financial_close_service.create_cycle(token, payload)
    except (
        WorkflowAuthenticationRequired,
        FinancialCloseConflict,
        FinancialCloseIntegrityError,
        FinancialClosePermissionDenied,
        FinancialCloseValidationError,
    ) as exc:
        _raise_financial_close_error(exc)
        raise AssertionError("unreachable")


@router.get("/cycles/{cycle_id}", response_model=CloseCycleDetail)
def get_financial_close_cycle(
    token: Token,
    cycle_id: str = CycleId,
) -> CloseCycleDetail:
    try:
        return financial_close_service.get_cycle(token, cycle_id)
    except (
        WorkflowAuthenticationRequired,
        FinancialCloseIntegrityError,
        FinancialCloseNotFound,
    ) as exc:
        _raise_financial_close_error(exc)
        raise AssertionError("unreachable")


@router.post(
    "/cycles/{cycle_id}/controls",
    response_model=CloseControlSummary,
    status_code=status.HTTP_201_CREATED,
)
def create_financial_close_control(
    payload: CloseControlCreate,
    token: Token,
    cycle_id: str = CycleId,
) -> CloseControlSummary:
    try:
        return financial_close_service.create_control(token, cycle_id, payload)
    except (
        WorkflowAuthenticationRequired,
        FinancialCloseConflict,
        FinancialCloseIntegrityError,
        FinancialCloseNotFound,
        FinancialClosePermissionDenied,
        FinancialCloseValidationError,
    ) as exc:
        _raise_financial_close_error(exc)
        raise AssertionError("unreachable")


@router.post(
    "/cycles/{cycle_id}/controls/{control_id}/preparations",
    response_model=CloseControlSummary,
    status_code=status.HTTP_201_CREATED,
)
def create_financial_close_preparation(
    payload: ClosePreparationCreate,
    token: Token,
    cycle_id: str = CycleId,
    control_id: str = ControlId,
) -> CloseControlSummary:
    try:
        return financial_close_service.create_preparation(
            token,
            cycle_id,
            control_id,
            payload,
        )
    except (
        WorkflowAuthenticationRequired,
        FinancialCloseConflict,
        FinancialCloseIntegrityError,
        FinancialCloseNotFound,
        FinancialClosePermissionDenied,
        FinancialCloseValidationError,
    ) as exc:
        _raise_financial_close_error(exc)
        raise AssertionError("unreachable")


@router.post(
    "/cycles/{cycle_id}/controls/{control_id}/reviews",
    response_model=CloseControlSummary,
    status_code=status.HTTP_201_CREATED,
)
def create_financial_close_review(
    payload: CloseReviewCreate,
    token: Token,
    cycle_id: str = CycleId,
    control_id: str = ControlId,
) -> CloseControlSummary:
    try:
        return financial_close_service.create_review(
            token,
            cycle_id,
            control_id,
            payload,
        )
    except (
        WorkflowAuthenticationRequired,
        FinancialCloseConflict,
        FinancialCloseIntegrityError,
        FinancialCloseNotFound,
        FinancialClosePermissionDenied,
        FinancialCloseValidationError,
    ) as exc:
        _raise_financial_close_error(exc)
        raise AssertionError("unreachable")


@router.get(
    "/cycles/{cycle_id}/controls/{control_id}/events",
    response_model=CloseControlEventList,
)
def get_financial_close_control_events(
    token: Token,
    cycle_id: str = CycleId,
    control_id: str = ControlId,
) -> CloseControlEventList:
    try:
        return financial_close_service.get_control_events(
            token,
            cycle_id,
            control_id,
        )
    except (
        WorkflowAuthenticationRequired,
        FinancialCloseIntegrityError,
        FinancialCloseNotFound,
    ) as exc:
        _raise_financial_close_error(exc)
        raise AssertionError("unreachable")


__all__ = ["router"]
