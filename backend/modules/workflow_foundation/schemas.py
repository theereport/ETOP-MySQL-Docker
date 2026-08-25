from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


RoleId = Literal[
    "workflow_coordinator",
    "credit_professional",
    "ap_professional",
    "workflow_observer",
]
ModuleId = Literal[
    "dashboard",
    "customer_360",
    "credit_risk",
    "accounts_payable",
    "financial_close",
    "cash_application",
    "payment_notes",
    "lockbox",
    "document_intelligence",
    "automation_center",
    "work_management",
    "report_builder",
    "sql_workspace",
    "knowledge_base",
    "ai_assistant",
    "document_ai_studio",
    "security_administration",
    "vendor_intelligence",
    "ar_collections",
    "freight_logistics",
    "inventory_purchasing",
    "tax_compliance",
    "sales_order_visibility",
    "pricing_contracts",
    "general_ledger",
]
TaskPriority = Literal["low", "medium", "high", "critical"]
TaskState = Literal[
    "open",
    "in_progress",
    "deferred",
    "completed",
    "cancelled",
    "reopened",
]
TaskCapability = Literal[
    "credit_risk",
    "accounts_payable",
    "lockbox",
    "reporting",
    "platform",
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class BootstrapStatus(StrictModel):
    bootstrap_required: bool
    account_count: int
    authentication_boundary: str
    authority_boundary: str


class LoginRequest(StrictModel):
    username: str = Field(min_length=3, max_length=80, pattern=r"^[A-Za-z0-9._-]+$")
    password: str = Field(min_length=12, max_length=200)


class BootstrapRequest(LoginRequest):
    display_name: str = Field(min_length=2, max_length=120)


class UserCreate(LoginRequest):
    display_name: str = Field(min_length=2, max_length=120)
    role_ids: list[RoleId] = Field(default_factory=lambda: ["workflow_observer"])
    module_ids: list[ModuleId] = Field(
        default_factory=lambda: ["dashboard", "work_management"]
    )


class RoleSummary(StrictModel):
    role_id: RoleId
    name: str
    description: str
    queue_scope: str
    authority_effect: Literal["none"]
    decision_authority: Literal[False]


class UserSummary(StrictModel):
    person_id: str
    user_id: str
    username: str
    display_name: str
    status: Literal["active", "inactive"]
    roles: list[RoleSummary]
    authentication_assurance: Literal["local_credential"]
    authority_status: Literal["not_configured"]
    created_at: datetime


class UserListResponse(StrictModel):
    users: list[UserSummary]
    authority_boundary: str


class ModuleSummary(StrictModel):
    module_id: ModuleId
    name: str
    description: str
    group: Literal["Overview", "Workspaces", "Tools", "System"]
    default_access: Literal[False]
    status: Literal["active"]
    authority_effect: Literal["none"]


class EffectivePermissions(StrictModel):
    module_ids: list[ModuleId]
    access_version: int = Field(ge=1)
    default_behavior: Literal["deny"]
    authority_effect: Literal["none"]
    decision_authority: Literal[False]


class SecurityUserSummary(StrictModel):
    user: UserSummary
    configured_module_ids: list[ModuleId]
    permissions: EffectivePermissions
    access_version: int = Field(ge=1)
    status_version: int = Field(ge=1)


class SecurityUserListResponse(StrictModel):
    users: list[SecurityUserSummary]
    modules: list[ModuleSummary]
    authority_boundary: str


class InvitationCreate(StrictModel):
    username: str = Field(min_length=3, max_length=80, pattern=r"^[A-Za-z0-9._-]+$")
    display_name: str = Field(min_length=2, max_length=120)
    role_ids: list[RoleId] = Field(min_length=1)
    module_ids: list[ModuleId] = Field(min_length=1)
    expires_in_hours: int = Field(default=48, ge=1, le=168)


class InvitationSummary(StrictModel):
    invitation_id: str
    username: str
    display_name: str
    role_ids: list[RoleId]
    module_ids: list[ModuleId]
    status: Literal["pending", "activated", "revoked", "expired"]
    created_by_user_id: str
    created_at: datetime
    expires_at: datetime
    activated_at: datetime | None
    activated_user_id: str | None


class InvitationCreateResponse(InvitationSummary):
    invitation_link: str
    link_displayed_once: Literal[True]


class InvitationListResponse(StrictModel):
    items: list[InvitationSummary]


class InvitationRevokeRequest(StrictModel):
    expected_status: Literal["pending"] = "pending"


class InvitationTokenRequest(StrictModel):
    token: str = Field(min_length=32, max_length=256)


class InvitationActivationRequest(InvitationTokenRequest):
    password: str = Field(min_length=12, max_length=200)


class InvitationPreview(StrictModel):
    username: str
    display_name: str
    expires_at: datetime
    status: Literal["pending"]


class ModuleAccessReplace(StrictModel):
    module_ids: list[ModuleId] = Field(default_factory=list)
    expected_version: int = Field(ge=1)


class UserStatusChange(StrictModel):
    status: Literal["active", "inactive"]
    expected_version: int = Field(ge=1)


class AuthSessionResponse(StrictModel):
    token: str
    expires_at: datetime
    user: UserSummary
    permissions: EffectivePermissions
    authority_boundary: str


class CurrentSessionResponse(StrictModel):
    expires_at: datetime
    user: UserSummary
    permissions: EffectivePermissions
    authority_boundary: str


class WorkflowDefinitionSummary(StrictModel):
    definition_id: str
    version: str
    title: str
    description: str
    states: list[TaskState]
    transitions: dict[str, list[TaskState]]
    status: Literal["active"]
    authority_effect: Literal["none"]


class WorkflowDefinitionListResponse(StrictModel):
    definitions: list[WorkflowDefinitionSummary]


class TaskCreate(StrictModel):
    title: str = Field(min_length=3, max_length=180)
    description: str = Field(default="", max_length=2_000)
    capability: TaskCapability
    context_type: str = Field(min_length=2, max_length=80, pattern=r"^[a-z][a-z0-9_]*$")
    context_id: str = Field(min_length=1, max_length=160)
    context_label: str = Field(min_length=1, max_length=240)
    queue_role_id: RoleId
    assignee_user_id: str | None = Field(default=None, max_length=80)
    priority: TaskPriority = "medium"
    due_date: date | None = None
    idempotency_key: str = Field(min_length=8, max_length=120)


class TaskAssignmentCreate(StrictModel):
    assignee_user_id: str
    note: str = Field(default="", max_length=1_000)
    expected_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=8, max_length=120)


class TaskTransitionCreate(StrictModel):
    target_state: TaskState
    note: str = Field(default="", max_length=1_000)
    expected_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=8, max_length=120)


class TaskAssignmentRecord(StrictModel):
    assignment_event_id: str
    task_id: str
    assignee: UserSummary
    prior_assignee_user_id: str | None
    assigned_by: UserSummary
    assignment_type: Literal["initial", "claim", "reassign"]
    note: str
    task_version: int
    created_at: datetime
    authority_effect: Literal["none"]


class TaskEventRecord(StrictModel):
    event_id: str
    task_id: str
    event_type: Literal["task_created", "task_state_changed"]
    from_state: TaskState | None
    to_state: TaskState
    actor: UserSummary
    note: str
    task_version: int
    created_at: datetime


class TaskSummary(StrictModel):
    task_id: str
    definition_id: str
    definition_version: str
    title: str
    description: str
    capability: TaskCapability
    context_type: str
    context_id: str
    context_label: str
    queue_role: RoleSummary
    assignee: UserSummary | None
    priority: TaskPriority
    state: TaskState
    due_date: date | None
    created_by: UserSummary
    created_at: datetime
    updated_at: datetime
    version: int
    permitted_actions: list[str]
    assignment_effect: Literal["work_ownership_only"]
    authority_effect: Literal["none"]
    execution_effect: Literal["none"]


class TaskDetail(TaskSummary):
    assignments: list[TaskAssignmentRecord]
    events: list[TaskEventRecord]


class TaskListResponse(StrictModel):
    items: list[TaskSummary]
    total: int
    queue_scope: Literal["personal_and_role", "coordinator_all"]
    authority_boundary: str


class NotificationSummary(StrictModel):
    notification_id: str
    task_id: str | None
    notification_type: str
    title: str
    message: str
    severity: Literal["info", "success", "warning", "critical"]
    created_at: datetime
    read_at: datetime | None


class NotificationListResponse(StrictModel):
    items: list[NotificationSummary]
    unread_count: int
    delivery_scope: Literal["in_app_local"]


class AuditEventRecord(StrictModel):
    audit_id: str
    event_type: str
    actor_user_id: str | None
    subject_type: str
    subject_id: str
    correlation_id: str
    occurred_at: datetime
    details: dict[str, object]
    previous_hash: str
    record_hash: str
    schema_version: Literal["1.0"]


class AuditEventListResponse(StrictModel):
    items: list[AuditEventRecord]
    total: int


class AuditIntegrityResponse(StrictModel):
    valid: bool
    checked_records: int
    first_invalid_audit_id: str | None
    algorithm: Literal["sha256_hash_chain"]


class WorkflowHealthResponse(StrictModel):
    status: Literal["ready"]
    users: int
    open_tasks: int
    unread_notifications: int
    audit_records: int
    audit_integrity: AuditIntegrityResponse
    authority_boundary: str
    erp_access: Literal["none"]
