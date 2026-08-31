from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit

from .repository import (
    WorkflowFoundationConflict,
    WorkflowFoundationNotFound,
    WorkflowFoundationRepository,
)
from .schemas import (
    AdminPasswordSet,
    AuditEventListResponse,
    AuditIntegrityResponse,
    AuthSessionResponse,
    BootstrapRequest,
    BootstrapStatus,
    CurrentSessionResponse,
    EffectivePermissions,
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
    TaskSummary,
    TaskTransitionCreate,
    UserCreate,
    UserListResponse,
    UserSummary,
    UserStatusChange,
    WorkflowDefinitionListResponse,
    WorkflowHealthResponse,
)


AUTHORITY_BOUNDARY = (
    "Authenticated identity and work assignment establish accountability only. "
    "They do not grant credit, invoice, payment, posting, order, cash-application, "
    "or ERP decision authority."
)
AUTHENTICATION_BOUNDARY = (
    "Credentials authenticate an account to this local ETOP instance only; "
    "enterprise identity-provider and multi-machine assurance are not connected."
)


class WorkflowAuthenticationRequired(PermissionError):
    pass


class WorkflowPermissionDenied(PermissionError):
    pass


class WorkflowValidationError(ValueError):
    pass


class WorkflowFoundationService:
    SESSION_HOURS = 12
    PASSWORD_RESET_HOURS = 24

    def __init__(
        self,
        repository: WorkflowFoundationRepository | None = None,
        clock: Callable[[], datetime] | None = None,
        token_factory: Callable[[], str] | None = None,
        invitation_token_factory: Callable[[], str] | None = None,
        app_url: str | None = None,
        session_signing_secret: str | None = None,
        session_namespace: str | None = None,
    ) -> None:
        self.repository = repository or WorkflowFoundationRepository()
        self._clock = clock or (lambda: datetime.now(UTC))
        self._token_factory = token_factory or (lambda: secrets.token_urlsafe(32))
        self._invitation_token_factory = invitation_token_factory or (
            lambda: secrets.token_urlsafe(32)
        )
        self._app_url = self._validated_app_url(
            app_url or os.getenv("ETOP_APP_URL", "http://127.0.0.1:5173")
        )
        configured_secret = (
            session_signing_secret
            if session_signing_secret is not None
            else os.getenv("ETOP_SESSION_SIGNING_SECRET")
        )
        if configured_secret and len(configured_secret) < 32:
            raise ValueError("ETOP_SESSION_SIGNING_SECRET must contain at least 32 characters.")
        self._session_signing_secret = (
            configured_secret.encode("utf-8") if configured_secret else None
        )
        self._session_namespace = (
            session_namespace
            if session_namespace is not None
            else os.getenv("ETOP_SESSION_NAMESPACE", "etop-local")
        )
        self.repository.initialize()

    @staticmethod
    def _validated_app_url(value: str) -> str:
        parsed = urlsplit(value.strip())
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "ETOP_APP_URL must be an http(s) application origin without credentials, query, or fragment."
            )
        path = parsed.path.rstrip("/")
        return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))

    @staticmethod
    def _password_digest(password: str, salt: bytes) -> str:
        return hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=2**14,
            r=8,
            p=1,
            dklen=32,
        ).hex()

    @classmethod
    def _password_record(cls, password: str) -> tuple[str, str]:
        salt = secrets.token_bytes(16)
        return salt.hex(), cls._password_digest(password, salt)

    @staticmethod
    def _token_hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def _session_token_hash(self, token: str) -> str:
        if self._session_signing_secret is None:
            # Compatibility for existing local installs that have not configured
            # isolated environment signing yet.
            return self._token_hash(token)
        namespaced_token = f"{self._session_namespace}\0{token}".encode("utf-8")
        return hmac.new(
            self._session_signing_secret,
            namespaced_token,
            hashlib.sha256,
        ).hexdigest()

    def bootstrap_status(self) -> BootstrapStatus:
        result = self.repository.bootstrap_status()
        return BootstrapStatus(
            **result,
            authentication_boundary=AUTHENTICATION_BOUNDARY,
            authority_boundary=AUTHORITY_BOUNDARY,
        )

    def bootstrap(self, payload: BootstrapRequest) -> AuthSessionResponse:
        salt, password_hash = self._password_record(payload.password)
        user_id = self.repository.bootstrap_user(
            username=payload.username,
            display_name=payload.display_name,
            password_salt=salt,
            password_hash=password_hash,
        )
        return self._issue_session(user_id)

    def login(self, payload: LoginRequest) -> AuthSessionResponse:
        account = self.repository.get_account_credentials(payload.username)
        invalid = WorkflowAuthenticationRequired(
            "The username or password was not recognized by this local ETOP instance."
        )
        if account is None or account["status"] != "active":
            raise invalid
        try:
            salt = bytes.fromhex(account["password_salt"])
            candidate = self._password_digest(payload.password, salt)
        except (TypeError, ValueError):
            raise invalid from None
        if not secrets.compare_digest(candidate, account["password_hash"]):
            raise invalid
        return self._issue_session(account["user_id"])

    def _issue_session(self, user_id: str) -> AuthSessionResponse:
        token = self._token_factory()
        now = self._clock()
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)
        expires_at = now.astimezone(UTC) + timedelta(hours=self.SESSION_HOURS)
        self.repository.create_session(
            user_id=user_id,
            token_hash=self._session_token_hash(token),
            expires_at=expires_at.isoformat(),
        )
        return AuthSessionResponse(
            token=token,
            expires_at=expires_at,
            user=UserSummary.model_validate(self.repository.get_user(user_id)),
            permissions=EffectivePermissions.model_validate(
                self.repository.get_permissions(user_id)
            ),
            authority_boundary=AUTHORITY_BOUNDARY,
        )

    def session_for_token(self, token: str) -> dict[str, Any]:
        if not token:
            raise WorkflowAuthenticationRequired("Sign in to the local workflow foundation.")
        session = self.repository.get_session(self._session_token_hash(token))
        if session is None:
            raise WorkflowAuthenticationRequired(
                "The local workflow session is missing, expired, or signed out."
            )
        return session

    def current_session(self, token: str) -> CurrentSessionResponse:
        session = self.session_for_token(token)
        return CurrentSessionResponse(
            expires_at=session["expires_at"],
            user=UserSummary.model_validate(session["user"]),
            permissions=EffectivePermissions.model_validate(
                self.repository.get_permissions(session["user"]["user_id"])
            ),
            authority_boundary=AUTHORITY_BOUNDARY,
        )

    def logout(self, token: str) -> None:
        session = self.session_for_token(token)
        self.repository.revoke_session(
            self._session_token_hash(token), session["user"]["user_id"]
        )

    @staticmethod
    def _role_ids(user: dict[str, Any]) -> set[str]:
        return {role["role_id"] for role in user["roles"]}

    def _require_coordinator(self, session: dict[str, Any]) -> None:
        if "workflow_coordinator" not in self._role_ids(session["user"]):
            raise WorkflowPermissionDenied(
                "Workflow Coordinator is required. This permission still grants no financial decision authority."
            )

    def authorize_module_access(
        self,
        token: str,
        acceptable_module_ids: tuple[str, ...] | list[str],
    ) -> dict[str, Any]:
        session = self.session_for_token(token)
        permissions = self.repository.get_permissions(session["user"]["user_id"])
        allowed = set(permissions["module_ids"])
        if not allowed.intersection(acceptable_module_ids):
            raise WorkflowPermissionDenied(
                "This account does not have access to the requested ETOP module. "
                "Module access grants no financial decision authority."
            )
        return session

    def _require_security_administrator(self, token: str) -> dict[str, Any]:
        session = self.authorize_module_access(token, ("security_administration",))
        self._require_coordinator(session)
        return session

    def list_users(self, token: str) -> UserListResponse:
        self._require_security_administrator(token)
        return UserListResponse(
            users=[UserSummary.model_validate(item) for item in self.repository.list_users()],
            authority_boundary=AUTHORITY_BOUNDARY,
        )

    def create_user(self, token: str, payload: UserCreate) -> UserSummary:
        session = self._require_security_administrator(token)
        role_ids = sorted(set(payload.role_ids))
        if not role_ids:
            raise WorkflowValidationError("At least one operational workflow role is required.")
        salt, password_hash = self._password_record(payload.password)
        result = self.repository.create_user(
            username=payload.username,
            display_name=payload.display_name,
            password_salt=salt,
            password_hash=password_hash,
            role_ids=role_ids,
            module_ids=sorted(set(payload.module_ids)),
            actor_user_id=session["user"]["user_id"],
        )
        return UserSummary.model_validate(result)

    def module_catalog(self, token: str) -> list[ModuleSummary]:
        self._require_security_administrator(token)
        return [
            ModuleSummary.model_validate(item)
            for item in self.repository.list_modules()
        ]

    def security_users(self, token: str) -> SecurityUserListResponse:
        self._require_security_administrator(token)
        return SecurityUserListResponse(
            users=[
                SecurityUserSummary.model_validate(item)
                for item in self.repository.list_security_users()
            ],
            modules=[
                ModuleSummary.model_validate(item)
                for item in self.repository.list_modules()
            ],
            authority_boundary=AUTHORITY_BOUNDARY,
        )

    def create_invitation(
        self,
        token: str,
        payload: InvitationCreate,
    ) -> InvitationCreateResponse:
        session = self._require_security_administrator(token)
        role_ids = sorted(set(payload.role_ids))
        module_ids = sorted(set(payload.module_ids))
        if (
            "security_administration" in module_ids
            and "workflow_coordinator" not in role_ids
        ):
            raise WorkflowValidationError(
                "Security & Access requires the Workflow Coordinator operational role. "
                "Neither setting grants financial decision authority."
            )
        invitation_token = self._invitation_token_factory()
        if len(invitation_token) < 32:
            raise RuntimeError("The configured invitation-token generator is too weak.")
        now = self._clock()
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)
        expires_at = now.astimezone(UTC) + timedelta(
            hours=payload.expires_in_hours
        )
        invitation = self.repository.create_invitation(
            username=payload.username,
            display_name=payload.display_name,
            token_hash=self._token_hash(invitation_token),
            role_ids=role_ids,
            module_ids=module_ids,
            expires_at=expires_at.isoformat(),
            actor_user_id=session["user"]["user_id"],
        )
        invitation_link = (
            f"{self._app_url}/#invite={quote(invitation_token, safe='-_')}"
        )
        return InvitationCreateResponse(
            **invitation,
            invitation_link=invitation_link,
            link_displayed_once=True,
        )

    def invitations(self, token: str) -> InvitationListResponse:
        self._require_security_administrator(token)
        return InvitationListResponse(
            items=[
                InvitationSummary.model_validate(item)
                for item in self.repository.list_invitations()
            ]
        )

    def revoke_invitation(
        self,
        token: str,
        invitation_id: str,
        payload: InvitationRevokeRequest,
    ) -> InvitationSummary:
        session = self._require_security_administrator(token)
        if payload.expected_status != "pending":
            raise WorkflowValidationError(
                "Invitation revocation requires the expected pending state."
            )
        return InvitationSummary.model_validate(
            self.repository.revoke_invitation(
                invitation_id=invitation_id,
                actor_user_id=session["user"]["user_id"],
            )
        )

    def preview_invitation(
        self,
        payload: InvitationTokenRequest,
    ) -> InvitationPreview:
        invitation = self.repository.invitation_for_token_hash(
            self._token_hash(payload.token)
        )
        if invitation is None:
            raise WorkflowFoundationNotFound(
                "The invitation token was not recognized by this local ETOP instance."
            )
        if invitation["status"] != "pending":
            raise WorkflowFoundationConflict(
                "This invitation is expired, revoked, or has already been activated."
            )
        return InvitationPreview(
            username=invitation["username"],
            display_name=invitation["display_name"],
            expires_at=invitation["expires_at"],
            status="pending",
        )

    def activate_invitation(
        self,
        payload: InvitationActivationRequest,
    ) -> AuthSessionResponse:
        salt, password_hash = self._password_record(payload.password)
        user_id = self.repository.activate_invitation(
            token_hash=self._token_hash(payload.token),
            password_salt=salt,
            password_hash=password_hash,
        )
        return self._issue_session(user_id)

    def request_password_reset(
        self,
        token: str,
        user_id: str,
    ) -> PasswordResetCreateResponse:
        session = self._require_security_administrator(token)
        reset_token = self._invitation_token_factory()
        if len(reset_token) < 32:
            raise RuntimeError("The configured invitation-token generator is too weak.")
        now = self._clock()
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)
        expires_at = now.astimezone(UTC) + timedelta(hours=self.PASSWORD_RESET_HOURS)
        reset = self.repository.create_password_reset(
            user_id=user_id,
            token_hash=self._token_hash(reset_token),
            expires_at=expires_at.isoformat(),
            actor_user_id=session["user"]["user_id"],
        )
        reset_link = f"{self._app_url}/#reset-password={quote(reset_token, safe='-_')}"
        return PasswordResetCreateResponse(
            reset_id=reset["reset_id"],
            user_id=reset["user_id"],
            status=reset["status"],
            expires_at=reset["expires_at"],
            reset_link=reset_link,
            link_displayed_once=True,
        )

    def preview_password_reset(
        self,
        payload: PasswordResetTokenRequest,
    ) -> PasswordResetPreview:
        reset = self.repository.password_reset_for_token_hash(
            self._token_hash(payload.token)
        )
        if reset is None:
            raise WorkflowFoundationNotFound(
                "The password reset token was not recognized by this local ETOP instance."
            )
        if reset["status"] != "pending":
            raise WorkflowFoundationConflict(
                "This password reset link is expired or has already been used."
            )
        target = self.repository.get_user(reset["user_id"])
        return PasswordResetPreview(
            username=target["username"],
            display_name=target["display_name"],
            expires_at=reset["expires_at"],
            status="pending",
        )

    def activate_password_reset(
        self,
        payload: PasswordResetActivationRequest,
    ) -> AuthSessionResponse:
        salt, password_hash = self._password_record(payload.password)
        user_id = self.repository.activate_password_reset(
            token_hash=self._token_hash(payload.token),
            password_salt=salt,
            password_hash=password_hash,
        )
        return self._issue_session(user_id)

    def set_user_password(
        self,
        token: str,
        user_id: str,
        payload: AdminPasswordSet,
    ) -> SecurityUserSummary:
        session = self._require_security_administrator(token)
        salt, password_hash = self._password_record(payload.new_password)
        return SecurityUserSummary.model_validate(
            self.repository.set_user_password(
                user_id=user_id,
                password_salt=salt,
                password_hash=password_hash,
                expected_version=payload.expected_version,
                actor_user_id=session["user"]["user_id"],
            )
        )

    def replace_user_module_access(
        self,
        token: str,
        user_id: str,
        payload: ModuleAccessReplace,
    ) -> SecurityUserSummary:
        session = self._require_security_administrator(token)
        actor_user_id = session["user"]["user_id"]
        if user_id == actor_user_id:
            raise WorkflowValidationError(
                "Use a different active Security & Access coordinator to change your own module access."
            )
        target = self.repository.get_user(user_id)
        target_roles = self._role_ids(target)
        module_ids = sorted(set(payload.module_ids))
        if (
            "security_administration" in module_ids
            and "workflow_coordinator" not in target_roles
        ):
            raise WorkflowValidationError(
                "Security & Access requires the Workflow Coordinator operational role."
            )
        return SecurityUserSummary.model_validate(
            self.repository.replace_module_access(
                user_id=user_id,
                module_ids=module_ids,
                expected_version=payload.expected_version,
                actor_user_id=actor_user_id,
            )
        )

    def change_user_status(
        self,
        token: str,
        user_id: str,
        payload: UserStatusChange,
    ) -> SecurityUserSummary:
        session = self._require_security_administrator(token)
        actor_user_id = session["user"]["user_id"]
        if user_id == actor_user_id:
            raise WorkflowValidationError(
                "A Security & Access coordinator cannot suspend or reactivate their own account."
            )
        return SecurityUserSummary.model_validate(
            self.repository.change_user_status(
                user_id=user_id,
                status=payload.status,
                expected_version=payload.expected_version,
                actor_user_id=actor_user_id,
            )
        )

    def list_roles(self, token: str) -> list[RoleSummary]:
        self.session_for_token(token)
        return [RoleSummary.model_validate(item) for item in self.repository.list_roles()]

    def list_definitions(self, token: str) -> WorkflowDefinitionListResponse:
        self.session_for_token(token)
        return WorkflowDefinitionListResponse(
            definitions=self.repository.list_definitions()
        )

    def _decorate_task(
        self,
        task: dict[str, Any],
        session: dict[str, Any],
    ) -> dict[str, Any]:
        actor = session["user"]
        actor_id = actor["user_id"]
        role_ids = self._role_ids(actor)
        coordinator = "workflow_coordinator" in role_ids
        assignee_id = task["assignee"]["user_id"] if task.get("assignee") else None
        permitted: list[str] = ["view"]
        if assignee_id is None and task["queue_role"]["role_id"] in role_ids:
            permitted.append("claim")
        if coordinator:
            permitted.append("assign")
        if coordinator or assignee_id == actor_id:
            permitted.extend(
                f"transition:{state}"
                for state in self.repository.TRANSITIONS.get(task["state"], [])
            )
        return {**task, "permitted_actions": permitted}

    def create_task(self, token: str, payload: TaskCreate) -> TaskDetail:
        session = self.session_for_token(token)
        role_ids = self._role_ids(session["user"])
        coordinator = "workflow_coordinator" in role_ids
        if payload.queue_role_id not in role_ids and not coordinator:
            raise WorkflowPermissionDenied(
                "A task may be created only in one of your operational role queues unless you are a Workflow Coordinator."
            )
        if payload.assignee_user_id and payload.assignee_user_id != session["user"]["user_id"]:
            self._require_coordinator(session)
        if payload.assignee_user_id:
            assignee = self.repository.get_user(payload.assignee_user_id)
            assignee_roles = self._role_ids(assignee)
            if payload.queue_role_id not in assignee_roles:
                raise WorkflowValidationError(
                    "The selected assignee does not hold the task's operational queue role."
                )
        result = self.repository.create_task(
            payload.model_dump(mode="json"), session["user"]["user_id"]
        )
        detail = self.repository.get_task(result["task_id"])
        return TaskDetail.model_validate(self._decorate_task(detail, session))

    def _task_visible(self, task: dict[str, Any], session: dict[str, Any]) -> bool:
        role_ids = self._role_ids(session["user"])
        if "workflow_coordinator" in role_ids:
            return True
        assignee = task.get("assignee")
        if assignee and assignee["user_id"] == session["user"]["user_id"]:
            return True
        return assignee is None and task["queue_role"]["role_id"] in role_ids

    def get_task(self, token: str, task_id: str) -> TaskDetail:
        session = self.session_for_token(token)
        task = self.repository.get_task(task_id)
        if not self._task_visible(task, session):
            raise WorkflowPermissionDenied("This task is outside your visible work queues.")
        return TaskDetail.model_validate(self._decorate_task(task, session))

    def list_tasks(
        self,
        token: str,
        *,
        mine: bool,
        capability: str | None,
        state: str | None,
    ) -> TaskListResponse:
        session = self.session_for_token(token)
        coordinator = "workflow_coordinator" in self._role_ids(session["user"])
        tasks = self.repository.list_tasks(
            actor_user_id=session["user"]["user_id"],
            coordinator=coordinator,
            mine=mine,
            capability=capability,
            state=state,
        )
        items = [
            TaskSummary.model_validate(self._decorate_task(task, session))
            for task in tasks
        ]
        return TaskListResponse(
            items=items,
            total=len(items),
            queue_scope="coordinator_all" if coordinator and not mine else "personal_and_role",
            authority_boundary=AUTHORITY_BOUNDARY,
        )

    def assign_task(
        self,
        token: str,
        task_id: str,
        payload: TaskAssignmentCreate,
    ) -> TaskDetail:
        session = self.session_for_token(token)
        task = self.repository.get_task(task_id)
        actor_id = session["user"]["user_id"]
        role_ids = self._role_ids(session["user"])
        coordinator = "workflow_coordinator" in role_ids
        current_assignee = task.get("assignee")
        claiming = current_assignee is None and payload.assignee_user_id == actor_id
        if claiming:
            if task["queue_role"]["role_id"] not in role_ids:
                raise WorkflowPermissionDenied("This task is outside your operational role queues.")
            assignment_type = "claim"
        else:
            if not coordinator:
                raise WorkflowPermissionDenied("Only a Workflow Coordinator may reassign work.")
            assignment_type = "reassign" if current_assignee else "initial"
        assignee = self.repository.get_user(payload.assignee_user_id)
        if task["queue_role"]["role_id"] not in self._role_ids(assignee):
            raise WorkflowValidationError(
                "The selected assignee does not hold the task's operational queue role."
            )
        result = self.repository.assign_task(
            task_id=task_id,
            assignee_user_id=payload.assignee_user_id,
            note=payload.note,
            expected_version=payload.expected_version,
            idempotency_key=payload.idempotency_key,
            actor_user_id=actor_id,
            assignment_type=assignment_type,
        )
        return TaskDetail.model_validate(self._decorate_task(result, session))

    def transition_task(
        self,
        token: str,
        task_id: str,
        payload: TaskTransitionCreate,
    ) -> TaskDetail:
        session = self.session_for_token(token)
        task = self.repository.get_task(task_id)
        actor_id = session["user"]["user_id"]
        coordinator = "workflow_coordinator" in self._role_ids(session["user"])
        assignee_id = task["assignee"]["user_id"] if task.get("assignee") else None
        if not coordinator and assignee_id != actor_id:
            raise WorkflowPermissionDenied(
                "Only the verified assignee or a Workflow Coordinator may transition this task."
            )
        result = self.repository.transition_task(
            task_id=task_id,
            target_state=payload.target_state,
            note=payload.note,
            expected_version=payload.expected_version,
            idempotency_key=payload.idempotency_key,
            actor_user_id=actor_id,
        )
        return TaskDetail.model_validate(self._decorate_task(result, session))

    def notifications(self, token: str) -> NotificationListResponse:
        session = self.session_for_token(token)
        items = [
            NotificationSummary.model_validate(item)
            for item in self.repository.list_notifications(session["user"]["user_id"])
        ]
        return NotificationListResponse(
            items=items,
            unread_count=sum(item.read_at is None for item in items),
            delivery_scope="in_app_local",
        )

    def mark_notification_read(
        self, token: str, notification_id: str
    ) -> NotificationSummary:
        session = self.session_for_token(token)
        result = self.repository.mark_notification_read(
            notification_id, session["user"]["user_id"]
        )
        return NotificationSummary.model_validate(result)

    def audit_events(
        self,
        token: str,
        *,
        subject_type: str | None,
        subject_id: str | None,
        limit: int,
    ) -> AuditEventListResponse:
        self._require_security_administrator(token)
        items = self.repository.list_audit(
            subject_type=subject_type, subject_id=subject_id, limit=limit
        )
        return AuditEventListResponse(items=items, total=len(items))

    def verify_audit(self, token: str) -> AuditIntegrityResponse:
        self._require_security_administrator(token)
        return AuditIntegrityResponse.model_validate(
            self.repository.verify_audit_integrity()
        )

    def health(self, token: str) -> WorkflowHealthResponse:
        session = self.session_for_token(token)
        counts = self.repository.counts(session["user"]["user_id"])
        integrity = AuditIntegrityResponse.model_validate(
            self.repository.verify_audit_integrity()
        )
        return WorkflowHealthResponse(
            status="ready",
            users=counts["users"],
            open_tasks=counts["open_tasks"],
            unread_notifications=counts["unread_notifications"],
            audit_records=counts["audit_records"],
            audit_integrity=integrity,
            authority_boundary=AUTHORITY_BOUNDARY,
            erp_access="none",
        )


workflow_foundation_service = WorkflowFoundationService()


__all__ = [
    "AUTHENTICATION_BOUNDARY",
    "AUTHORITY_BOUNDARY",
    "WorkflowAuthenticationRequired",
    "WorkflowFoundationConflict",
    "WorkflowFoundationNotFound",
    "WorkflowFoundationService",
    "WorkflowPermissionDenied",
    "WorkflowValidationError",
    "workflow_foundation_service",
]
