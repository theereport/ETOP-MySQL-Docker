from __future__ import annotations

import hashlib
import json
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import case, delete, func, select
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import IntegrityError

from data.mysql import (
    get_engine,
    metadata,
    wf_access_profiles_table,
    wf_audit_events_table,
    wf_definitions_table,
    wf_invitation_events_table,
    wf_login_attempts_table,
    wf_module_access_events_table,
    wf_modules_table,
    wf_notifications_table,
    wf_password_reset_events_table,
    wf_password_reset_tokens_table,
    wf_persons_table,
    wf_role_assignments_table,
    wf_roles_table,
    wf_sessions_table,
    wf_task_assignments_table,
    wf_task_events_table,
    wf_tasks_table,
    wf_user_accounts_table,
    wf_user_invitations_table,
    wf_user_module_access_table,
)


class WorkflowFoundationConflict(RuntimeError):
    """A version, idempotency, or bootstrap precondition was not met."""


class WorkflowFoundationNotFound(LookupError):
    """A governed workflow record was not found."""


class WorkflowFoundationRepository:
    """Durable local workflow state with append-only hash-chained evidence."""

    ROLE_SEEDS = (
        (
            "workflow_coordinator",
            "Workflow Coordinator",
            "May administer local workflow identities and coordinate work ownership. This role grants no financial decision authority.",
            "platform",
        ),
        (
            "credit_professional",
            "Credit Professional",
            "Receives and owns Credit Risk follow-up work. Assignment is not credit approval authority.",
            "credit_risk",
        ),
        (
            "ap_professional",
            "Accounts Payable Professional",
            "Receives and owns Accounts Payable follow-up work. Assignment is not invoice or payment authority.",
            "accounts_payable",
        ),
        (
            "workflow_observer",
            "Workflow Observer",
            "May inspect work explicitly assigned to the account and its role queues.",
            "shared",
        ),
    )

    MODULE_SEEDS = (
        (
            "dashboard",
            "Dashboard",
            "Enterprise command center, priorities, and platform health.",
            "Overview",
        ),
        (
            "customer_360",
            "Customer 360",
            "Customer search, account evidence, and customer intelligence.",
            "Workspaces",
        ),
        (
            "credit_risk",
            "Credit Risk",
            "Credit evidence, assessments, monitoring, and decision preparation.",
            "Workspaces",
        ),
        (
            "accounts_payable",
            "Accounts Payable",
            "Vendor invoice, exception, ERP evidence, and spend intelligence.",
            "Workspaces",
        ),
        (
            "financial_close",
            "Financial Close",
            "Local close planning and evidence-readiness controls.",
            "Workspaces",
        ),
        (
            "cash_application",
            "Cash Application",
            "Payment matching and governed allocation recommendations.",
            "Workspaces",
        ),
        (
            "payment_notes",
            "Payment Notes",
            "Remote-capture check reconciliation against expected Payment Notes with local review evidence.",
            "Workspaces",
        ),
        (
            "lockbox",
            "Lockbox Automation",
            "PNC lockbox intake, preparation, review, export, and training.",
            "Workspaces",
        ),
        (
            "document_intelligence",
            "Document Intelligence",
            "Document intake, extraction, review, and operational queues.",
            "Workspaces",
        ),
        (
            "automation_center",
            "Automation Center",
            "Governed schedules, executions, and delivery monitoring.",
            "Workspaces",
        ),
        (
            "work_management",
            "Work Management",
            "Authenticated identity, durable assignments, tasks, and audit.",
            "Workspaces",
        ),
        (
            "report_builder",
            "Report Builder",
            "Saved report design, preview, export, and schedule handoff.",
            "Tools",
        ),
        (
            "sql_workspace",
            "SQL Workspace",
            "Read-only SQL validation, execution, export, and saved queries.",
            "Tools",
        ),
        (
            "knowledge_base",
            "Knowledge Base",
            "Local SOP indexing, status, and grounded search.",
            "Tools",
        ),
        (
            "ai_assistant",
            "AI Assistant",
            "Local AI and company-knowledge assistance.",
            "Tools",
        ),
        (
            "document_ai_studio",
            "Document AI Studio",
            "Document training, extraction configuration, and evidence review.",
            "System",
        ),
        (
            "security_administration",
            "Security & Access",
            "Local account invitations, lifecycle, and module access administration.",
            "System",
        ),
        (
            "vendor_intelligence",
            "Vendor Intelligence",
            "Vendor identity, purchase orders, receiving, and payables evidence from MaddenCo.",
            "Workspaces",
        ),
        (
            "ar_collections",
            "AR Collections",
            "Itemized open A/R, payment history, GL reference, and aging trend evidence from MaddenCo.",
            "Workspaces",
        ),
        (
            "freight_logistics",
            "Freight & Logistics",
            "Route schedule, load manifest, COD payments, and delivery exception evidence from MaddenCo.",
            "Workspaces",
        ),
        (
            "inventory_purchasing",
            "Inventory & Purchasing",
            "Item identity, month-end inventory valuation, open purchase-order exposure, and receiving evidence from MaddenCo.",
            "Workspaces",
        ),
        (
            "tax_compliance",
            "Tax Compliance",
            "Tax authority rates, exemption codes, and customer exemption-code verification from MaddenCo.",
            "Workspaces",
        ),
        (
            "sales_order_visibility",
            "Sales Order Visibility",
            "Invoice history, line items, memos, credit authorizations, and delivery cross-reference from MaddenCo. Invoice-forward only.",
            "Workspaces",
        ),
        (
            "pricing_contracts",
            "Pricing & Contracts",
            "Customer/vendor/product pricing overrides, product-class labels, and a customer-class reference from MaddenCo.",
            "Workspaces",
        ),
        (
            "general_ledger",
            "General Ledger",
            "Chart of accounts, period balances, and posted transaction evidence from MaddenCo.",
            "Workspaces",
        ),
        (
            "cash_flow_forecasting",
            "Cash Flow Forecasting",
            "14-week rolling cash flow projection with a prior-year backtest and accuracy history.",
            "Workspaces",
        ),
    )

    DEFAULT_DIRECT_USER_MODULES = ("dashboard", "work_management")

    DEFINITION_ID = "WF-WORK-FOLLOW-UP"
    DEFINITION_VERSION = "1.0.0"
    STATES = [
        "open",
        "in_progress",
        "deferred",
        "completed",
        "cancelled",
        "reopened",
    ]
    TRANSITIONS = {
        "open": ["in_progress", "deferred", "cancelled"],
        "in_progress": ["deferred", "completed", "cancelled"],
        "deferred": ["open", "in_progress", "cancelled"],
        "completed": ["reopened"],
        "cancelled": ["reopened"],
        "reopened": ["in_progress", "deferred", "cancelled"],
    }

    def __init__(
        self,
        engine: Engine | None = None,
        clock: Callable[[], datetime] | None = None,
        id_factory: Callable[[str], str] | None = None,
    ) -> None:
        self._engine = engine or get_engine()
        self._clock = clock or (lambda: datetime.now(UTC))
        self._id_factory = id_factory or (
            lambda prefix: f"{prefix}-{uuid4().hex}"
        )
        self._initialization_lock = threading.Lock()

    def _now(self) -> str:
        value = self._clock()
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).isoformat()

    def _id(self, prefix: str) -> str:
        return self._id_factory(prefix)

    def initialize(self) -> None:
        with self._initialization_lock:
            metadata.create_all(self._engine, checkfirst=True)
            now = self._now()
            with self._engine.begin() as connection:
                for role in self.ROLE_SEEDS:
                    role_id = role[0]
                    exists = connection.execute(
                        select(wf_roles_table.c.role_id).where(
                            wf_roles_table.c.role_id == role_id
                        )
                    ).first()
                    if exists is None:
                        connection.execute(
                            wf_roles_table.insert().values(
                                role_id=role[0],
                                name=role[1],
                                description=role[2],
                                queue_scope=role[3],
                                authority_effect="none",
                                decision_authority=0,
                                created_at=now,
                            )
                        )
                for module in self.MODULE_SEEDS:
                    module_id = module[0]
                    exists = connection.execute(
                        select(wf_modules_table.c.module_id).where(
                            wf_modules_table.c.module_id == module_id
                        )
                    ).first()
                    if exists is None:
                        connection.execute(
                            wf_modules_table.insert().values(
                                module_id=module[0],
                                name=module[1],
                                description=module[2],
                                module_group=module[3],
                                default_access=0,
                                status="active",
                                authority_effect="none",
                                created_at=now,
                            )
                        )
                definition_exists = connection.execute(
                    select(wf_definitions_table.c.definition_id).where(
                        wf_definitions_table.c.definition_id == self.DEFINITION_ID,
                        wf_definitions_table.c.version == self.DEFINITION_VERSION,
                    )
                ).first()
                if definition_exists is None:
                    connection.execute(
                        wf_definitions_table.insert().values(
                            definition_id=self.DEFINITION_ID,
                            version=self.DEFINITION_VERSION,
                            title="Governed work follow-up",
                            description=(
                                "Coordinates accountable follow-up work without "
                                "making a business decision or executing a "
                                "source-system action."
                            ),
                            states_json=self._canonical_json(self.STATES),
                            transitions_json=self._canonical_json(self.TRANSITIONS),
                            status="active",
                            authority_effect="none",
                            created_at=now,
                        )
                    )

                # Backfills an access profile/module grant for any account
                # that predates access-control tracking (e.g. migrated from
                # an older SQLite install). Every code path that creates a
                # user going forward inserts its access profile inline, so
                # this is normally a no-op on a fresh schema.
                legacy_users = connection.execute(
                    select(wf_user_accounts_table.c.user_id, wf_user_accounts_table.c.created_at)
                    .select_from(
                        wf_user_accounts_table.outerjoin(
                            wf_access_profiles_table,
                            wf_access_profiles_table.c.user_id
                            == wf_user_accounts_table.c.user_id,
                        )
                    )
                    .where(wf_access_profiles_table.c.user_id.is_(None))
                    .order_by(
                        wf_user_accounts_table.c.created_at,
                        wf_user_accounts_table.c.user_id,
                    )
                ).all()
                for legacy_user in legacy_users:
                    user_id = legacy_user.user_id
                    role_ids = {
                        row.role_id
                        for row in connection.execute(
                            select(wf_role_assignments_table.c.role_id).where(
                                wf_role_assignments_table.c.user_id == user_id,
                                wf_role_assignments_table.c.assignment_status
                                == "active",
                                wf_role_assignments_table.c.effective_to.is_(None),
                            )
                        ).all()
                    }
                    if "workflow_coordinator" in role_ids:
                        granted_modules = [item[0] for item in self.MODULE_SEEDS]
                    else:
                        granted = set(self.DEFAULT_DIRECT_USER_MODULES)
                        if "credit_professional" in role_ids:
                            granted.update(("customer_360", "credit_risk"))
                        if "ap_professional" in role_ids:
                            granted.update(
                                ("accounts_payable", "document_intelligence")
                            )
                        granted_modules = sorted(granted)
                    connection.execute(
                        wf_access_profiles_table.insert().values(
                            user_id=user_id,
                            access_version=1,
                            updated_at=now,
                            updated_by_user_id=None,
                        )
                    )
                    for module_id in granted_modules:
                        connection.execute(
                            wf_user_module_access_table.insert().values(
                                user_id=user_id,
                                module_id=module_id,
                                allowed=1,
                                updated_at=now,
                                updated_by_user_id=None,
                            )
                        )
                    connection.execute(
                        wf_module_access_events_table.insert().values(
                            access_event_id=self._id("ACE"),
                            user_id=user_id,
                            actor_user_id=None,
                            before_module_ids_json="[]",
                            after_module_ids_json=self._canonical_json(
                                granted_modules
                            ),
                            access_version=1,
                            reason="compatibility_migration_from_pre_access_control",
                            created_at=now,
                        )
                    )
                    self._append_audit(
                        connection,
                        event_type="identity.module_access_migrated",
                        actor_user_id=None,
                        subject_type="user_account",
                        subject_id=user_id,
                        correlation_id=self._id("COR"),
                        details={
                            "module_ids": granted_modules,
                            "access_version": 1,
                            "default_behavior": "deny",
                            "authority_effect": "none",
                        },
                        occurred_at=now,
                    )

    @staticmethod
    def _canonical_json(value: Any) -> str:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    def _append_audit(
        self,
        connection: Connection,
        *,
        event_type: str,
        actor_user_id: str | None,
        subject_type: str,
        subject_id: str,
        correlation_id: str,
        details: dict[str, Any],
        occurred_at: str | None = None,
    ) -> str:
        audit_id = self._id("AUD")
        timestamp = occurred_at or self._now()
        prior = connection.execute(
            select(wf_audit_events_table.c.record_hash)
            .order_by(wf_audit_events_table.c.sequence.desc())
            .limit(1)
        ).first()
        previous_hash = prior.record_hash if prior else "0" * 64
        basis = {
            "audit_id": audit_id,
            "event_type": event_type,
            "actor_user_id": actor_user_id,
            "subject_type": subject_type,
            "subject_id": subject_id,
            "correlation_id": correlation_id,
            "occurred_at": timestamp,
            "details": details,
            "previous_hash": previous_hash,
            "schema_version": "1.0",
        }
        record_hash = hashlib.sha256(
            self._canonical_json(basis).encode("utf-8")
        ).hexdigest()
        connection.execute(
            wf_audit_events_table.insert().values(
                audit_id=audit_id,
                event_type=event_type,
                actor_user_id=actor_user_id,
                subject_type=subject_type,
                subject_id=subject_id,
                correlation_id=correlation_id,
                occurred_at=timestamp,
                details_json=self._canonical_json(details),
                previous_hash=previous_hash,
                record_hash=record_hash,
                schema_version="1.0",
            )
        )
        return audit_id

    def bootstrap_status(self) -> dict[str, Any]:
        with self._engine.connect() as connection:
            count = connection.execute(
                select(func.count()).select_from(wf_user_accounts_table)
            ).scalar_one()
            return {"bootstrap_required": count == 0, "account_count": count}

    def bootstrap_user(
        self,
        *,
        username: str,
        display_name: str,
        password_salt: str,
        password_hash: str,
    ) -> str:
        now = self._now()
        person_id = self._id("PER")
        user_id = self._id("USR")
        role_assignment_id = self._id("RLA")
        correlation_id = self._id("COR")
        with self._engine.begin() as connection:
            existing = connection.execute(
                select(func.count())
                .select_from(wf_user_accounts_table)
                .with_for_update()
            ).scalar_one()
            if existing:
                raise WorkflowFoundationConflict(
                    "The local identity foundation has already been bootstrapped."
                )
            connection.execute(
                wf_persons_table.insert().values(
                    person_id=person_id,
                    display_name=display_name,
                    status="active",
                    created_at=now,
                    created_by_user_id=None,
                )
            )
            connection.execute(
                wf_user_accounts_table.insert().values(
                    user_id=user_id,
                    person_id=person_id,
                    username=username,
                    password_salt=password_salt,
                    password_hash=password_hash,
                    password_algorithm="scrypt-n16384-r8-p1-v1",
                    status="active",
                    created_at=now,
                    updated_at=now,
                )
            )
            connection.execute(
                wf_role_assignments_table.insert().values(
                    role_assignment_id=role_assignment_id,
                    user_id=user_id,
                    role_id="workflow_coordinator",
                    effective_from=now,
                    effective_to=None,
                    assignment_status="active",
                    assigned_by_user_id=user_id,
                    created_at=now,
                )
            )
            module_ids = [item[0] for item in self.MODULE_SEEDS]
            connection.execute(
                wf_access_profiles_table.insert().values(
                    user_id=user_id,
                    access_version=1,
                    updated_at=now,
                    updated_by_user_id=user_id,
                )
            )
            for module_id in module_ids:
                connection.execute(
                    wf_user_module_access_table.insert().values(
                        user_id=user_id,
                        module_id=module_id,
                        allowed=1,
                        updated_at=now,
                        updated_by_user_id=user_id,
                    )
                )
            connection.execute(
                wf_module_access_events_table.insert().values(
                    access_event_id=self._id("ACE"),
                    user_id=user_id,
                    actor_user_id=user_id,
                    before_module_ids_json="[]",
                    after_module_ids_json=self._canonical_json(module_ids),
                    access_version=1,
                    reason="initial_bootstrap_access",
                    created_at=now,
                )
            )
            self._append_audit(
                connection,
                event_type="identity.bootstrap_completed",
                actor_user_id=user_id,
                subject_type="user_account",
                subject_id=user_id,
                correlation_id=correlation_id,
                details={
                    "person_id": person_id,
                    "username": username,
                    "roles": ["workflow_coordinator"],
                    "module_ids": module_ids,
                    "default_behavior": "deny",
                    "authority_effect": "none",
                },
                occurred_at=now,
            )
        return user_id

    def get_account_credentials(self, username: str) -> dict[str, Any] | None:
        with self._engine.connect() as connection:
            row = connection.execute(
                select(
                    wf_user_accounts_table.c.user_id,
                    wf_user_accounts_table.c.password_salt,
                    wf_user_accounts_table.c.password_hash,
                    wf_user_accounts_table.c.password_algorithm,
                    wf_user_accounts_table.c.status,
                ).where(func.lower(wf_user_accounts_table.c.username) == username.lower())
            ).mappings().first()
            return dict(row) if row else None

    def get_login_lockout(self, username: str) -> dict[str, Any] | None:
        key = username.strip().lower()
        with self._engine.connect() as connection:
            row = connection.execute(
                select(
                    wf_login_attempts_table.c.failed_count,
                    wf_login_attempts_table.c.locked_until,
                ).where(wf_login_attempts_table.c.username == key)
            ).mappings().first()
            return dict(row) if row else None

    def record_failed_login(
        self,
        username: str,
        *,
        lockout_threshold: int,
        lockout_until: str | None,
    ) -> None:
        key = username.strip().lower()
        now = self._now()
        with self._engine.begin() as connection:
            existing = connection.execute(
                select(wf_login_attempts_table.c.failed_count).where(
                    wf_login_attempts_table.c.username == key
                )
            ).first()
            next_count = (existing[0] if existing else 0) + 1
            locked_until = (
                lockout_until if next_count >= lockout_threshold else None
            )
            if existing is None:
                connection.execute(
                    wf_login_attempts_table.insert().values(
                        username=key,
                        failed_count=next_count,
                        first_failed_at=now,
                        locked_until=locked_until,
                        updated_at=now,
                    )
                )
            else:
                connection.execute(
                    wf_login_attempts_table.update()
                    .where(wf_login_attempts_table.c.username == key)
                    .values(
                        failed_count=next_count,
                        locked_until=locked_until,
                        updated_at=now,
                    )
                )

    def clear_login_attempts(self, username: str) -> None:
        key = username.strip().lower()
        with self._engine.begin() as connection:
            connection.execute(
                delete(wf_login_attempts_table).where(
                    wf_login_attempts_table.c.username == key
                )
            )

    def create_session(
        self,
        *,
        user_id: str,
        token_hash: str,
        expires_at: str,
    ) -> str:
        session_id = self._id("SES")
        now = self._now()
        correlation_id = self._id("COR")
        with self._engine.begin() as connection:
            connection.execute(
                wf_sessions_table.insert().values(
                    session_id=session_id,
                    user_id=user_id,
                    token_hash=token_hash,
                    issued_at=now,
                    expires_at=expires_at,
                    revoked_at=None,
                    last_seen_at=now,
                )
            )
            self._append_audit(
                connection,
                event_type="identity.session_started",
                actor_user_id=user_id,
                subject_type="session",
                subject_id=session_id,
                correlation_id=correlation_id,
                details={
                    "expires_at": expires_at,
                    "authentication_assurance": "local_credential",
                },
                occurred_at=now,
            )
        return session_id

    def get_session(self, token_hash: str) -> dict[str, Any] | None:
        now = self._now()
        with self._engine.begin() as connection:
            row = connection.execute(
                select(
                    wf_sessions_table.c.session_id,
                    wf_sessions_table.c.user_id,
                    wf_sessions_table.c.expires_at,
                )
                .select_from(
                    wf_sessions_table.join(
                        wf_user_accounts_table,
                        wf_user_accounts_table.c.user_id == wf_sessions_table.c.user_id,
                    )
                )
                .where(
                    wf_sessions_table.c.token_hash == token_hash,
                    wf_sessions_table.c.revoked_at.is_(None),
                    wf_sessions_table.c.expires_at > now,
                    wf_user_accounts_table.c.status == "active",
                )
            ).first()
            if row is None:
                return None
            connection.execute(
                wf_sessions_table.update()
                .where(wf_sessions_table.c.session_id == row.session_id)
                .values(last_seen_at=now)
            )
            return {
                "session_id": row.session_id,
                "expires_at": row.expires_at,
                "user": self._user_summary(connection, row.user_id),
            }

    def get_session_with_permissions(
        self, token_hash: str
    ) -> tuple[dict[str, Any], dict[str, Any]] | None:
        """Combined sibling of get_session() + get_permissions() for the two
        callers (authorize_module_access, current_session) that need both
        together on every authenticated request. One held connection
        instead of two separate pool checkouts, and the user-identity and
        access-profile-status/version reads are combined into a single
        query instead of two - 4 round trips total (1 combined identity+
        access-profile select, 1 last_seen_at update, 1 roles select, 1
        configured-module-ids select) instead of 6 across 2 connections."""

        now = self._now()
        with self._engine.begin() as connection:
            row = connection.execute(
                select(
                    wf_sessions_table.c.session_id,
                    wf_sessions_table.c.expires_at,
                    wf_user_accounts_table.c.user_id,
                    wf_user_accounts_table.c.username,
                    wf_user_accounts_table.c.status,
                    wf_user_accounts_table.c.created_at,
                    wf_persons_table.c.person_id,
                    wf_persons_table.c.display_name,
                    wf_access_profiles_table.c.access_version,
                )
                .select_from(
                    wf_sessions_table.join(
                        wf_user_accounts_table,
                        wf_user_accounts_table.c.user_id == wf_sessions_table.c.user_id,
                    )
                    .join(
                        wf_persons_table,
                        wf_persons_table.c.person_id == wf_user_accounts_table.c.person_id,
                    )
                    .join(
                        wf_access_profiles_table,
                        wf_access_profiles_table.c.user_id == wf_user_accounts_table.c.user_id,
                    )
                )
                .where(
                    wf_sessions_table.c.token_hash == token_hash,
                    wf_sessions_table.c.revoked_at.is_(None),
                    wf_sessions_table.c.expires_at > now,
                    wf_user_accounts_table.c.status == "active",
                )
            ).mappings().first()
            if row is None:
                return None
            connection.execute(
                wf_sessions_table.update()
                .where(wf_sessions_table.c.session_id == row["session_id"])
                .values(last_seen_at=now)
            )
            user_id = row["user_id"]
            configured = self._configured_module_ids(connection, user_id)
            roles = connection.execute(
                select(wf_roles_table)
                .select_from(
                    wf_role_assignments_table.join(
                        wf_roles_table,
                        wf_roles_table.c.role_id == wf_role_assignments_table.c.role_id,
                    )
                )
                .where(
                    wf_role_assignments_table.c.user_id == user_id,
                    wf_role_assignments_table.c.assignment_status == "active",
                    wf_role_assignments_table.c.effective_from <= now,
                    (
                        wf_role_assignments_table.c.effective_to.is_(None)
                        | (wf_role_assignments_table.c.effective_to > now)
                    ),
                )
                .order_by(wf_roles_table.c.name, wf_roles_table.c.role_id)
            ).mappings().all()

            session = {
                "session_id": row["session_id"],
                "expires_at": row["expires_at"],
                "user": {
                    "person_id": row["person_id"],
                    "user_id": user_id,
                    "username": row["username"],
                    "display_name": row["display_name"],
                    "status": row["status"],
                    "roles": [self._role_summary(role) for role in roles],
                    "authentication_assurance": "local_credential",
                    "authority_status": "not_configured",
                    "created_at": row["created_at"],
                },
            }
            permissions = {
                "module_ids": configured if row["status"] == "active" else [],
                "access_version": row["access_version"],
                "default_behavior": "deny",
                "authority_effect": "none",
                "decision_authority": False,
            }
            return session, permissions

    def revoke_session(self, token_hash: str, actor_user_id: str) -> None:
        now = self._now()
        with self._engine.begin() as connection:
            row = connection.execute(
                select(wf_sessions_table.c.session_id).where(
                    wf_sessions_table.c.token_hash == token_hash,
                    wf_sessions_table.c.revoked_at.is_(None),
                )
            ).first()
            if row is None:
                return
            connection.execute(
                wf_sessions_table.update()
                .where(wf_sessions_table.c.session_id == row.session_id)
                .values(revoked_at=now)
            )
            self._append_audit(
                connection,
                event_type="identity.session_ended",
                actor_user_id=actor_user_id,
                subject_type="session",
                subject_id=row.session_id,
                correlation_id=self._id("COR"),
                details={"reason": "operator_sign_out"},
                occurred_at=now,
            )

    def _role_summary(self, row: Any) -> dict[str, Any]:
        return {
            "role_id": row["role_id"],
            "name": row["name"],
            "description": row["description"],
            "queue_scope": row["queue_scope"],
            "authority_effect": "none",
            "decision_authority": False,
        }

    def _user_summary(
        self,
        connection: Connection,
        user_id: str,
    ) -> dict[str, Any]:
        row = connection.execute(
            select(
                wf_user_accounts_table.c.user_id,
                wf_user_accounts_table.c.username,
                wf_user_accounts_table.c.status,
                wf_user_accounts_table.c.created_at,
                wf_persons_table.c.person_id,
                wf_persons_table.c.display_name,
            ).select_from(
                wf_user_accounts_table.join(
                    wf_persons_table,
                    wf_persons_table.c.person_id == wf_user_accounts_table.c.person_id,
                )
            ).where(wf_user_accounts_table.c.user_id == user_id)
        ).mappings().first()
        if row is None:
            raise WorkflowFoundationNotFound(f"Workflow user {user_id} was not found.")
        now = self._now()
        roles = connection.execute(
            select(wf_roles_table)
            .select_from(
                wf_role_assignments_table.join(
                    wf_roles_table,
                    wf_roles_table.c.role_id == wf_role_assignments_table.c.role_id,
                )
            )
            .where(
                wf_role_assignments_table.c.user_id == user_id,
                wf_role_assignments_table.c.assignment_status == "active",
                wf_role_assignments_table.c.effective_from <= now,
                (
                    wf_role_assignments_table.c.effective_to.is_(None)
                    | (wf_role_assignments_table.c.effective_to > now)
                ),
            )
            .order_by(wf_roles_table.c.name, wf_roles_table.c.role_id)
        ).mappings().all()
        return {
            "person_id": row["person_id"],
            "user_id": row["user_id"],
            "username": row["username"],
            "display_name": row["display_name"],
            "status": row["status"],
            "roles": [self._role_summary(role) for role in roles],
            "authentication_assurance": "local_credential",
            "authority_status": "not_configured",
            "created_at": row["created_at"],
        }

    def _user_summaries_for_ids(
        self,
        connection: Connection,
        user_ids: list[str],
    ) -> dict[str, dict[str, Any]]:
        """Batched sibling of _user_summary() - one query for identity, one
        for roles, regardless of how many user_ids are requested, instead of
        two queries per user."""

        if not user_ids:
            return {}

        identity_rows = connection.execute(
            select(
                wf_user_accounts_table.c.user_id,
                wf_user_accounts_table.c.username,
                wf_user_accounts_table.c.status,
                wf_user_accounts_table.c.created_at,
                wf_persons_table.c.person_id,
                wf_persons_table.c.display_name,
            ).select_from(
                wf_user_accounts_table.join(
                    wf_persons_table,
                    wf_persons_table.c.person_id == wf_user_accounts_table.c.person_id,
                )
            ).where(wf_user_accounts_table.c.user_id.in_(user_ids))
        ).mappings().all()

        now = self._now()
        role_rows = connection.execute(
            select(
                wf_role_assignments_table.c.user_id,
                wf_roles_table.c.role_id,
                wf_roles_table.c.name,
                wf_roles_table.c.description,
                wf_roles_table.c.queue_scope,
            )
            .select_from(
                wf_role_assignments_table.join(
                    wf_roles_table,
                    wf_roles_table.c.role_id == wf_role_assignments_table.c.role_id,
                )
            )
            .where(
                wf_role_assignments_table.c.user_id.in_(user_ids),
                wf_role_assignments_table.c.assignment_status == "active",
                wf_role_assignments_table.c.effective_from <= now,
                (
                    wf_role_assignments_table.c.effective_to.is_(None)
                    | (wf_role_assignments_table.c.effective_to > now)
                ),
            )
            .order_by(wf_roles_table.c.name, wf_roles_table.c.role_id)
        ).mappings().all()

        roles_by_user: dict[str, list[dict[str, Any]]] = {}
        for role_row in role_rows:
            roles_by_user.setdefault(role_row["user_id"], []).append(
                self._role_summary(role_row)
            )

        return {
            row["user_id"]: {
                "person_id": row["person_id"],
                "user_id": row["user_id"],
                "username": row["username"],
                "display_name": row["display_name"],
                "status": row["status"],
                "roles": roles_by_user.get(row["user_id"], []),
                "authentication_assurance": "local_credential",
                "authority_status": "not_configured",
                "created_at": row["created_at"],
            }
            for row in identity_rows
        }

    def list_users(self) -> list[dict[str, Any]]:
        with self._engine.connect() as connection:
            rows = connection.execute(
                select(wf_user_accounts_table.c.user_id).order_by(
                    func.lower(wf_user_accounts_table.c.username)
                )
            ).all()
            user_ids = [row.user_id for row in rows]
            summaries = self._user_summaries_for_ids(connection, user_ids)
            missing = [
                user_id for user_id in user_ids if user_id not in summaries
            ]
            if missing:
                raise WorkflowFoundationNotFound(
                    f"Workflow user {missing[0]} was not found."
                )
            return [summaries[user_id] for user_id in user_ids]

    def get_user(self, user_id: str) -> dict[str, Any]:
        with self._engine.connect() as connection:
            return self._user_summary(connection, user_id)

    def create_user(
        self,
        *,
        username: str,
        display_name: str,
        password_salt: str,
        password_hash: str,
        role_ids: list[str],
        module_ids: list[str],
        actor_user_id: str,
    ) -> dict[str, Any]:
        now = self._now()
        user_id = self._id("USR")
        person_id = self._id("PER")
        correlation_id = self._id("COR")
        try:
            with self._engine.begin() as connection:
                connection.execute(
                    wf_persons_table.insert().values(
                        person_id=person_id,
                        display_name=display_name,
                        status="active",
                        created_at=now,
                        created_by_user_id=actor_user_id,
                    )
                )
                connection.execute(
                    wf_user_accounts_table.insert().values(
                        user_id=user_id,
                        person_id=person_id,
                        username=username,
                        password_salt=password_salt,
                        password_hash=password_hash,
                        password_algorithm="scrypt-n16384-r8-p1-v1",
                        status="active",
                        created_at=now,
                        updated_at=now,
                    )
                )
                for role_id in sorted(set(role_ids)):
                    connection.execute(
                        wf_role_assignments_table.insert().values(
                            role_assignment_id=self._id("RLA"),
                            user_id=user_id,
                            role_id=role_id,
                            effective_from=now,
                            effective_to=None,
                            assignment_status="active",
                            assigned_by_user_id=actor_user_id,
                            created_at=now,
                        )
                    )
                configured_modules = sorted(set(module_ids))
                connection.execute(
                    wf_access_profiles_table.insert().values(
                        user_id=user_id,
                        access_version=1,
                        updated_at=now,
                        updated_by_user_id=actor_user_id,
                    )
                )
                for module_id in configured_modules:
                    connection.execute(
                        wf_user_module_access_table.insert().values(
                            user_id=user_id,
                            module_id=module_id,
                            allowed=1,
                            updated_at=now,
                            updated_by_user_id=actor_user_id,
                        )
                    )
                connection.execute(
                    wf_module_access_events_table.insert().values(
                        access_event_id=self._id("ACE"),
                        user_id=user_id,
                        actor_user_id=actor_user_id,
                        before_module_ids_json="[]",
                        after_module_ids_json=self._canonical_json(
                            configured_modules
                        ),
                        access_version=1,
                        reason="direct_local_account_creation",
                        created_at=now,
                    )
                )
                self._append_audit(
                    connection,
                    event_type="identity.user_created",
                    actor_user_id=actor_user_id,
                    subject_type="user_account",
                    subject_id=user_id,
                    correlation_id=correlation_id,
                    details={
                        "person_id": person_id,
                        "username": username,
                        "roles": sorted(set(role_ids)),
                        "module_ids": configured_modules,
                        "default_behavior": "deny",
                        "authority_effect": "none",
                    },
                    occurred_at=now,
                )
            return self.get_user(user_id)
        except IntegrityError as exc:
            raise WorkflowFoundationConflict(
                "That username already exists or a requested workflow role is invalid."
            ) from exc

    def _module_summary(self, row: Any) -> dict[str, Any]:
        return {
            "module_id": row["module_id"],
            "name": row["name"],
            "description": row["description"],
            "group": row["module_group"],
            "default_access": False,
            "status": row["status"],
            "authority_effect": "none",
        }

    def list_modules(self) -> list[dict[str, Any]]:
        group_order = case(
            (wf_modules_table.c.module_group == "Overview", 1),
            (wf_modules_table.c.module_group == "Workspaces", 2),
            (wf_modules_table.c.module_group == "Tools", 3),
            else_=4,
        )
        with self._engine.connect() as connection:
            rows = connection.execute(
                select(wf_modules_table)
                .where(wf_modules_table.c.status == "active")
                .order_by(
                    group_order, wf_modules_table.c.name, wf_modules_table.c.module_id
                )
            ).mappings().all()
            return [self._module_summary(row) for row in rows]

    def _configured_module_ids(
        self,
        connection: Connection,
        user_id: str,
    ) -> list[str]:
        rows = connection.execute(
            select(wf_user_module_access_table.c.module_id)
            .select_from(
                wf_user_module_access_table.join(
                    wf_modules_table,
                    wf_modules_table.c.module_id
                    == wf_user_module_access_table.c.module_id,
                )
            )
            .where(
                wf_user_module_access_table.c.user_id == user_id,
                wf_user_module_access_table.c.allowed == 1,
                wf_modules_table.c.status == "active",
            )
            .order_by(wf_user_module_access_table.c.module_id)
        ).all()
        return [row.module_id for row in rows]

    def _permission_summary(
        self,
        connection: Connection,
        user_id: str,
    ) -> dict[str, Any]:
        row = connection.execute(
            select(
                wf_user_accounts_table.c.status,
                wf_access_profiles_table.c.access_version,
            )
            .select_from(
                wf_user_accounts_table.join(
                    wf_access_profiles_table,
                    wf_access_profiles_table.c.user_id
                    == wf_user_accounts_table.c.user_id,
                )
            )
            .where(wf_user_accounts_table.c.user_id == user_id)
        ).mappings().first()
        if row is None:
            raise WorkflowFoundationNotFound(
                f"Workflow user {user_id} or its access profile was not found."
            )
        configured = self._configured_module_ids(connection, user_id)
        return {
            "module_ids": configured if row["status"] == "active" else [],
            "access_version": row["access_version"],
            "default_behavior": "deny",
            "authority_effect": "none",
            "decision_authority": False,
        }

    def get_permissions(self, user_id: str) -> dict[str, Any]:
        with self._engine.connect() as connection:
            return self._permission_summary(connection, user_id)

    def _security_user_summary(
        self,
        connection: Connection,
        user_id: str,
    ) -> dict[str, Any]:
        status_row = connection.execute(
            select(
                wf_user_accounts_table.c.status_version,
                wf_user_accounts_table.c.credential_version,
            ).where(wf_user_accounts_table.c.user_id == user_id)
        ).mappings().first()
        if status_row is None:
            raise WorkflowFoundationNotFound(f"Workflow user {user_id} was not found.")
        permission = self._permission_summary(connection, user_id)
        configured = self._configured_module_ids(connection, user_id)
        return {
            "user": self._user_summary(connection, user_id),
            "configured_module_ids": configured,
            "permissions": permission,
            "access_version": permission["access_version"],
            "status_version": status_row["status_version"],
            "credential_version": status_row["credential_version"],
        }

    def list_security_users(self) -> list[dict[str, Any]]:
        with self._engine.connect() as connection:
            rows = connection.execute(
                select(wf_user_accounts_table.c.user_id).order_by(
                    func.lower(wf_user_accounts_table.c.username)
                )
            ).all()
            return [
                self._security_user_summary(connection, row.user_id)
                for row in rows
            ]

    def get_security_user(self, user_id: str) -> dict[str, Any]:
        with self._engine.connect() as connection:
            return self._security_user_summary(connection, user_id)

    def replace_module_access(
        self,
        *,
        user_id: str,
        module_ids: list[str],
        expected_version: int,
        actor_user_id: str,
    ) -> dict[str, Any]:
        now = self._now()
        correlation_id = self._id("COR")
        with self._engine.begin() as connection:
            profile = connection.execute(
                select(wf_access_profiles_table.c.access_version)
                .where(wf_access_profiles_table.c.user_id == user_id)
                .with_for_update()
            ).first()
            if profile is None:
                raise WorkflowFoundationNotFound(
                    f"Workflow user {user_id} or its access profile was not found."
                )
            if profile.access_version != expected_version:
                raise WorkflowFoundationConflict(
                    "The module-access profile changed. Refresh before saving access."
                )
            valid_modules = {
                row.module_id
                for row in connection.execute(
                    select(wf_modules_table.c.module_id).where(
                        wf_modules_table.c.status == "active"
                    )
                ).all()
            }
            requested = sorted(set(module_ids))
            unknown = sorted(set(requested) - valid_modules)
            if unknown:
                raise WorkflowFoundationConflict(
                    f"Unknown or inactive ETOP module access was requested: {', '.join(unknown)}."
                )
            before = self._configured_module_ids(connection, user_id)
            if before == requested:
                return self._security_user_summary(connection, user_id)
            if (
                "security_administration" in before
                and "security_administration" not in requested
                and self._is_workflow_coordinator(connection, user_id)
                and self._active_security_coordinator_count(
                    connection,
                    excluding_user_id=user_id,
                ) == 0
            ):
                raise WorkflowFoundationConflict(
                    "The last active Security & Access coordinator cannot lose "
                    "Security & Access module access."
                )
            next_version = expected_version + 1
            existing_module_ids = {
                row.module_id
                for row in connection.execute(
                    select(wf_user_module_access_table.c.module_id).where(
                        wf_user_module_access_table.c.user_id == user_id
                    )
                ).all()
            }
            for module_id in sorted(valid_modules):
                allowed = 1 if module_id in requested else 0
                if module_id in existing_module_ids:
                    connection.execute(
                        wf_user_module_access_table.update()
                        .where(
                            wf_user_module_access_table.c.user_id == user_id,
                            wf_user_module_access_table.c.module_id == module_id,
                        )
                        .values(
                            allowed=allowed,
                            updated_at=now,
                            updated_by_user_id=actor_user_id,
                        )
                    )
                else:
                    connection.execute(
                        wf_user_module_access_table.insert().values(
                            user_id=user_id,
                            module_id=module_id,
                            allowed=allowed,
                            updated_at=now,
                            updated_by_user_id=actor_user_id,
                        )
                    )
            connection.execute(
                wf_access_profiles_table.update()
                .where(wf_access_profiles_table.c.user_id == user_id)
                .values(
                    access_version=next_version,
                    updated_at=now,
                    updated_by_user_id=actor_user_id,
                )
            )
            connection.execute(
                wf_module_access_events_table.insert().values(
                    access_event_id=self._id("ACE"),
                    user_id=user_id,
                    actor_user_id=actor_user_id,
                    before_module_ids_json=self._canonical_json(before),
                    after_module_ids_json=self._canonical_json(requested),
                    access_version=next_version,
                    reason="coordinator_module_access_replacement",
                    created_at=now,
                )
            )
            self._append_audit(
                connection,
                event_type="identity.module_access_changed",
                actor_user_id=actor_user_id,
                subject_type="user_account",
                subject_id=user_id,
                correlation_id=correlation_id,
                details={
                    "before_module_ids": before,
                    "after_module_ids": requested,
                    "access_version": next_version,
                    "default_behavior": "deny",
                    "authority_effect": "none",
                },
                occurred_at=now,
            )
            return self._security_user_summary(connection, user_id)

    def _is_workflow_coordinator(
        self,
        connection: Connection,
        user_id: str,
    ) -> bool:
        now = self._now()
        return connection.execute(
            select(wf_role_assignments_table.c.role_assignment_id)
            .where(
                wf_role_assignments_table.c.user_id == user_id,
                wf_role_assignments_table.c.role_id == "workflow_coordinator",
                wf_role_assignments_table.c.assignment_status == "active",
                wf_role_assignments_table.c.effective_from <= now,
                (
                    wf_role_assignments_table.c.effective_to.is_(None)
                    | (wf_role_assignments_table.c.effective_to > now)
                ),
            )
            .limit(1)
        ).first() is not None

    def _active_security_coordinator_count(
        self,
        connection: Connection,
        *,
        excluding_user_id: str | None = None,
    ) -> int:
        now = self._now()
        conditions = [
            wf_user_accounts_table.c.status == "active",
            wf_role_assignments_table.c.role_id == "workflow_coordinator",
            wf_role_assignments_table.c.assignment_status == "active",
            wf_role_assignments_table.c.effective_from <= now,
            (
                wf_role_assignments_table.c.effective_to.is_(None)
                | (wf_role_assignments_table.c.effective_to > now)
            ),
            wf_user_module_access_table.c.module_id == "security_administration",
            wf_user_module_access_table.c.allowed == 1,
        ]
        if excluding_user_id:
            conditions.append(wf_user_accounts_table.c.user_id != excluding_user_id)
        count = connection.execute(
            select(func.count(func.distinct(wf_user_accounts_table.c.user_id)))
            .select_from(
                wf_user_accounts_table.join(
                    wf_role_assignments_table,
                    wf_role_assignments_table.c.user_id
                    == wf_user_accounts_table.c.user_id,
                ).join(
                    wf_user_module_access_table,
                    wf_user_module_access_table.c.user_id
                    == wf_user_accounts_table.c.user_id,
                )
            )
            .where(*conditions)
        ).scalar_one()
        return int(count)

    def active_security_coordinator_count(
        self,
        *,
        excluding_user_id: str | None = None,
    ) -> int:
        with self._engine.connect() as connection:
            return self._active_security_coordinator_count(
                connection,
                excluding_user_id=excluding_user_id,
            )

    def change_user_status(
        self,
        *,
        user_id: str,
        status: str,
        expected_version: int,
        actor_user_id: str,
    ) -> dict[str, Any]:
        now = self._now()
        with self._engine.begin() as connection:
            row = connection.execute(
                select(
                    wf_user_accounts_table.c.status,
                    wf_user_accounts_table.c.status_version,
                    wf_user_accounts_table.c.person_id,
                )
                .where(wf_user_accounts_table.c.user_id == user_id)
                .with_for_update()
            ).first()
            if row is None:
                raise WorkflowFoundationNotFound(f"Workflow user {user_id} was not found.")
            if row.status_version != expected_version:
                raise WorkflowFoundationConflict(
                    "The account lifecycle changed. Refresh before changing its status."
                )
            if row.status == status:
                return self._security_user_summary(connection, user_id)
            if (
                status == "inactive"
                and row.status == "active"
                and self._is_workflow_coordinator(connection, user_id)
                and "security_administration"
                in self._configured_module_ids(connection, user_id)
                and self._active_security_coordinator_count(
                    connection,
                    excluding_user_id=user_id,
                ) == 0
            ):
                raise WorkflowFoundationConflict(
                    "The last active Security & Access coordinator cannot be suspended."
                )
            next_version = expected_version + 1
            connection.execute(
                wf_user_accounts_table.update()
                .where(wf_user_accounts_table.c.user_id == user_id)
                .values(status=status, status_version=next_version, updated_at=now)
            )
            connection.execute(
                wf_persons_table.update()
                .where(wf_persons_table.c.person_id == row.person_id)
                .values(status=status)
            )
            if status == "inactive":
                connection.execute(
                    wf_sessions_table.update()
                    .where(
                        wf_sessions_table.c.user_id == user_id,
                        wf_sessions_table.c.revoked_at.is_(None),
                    )
                    .values(revoked_at=now)
                )
            self._append_audit(
                connection,
                event_type=(
                    "identity.user_reactivated"
                    if status == "active"
                    else "identity.user_suspended"
                ),
                actor_user_id=actor_user_id,
                subject_type="user_account",
                subject_id=user_id,
                correlation_id=self._id("COR"),
                details={
                    "before_status": row.status,
                    "after_status": status,
                    "status_version": next_version,
                    "sessions_revoked": status == "inactive",
                    "authority_effect": "none",
                },
                occurred_at=now,
            )
            return self._security_user_summary(connection, user_id)

    def _invitation_summary(self, row: Any) -> dict[str, Any]:
        return {
            "invitation_id": row["invitation_id"],
            "username": row["username"],
            "display_name": row["display_name"],
            "role_ids": json.loads(row["role_ids_json"]),
            "module_ids": json.loads(row["module_ids_json"]),
            "status": row["status"],
            "created_by_user_id": row["created_by_user_id"],
            "created_at": row["created_at"],
            "expires_at": row["expires_at"],
            "activated_at": row["activated_at"],
            "activated_user_id": row["activated_user_id"],
        }

    def _expire_pending_invitations(
        self,
        connection: Connection,
        now: str,
    ) -> None:
        rows = connection.execute(
            select(wf_user_invitations_table)
            .where(
                wf_user_invitations_table.c.status == "pending",
                wf_user_invitations_table.c.expires_at <= now,
            )
            .order_by(
                wf_user_invitations_table.c.created_at,
                wf_user_invitations_table.c.invitation_id,
            )
        ).mappings().all()
        for row in rows:
            connection.execute(
                wf_user_invitations_table.update()
                .where(
                    wf_user_invitations_table.c.invitation_id
                    == row["invitation_id"],
                    wf_user_invitations_table.c.status == "pending",
                )
                .values(status="expired")
            )
            connection.execute(
                wf_invitation_events_table.insert().values(
                    invitation_event_id=self._id("IVE"),
                    invitation_id=row["invitation_id"],
                    event_type="expired",
                    actor_user_id=None,
                    created_at=now,
                    details_json=self._canonical_json(
                        {"reason": "configured_expiration"}
                    ),
                )
            )
            self._append_audit(
                connection,
                event_type="identity.invitation_expired",
                actor_user_id=None,
                subject_type="user_invitation",
                subject_id=row["invitation_id"],
                correlation_id=self._id("COR"),
                details={"username": row["username"], "token_retained": False},
                occurred_at=now,
            )

    def create_invitation(
        self,
        *,
        username: str,
        display_name: str,
        token_hash: str,
        role_ids: list[str],
        module_ids: list[str],
        expires_at: str,
        actor_user_id: str,
    ) -> dict[str, Any]:
        now = self._now()
        invitation_id = self._id("INV")
        try:
            with self._engine.begin() as connection:
                self._expire_pending_invitations(connection, now)
                if connection.execute(
                    select(wf_user_accounts_table.c.user_id).where(
                        func.lower(wf_user_accounts_table.c.username)
                        == username.lower()
                    )
                ).first():
                    raise WorkflowFoundationConflict(
                        "That local username already exists."
                    )
                valid_roles = {
                    row.role_id
                    for row in connection.execute(
                        select(wf_roles_table.c.role_id)
                    ).all()
                }
                valid_modules = {
                    row.module_id
                    for row in connection.execute(
                        select(wf_modules_table.c.module_id).where(
                            wf_modules_table.c.status == "active"
                        )
                    ).all()
                }
                requested_roles = sorted(set(role_ids))
                requested_modules = sorted(set(module_ids))
                if set(requested_roles) - valid_roles:
                    raise WorkflowFoundationConflict(
                        "An unknown workflow role was requested."
                    )
                if set(requested_modules) - valid_modules:
                    raise WorkflowFoundationConflict(
                        "An unknown ETOP module was requested."
                    )
                connection.execute(
                    wf_user_invitations_table.insert().values(
                        invitation_id=invitation_id,
                        username=username,
                        display_name=display_name,
                        token_hash=token_hash,
                        role_ids_json=self._canonical_json(requested_roles),
                        module_ids_json=self._canonical_json(requested_modules),
                        status="pending",
                        created_by_user_id=actor_user_id,
                        created_at=now,
                        expires_at=expires_at,
                        activated_at=None,
                        activated_user_id=None,
                    )
                )
                connection.execute(
                    wf_invitation_events_table.insert().values(
                        invitation_event_id=self._id("IVE"),
                        invitation_id=invitation_id,
                        event_type="created",
                        actor_user_id=actor_user_id,
                        created_at=now,
                        details_json=self._canonical_json(
                            {
                                "username": username,
                                "role_ids": requested_roles,
                                "module_ids": requested_modules,
                                "expires_at": expires_at,
                                "token_stored_as": "sha256",
                            }
                        ),
                    )
                )
                self._append_audit(
                    connection,
                    event_type="identity.invitation_created",
                    actor_user_id=actor_user_id,
                    subject_type="user_invitation",
                    subject_id=invitation_id,
                    correlation_id=self._id("COR"),
                    details={
                        "username": username,
                        "role_ids": requested_roles,
                        "module_ids": requested_modules,
                        "expires_at": expires_at,
                        "token_stored_as": "sha256",
                        "authority_effect": "none",
                    },
                    occurred_at=now,
                )
                row = connection.execute(
                    select(wf_user_invitations_table).where(
                        wf_user_invitations_table.c.invitation_id == invitation_id
                    )
                ).mappings().first()
                return self._invitation_summary(row)
        except IntegrityError as exc:
            raise WorkflowFoundationConflict(
                "A pending invitation for that username already exists."
            ) from exc

    def list_invitations(self) -> list[dict[str, Any]]:
        now = self._now()
        with self._engine.begin() as connection:
            self._expire_pending_invitations(connection, now)
            rows = connection.execute(
                select(wf_user_invitations_table).order_by(
                    wf_user_invitations_table.c.created_at.desc(),
                    wf_user_invitations_table.c.invitation_id.desc(),
                )
            ).mappings().all()
            return [self._invitation_summary(row) for row in rows]

    def revoke_invitation(
        self,
        *,
        invitation_id: str,
        actor_user_id: str,
    ) -> dict[str, Any]:
        now = self._now()
        with self._engine.begin() as connection:
            self._expire_pending_invitations(connection, now)
            row = connection.execute(
                select(wf_user_invitations_table).where(
                    wf_user_invitations_table.c.invitation_id == invitation_id
                )
            ).mappings().first()
            if row is None:
                raise WorkflowFoundationNotFound(
                    f"Invitation {invitation_id} was not found."
                )
            if row["status"] != "pending":
                raise WorkflowFoundationConflict(
                    "Only a pending invitation can be revoked. Refresh its current status."
                )
            changed = connection.execute(
                wf_user_invitations_table.update()
                .where(
                    wf_user_invitations_table.c.invitation_id == invitation_id,
                    wf_user_invitations_table.c.status == "pending",
                )
                .values(status="revoked")
            ).rowcount
            if changed != 1:
                raise WorkflowFoundationConflict(
                    "The invitation changed before it could be revoked."
                )
            connection.execute(
                wf_invitation_events_table.insert().values(
                    invitation_event_id=self._id("IVE"),
                    invitation_id=invitation_id,
                    event_type="revoked",
                    actor_user_id=actor_user_id,
                    created_at=now,
                    details_json=self._canonical_json(
                        {"reason": "coordinator_revocation", "token_reusable": False}
                    ),
                )
            )
            self._append_audit(
                connection,
                event_type="identity.invitation_revoked",
                actor_user_id=actor_user_id,
                subject_type="user_invitation",
                subject_id=invitation_id,
                correlation_id=self._id("COR"),
                details={
                    "username": row["username"],
                    "prior_status": "pending",
                    "after_status": "revoked",
                    "token_reusable": False,
                    "authority_effect": "none",
                },
                occurred_at=now,
            )
            updated = connection.execute(
                select(wf_user_invitations_table).where(
                    wf_user_invitations_table.c.invitation_id == invitation_id
                )
            ).mappings().first()
            return self._invitation_summary(updated)

    def invitation_for_token_hash(self, token_hash: str) -> dict[str, Any] | None:
        now = self._now()
        with self._engine.begin() as connection:
            self._expire_pending_invitations(connection, now)
            row = connection.execute(
                select(wf_user_invitations_table).where(
                    wf_user_invitations_table.c.token_hash == token_hash
                )
            ).mappings().first()
            return self._invitation_summary(row) if row else None

    def activate_invitation(
        self,
        *,
        token_hash: str,
        password_salt: str,
        password_hash: str,
    ) -> str:
        now = self._now()
        try:
            with self._engine.begin() as connection:
                self._expire_pending_invitations(connection, now)
                invitation = connection.execute(
                    select(wf_user_invitations_table).where(
                        wf_user_invitations_table.c.token_hash == token_hash
                    )
                ).mappings().first()
                if invitation is None:
                    raise WorkflowFoundationNotFound(
                        "The invitation token was not recognized by this local ETOP instance."
                    )
                if invitation["status"] != "pending":
                    raise WorkflowFoundationConflict(
                        "This invitation is expired, revoked, or has already been activated."
                    )
                user_id = self._id("USR")
                person_id = self._id("PER")
                role_ids = json.loads(invitation["role_ids_json"])
                module_ids = json.loads(invitation["module_ids_json"])
                connection.execute(
                    wf_persons_table.insert().values(
                        person_id=person_id,
                        display_name=invitation["display_name"],
                        status="active",
                        created_at=now,
                        created_by_user_id=invitation["created_by_user_id"],
                    )
                )
                connection.execute(
                    wf_user_accounts_table.insert().values(
                        user_id=user_id,
                        person_id=person_id,
                        username=invitation["username"],
                        password_salt=password_salt,
                        password_hash=password_hash,
                        password_algorithm="scrypt-n16384-r8-p1-v1",
                        status="active",
                        status_version=1,
                        created_at=now,
                        updated_at=now,
                    )
                )
                for role_id in role_ids:
                    connection.execute(
                        wf_role_assignments_table.insert().values(
                            role_assignment_id=self._id("RLA"),
                            user_id=user_id,
                            role_id=role_id,
                            effective_from=now,
                            effective_to=None,
                            assignment_status="active",
                            assigned_by_user_id=invitation["created_by_user_id"],
                            created_at=now,
                        )
                    )
                connection.execute(
                    wf_access_profiles_table.insert().values(
                        user_id=user_id,
                        access_version=1,
                        updated_at=now,
                        updated_by_user_id=invitation["created_by_user_id"],
                    )
                )
                for module_id in module_ids:
                    connection.execute(
                        wf_user_module_access_table.insert().values(
                            user_id=user_id,
                            module_id=module_id,
                            allowed=1,
                            updated_at=now,
                            updated_by_user_id=invitation["created_by_user_id"],
                        )
                    )
                connection.execute(
                    wf_module_access_events_table.insert().values(
                        access_event_id=self._id("ACE"),
                        user_id=user_id,
                        actor_user_id=invitation["created_by_user_id"],
                        before_module_ids_json="[]",
                        after_module_ids_json=self._canonical_json(module_ids),
                        access_version=1,
                        reason="invitation_activation",
                        created_at=now,
                    )
                )
                changed = connection.execute(
                    wf_user_invitations_table.update()
                    .where(
                        wf_user_invitations_table.c.invitation_id
                        == invitation["invitation_id"],
                        wf_user_invitations_table.c.status == "pending",
                    )
                    .values(
                        status="activated",
                        activated_at=now,
                        activated_user_id=user_id,
                    )
                ).rowcount
                if changed != 1:
                    raise WorkflowFoundationConflict(
                        "This invitation was activated by another request."
                    )
                connection.execute(
                    wf_invitation_events_table.insert().values(
                        invitation_event_id=self._id("IVE"),
                        invitation_id=invitation["invitation_id"],
                        event_type="activated",
                        actor_user_id=user_id,
                        created_at=now,
                        details_json=self._canonical_json(
                            {
                                "user_id": user_id,
                                "person_id": person_id,
                                "token_reusable": False,
                            }
                        ),
                    )
                )
                self._append_audit(
                    connection,
                    event_type="identity.invitation_activated",
                    actor_user_id=user_id,
                    subject_type="user_account",
                    subject_id=user_id,
                    correlation_id=self._id("COR"),
                    details={
                        "invitation_id": invitation["invitation_id"],
                        "person_id": person_id,
                        "username": invitation["username"],
                        "role_ids": role_ids,
                        "module_ids": module_ids,
                        "token_reusable": False,
                        "authority_effect": "none",
                    },
                    occurred_at=now,
                )
                return user_id
        except IntegrityError as exc:
            raise WorkflowFoundationConflict(
                "The invited username was activated elsewhere or now conflicts with an account."
            ) from exc

    def _password_reset_summary(self, row: Any) -> dict[str, Any]:
        return {
            "reset_id": row["reset_id"],
            "user_id": row["user_id"],
            "status": row["status"],
            "created_by_user_id": row["created_by_user_id"],
            "created_at": row["created_at"],
            "expires_at": row["expires_at"],
            "activated_at": row["activated_at"],
        }

    def _expire_pending_password_resets(
        self,
        connection: Connection,
        now: str,
    ) -> None:
        rows = connection.execute(
            select(wf_password_reset_tokens_table)
            .where(
                wf_password_reset_tokens_table.c.status == "pending",
                wf_password_reset_tokens_table.c.expires_at <= now,
            )
            .order_by(
                wf_password_reset_tokens_table.c.created_at,
                wf_password_reset_tokens_table.c.reset_id,
            )
        ).mappings().all()
        for row in rows:
            connection.execute(
                wf_password_reset_tokens_table.update()
                .where(
                    wf_password_reset_tokens_table.c.reset_id == row["reset_id"],
                    wf_password_reset_tokens_table.c.status == "pending",
                )
                .values(status="expired")
            )
            connection.execute(
                wf_password_reset_events_table.insert().values(
                    reset_event_id=self._id("PRE"),
                    reset_id=row["reset_id"],
                    event_type="expired",
                    actor_user_id=None,
                    created_at=now,
                    details_json=self._canonical_json(
                        {"reason": "configured_expiration"}
                    ),
                )
            )
            self._append_audit(
                connection,
                event_type="identity.password_reset_expired",
                actor_user_id=None,
                subject_type="password_reset",
                subject_id=row["reset_id"],
                correlation_id=self._id("COR"),
                details={"user_id": row["user_id"], "token_retained": False},
                occurred_at=now,
            )

    def create_password_reset(
        self,
        *,
        user_id: str,
        token_hash: str,
        expires_at: str,
        actor_user_id: str,
    ) -> dict[str, Any]:
        now = self._now()
        reset_id = self._id("PWR")
        with self._engine.begin() as connection:
            self._expire_pending_password_resets(connection, now)
            if connection.execute(
                select(wf_user_accounts_table.c.user_id).where(
                    wf_user_accounts_table.c.user_id == user_id
                )
            ).first() is None:
                raise WorkflowFoundationNotFound(f"Workflow user {user_id} was not found.")
            connection.execute(
                wf_password_reset_tokens_table.insert().values(
                    reset_id=reset_id,
                    user_id=user_id,
                    token_hash=token_hash,
                    status="pending",
                    created_by_user_id=actor_user_id,
                    created_at=now,
                    expires_at=expires_at,
                    activated_at=None,
                )
            )
            connection.execute(
                wf_password_reset_events_table.insert().values(
                    reset_event_id=self._id("PRE"),
                    reset_id=reset_id,
                    event_type="created",
                    actor_user_id=actor_user_id,
                    created_at=now,
                    details_json=self._canonical_json(
                        {
                            "user_id": user_id,
                            "expires_at": expires_at,
                            "token_stored_as": "sha256",
                        }
                    ),
                )
            )
            self._append_audit(
                connection,
                event_type="identity.password_reset_requested",
                actor_user_id=actor_user_id,
                subject_type="user_account",
                subject_id=user_id,
                correlation_id=self._id("COR"),
                details={
                    "reset_id": reset_id,
                    "expires_at": expires_at,
                    "token_stored_as": "sha256",
                    "authority_effect": "none",
                },
                occurred_at=now,
            )
            row = connection.execute(
                select(wf_password_reset_tokens_table).where(
                    wf_password_reset_tokens_table.c.reset_id == reset_id
                )
            ).mappings().first()
            return self._password_reset_summary(row)

    def password_reset_for_token_hash(self, token_hash: str) -> dict[str, Any] | None:
        now = self._now()
        with self._engine.begin() as connection:
            self._expire_pending_password_resets(connection, now)
            row = connection.execute(
                select(wf_password_reset_tokens_table).where(
                    wf_password_reset_tokens_table.c.token_hash == token_hash
                )
            ).mappings().first()
            return self._password_reset_summary(row) if row else None

    def activate_password_reset(
        self,
        *,
        token_hash: str,
        password_salt: str,
        password_hash: str,
    ) -> str:
        now = self._now()
        with self._engine.begin() as connection:
            self._expire_pending_password_resets(connection, now)
            reset = connection.execute(
                select(wf_password_reset_tokens_table).where(
                    wf_password_reset_tokens_table.c.token_hash == token_hash
                )
            ).mappings().first()
            if reset is None:
                raise WorkflowFoundationNotFound(
                    "The password reset token was not recognized by this local ETOP instance."
                )
            if reset["status"] != "pending":
                raise WorkflowFoundationConflict(
                    "This password reset link is expired or has already been used."
                )
            user_id = reset["user_id"]
            changed = connection.execute(
                wf_user_accounts_table.update()
                .where(wf_user_accounts_table.c.user_id == user_id)
                .values(
                    password_salt=password_salt,
                    password_hash=password_hash,
                    credential_version=wf_user_accounts_table.c.credential_version
                    + 1,
                    updated_at=now,
                )
            ).rowcount
            if changed != 1:
                raise WorkflowFoundationNotFound(f"Workflow user {user_id} was not found.")
            connection.execute(
                wf_sessions_table.update()
                .where(
                    wf_sessions_table.c.user_id == user_id,
                    wf_sessions_table.c.revoked_at.is_(None),
                )
                .values(revoked_at=now)
            )
            changed = connection.execute(
                wf_password_reset_tokens_table.update()
                .where(
                    wf_password_reset_tokens_table.c.reset_id == reset["reset_id"],
                    wf_password_reset_tokens_table.c.status == "pending",
                )
                .values(status="activated", activated_at=now)
            ).rowcount
            if changed != 1:
                raise WorkflowFoundationConflict(
                    "This password reset link was activated by another request."
                )
            connection.execute(
                wf_password_reset_events_table.insert().values(
                    reset_event_id=self._id("PRE"),
                    reset_id=reset["reset_id"],
                    event_type="activated",
                    actor_user_id=user_id,
                    created_at=now,
                    details_json=self._canonical_json(
                        {
                            "user_id": user_id,
                            "sessions_revoked": True,
                            "token_reusable": False,
                        }
                    ),
                )
            )
            self._append_audit(
                connection,
                event_type="identity.password_reset_completed",
                actor_user_id=user_id,
                subject_type="user_account",
                subject_id=user_id,
                correlation_id=self._id("COR"),
                details={
                    "reset_id": reset["reset_id"],
                    "sessions_revoked": True,
                    "token_reusable": False,
                    "authority_effect": "none",
                },
                occurred_at=now,
            )
            return user_id

    def set_user_password(
        self,
        *,
        user_id: str,
        password_salt: str,
        password_hash: str,
        expected_version: int,
        actor_user_id: str,
    ) -> dict[str, Any]:
        now = self._now()
        with self._engine.begin() as connection:
            row = connection.execute(
                select(wf_user_accounts_table.c.credential_version)
                .where(wf_user_accounts_table.c.user_id == user_id)
                .with_for_update()
            ).first()
            if row is None:
                raise WorkflowFoundationNotFound(f"Workflow user {user_id} was not found.")
            if row.credential_version != expected_version:
                raise WorkflowFoundationConflict(
                    "The account credential changed. Refresh before setting a new password."
                )
            next_version = expected_version + 1
            connection.execute(
                wf_user_accounts_table.update()
                .where(wf_user_accounts_table.c.user_id == user_id)
                .values(
                    password_salt=password_salt,
                    password_hash=password_hash,
                    credential_version=next_version,
                    updated_at=now,
                )
            )
            connection.execute(
                wf_sessions_table.update()
                .where(
                    wf_sessions_table.c.user_id == user_id,
                    wf_sessions_table.c.revoked_at.is_(None),
                )
                .values(revoked_at=now)
            )
            self._append_audit(
                connection,
                event_type="identity.password_set_by_admin",
                actor_user_id=actor_user_id,
                subject_type="user_account",
                subject_id=user_id,
                correlation_id=self._id("COR"),
                details={
                    "credential_version": next_version,
                    "sessions_revoked": True,
                    "authority_effect": "none",
                },
                occurred_at=now,
            )
            return self._security_user_summary(connection, user_id)

    def list_roles(self) -> list[dict[str, Any]]:
        with self._engine.connect() as connection:
            rows = connection.execute(
                select(wf_roles_table).order_by(
                    wf_roles_table.c.name, wf_roles_table.c.role_id
                )
            ).mappings().all()
            return [self._role_summary(row) for row in rows]

    def list_definitions(self) -> list[dict[str, Any]]:
        with self._engine.connect() as connection:
            rows = connection.execute(
                select(wf_definitions_table).order_by(
                    wf_definitions_table.c.definition_id,
                    wf_definitions_table.c.version,
                )
            ).mappings().all()
            return [
                {
                    "definition_id": row["definition_id"],
                    "version": row["version"],
                    "title": row["title"],
                    "description": row["description"],
                    "states": json.loads(row["states_json"]),
                    "transitions": json.loads(row["transitions_json"]),
                    "status": row["status"],
                    "authority_effect": row["authority_effect"],
                }
                for row in rows
            ]

    def user_role_ids(self, user_id: str) -> set[str]:
        return {role["role_id"] for role in self.get_user(user_id)["roles"]}

    def _latest_assignee_id(
        self,
        connection: Connection,
        task_id: str,
    ) -> str | None:
        row = connection.execute(
            select(wf_task_assignments_table.c.assignee_user_id)
            .where(wf_task_assignments_table.c.task_id == task_id)
            .order_by(wf_task_assignments_table.c.sequence.desc())
            .limit(1)
        ).first()
        return row.assignee_user_id if row else None

    def _task_summary(
        self,
        connection: Connection,
        row: Any,
    ) -> dict[str, Any]:
        assignee_id = self._latest_assignee_id(connection, row["task_id"])
        role_row = connection.execute(
            select(wf_roles_table).where(
                wf_roles_table.c.role_id == row["queue_role_id"]
            )
        ).mappings().first()
        return {
            "task_id": row["task_id"],
            "definition_id": row["definition_id"],
            "definition_version": row["definition_version"],
            "title": row["title"],
            "description": row["description"],
            "capability": row["capability"],
            "context_type": row["context_type"],
            "context_id": row["context_id"],
            "context_label": row["context_label"],
            "queue_role": self._role_summary(role_row),
            "assignee": self._user_summary(connection, assignee_id) if assignee_id else None,
            "priority": row["priority"],
            "state": row["state"],
            "due_date": row["due_date"],
            "created_by": self._user_summary(connection, row["created_by_user_id"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "version": row["version"],
            "assignment_effect": row["assignment_effect"],
            "authority_effect": row["authority_effect"],
            "execution_effect": row["execution_effect"],
        }

    def _get_task_row(self, connection: Connection, task_id: str) -> Any:
        row = connection.execute(
            select(wf_tasks_table).where(wf_tasks_table.c.task_id == task_id)
        ).mappings().first()
        if row is None:
            raise WorkflowFoundationNotFound(f"Workflow task {task_id} was not found.")
        return row

    def create_task(self, payload: dict[str, Any], actor_user_id: str) -> dict[str, Any]:
        now = self._now()
        task_id = self._id("TSK")
        correlation_id = self._id("COR")
        request_sha256 = hashlib.sha256(
            self._canonical_json(
                {"actor_user_id": actor_user_id, **payload}
            ).encode("utf-8")
        ).hexdigest()
        try:
            with self._engine.begin() as connection:
                existing = connection.execute(
                    select(wf_tasks_table).where(
                        wf_tasks_table.c.created_by_user_id == actor_user_id,
                        wf_tasks_table.c.idempotency_key
                        == payload["idempotency_key"],
                    )
                ).mappings().first()
                if existing:
                    if existing["request_sha256"] != request_sha256:
                        raise WorkflowFoundationConflict(
                            "That task idempotency key was already used with a different request."
                        )
                    return self._task_summary(connection, existing)
                connection.execute(
                    wf_tasks_table.insert().values(
                        task_id=task_id,
                        definition_id=self.DEFINITION_ID,
                        definition_version=self.DEFINITION_VERSION,
                        title=payload["title"],
                        description=payload["description"],
                        capability=payload["capability"],
                        context_type=payload["context_type"],
                        context_id=payload["context_id"],
                        context_label=payload["context_label"],
                        queue_role_id=payload["queue_role_id"],
                        priority=payload["priority"],
                        state="open",
                        due_date=payload.get("due_date"),
                        created_by_user_id=actor_user_id,
                        idempotency_key=payload["idempotency_key"],
                        request_sha256=request_sha256,
                        created_at=now,
                        updated_at=now,
                        version=1,
                        assignment_effect="work_ownership_only",
                        authority_effect="none",
                        execution_effect="none",
                    )
                )
                connection.execute(
                    wf_task_events_table.insert().values(
                        event_id=self._id("TEV"),
                        task_id=task_id,
                        event_type="task_created",
                        from_state=None,
                        to_state="open",
                        actor_user_id=actor_user_id,
                        note="Task created from a governed context reference.",
                        idempotency_key=f"create:{task_id}",
                        task_version=1,
                        created_at=now,
                    )
                )
                self._append_audit(
                    connection,
                    event_type="workflow.task_created",
                    actor_user_id=actor_user_id,
                    subject_type="workflow_task",
                    subject_id=task_id,
                    correlation_id=correlation_id,
                    details={
                        "definition_id": self.DEFINITION_ID,
                        "definition_version": self.DEFINITION_VERSION,
                        "capability": payload["capability"],
                        "context_type": payload["context_type"],
                        "context_id": payload["context_id"],
                        "queue_role_id": payload["queue_role_id"],
                        "state": "open",
                        "authority_effect": "none",
                        "execution_effect": "none",
                    },
                    occurred_at=now,
                )
                if payload.get("assignee_user_id"):
                    self._insert_assignment(
                        connection,
                        task_id=task_id,
                        assignee_user_id=payload["assignee_user_id"],
                        assigned_by_user_id=actor_user_id,
                        assignment_type="initial",
                        note="Initial verified work ownership.",
                        idempotency_key=f"initial:{task_id}",
                        task_version=1,
                        correlation_id=correlation_id,
                        created_at=now,
                    )
            return self.get_task(task_id)
        except IntegrityError as exc:
            raise WorkflowFoundationConflict(
                "The task could not be created because its role, assignee, or idempotency evidence is invalid."
            ) from exc

    def _insert_notification(
        self,
        connection: Connection,
        *,
        recipient_user_id: str,
        task_id: str | None,
        notification_type: str,
        title: str,
        message: str,
        severity: str,
        created_at: str,
    ) -> str:
        notification_id = self._id("NTF")
        connection.execute(
            wf_notifications_table.insert().values(
                notification_id=notification_id,
                recipient_user_id=recipient_user_id,
                task_id=task_id,
                notification_type=notification_type,
                title=title,
                message=message,
                severity=severity,
                created_at=created_at,
                read_at=None,
            )
        )
        return notification_id

    def _insert_assignment(
        self,
        connection: Connection,
        *,
        task_id: str,
        assignee_user_id: str,
        assigned_by_user_id: str,
        assignment_type: str,
        note: str,
        idempotency_key: str,
        task_version: int,
        correlation_id: str,
        created_at: str,
    ) -> None:
        prior_assignee = self._latest_assignee_id(connection, task_id)
        connection.execute(
            wf_task_assignments_table.insert().values(
                assignment_event_id=self._id("ASN"),
                task_id=task_id,
                assignee_user_id=assignee_user_id,
                prior_assignee_user_id=prior_assignee,
                assigned_by_user_id=assigned_by_user_id,
                assignment_type=assignment_type,
                note=note,
                idempotency_key=idempotency_key,
                task_version=task_version,
                created_at=created_at,
                authority_effect="none",
            )
        )
        task = self._get_task_row(connection, task_id)
        self._insert_notification(
            connection,
            recipient_user_id=assignee_user_id,
            task_id=task_id,
            notification_type="task_assigned",
            title="Work assigned",
            message=f"{task['title']} · {task['context_label']}",
            severity="info",
            created_at=created_at,
        )
        self._append_audit(
            connection,
            event_type="workflow.task_assigned",
            actor_user_id=assigned_by_user_id,
            subject_type="workflow_task",
            subject_id=task_id,
            correlation_id=correlation_id,
            details={
                "assignee_user_id": assignee_user_id,
                "prior_assignee_user_id": prior_assignee,
                "assignment_type": assignment_type,
                "task_version": task_version,
                "authority_effect": "none",
            },
            occurred_at=created_at,
        )

    def _task_detail(self, connection: Connection, task_id: str) -> dict[str, Any]:
        row = self._get_task_row(connection, task_id)
        task = self._task_summary(connection, row)
        assignment_rows = connection.execute(
            select(wf_task_assignments_table)
            .where(wf_task_assignments_table.c.task_id == task_id)
            .order_by(wf_task_assignments_table.c.sequence)
        ).mappings().all()
        event_rows = connection.execute(
            select(wf_task_events_table)
            .where(wf_task_events_table.c.task_id == task_id)
            .order_by(wf_task_events_table.c.sequence)
        ).mappings().all()
        task["assignments"] = [
            {
                "assignment_event_id": item["assignment_event_id"],
                "task_id": item["task_id"],
                "assignee": self._user_summary(connection, item["assignee_user_id"]),
                "prior_assignee_user_id": item["prior_assignee_user_id"],
                "assigned_by": self._user_summary(connection, item["assigned_by_user_id"]),
                "assignment_type": item["assignment_type"],
                "note": item["note"],
                "task_version": item["task_version"],
                "created_at": item["created_at"],
                "authority_effect": item["authority_effect"],
            }
            for item in assignment_rows
        ]
        task["events"] = [
            {
                "event_id": item["event_id"],
                "task_id": item["task_id"],
                "event_type": item["event_type"],
                "from_state": item["from_state"],
                "to_state": item["to_state"],
                "actor": self._user_summary(connection, item["actor_user_id"]),
                "note": item["note"],
                "task_version": item["task_version"],
                "created_at": item["created_at"],
            }
            for item in event_rows
        ]
        return task

    def get_task(self, task_id: str) -> dict[str, Any]:
        with self._engine.connect() as connection:
            return self._task_detail(connection, task_id)

    def list_tasks(
        self,
        *,
        actor_user_id: str,
        coordinator: bool,
        mine: bool,
        capability: str | None,
        state: str | None,
    ) -> list[dict[str, Any]]:
        with self._engine.connect() as connection:
            conditions = []
            if capability:
                conditions.append(wf_tasks_table.c.capability == capability)
            if state:
                conditions.append(wf_tasks_table.c.state == state)
            role_ids = self.user_role_ids(actor_user_id)
            latest_assignee = (
                select(wf_task_assignments_table.c.assignee_user_id)
                .where(wf_task_assignments_table.c.task_id == wf_tasks_table.c.task_id)
                .order_by(wf_task_assignments_table.c.sequence.desc())
                .limit(1)
                .scalar_subquery()
            )
            if coordinator and not mine:
                pass
            elif mine:
                conditions.append(latest_assignee == actor_user_id)
            else:
                has_any_assignment = (
                    select(wf_task_assignments_table.c.assignment_event_id)
                    .where(
                        wf_task_assignments_table.c.task_id
                        == wf_tasks_table.c.task_id
                    )
                    .exists()
                )
                conditions.append(
                    (latest_assignee == actor_user_id)
                    | (
                        ~has_any_assignment
                        & wf_tasks_table.c.queue_role_id.in_(sorted(role_ids))
                    )
                )
            priority_order = case(
                (wf_tasks_table.c.priority == "critical", 1),
                (wf_tasks_table.c.priority == "high", 2),
                (wf_tasks_table.c.priority == "medium", 3),
                else_=4,
            )
            due_date_order = case(
                (wf_tasks_table.c.due_date.is_(None), 1), else_=0
            )
            rows = connection.execute(
                select(wf_tasks_table)
                .where(*conditions)
                .order_by(
                    priority_order,
                    due_date_order,
                    wf_tasks_table.c.due_date,
                    wf_tasks_table.c.updated_at.desc(),
                    wf_tasks_table.c.task_id,
                )
            ).mappings().all()
            return [self._task_summary(connection, row) for row in rows]

    def assign_task(
        self,
        *,
        task_id: str,
        assignee_user_id: str,
        note: str,
        expected_version: int,
        idempotency_key: str,
        actor_user_id: str,
        assignment_type: str,
    ) -> dict[str, Any]:
        now = self._now()
        correlation_id = self._id("COR")
        with self._engine.begin() as connection:
            existing = connection.execute(
                select(wf_task_assignments_table).where(
                    wf_task_assignments_table.c.idempotency_key == idempotency_key
                )
            ).mappings().first()
            if existing:
                if (
                    existing["task_id"] != task_id
                    or existing["assignee_user_id"] != assignee_user_id
                    or existing["assigned_by_user_id"] != actor_user_id
                    or existing["note"] != note
                ):
                    raise WorkflowFoundationConflict(
                        "That assignment idempotency key was already used with a different request."
                    )
                return self._task_detail(connection, task_id)
            task = self._get_task_row(connection, task_id)
            if task["version"] != expected_version:
                raise WorkflowFoundationConflict(
                    f"Task version changed. Expected {expected_version}; current version is {task['version']}."
                )
            new_version = expected_version + 1
            connection.execute(
                wf_tasks_table.update()
                .where(
                    wf_tasks_table.c.task_id == task_id,
                    wf_tasks_table.c.version == expected_version,
                )
                .values(version=new_version, updated_at=now)
            )
            self._insert_assignment(
                connection,
                task_id=task_id,
                assignee_user_id=assignee_user_id,
                assigned_by_user_id=actor_user_id,
                assignment_type=assignment_type,
                note=note,
                idempotency_key=idempotency_key,
                task_version=new_version,
                correlation_id=correlation_id,
                created_at=now,
            )
        return self.get_task(task_id)

    def transition_task(
        self,
        *,
        task_id: str,
        target_state: str,
        note: str,
        expected_version: int,
        idempotency_key: str,
        actor_user_id: str,
    ) -> dict[str, Any]:
        now = self._now()
        correlation_id = self._id("COR")
        with self._engine.begin() as connection:
            existing = connection.execute(
                select(wf_task_events_table).where(
                    wf_task_events_table.c.idempotency_key == idempotency_key
                )
            ).mappings().first()
            if existing:
                if (
                    existing["task_id"] != task_id
                    or existing["to_state"] != target_state
                    or existing["actor_user_id"] != actor_user_id
                    or existing["note"] != note
                ):
                    raise WorkflowFoundationConflict(
                        "That transition idempotency key was already used with a different request."
                    )
                return self._task_detail(connection, task_id)
            task = self._get_task_row(connection, task_id)
            if task["version"] != expected_version:
                raise WorkflowFoundationConflict(
                    f"Task version changed. Expected {expected_version}; current version is {task['version']}."
                )
            allowed = self.TRANSITIONS.get(task["state"], [])
            if target_state not in allowed:
                raise WorkflowFoundationConflict(
                    f"Transition from {task['state']} to {target_state} is not permitted by {self.DEFINITION_ID} {self.DEFINITION_VERSION}."
                )
            new_version = expected_version + 1
            changed = connection.execute(
                wf_tasks_table.update()
                .where(
                    wf_tasks_table.c.task_id == task_id,
                    wf_tasks_table.c.version == expected_version,
                )
                .values(state=target_state, version=new_version, updated_at=now)
            ).rowcount
            if changed != 1:
                raise WorkflowFoundationConflict("The task changed during transition.")
            connection.execute(
                wf_task_events_table.insert().values(
                    event_id=self._id("TEV"),
                    task_id=task_id,
                    event_type="task_state_changed",
                    from_state=task["state"],
                    to_state=target_state,
                    actor_user_id=actor_user_id,
                    note=note,
                    idempotency_key=idempotency_key,
                    task_version=new_version,
                    created_at=now,
                )
            )
            assignee_id = self._latest_assignee_id(connection, task_id)
            if assignee_id:
                self._insert_notification(
                    connection,
                    recipient_user_id=assignee_id,
                    task_id=task_id,
                    notification_type="task_state_changed",
                    title="Work state changed",
                    message=f"{task['title']} is now {target_state.replace('_', ' ')}.",
                    severity="success" if target_state == "completed" else "info",
                    created_at=now,
                )
            self._append_audit(
                connection,
                event_type="workflow.task_state_changed",
                actor_user_id=actor_user_id,
                subject_type="workflow_task",
                subject_id=task_id,
                correlation_id=correlation_id,
                details={
                    "from_state": task["state"],
                    "to_state": target_state,
                    "task_version": new_version,
                    "authority_effect": "none",
                    "execution_effect": "none",
                },
                occurred_at=now,
            )
        return self.get_task(task_id)

    def list_notifications(self, user_id: str) -> list[dict[str, Any]]:
        with self._engine.connect() as connection:
            rows = connection.execute(
                select(wf_notifications_table)
                .where(wf_notifications_table.c.recipient_user_id == user_id)
                .order_by(
                    wf_notifications_table.c.created_at.desc(),
                    wf_notifications_table.c.notification_id.desc(),
                )
                .limit(250)
            ).mappings().all()
            return [
                {
                    "notification_id": row["notification_id"],
                    "task_id": row["task_id"],
                    "notification_type": row["notification_type"],
                    "title": row["title"],
                    "message": row["message"],
                    "severity": row["severity"],
                    "created_at": row["created_at"],
                    "read_at": row["read_at"],
                }
                for row in rows
            ]

    def mark_notification_read(
        self,
        notification_id: str,
        actor_user_id: str,
    ) -> dict[str, Any]:
        now = self._now()
        with self._engine.begin() as connection:
            row = connection.execute(
                select(wf_notifications_table).where(
                    wf_notifications_table.c.notification_id == notification_id,
                    wf_notifications_table.c.recipient_user_id == actor_user_id,
                )
            ).mappings().first()
            if row is None:
                raise WorkflowFoundationNotFound(
                    f"Notification {notification_id} was not found for this user."
                )
            if row["read_at"] is None:
                connection.execute(
                    wf_notifications_table.update()
                    .where(
                        wf_notifications_table.c.notification_id == notification_id
                    )
                    .values(read_at=now)
                )
                self._append_audit(
                    connection,
                    event_type="notification.read",
                    actor_user_id=actor_user_id,
                    subject_type="notification",
                    subject_id=notification_id,
                    correlation_id=self._id("COR"),
                    details={
                        "task_id": row["task_id"],
                        "delivery_scope": "in_app_local",
                    },
                    occurred_at=now,
                )
            updated = connection.execute(
                select(wf_notifications_table).where(
                    wf_notifications_table.c.notification_id == notification_id
                )
            ).mappings().first()
            return {
                "notification_id": updated["notification_id"],
                "task_id": updated["task_id"],
                "notification_type": updated["notification_type"],
                "title": updated["title"],
                "message": updated["message"],
                "severity": updated["severity"],
                "created_at": updated["created_at"],
                "read_at": updated["read_at"],
            }

    def list_audit(
        self,
        *,
        subject_type: str | None = None,
        subject_id: str | None = None,
        limit: int = 250,
    ) -> list[dict[str, Any]]:
        with self._engine.connect() as connection:
            conditions = []
            if subject_type:
                conditions.append(wf_audit_events_table.c.subject_type == subject_type)
            if subject_id:
                conditions.append(wf_audit_events_table.c.subject_id == subject_id)
            rows = connection.execute(
                select(wf_audit_events_table)
                .where(*conditions)
                .order_by(wf_audit_events_table.c.sequence.desc())
                .limit(limit)
            ).mappings().all()
            return [
                {
                    "audit_id": row["audit_id"],
                    "event_type": row["event_type"],
                    "actor_user_id": row["actor_user_id"],
                    "subject_type": row["subject_type"],
                    "subject_id": row["subject_id"],
                    "correlation_id": row["correlation_id"],
                    "occurred_at": row["occurred_at"],
                    "details": json.loads(row["details_json"]),
                    "previous_hash": row["previous_hash"],
                    "record_hash": row["record_hash"],
                    "schema_version": row["schema_version"],
                }
                for row in rows
            ]

    def verify_audit_integrity(self) -> dict[str, Any]:
        with self._engine.connect() as connection:
            rows = connection.execute(
                select(wf_audit_events_table).order_by(
                    wf_audit_events_table.c.sequence
                )
            ).mappings().all()
            previous_hash = "0" * 64
            for index, row in enumerate(rows):
                details = json.loads(row["details_json"])
                basis = {
                    "audit_id": row["audit_id"],
                    "event_type": row["event_type"],
                    "actor_user_id": row["actor_user_id"],
                    "subject_type": row["subject_type"],
                    "subject_id": row["subject_id"],
                    "correlation_id": row["correlation_id"],
                    "occurred_at": row["occurred_at"],
                    "details": details,
                    "previous_hash": row["previous_hash"],
                    "schema_version": row["schema_version"],
                }
                calculated = hashlib.sha256(
                    self._canonical_json(basis).encode("utf-8")
                ).hexdigest()
                if row["previous_hash"] != previous_hash or row["record_hash"] != calculated:
                    return {
                        "valid": False,
                        "checked_records": index + 1,
                        "first_invalid_audit_id": row["audit_id"],
                        "algorithm": "sha256_hash_chain",
                    }
                previous_hash = row["record_hash"]
            return {
                "valid": True,
                "checked_records": len(rows),
                "first_invalid_audit_id": None,
                "algorithm": "sha256_hash_chain",
            }

    def counts(self, user_id: str | None = None) -> dict[str, int]:
        with self._engine.connect() as connection:
            users = connection.execute(
                select(func.count()).select_from(wf_user_accounts_table)
            ).scalar_one()
            open_tasks = connection.execute(
                select(func.count())
                .select_from(wf_tasks_table)
                .where(wf_tasks_table.c.state.notin_(("completed", "cancelled")))
            ).scalar_one()
            audit_records = connection.execute(
                select(func.count()).select_from(wf_audit_events_table)
            ).scalar_one()
            unread = 0
            if user_id:
                unread = connection.execute(
                    select(func.count())
                    .select_from(wf_notifications_table)
                    .where(
                        wf_notifications_table.c.recipient_user_id == user_id,
                        wf_notifications_table.c.read_at.is_(None),
                    )
                ).scalar_one()
            return {
                "users": users,
                "open_tasks": open_tasks,
                "audit_records": audit_records,
                "unread_notifications": unread,
            }
