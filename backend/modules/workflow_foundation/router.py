from __future__ import annotations

import os
from typing import Annotated, Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, Response, status

from .repository import WorkflowFoundationConflict, WorkflowFoundationNotFound
from .schemas import (
    AdminPasswordSet,
    AuditEventListResponse,
    AuditIntegrityResponse,
    AuthSessionResponse,
    BootstrapRequest,
    BootstrapStatus,
    CurrentSessionResponse,
    InvitationActivationRequest,
    InvitationCreate,
    InvitationCreateResponse,
    InvitationListResponse,
    InvitationPreview,
    InvitationRevokeRequest,
    InvitationSummary,
    InvitationTokenRequest,
    LoginRequest,
    ModuleAccessReplace,
    ModuleSummary,
    NotificationListResponse,
    NotificationSummary,
    PasswordResetActivationRequest,
    PasswordResetCreateResponse,
    PasswordResetPreview,
    PasswordResetTokenRequest,
    RoleSummary,
    SecurityUserListResponse,
    SecurityUserSummary,
    TaskAssignmentCreate,
    TaskCreate,
    TaskDetail,
    TaskListResponse,
    TaskTransitionCreate,
    UserCreate,
    UserListResponse,
    UserSummary,
    UserStatusChange,
    WorkflowDefinitionListResponse,
    WorkflowHealthResponse,
)
from .service import (
    WorkflowAuthenticationRequired,
    WorkflowPermissionDenied,
    WorkflowValidationError,
    workflow_foundation_service,
)


router = APIRouter(
    prefix="/api/v1/workflow-foundation",
    tags=["Identity, Assignment, and Governed Workflow Foundation"],
)


def _bearer_token(
    authorization: Annotated[str | None, Header()] = None,
) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "workflow_authentication_required",
                "message": "Sign in to the local workflow foundation.",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "workflow_authentication_required",
                "message": "Sign in to the local workflow foundation.",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token


Token = Annotated[str, Depends(_bearer_token)]
DEFAULT_SESSION_COOKIE_NAME = "etop_local_session"


def _session_cookie_name() -> str:
    value = os.getenv("ETOP_COOKIE_NAME", DEFAULT_SESSION_COOKIE_NAME)
    if not value or not value.replace("_", "a").replace("-", "a").isalnum():
        raise RuntimeError("ETOP_COOKIE_NAME must contain only letters, digits, '_' or '-'.")
    return value


def _session_cookie_domain() -> str | None:
    return os.getenv("ETOP_COOKIE_DOMAIN") or None


def _session_cookie_secure() -> bool:
    return urlsplit(
        os.getenv("ETOP_APP_URL", "http://127.0.0.1:5173")
    ).scheme == "https"


def _set_session_cookie(response: Response, session: AuthSessionResponse) -> None:
    response.set_cookie(
        key=_session_cookie_name(),
        value=session.token,
        max_age=12 * 60 * 60,
        httponly=True,
        secure=_session_cookie_secure(),
        samesite="strict",
        path="/",
        domain=_session_cookie_domain(),
    )


def _raise_workflow_error(exc: Exception) -> None:
    if isinstance(exc, WorkflowAuthenticationRequired):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "workflow_authentication_required", "message": str(exc)},
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    if isinstance(exc, WorkflowPermissionDenied):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "workflow_permission_denied", "message": str(exc)},
        ) from exc
    if isinstance(exc, WorkflowFoundationNotFound):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "workflow_record_not_found", "message": str(exc)},
        ) from exc
    if isinstance(exc, WorkflowFoundationConflict):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "workflow_conflict", "message": str(exc)},
        ) from exc
    if isinstance(exc, WorkflowValidationError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "workflow_validation_error", "message": str(exc)},
        ) from exc
    raise exc


@router.get("/bootstrap-status", response_model=BootstrapStatus)
def get_bootstrap_status() -> BootstrapStatus:
    return workflow_foundation_service.bootstrap_status()


@router.post(
    "/bootstrap",
    response_model=AuthSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
def bootstrap_local_identity(
    payload: BootstrapRequest,
    response: Response,
) -> AuthSessionResponse:
    try:
        session = workflow_foundation_service.bootstrap(payload)
        _set_session_cookie(response, session)
        return session
    except (WorkflowFoundationConflict, WorkflowValidationError) as exc:
        _raise_workflow_error(exc)
        raise AssertionError("unreachable")


@router.post("/sessions", response_model=AuthSessionResponse)
def create_local_session(
    payload: LoginRequest,
    response: Response,
) -> AuthSessionResponse:
    try:
        session = workflow_foundation_service.login(payload)
        _set_session_cookie(response, session)
        return session
    except WorkflowAuthenticationRequired as exc:
        _raise_workflow_error(exc)
        raise AssertionError("unreachable")


@router.post("/invitations/preview", response_model=InvitationPreview)
def preview_local_invitation(payload: InvitationTokenRequest) -> InvitationPreview:
    try:
        return workflow_foundation_service.preview_invitation(payload)
    except (WorkflowFoundationNotFound, WorkflowFoundationConflict) as exc:
        _raise_workflow_error(exc)
        raise AssertionError("unreachable")


@router.post(
    "/invitations/activate",
    response_model=AuthSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
def activate_local_invitation(
    payload: InvitationActivationRequest,
    response: Response,
) -> AuthSessionResponse:
    try:
        session = workflow_foundation_service.activate_invitation(payload)
        _set_session_cookie(response, session)
        return session
    except (
        WorkflowFoundationNotFound,
        WorkflowFoundationConflict,
        WorkflowValidationError,
    ) as exc:
        _raise_workflow_error(exc)
        raise AssertionError("unreachable")


@router.post("/password-reset/preview", response_model=PasswordResetPreview)
def preview_local_password_reset(payload: PasswordResetTokenRequest) -> PasswordResetPreview:
    try:
        return workflow_foundation_service.preview_password_reset(payload)
    except (WorkflowFoundationNotFound, WorkflowFoundationConflict) as exc:
        _raise_workflow_error(exc)
        raise AssertionError("unreachable")


@router.post(
    "/password-reset/activate",
    response_model=AuthSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
def activate_local_password_reset(
    payload: PasswordResetActivationRequest,
    response: Response,
) -> AuthSessionResponse:
    try:
        session = workflow_foundation_service.activate_password_reset(payload)
        _set_session_cookie(response, session)
        return session
    except (
        WorkflowFoundationNotFound,
        WorkflowFoundationConflict,
        WorkflowValidationError,
    ) as exc:
        _raise_workflow_error(exc)
        raise AssertionError("unreachable")


@router.get("/session", response_model=CurrentSessionResponse)
def get_current_session(token: Token) -> CurrentSessionResponse:
    try:
        return workflow_foundation_service.current_session(token)
    except WorkflowAuthenticationRequired as exc:
        _raise_workflow_error(exc)
        raise AssertionError("unreachable")


@router.delete("/session", status_code=status.HTTP_204_NO_CONTENT)
def delete_current_session(token: Token) -> Response:
    try:
        workflow_foundation_service.logout(token)
    except WorkflowAuthenticationRequired as exc:
        _raise_workflow_error(exc)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(
        _session_cookie_name(),
        path="/",
        domain=_session_cookie_domain(),
        httponly=True,
        samesite="strict",
        secure=_session_cookie_secure(),
    )
    return response


@router.get("/health", response_model=WorkflowHealthResponse)
def get_workflow_health(token: Token) -> WorkflowHealthResponse:
    try:
        return workflow_foundation_service.health(token)
    except (WorkflowAuthenticationRequired, WorkflowPermissionDenied) as exc:
        _raise_workflow_error(exc)
        raise AssertionError("unreachable")


@router.get("/users", response_model=UserListResponse)
def list_users(token: Token) -> UserListResponse:
    try:
        return workflow_foundation_service.list_users(token)
    except WorkflowAuthenticationRequired as exc:
        _raise_workflow_error(exc)
        raise AssertionError("unreachable")


@router.post(
    "/users",
    response_model=UserSummary,
    status_code=status.HTTP_201_CREATED,
)
def create_user(payload: UserCreate, token: Token) -> UserSummary:
    try:
        return workflow_foundation_service.create_user(token, payload)
    except (
        WorkflowAuthenticationRequired,
        WorkflowFoundationConflict,
        WorkflowPermissionDenied,
        WorkflowValidationError,
    ) as exc:
        _raise_workflow_error(exc)
        raise AssertionError("unreachable")


@router.get("/security/modules", response_model=list[ModuleSummary])
def list_security_modules(token: Token) -> list[ModuleSummary]:
    try:
        return workflow_foundation_service.module_catalog(token)
    except (WorkflowAuthenticationRequired, WorkflowPermissionDenied) as exc:
        _raise_workflow_error(exc)
        raise AssertionError("unreachable")


@router.get("/security/users", response_model=SecurityUserListResponse)
def list_security_users(token: Token) -> SecurityUserListResponse:
    try:
        return workflow_foundation_service.security_users(token)
    except (WorkflowAuthenticationRequired, WorkflowPermissionDenied) as exc:
        _raise_workflow_error(exc)
        raise AssertionError("unreachable")


@router.put(
    "/security/users/{user_id}/modules",
    response_model=SecurityUserSummary,
)
def replace_security_user_modules(
    payload: ModuleAccessReplace,
    token: Token,
    user_id: str = Path(min_length=5, max_length=80, pattern=r"^USR-[A-Za-z0-9_-]+$"),
) -> SecurityUserSummary:
    try:
        return workflow_foundation_service.replace_user_module_access(
            token, user_id, payload
        )
    except (
        WorkflowAuthenticationRequired,
        WorkflowFoundationConflict,
        WorkflowFoundationNotFound,
        WorkflowPermissionDenied,
        WorkflowValidationError,
    ) as exc:
        _raise_workflow_error(exc)
        raise AssertionError("unreachable")


@router.patch(
    "/security/users/{user_id}/status",
    response_model=SecurityUserSummary,
)
def change_security_user_status(
    payload: UserStatusChange,
    token: Token,
    user_id: str = Path(min_length=5, max_length=80, pattern=r"^USR-[A-Za-z0-9_-]+$"),
) -> SecurityUserSummary:
    try:
        return workflow_foundation_service.change_user_status(token, user_id, payload)
    except (
        WorkflowAuthenticationRequired,
        WorkflowFoundationConflict,
        WorkflowFoundationNotFound,
        WorkflowPermissionDenied,
        WorkflowValidationError,
    ) as exc:
        _raise_workflow_error(exc)
        raise AssertionError("unreachable")


@router.post(
    "/security/users/{user_id}/password-reset",
    response_model=PasswordResetCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_security_password_reset(
    token: Token,
    user_id: str = Path(min_length=5, max_length=80, pattern=r"^USR-[A-Za-z0-9_-]+$"),
) -> PasswordResetCreateResponse:
    try:
        return workflow_foundation_service.request_password_reset(token, user_id)
    except (
        WorkflowAuthenticationRequired,
        WorkflowFoundationNotFound,
        WorkflowPermissionDenied,
    ) as exc:
        _raise_workflow_error(exc)
        raise AssertionError("unreachable")


@router.put(
    "/security/users/{user_id}/password",
    response_model=SecurityUserSummary,
)
def set_security_user_password(
    payload: AdminPasswordSet,
    token: Token,
    user_id: str = Path(min_length=5, max_length=80, pattern=r"^USR-[A-Za-z0-9_-]+$"),
) -> SecurityUserSummary:
    try:
        return workflow_foundation_service.set_user_password(token, user_id, payload)
    except (
        WorkflowAuthenticationRequired,
        WorkflowFoundationConflict,
        WorkflowFoundationNotFound,
        WorkflowPermissionDenied,
    ) as exc:
        _raise_workflow_error(exc)
        raise AssertionError("unreachable")


@router.get("/security/invitations", response_model=InvitationListResponse)
def list_security_invitations(token: Token) -> InvitationListResponse:
    try:
        return workflow_foundation_service.invitations(token)
    except (WorkflowAuthenticationRequired, WorkflowPermissionDenied) as exc:
        _raise_workflow_error(exc)
        raise AssertionError("unreachable")


@router.post(
    "/security/invitations",
    response_model=InvitationCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_security_invitation(
    payload: InvitationCreate,
    token: Token,
) -> InvitationCreateResponse:
    try:
        return workflow_foundation_service.create_invitation(token, payload)
    except (
        WorkflowAuthenticationRequired,
        WorkflowFoundationConflict,
        WorkflowPermissionDenied,
        WorkflowValidationError,
    ) as exc:
        _raise_workflow_error(exc)
        raise AssertionError("unreachable")


@router.post(
    "/security/invitations/{invitation_id}/revoke",
    response_model=InvitationSummary,
)
def revoke_security_invitation(
    payload: InvitationRevokeRequest,
    token: Token,
    invitation_id: str = Path(
        min_length=5,
        max_length=80,
        pattern=r"^INV-[A-Za-z0-9_-]+$",
    ),
) -> InvitationSummary:
    try:
        return workflow_foundation_service.revoke_invitation(
            token, invitation_id, payload
        )
    except (
        WorkflowAuthenticationRequired,
        WorkflowFoundationConflict,
        WorkflowFoundationNotFound,
        WorkflowPermissionDenied,
        WorkflowValidationError,
    ) as exc:
        _raise_workflow_error(exc)
        raise AssertionError("unreachable")


@router.get("/roles", response_model=list[RoleSummary])
def list_roles(token: Token) -> list[RoleSummary]:
    try:
        return workflow_foundation_service.list_roles(token)
    except WorkflowAuthenticationRequired as exc:
        _raise_workflow_error(exc)
        raise AssertionError("unreachable")


@router.get("/definitions", response_model=WorkflowDefinitionListResponse)
def list_definitions(token: Token) -> WorkflowDefinitionListResponse:
    try:
        return workflow_foundation_service.list_definitions(token)
    except WorkflowAuthenticationRequired as exc:
        _raise_workflow_error(exc)
        raise AssertionError("unreachable")


@router.get("/tasks", response_model=TaskListResponse)
def list_tasks(
    token: Token,
    mine: bool = Query(default=False),
    capability: Literal[
        "credit_risk", "accounts_payable", "lockbox", "reporting", "platform"
    ]
    | None = Query(default=None),
    state_filter: Literal[
        "open", "in_progress", "deferred", "completed", "cancelled", "reopened"
    ]
    | None = Query(default=None, alias="state"),
) -> TaskListResponse:
    try:
        return workflow_foundation_service.list_tasks(
            token, mine=mine, capability=capability, state=state_filter
        )
    except WorkflowAuthenticationRequired as exc:
        _raise_workflow_error(exc)
        raise AssertionError("unreachable")


@router.post(
    "/tasks",
    response_model=TaskDetail,
    status_code=status.HTTP_201_CREATED,
)
def create_task(payload: TaskCreate, token: Token) -> TaskDetail:
    try:
        return workflow_foundation_service.create_task(token, payload)
    except (
        WorkflowAuthenticationRequired,
        WorkflowFoundationConflict,
        WorkflowFoundationNotFound,
        WorkflowPermissionDenied,
        WorkflowValidationError,
    ) as exc:
        _raise_workflow_error(exc)
        raise AssertionError("unreachable")


@router.get("/tasks/{task_id}", response_model=TaskDetail)
def get_task(
    token: Token,
    task_id: str = Path(min_length=5, max_length=80, pattern=r"^TSK-[A-Za-z0-9-]+$"),
) -> TaskDetail:
    try:
        return workflow_foundation_service.get_task(token, task_id)
    except (
        WorkflowAuthenticationRequired,
        WorkflowFoundationNotFound,
        WorkflowPermissionDenied,
    ) as exc:
        _raise_workflow_error(exc)
        raise AssertionError("unreachable")


@router.post("/tasks/{task_id}/assignments", response_model=TaskDetail)
def assign_task(
    payload: TaskAssignmentCreate,
    token: Token,
    task_id: str = Path(min_length=5, max_length=80, pattern=r"^TSK-[A-Za-z0-9-]+$"),
) -> TaskDetail:
    try:
        return workflow_foundation_service.assign_task(token, task_id, payload)
    except (
        WorkflowAuthenticationRequired,
        WorkflowFoundationConflict,
        WorkflowFoundationNotFound,
        WorkflowPermissionDenied,
        WorkflowValidationError,
    ) as exc:
        _raise_workflow_error(exc)
        raise AssertionError("unreachable")


@router.post("/tasks/{task_id}/transitions", response_model=TaskDetail)
def transition_task(
    payload: TaskTransitionCreate,
    token: Token,
    task_id: str = Path(min_length=5, max_length=80, pattern=r"^TSK-[A-Za-z0-9-]+$"),
) -> TaskDetail:
    try:
        return workflow_foundation_service.transition_task(token, task_id, payload)
    except (
        WorkflowAuthenticationRequired,
        WorkflowFoundationConflict,
        WorkflowFoundationNotFound,
        WorkflowPermissionDenied,
    ) as exc:
        _raise_workflow_error(exc)
        raise AssertionError("unreachable")


@router.get("/notifications", response_model=NotificationListResponse)
def list_notifications(token: Token) -> NotificationListResponse:
    try:
        return workflow_foundation_service.notifications(token)
    except WorkflowAuthenticationRequired as exc:
        _raise_workflow_error(exc)
        raise AssertionError("unreachable")


@router.post(
    "/notifications/{notification_id}/read",
    response_model=NotificationSummary,
)
def mark_notification_read(
    token: Token,
    notification_id: str = Path(
        min_length=5, max_length=80, pattern=r"^NTF-[A-Za-z0-9-]+$"
    ),
) -> NotificationSummary:
    try:
        return workflow_foundation_service.mark_notification_read(token, notification_id)
    except (WorkflowAuthenticationRequired, WorkflowFoundationNotFound) as exc:
        _raise_workflow_error(exc)
        raise AssertionError("unreachable")


@router.get("/audit", response_model=AuditEventListResponse)
def list_audit_events(
    token: Token,
    subject_type: str | None = Query(default=None, max_length=80),
    subject_id: str | None = Query(default=None, max_length=160),
    limit: int = Query(default=250, ge=1, le=500),
) -> AuditEventListResponse:
    try:
        return workflow_foundation_service.audit_events(
            token, subject_type=subject_type, subject_id=subject_id, limit=limit
        )
    except (WorkflowAuthenticationRequired, WorkflowPermissionDenied) as exc:
        _raise_workflow_error(exc)
        raise AssertionError("unreachable")


@router.get("/audit/integrity", response_model=AuditIntegrityResponse)
def verify_audit_integrity(token: Token) -> AuditIntegrityResponse:
    try:
        return workflow_foundation_service.verify_audit(token)
    except (WorkflowAuthenticationRequired, WorkflowPermissionDenied) as exc:
        _raise_workflow_error(exc)
        raise AssertionError("unreachable")
