from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from data.database import get_connection


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
        connection_factory: Callable[[], sqlite3.Connection] = get_connection,
        clock: Callable[[], datetime] | None = None,
        id_factory: Callable[[str], str] | None = None,
    ) -> None:
        self._connection_factory = connection_factory
        self._clock = clock or (lambda: datetime.now(UTC))
        self._id_factory = id_factory or (
            lambda prefix: f"{prefix}-{uuid4().hex}"
        )
        self._initialization_lock = threading.Lock()

    def _connection(self) -> sqlite3.Connection:
        connection = self._connection_factory()
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON;")
        return connection

    def _now(self) -> str:
        value = self._clock()
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).isoformat()

    def _id(self, prefix: str) -> str:
        return self._id_factory(prefix)

    def initialize(self) -> None:
        with self._initialization_lock:
            connection = self._connection()
            try:
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS wf_persons (
                        person_id TEXT PRIMARY KEY,
                        display_name TEXT NOT NULL,
                        status TEXT NOT NULL CHECK (status IN ('active', 'inactive')),
                        created_at TEXT NOT NULL,
                        created_by_user_id TEXT
                    );

                    CREATE TABLE IF NOT EXISTS wf_user_accounts (
                        user_id TEXT PRIMARY KEY,
                        person_id TEXT NOT NULL UNIQUE,
                        username TEXT NOT NULL COLLATE NOCASE UNIQUE,
                        password_salt TEXT NOT NULL,
                        password_hash TEXT NOT NULL,
                        password_algorithm TEXT NOT NULL CHECK (
                            password_algorithm = 'scrypt-n16384-r8-p1-v1'
                        ),
                        status TEXT NOT NULL CHECK (status IN ('active', 'inactive')),
                        status_version INTEGER NOT NULL DEFAULT 1 CHECK (status_version >= 1),
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        FOREIGN KEY (person_id) REFERENCES wf_persons(person_id)
                    );

                    CREATE TABLE IF NOT EXISTS wf_roles (
                        role_id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        description TEXT NOT NULL,
                        queue_scope TEXT NOT NULL,
                        authority_effect TEXT NOT NULL CHECK (authority_effect = 'none'),
                        decision_authority INTEGER NOT NULL CHECK (decision_authority = 0),
                        created_at TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS wf_role_assignments (
                        role_assignment_id TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        role_id TEXT NOT NULL,
                        effective_from TEXT NOT NULL,
                        effective_to TEXT,
                        assignment_status TEXT NOT NULL CHECK (
                            assignment_status = 'active'
                        ),
                        assigned_by_user_id TEXT,
                        created_at TEXT NOT NULL,
                        UNIQUE (user_id, role_id, effective_from),
                        FOREIGN KEY (user_id) REFERENCES wf_user_accounts(user_id),
                        FOREIGN KEY (role_id) REFERENCES wf_roles(role_id)
                    );

                    CREATE TRIGGER IF NOT EXISTS wf_role_assignments_no_update
                    BEFORE UPDATE ON wf_role_assignments
                    BEGIN
                        SELECT RAISE(ABORT, 'Workflow role assignments are append-only.');
                    END;

                    CREATE TRIGGER IF NOT EXISTS wf_role_assignments_no_delete
                    BEFORE DELETE ON wf_role_assignments
                    BEGIN
                        SELECT RAISE(ABORT, 'Workflow role assignments are append-only.');
                    END;

                    CREATE TABLE IF NOT EXISTS wf_sessions (
                        session_id TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        token_hash TEXT NOT NULL UNIQUE,
                        issued_at TEXT NOT NULL,
                        expires_at TEXT NOT NULL,
                        revoked_at TEXT,
                        last_seen_at TEXT NOT NULL,
                        FOREIGN KEY (user_id) REFERENCES wf_user_accounts(user_id)
                    );

                    CREATE INDEX IF NOT EXISTS idx_wf_sessions_token
                    ON wf_sessions(token_hash, expires_at);

                    CREATE TABLE IF NOT EXISTS wf_modules (
                        module_id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        description TEXT NOT NULL,
                        module_group TEXT NOT NULL CHECK (
                            module_group IN ('Overview', 'Workspaces', 'Tools', 'System')
                        ),
                        default_access INTEGER NOT NULL CHECK (default_access = 0),
                        status TEXT NOT NULL CHECK (status = 'active'),
                        authority_effect TEXT NOT NULL CHECK (authority_effect = 'none'),
                        created_at TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS wf_access_profiles (
                        user_id TEXT PRIMARY KEY,
                        access_version INTEGER NOT NULL CHECK (access_version >= 1),
                        updated_at TEXT NOT NULL,
                        updated_by_user_id TEXT,
                        FOREIGN KEY (user_id) REFERENCES wf_user_accounts(user_id),
                        FOREIGN KEY (updated_by_user_id) REFERENCES wf_user_accounts(user_id)
                    );

                    CREATE TABLE IF NOT EXISTS wf_user_module_access (
                        user_id TEXT NOT NULL,
                        module_id TEXT NOT NULL,
                        allowed INTEGER NOT NULL CHECK (allowed IN (0, 1)),
                        updated_at TEXT NOT NULL,
                        updated_by_user_id TEXT,
                        PRIMARY KEY (user_id, module_id),
                        FOREIGN KEY (user_id) REFERENCES wf_user_accounts(user_id),
                        FOREIGN KEY (module_id) REFERENCES wf_modules(module_id),
                        FOREIGN KEY (updated_by_user_id) REFERENCES wf_user_accounts(user_id)
                    );

                    CREATE TABLE IF NOT EXISTS wf_module_access_events (
                        access_event_id TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        actor_user_id TEXT,
                        before_module_ids_json TEXT NOT NULL,
                        after_module_ids_json TEXT NOT NULL,
                        access_version INTEGER NOT NULL CHECK (access_version >= 1),
                        reason TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        FOREIGN KEY (user_id) REFERENCES wf_user_accounts(user_id),
                        FOREIGN KEY (actor_user_id) REFERENCES wf_user_accounts(user_id)
                    );

                    CREATE TRIGGER IF NOT EXISTS wf_module_access_events_no_update
                    BEFORE UPDATE ON wf_module_access_events
                    BEGIN
                        SELECT RAISE(ABORT, 'Module access events are append-only.');
                    END;

                    CREATE TRIGGER IF NOT EXISTS wf_module_access_events_no_delete
                    BEFORE DELETE ON wf_module_access_events
                    BEGIN
                        SELECT RAISE(ABORT, 'Module access events are append-only.');
                    END;

                    CREATE TABLE IF NOT EXISTS wf_user_invitations (
                        invitation_id TEXT PRIMARY KEY,
                        username TEXT NOT NULL COLLATE NOCASE,
                        display_name TEXT NOT NULL,
                        token_hash TEXT NOT NULL UNIQUE CHECK (length(token_hash) = 64),
                        role_ids_json TEXT NOT NULL,
                        module_ids_json TEXT NOT NULL,
                        status TEXT NOT NULL CHECK (
                            status IN ('pending', 'activated', 'revoked', 'expired')
                        ),
                        created_by_user_id TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        expires_at TEXT NOT NULL,
                        activated_at TEXT,
                        activated_user_id TEXT,
                        FOREIGN KEY (created_by_user_id) REFERENCES wf_user_accounts(user_id),
                        FOREIGN KEY (activated_user_id) REFERENCES wf_user_accounts(user_id)
                    );

                    CREATE UNIQUE INDEX IF NOT EXISTS idx_wf_pending_invitation_username
                    ON wf_user_invitations(username COLLATE NOCASE)
                    WHERE status = 'pending';

                    CREATE TABLE IF NOT EXISTS wf_invitation_events (
                        invitation_event_id TEXT PRIMARY KEY,
                        invitation_id TEXT NOT NULL,
                        event_type TEXT NOT NULL CHECK (
                            event_type IN ('created', 'activated', 'revoked', 'expired')
                        ),
                        actor_user_id TEXT,
                        created_at TEXT NOT NULL,
                        details_json TEXT NOT NULL,
                        FOREIGN KEY (invitation_id) REFERENCES wf_user_invitations(invitation_id),
                        FOREIGN KEY (actor_user_id) REFERENCES wf_user_accounts(user_id)
                    );

                    CREATE TRIGGER IF NOT EXISTS wf_invitation_events_no_update
                    BEFORE UPDATE ON wf_invitation_events
                    BEGIN
                        SELECT RAISE(ABORT, 'Invitation events are append-only.');
                    END;

                    CREATE TRIGGER IF NOT EXISTS wf_invitation_events_no_delete
                    BEFORE DELETE ON wf_invitation_events
                    BEGIN
                        SELECT RAISE(ABORT, 'Invitation events are append-only.');
                    END;

                    CREATE TABLE IF NOT EXISTS wf_definitions (
                        definition_id TEXT NOT NULL,
                        version TEXT NOT NULL,
                        title TEXT NOT NULL,
                        description TEXT NOT NULL,
                        states_json TEXT NOT NULL,
                        transitions_json TEXT NOT NULL,
                        status TEXT NOT NULL CHECK (status = 'active'),
                        authority_effect TEXT NOT NULL CHECK (authority_effect = 'none'),
                        created_at TEXT NOT NULL,
                        PRIMARY KEY (definition_id, version)
                    );

                    CREATE TABLE IF NOT EXISTS wf_tasks (
                        task_id TEXT PRIMARY KEY,
                        definition_id TEXT NOT NULL,
                        definition_version TEXT NOT NULL,
                        title TEXT NOT NULL,
                        description TEXT NOT NULL,
                        capability TEXT NOT NULL CHECK (
                            capability IN (
                                'credit_risk', 'accounts_payable', 'lockbox',
                                'reporting', 'platform'
                            )
                        ),
                        context_type TEXT NOT NULL,
                        context_id TEXT NOT NULL,
                        context_label TEXT NOT NULL,
                        queue_role_id TEXT NOT NULL,
                        priority TEXT NOT NULL CHECK (
                            priority IN ('low', 'medium', 'high', 'critical')
                        ),
                        state TEXT NOT NULL CHECK (
                            state IN (
                                'open', 'in_progress', 'deferred',
                                'completed', 'cancelled', 'reopened'
                            )
                        ),
                        due_date TEXT,
                        created_by_user_id TEXT NOT NULL,
                        idempotency_key TEXT NOT NULL,
                        request_sha256 TEXT NOT NULL CHECK (length(request_sha256) = 64),
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        version INTEGER NOT NULL CHECK (version >= 1),
                        assignment_effect TEXT NOT NULL CHECK (
                            assignment_effect = 'work_ownership_only'
                        ),
                        authority_effect TEXT NOT NULL CHECK (authority_effect = 'none'),
                        execution_effect TEXT NOT NULL CHECK (execution_effect = 'none'),
                        UNIQUE (created_by_user_id, idempotency_key),
                        FOREIGN KEY (definition_id, definition_version)
                            REFERENCES wf_definitions(definition_id, version),
                        FOREIGN KEY (queue_role_id) REFERENCES wf_roles(role_id),
                        FOREIGN KEY (created_by_user_id) REFERENCES wf_user_accounts(user_id)
                    );

                    CREATE INDEX IF NOT EXISTS idx_wf_tasks_queue
                    ON wf_tasks(queue_role_id, state, due_date, updated_at DESC);

                    CREATE INDEX IF NOT EXISTS idx_wf_tasks_context
                    ON wf_tasks(capability, context_type, context_id);

                    CREATE TABLE IF NOT EXISTS wf_task_assignments (
                        assignment_event_id TEXT PRIMARY KEY,
                        task_id TEXT NOT NULL,
                        assignee_user_id TEXT NOT NULL,
                        prior_assignee_user_id TEXT,
                        assigned_by_user_id TEXT NOT NULL,
                        assignment_type TEXT NOT NULL CHECK (
                            assignment_type IN ('initial', 'claim', 'reassign')
                        ),
                        note TEXT NOT NULL,
                        idempotency_key TEXT NOT NULL UNIQUE,
                        task_version INTEGER NOT NULL,
                        created_at TEXT NOT NULL,
                        authority_effect TEXT NOT NULL CHECK (authority_effect = 'none'),
                        FOREIGN KEY (task_id) REFERENCES wf_tasks(task_id),
                        FOREIGN KEY (assignee_user_id) REFERENCES wf_user_accounts(user_id),
                        FOREIGN KEY (assigned_by_user_id) REFERENCES wf_user_accounts(user_id)
                    );

                    CREATE INDEX IF NOT EXISTS idx_wf_assignments_task
                    ON wf_task_assignments(task_id, created_at DESC, assignment_event_id DESC);

                    CREATE TRIGGER IF NOT EXISTS wf_task_assignments_no_update
                    BEFORE UPDATE ON wf_task_assignments
                    BEGIN
                        SELECT RAISE(ABORT, 'Workflow assignments are append-only.');
                    END;

                    CREATE TRIGGER IF NOT EXISTS wf_task_assignments_no_delete
                    BEFORE DELETE ON wf_task_assignments
                    BEGIN
                        SELECT RAISE(ABORT, 'Workflow assignments are append-only.');
                    END;

                    CREATE TABLE IF NOT EXISTS wf_task_events (
                        event_id TEXT PRIMARY KEY,
                        task_id TEXT NOT NULL,
                        event_type TEXT NOT NULL CHECK (
                            event_type IN ('task_created', 'task_state_changed')
                        ),
                        from_state TEXT,
                        to_state TEXT NOT NULL,
                        actor_user_id TEXT NOT NULL,
                        note TEXT NOT NULL,
                        idempotency_key TEXT NOT NULL UNIQUE,
                        task_version INTEGER NOT NULL,
                        created_at TEXT NOT NULL,
                        FOREIGN KEY (task_id) REFERENCES wf_tasks(task_id),
                        FOREIGN KEY (actor_user_id) REFERENCES wf_user_accounts(user_id)
                    );

                    CREATE INDEX IF NOT EXISTS idx_wf_task_events_task
                    ON wf_task_events(task_id, created_at, event_id);

                    CREATE TRIGGER IF NOT EXISTS wf_task_events_no_update
                    BEFORE UPDATE ON wf_task_events
                    BEGIN
                        SELECT RAISE(ABORT, 'Workflow task events are append-only.');
                    END;

                    CREATE TRIGGER IF NOT EXISTS wf_task_events_no_delete
                    BEFORE DELETE ON wf_task_events
                    BEGIN
                        SELECT RAISE(ABORT, 'Workflow task events are append-only.');
                    END;

                    CREATE TABLE IF NOT EXISTS wf_notifications (
                        notification_id TEXT PRIMARY KEY,
                        recipient_user_id TEXT NOT NULL,
                        task_id TEXT,
                        notification_type TEXT NOT NULL,
                        title TEXT NOT NULL,
                        message TEXT NOT NULL,
                        severity TEXT NOT NULL CHECK (
                            severity IN ('info', 'success', 'warning', 'critical')
                        ),
                        created_at TEXT NOT NULL,
                        read_at TEXT,
                        FOREIGN KEY (recipient_user_id) REFERENCES wf_user_accounts(user_id),
                        FOREIGN KEY (task_id) REFERENCES wf_tasks(task_id)
                    );

                    CREATE INDEX IF NOT EXISTS idx_wf_notifications_recipient
                    ON wf_notifications(recipient_user_id, read_at, created_at DESC);

                    CREATE TABLE IF NOT EXISTS wf_audit_events (
                        audit_id TEXT PRIMARY KEY,
                        event_type TEXT NOT NULL,
                        actor_user_id TEXT,
                        subject_type TEXT NOT NULL,
                        subject_id TEXT NOT NULL,
                        correlation_id TEXT NOT NULL,
                        occurred_at TEXT NOT NULL,
                        details_json TEXT NOT NULL,
                        previous_hash TEXT NOT NULL,
                        record_hash TEXT NOT NULL UNIQUE,
                        schema_version TEXT NOT NULL CHECK (schema_version = '1.0')
                    );

                    CREATE INDEX IF NOT EXISTS idx_wf_audit_subject
                    ON wf_audit_events(subject_type, subject_id, occurred_at, audit_id);

                    CREATE TRIGGER IF NOT EXISTS wf_audit_events_no_update
                    BEFORE UPDATE ON wf_audit_events
                    BEGIN
                        SELECT RAISE(ABORT, 'Workflow audit records are append-only.');
                    END;

                    CREATE TRIGGER IF NOT EXISTS wf_audit_events_no_delete
                    BEFORE DELETE ON wf_audit_events
                    BEGIN
                        SELECT RAISE(ABORT, 'Workflow audit records are append-only.');
                    END;
                    """
                )
                now = self._now()
                account_columns = {
                    row["name"]
                    for row in connection.execute(
                        "PRAGMA table_info(wf_user_accounts)"
                    ).fetchall()
                }
                if "status_version" not in account_columns:
                    connection.execute(
                        "ALTER TABLE wf_user_accounts "
                        "ADD COLUMN status_version INTEGER NOT NULL DEFAULT 1"
                    )
                connection.executemany(
                    """
                    INSERT OR IGNORE INTO wf_roles(
                        role_id, name, description, queue_scope,
                        authority_effect, decision_authority, created_at
                    ) VALUES (?, ?, ?, ?, 'none', 0, ?)
                    """,
                    [(*role, now) for role in self.ROLE_SEEDS],
                )
                connection.executemany(
                    """
                    INSERT OR IGNORE INTO wf_modules(
                        module_id, name, description, module_group,
                        default_access, status, authority_effect, created_at
                    ) VALUES (?, ?, ?, ?, 0, 'active', 'none', ?)
                    """,
                    [(*module, now) for module in self.MODULE_SEEDS],
                )
                connection.execute(
                    """
                    INSERT OR IGNORE INTO wf_definitions(
                        definition_id, version, title, description,
                        states_json, transitions_json, status,
                        authority_effect, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, 'active', 'none', ?)
                    """,
                    (
                        self.DEFINITION_ID,
                        self.DEFINITION_VERSION,
                        "Governed work follow-up",
                        "Coordinates accountable follow-up work without making a business decision or executing a source-system action.",
                        self._canonical_json(self.STATES),
                        self._canonical_json(self.TRANSITIONS),
                        now,
                    ),
                )
                legacy_users = connection.execute(
                    """
                    SELECT u.user_id
                    FROM wf_user_accounts u
                    LEFT JOIN wf_access_profiles p ON p.user_id = u.user_id
                    WHERE p.user_id IS NULL
                    ORDER BY u.created_at, u.user_id
                    """
                ).fetchall()
                for legacy_user in legacy_users:
                    user_id = legacy_user["user_id"]
                    role_ids = {
                        row["role_id"]
                        for row in connection.execute(
                            """
                            SELECT role_id FROM wf_role_assignments
                            WHERE user_id = ? AND assignment_status = 'active'
                              AND effective_to IS NULL
                            """,
                            (user_id,),
                        ).fetchall()
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
                        """
                        INSERT INTO wf_access_profiles(
                            user_id, access_version, updated_at, updated_by_user_id
                        ) VALUES (?, 1, ?, NULL)
                        """,
                        (user_id, now),
                    )
                    connection.executemany(
                        """
                        INSERT INTO wf_user_module_access(
                            user_id, module_id, allowed, updated_at,
                            updated_by_user_id
                        ) VALUES (?, ?, 1, ?, NULL)
                        """,
                        [(user_id, module_id, now) for module_id in granted_modules],
                    )
                    connection.execute(
                        """
                        INSERT INTO wf_module_access_events(
                            access_event_id, user_id, actor_user_id,
                            before_module_ids_json, after_module_ids_json,
                            access_version, reason, created_at
                        ) VALUES (?, ?, NULL, '[]', ?, 1, ?, ?)
                        """,
                        (
                            self._id("ACE"),
                            user_id,
                            self._canonical_json(granted_modules),
                            "compatibility_migration_from_pre_access_control",
                            now,
                        ),
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
                connection.commit()
            finally:
                connection.close()

    @staticmethod
    def _canonical_json(value: Any) -> str:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    def _append_audit(
        self,
        connection: sqlite3.Connection,
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
            "SELECT record_hash FROM wf_audit_events ORDER BY rowid DESC LIMIT 1"
        ).fetchone()
        previous_hash = prior["record_hash"] if prior else "0" * 64
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
            """
            INSERT INTO wf_audit_events(
                audit_id, event_type, actor_user_id, subject_type,
                subject_id, correlation_id, occurred_at, details_json,
                previous_hash, record_hash, schema_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '1.0')
            """,
            (
                audit_id,
                event_type,
                actor_user_id,
                subject_type,
                subject_id,
                correlation_id,
                timestamp,
                self._canonical_json(details),
                previous_hash,
                record_hash,
            ),
        )
        return audit_id

    def bootstrap_status(self) -> dict[str, Any]:
        connection = self._connection()
        try:
            count = int(
                connection.execute(
                    "SELECT COUNT(*) AS count FROM wf_user_accounts"
                ).fetchone()["count"]
            )
            return {"bootstrap_required": count == 0, "account_count": count}
        finally:
            connection.close()

    def bootstrap_user(
        self,
        *,
        username: str,
        display_name: str,
        password_salt: str,
        password_hash: str,
    ) -> str:
        connection = self._connection()
        now = self._now()
        person_id = self._id("PER")
        user_id = self._id("USR")
        role_assignment_id = self._id("RLA")
        correlation_id = self._id("COR")
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT COUNT(*) AS count FROM wf_user_accounts"
            ).fetchone()["count"]
            if existing:
                raise WorkflowFoundationConflict(
                    "The local identity foundation has already been bootstrapped."
                )
            connection.execute(
                """
                INSERT INTO wf_persons(
                    person_id, display_name, status, created_at, created_by_user_id
                ) VALUES (?, ?, 'active', ?, NULL)
                """,
                (person_id, display_name, now),
            )
            connection.execute(
                """
                INSERT INTO wf_user_accounts(
                    user_id, person_id, username, password_salt, password_hash,
                    password_algorithm, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 'scrypt-n16384-r8-p1-v1', 'active', ?, ?)
                """,
                (user_id, person_id, username, password_salt, password_hash, now, now),
            )
            connection.execute(
                """
                INSERT INTO wf_role_assignments(
                    role_assignment_id, user_id, role_id, effective_from,
                    effective_to, assignment_status, assigned_by_user_id, created_at
                ) VALUES (?, ?, 'workflow_coordinator', ?, NULL, 'active', ?, ?)
                """,
                (role_assignment_id, user_id, now, user_id, now),
            )
            module_ids = [item[0] for item in self.MODULE_SEEDS]
            connection.execute(
                """
                INSERT INTO wf_access_profiles(
                    user_id, access_version, updated_at, updated_by_user_id
                ) VALUES (?, 1, ?, ?)
                """,
                (user_id, now, user_id),
            )
            connection.executemany(
                """
                INSERT INTO wf_user_module_access(
                    user_id, module_id, allowed, updated_at, updated_by_user_id
                ) VALUES (?, ?, 1, ?, ?)
                """,
                [(user_id, module_id, now, user_id) for module_id in module_ids],
            )
            connection.execute(
                """
                INSERT INTO wf_module_access_events(
                    access_event_id, user_id, actor_user_id,
                    before_module_ids_json, after_module_ids_json,
                    access_version, reason, created_at
                ) VALUES (?, ?, ?, '[]', ?, 1, ?, ?)
                """,
                (
                    self._id("ACE"),
                    user_id,
                    user_id,
                    self._canonical_json(module_ids),
                    "initial_bootstrap_access",
                    now,
                ),
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
            connection.commit()
            return user_id
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def get_account_credentials(self, username: str) -> dict[str, Any] | None:
        connection = self._connection()
        try:
            row = connection.execute(
                """
                SELECT user_id, password_salt, password_hash,
                       password_algorithm, status
                FROM wf_user_accounts
                WHERE username = ? COLLATE NOCASE
                """,
                (username,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            connection.close()

    def create_session(
        self,
        *,
        user_id: str,
        token_hash: str,
        expires_at: str,
    ) -> str:
        connection = self._connection()
        session_id = self._id("SES")
        now = self._now()
        correlation_id = self._id("COR")
        try:
            with connection:
                connection.execute(
                    """
                    INSERT INTO wf_sessions(
                        session_id, user_id, token_hash, issued_at,
                        expires_at, revoked_at, last_seen_at
                    ) VALUES (?, ?, ?, ?, ?, NULL, ?)
                    """,
                    (session_id, user_id, token_hash, now, expires_at, now),
                )
                self._append_audit(
                    connection,
                    event_type="identity.session_started",
                    actor_user_id=user_id,
                    subject_type="session",
                    subject_id=session_id,
                    correlation_id=correlation_id,
                    details={"expires_at": expires_at, "authentication_assurance": "local_credential"},
                    occurred_at=now,
                )
            return session_id
        finally:
            connection.close()

    def get_session(self, token_hash: str) -> dict[str, Any] | None:
        connection = self._connection()
        now = self._now()
        try:
            row = connection.execute(
                """
                SELECT s.session_id, s.user_id, s.expires_at
                FROM wf_sessions s
                JOIN wf_user_accounts u ON u.user_id = s.user_id
                WHERE s.token_hash = ?
                  AND s.revoked_at IS NULL
                  AND s.expires_at > ?
                  AND u.status = 'active'
                """,
                (token_hash, now),
            ).fetchone()
            if row is None:
                return None
            connection.execute(
                "UPDATE wf_sessions SET last_seen_at = ? WHERE session_id = ?",
                (now, row["session_id"]),
            )
            connection.commit()
            return {
                "session_id": row["session_id"],
                "expires_at": row["expires_at"],
                "user": self._user_summary(connection, row["user_id"]),
            }
        finally:
            connection.close()

    def revoke_session(self, token_hash: str, actor_user_id: str) -> None:
        connection = self._connection()
        now = self._now()
        try:
            with connection:
                row = connection.execute(
                    "SELECT session_id FROM wf_sessions WHERE token_hash = ? AND revoked_at IS NULL",
                    (token_hash,),
                ).fetchone()
                if row is None:
                    return
                connection.execute(
                    "UPDATE wf_sessions SET revoked_at = ? WHERE session_id = ?",
                    (now, row["session_id"]),
                )
                self._append_audit(
                    connection,
                    event_type="identity.session_ended",
                    actor_user_id=actor_user_id,
                    subject_type="session",
                    subject_id=row["session_id"],
                    correlation_id=self._id("COR"),
                    details={"reason": "operator_sign_out"},
                    occurred_at=now,
                )
        finally:
            connection.close()

    def _role_summary(self, row: sqlite3.Row) -> dict[str, Any]:
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
        connection: sqlite3.Connection,
        user_id: str,
    ) -> dict[str, Any]:
        row = connection.execute(
            """
            SELECT u.user_id, u.username, u.status, u.created_at,
                   p.person_id, p.display_name
            FROM wf_user_accounts u
            JOIN wf_persons p ON p.person_id = u.person_id
            WHERE u.user_id = ?
            """,
            (user_id,),
        ).fetchone()
        if row is None:
            raise WorkflowFoundationNotFound(f"Workflow user {user_id} was not found.")
        now = self._now()
        roles = connection.execute(
            """
            SELECT r.*
            FROM wf_role_assignments a
            JOIN wf_roles r ON r.role_id = a.role_id
            WHERE a.user_id = ?
              AND a.assignment_status = 'active'
              AND a.effective_from <= ?
              AND (a.effective_to IS NULL OR a.effective_to > ?)
            ORDER BY r.name, r.role_id
            """,
            (user_id, now, now),
        ).fetchall()
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

    def list_users(self) -> list[dict[str, Any]]:
        connection = self._connection()
        try:
            rows = connection.execute(
                "SELECT user_id FROM wf_user_accounts ORDER BY username COLLATE NOCASE"
            ).fetchall()
            return [self._user_summary(connection, row["user_id"]) for row in rows]
        finally:
            connection.close()

    def get_user(self, user_id: str) -> dict[str, Any]:
        connection = self._connection()
        try:
            return self._user_summary(connection, user_id)
        finally:
            connection.close()

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
        connection = self._connection()
        now = self._now()
        user_id = self._id("USR")
        person_id = self._id("PER")
        correlation_id = self._id("COR")
        try:
            with connection:
                connection.execute(
                    """
                    INSERT INTO wf_persons(
                        person_id, display_name, status, created_at, created_by_user_id
                    ) VALUES (?, ?, 'active', ?, ?)
                    """,
                    (person_id, display_name, now, actor_user_id),
                )
                connection.execute(
                    """
                    INSERT INTO wf_user_accounts(
                        user_id, person_id, username, password_salt, password_hash,
                        password_algorithm, status, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, 'scrypt-n16384-r8-p1-v1', 'active', ?, ?)
                    """,
                    (user_id, person_id, username, password_salt, password_hash, now, now),
                )
                for role_id in sorted(set(role_ids)):
                    connection.execute(
                        """
                        INSERT INTO wf_role_assignments(
                            role_assignment_id, user_id, role_id,
                            effective_from, effective_to, assignment_status,
                            assigned_by_user_id, created_at
                        ) VALUES (?, ?, ?, ?, NULL, 'active', ?, ?)
                        """,
                        (self._id("RLA"), user_id, role_id, now, actor_user_id, now),
                    )
                configured_modules = sorted(set(module_ids))
                connection.execute(
                    """
                    INSERT INTO wf_access_profiles(
                        user_id, access_version, updated_at, updated_by_user_id
                    ) VALUES (?, 1, ?, ?)
                    """,
                    (user_id, now, actor_user_id),
                )
                connection.executemany(
                    """
                    INSERT INTO wf_user_module_access(
                        user_id, module_id, allowed, updated_at,
                        updated_by_user_id
                    ) VALUES (?, ?, 1, ?, ?)
                    """,
                    [
                        (user_id, module_id, now, actor_user_id)
                        for module_id in configured_modules
                    ],
                )
                connection.execute(
                    """
                    INSERT INTO wf_module_access_events(
                        access_event_id, user_id, actor_user_id,
                        before_module_ids_json, after_module_ids_json,
                        access_version, reason, created_at
                    ) VALUES (?, ?, ?, '[]', ?, 1, ?, ?)
                    """,
                    (
                        self._id("ACE"),
                        user_id,
                        actor_user_id,
                        self._canonical_json(configured_modules),
                        "direct_local_account_creation",
                        now,
                    ),
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
        except sqlite3.IntegrityError as exc:
            raise WorkflowFoundationConflict(
                "That username already exists or a requested workflow role is invalid."
            ) from exc
        finally:
            connection.close()

    def _module_summary(self, row: sqlite3.Row) -> dict[str, Any]:
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
        connection = self._connection()
        try:
            rows = connection.execute(
                """
                SELECT * FROM wf_modules
                WHERE status = 'active'
                ORDER BY CASE module_group
                    WHEN 'Overview' THEN 1
                    WHEN 'Workspaces' THEN 2
                    WHEN 'Tools' THEN 3
                    ELSE 4 END,
                    name, module_id
                """
            ).fetchall()
            return [self._module_summary(row) for row in rows]
        finally:
            connection.close()

    def _configured_module_ids(
        self,
        connection: sqlite3.Connection,
        user_id: str,
    ) -> list[str]:
        return [
            row["module_id"]
            for row in connection.execute(
                """
                SELECT a.module_id
                FROM wf_user_module_access a
                JOIN wf_modules m ON m.module_id = a.module_id
                WHERE a.user_id = ? AND a.allowed = 1 AND m.status = 'active'
                ORDER BY a.module_id
                """,
                (user_id,),
            ).fetchall()
        ]

    def _permission_summary(
        self,
        connection: sqlite3.Connection,
        user_id: str,
    ) -> dict[str, Any]:
        row = connection.execute(
            """
            SELECT u.status, p.access_version
            FROM wf_user_accounts u
            JOIN wf_access_profiles p ON p.user_id = u.user_id
            WHERE u.user_id = ?
            """,
            (user_id,),
        ).fetchone()
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
        connection = self._connection()
        try:
            return self._permission_summary(connection, user_id)
        finally:
            connection.close()

    def _security_user_summary(
        self,
        connection: sqlite3.Connection,
        user_id: str,
    ) -> dict[str, Any]:
        status_row = connection.execute(
            """
            SELECT status_version FROM wf_user_accounts WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()
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
        }

    def list_security_users(self) -> list[dict[str, Any]]:
        connection = self._connection()
        try:
            rows = connection.execute(
                "SELECT user_id FROM wf_user_accounts ORDER BY username COLLATE NOCASE"
            ).fetchall()
            return [
                self._security_user_summary(connection, row["user_id"])
                for row in rows
            ]
        finally:
            connection.close()

    def get_security_user(self, user_id: str) -> dict[str, Any]:
        connection = self._connection()
        try:
            return self._security_user_summary(connection, user_id)
        finally:
            connection.close()

    def replace_module_access(
        self,
        *,
        user_id: str,
        module_ids: list[str],
        expected_version: int,
        actor_user_id: str,
    ) -> dict[str, Any]:
        connection = self._connection()
        now = self._now()
        correlation_id = self._id("COR")
        try:
            connection.execute("BEGIN IMMEDIATE")
            profile = connection.execute(
                "SELECT access_version FROM wf_access_profiles WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            if profile is None:
                raise WorkflowFoundationNotFound(
                    f"Workflow user {user_id} or its access profile was not found."
                )
            if profile["access_version"] != expected_version:
                raise WorkflowFoundationConflict(
                    "The module-access profile changed. Refresh before saving access."
                )
            valid_modules = {
                row["module_id"]
                for row in connection.execute(
                    "SELECT module_id FROM wf_modules WHERE status = 'active'"
                ).fetchall()
            }
            requested = sorted(set(module_ids))
            unknown = sorted(set(requested) - valid_modules)
            if unknown:
                raise WorkflowFoundationConflict(
                    f"Unknown or inactive ETOP module access was requested: {', '.join(unknown)}."
                )
            before = self._configured_module_ids(connection, user_id)
            if before == requested:
                connection.commit()
                return self.get_security_user(user_id)
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
            for module_id in sorted(valid_modules):
                connection.execute(
                    """
                    INSERT INTO wf_user_module_access(
                        user_id, module_id, allowed, updated_at,
                        updated_by_user_id
                    ) VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(user_id, module_id) DO UPDATE SET
                        allowed = excluded.allowed,
                        updated_at = excluded.updated_at,
                        updated_by_user_id = excluded.updated_by_user_id
                    """,
                    (
                        user_id,
                        module_id,
                        1 if module_id in requested else 0,
                        now,
                        actor_user_id,
                    ),
                )
            connection.execute(
                """
                UPDATE wf_access_profiles
                SET access_version = ?, updated_at = ?, updated_by_user_id = ?
                WHERE user_id = ?
                """,
                (next_version, now, actor_user_id, user_id),
            )
            connection.execute(
                """
                INSERT INTO wf_module_access_events(
                    access_event_id, user_id, actor_user_id,
                    before_module_ids_json, after_module_ids_json,
                    access_version, reason, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self._id("ACE"),
                    user_id,
                    actor_user_id,
                    self._canonical_json(before),
                    self._canonical_json(requested),
                    next_version,
                    "coordinator_module_access_replacement",
                    now,
                ),
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
            connection.commit()
            return self.get_security_user(user_id)
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _is_workflow_coordinator(
        self,
        connection: sqlite3.Connection,
        user_id: str,
    ) -> bool:
        now = self._now()
        return connection.execute(
            """
            SELECT 1
            FROM wf_role_assignments
            WHERE user_id = ?
              AND role_id = 'workflow_coordinator'
              AND assignment_status = 'active'
              AND effective_from <= ?
              AND (effective_to IS NULL OR effective_to > ?)
            LIMIT 1
            """,
            (user_id, now, now),
        ).fetchone() is not None

    def _active_security_coordinator_count(
        self,
        connection: sqlite3.Connection,
        *,
        excluding_user_id: str | None = None,
    ) -> int:
        now = self._now()
        values: list[Any] = [now, now]
        exclusion = ""
        if excluding_user_id:
            exclusion = "AND u.user_id <> ?"
            values.append(excluding_user_id)
        row = connection.execute(
            f"""
            SELECT COUNT(DISTINCT u.user_id) AS count
            FROM wf_user_accounts u
            JOIN wf_role_assignments r ON r.user_id = u.user_id
            JOIN wf_user_module_access m ON m.user_id = u.user_id
            WHERE u.status = 'active'
              AND r.role_id = 'workflow_coordinator'
              AND r.assignment_status = 'active'
              AND r.effective_from <= ?
              AND (r.effective_to IS NULL OR r.effective_to > ?)
              AND m.module_id = 'security_administration'
              AND m.allowed = 1
              {exclusion}
            """,
            values,
        ).fetchone()
        return int(row["count"])

    def active_security_coordinator_count(
        self,
        *,
        excluding_user_id: str | None = None,
    ) -> int:
        connection = self._connection()
        try:
            return self._active_security_coordinator_count(
                connection,
                excluding_user_id=excluding_user_id,
            )
        finally:
            connection.close()

    def change_user_status(
        self,
        *,
        user_id: str,
        status: str,
        expected_version: int,
        actor_user_id: str,
    ) -> dict[str, Any]:
        connection = self._connection()
        now = self._now()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT u.status, u.status_version, u.person_id
                FROM wf_user_accounts u WHERE u.user_id = ?
                """,
                (user_id,),
            ).fetchone()
            if row is None:
                raise WorkflowFoundationNotFound(f"Workflow user {user_id} was not found.")
            if row["status_version"] != expected_version:
                raise WorkflowFoundationConflict(
                    "The account lifecycle changed. Refresh before changing its status."
                )
            if row["status"] == status:
                connection.commit()
                return self.get_security_user(user_id)
            if (
                status == "inactive"
                and row["status"] == "active"
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
                """
                UPDATE wf_user_accounts
                SET status = ?, status_version = ?, updated_at = ?
                WHERE user_id = ?
                """,
                (status, next_version, now, user_id),
            )
            connection.execute(
                "UPDATE wf_persons SET status = ? WHERE person_id = ?",
                (status, row["person_id"]),
            )
            if status == "inactive":
                connection.execute(
                    """
                    UPDATE wf_sessions SET revoked_at = ?
                    WHERE user_id = ? AND revoked_at IS NULL
                    """,
                    (now, user_id),
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
                    "before_status": row["status"],
                    "after_status": status,
                    "status_version": next_version,
                    "sessions_revoked": status == "inactive",
                    "authority_effect": "none",
                },
                occurred_at=now,
            )
            connection.commit()
            return self.get_security_user(user_id)
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _invitation_summary(self, row: sqlite3.Row) -> dict[str, Any]:
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
        connection: sqlite3.Connection,
        now: str,
    ) -> None:
        rows = connection.execute(
            """
            SELECT * FROM wf_user_invitations
            WHERE status = 'pending' AND expires_at <= ?
            ORDER BY created_at, invitation_id
            """,
            (now,),
        ).fetchall()
        for row in rows:
            connection.execute(
                """
                UPDATE wf_user_invitations SET status = 'expired'
                WHERE invitation_id = ? AND status = 'pending'
                """,
                (row["invitation_id"],),
            )
            connection.execute(
                """
                INSERT INTO wf_invitation_events(
                    invitation_event_id, invitation_id, event_type,
                    actor_user_id, created_at, details_json
                ) VALUES (?, ?, 'expired', NULL, ?, ?)
                """,
                (
                    self._id("IVE"),
                    row["invitation_id"],
                    now,
                    self._canonical_json({"reason": "configured_expiration"}),
                ),
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
        connection = self._connection()
        now = self._now()
        invitation_id = self._id("INV")
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._expire_pending_invitations(connection, now)
            if connection.execute(
                "SELECT 1 FROM wf_user_accounts WHERE username = ? COLLATE NOCASE",
                (username,),
            ).fetchone():
                raise WorkflowFoundationConflict("That local username already exists.")
            valid_roles = {
                row["role_id"]
                for row in connection.execute("SELECT role_id FROM wf_roles").fetchall()
            }
            valid_modules = {
                row["module_id"]
                for row in connection.execute(
                    "SELECT module_id FROM wf_modules WHERE status = 'active'"
                ).fetchall()
            }
            requested_roles = sorted(set(role_ids))
            requested_modules = sorted(set(module_ids))
            if set(requested_roles) - valid_roles:
                raise WorkflowFoundationConflict("An unknown workflow role was requested.")
            if set(requested_modules) - valid_modules:
                raise WorkflowFoundationConflict("An unknown ETOP module was requested.")
            connection.execute(
                """
                INSERT INTO wf_user_invitations(
                    invitation_id, username, display_name, token_hash,
                    role_ids_json, module_ids_json, status,
                    created_by_user_id, created_at, expires_at,
                    activated_at, activated_user_id
                ) VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, NULL, NULL)
                """,
                (
                    invitation_id,
                    username,
                    display_name,
                    token_hash,
                    self._canonical_json(requested_roles),
                    self._canonical_json(requested_modules),
                    actor_user_id,
                    now,
                    expires_at,
                ),
            )
            connection.execute(
                """
                INSERT INTO wf_invitation_events(
                    invitation_event_id, invitation_id, event_type,
                    actor_user_id, created_at, details_json
                ) VALUES (?, ?, 'created', ?, ?, ?)
                """,
                (
                    self._id("IVE"),
                    invitation_id,
                    actor_user_id,
                    now,
                    self._canonical_json(
                        {
                            "username": username,
                            "role_ids": requested_roles,
                            "module_ids": requested_modules,
                            "expires_at": expires_at,
                            "token_stored_as": "sha256",
                        }
                    ),
                ),
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
            connection.commit()
            row = connection.execute(
                "SELECT * FROM wf_user_invitations WHERE invitation_id = ?",
                (invitation_id,),
            ).fetchone()
            return self._invitation_summary(row)
        except sqlite3.IntegrityError as exc:
            connection.rollback()
            raise WorkflowFoundationConflict(
                "A pending invitation for that username already exists."
            ) from exc
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def list_invitations(self) -> list[dict[str, Any]]:
        connection = self._connection()
        now = self._now()
        try:
            with connection:
                self._expire_pending_invitations(connection, now)
            rows = connection.execute(
                """
                SELECT * FROM wf_user_invitations
                ORDER BY created_at DESC, invitation_id DESC
                """
            ).fetchall()
            return [self._invitation_summary(row) for row in rows]
        finally:
            connection.close()

    def revoke_invitation(
        self,
        *,
        invitation_id: str,
        actor_user_id: str,
    ) -> dict[str, Any]:
        connection = self._connection()
        now = self._now()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._expire_pending_invitations(connection, now)
            row = connection.execute(
                "SELECT * FROM wf_user_invitations WHERE invitation_id = ?",
                (invitation_id,),
            ).fetchone()
            if row is None:
                raise WorkflowFoundationNotFound(
                    f"Invitation {invitation_id} was not found."
                )
            if row["status"] != "pending":
                raise WorkflowFoundationConflict(
                    "Only a pending invitation can be revoked. Refresh its current status."
                )
            changed = connection.execute(
                """
                UPDATE wf_user_invitations SET status = 'revoked'
                WHERE invitation_id = ? AND status = 'pending'
                """,
                (invitation_id,),
            ).rowcount
            if changed != 1:
                raise WorkflowFoundationConflict(
                    "The invitation changed before it could be revoked."
                )
            connection.execute(
                """
                INSERT INTO wf_invitation_events(
                    invitation_event_id, invitation_id, event_type,
                    actor_user_id, created_at, details_json
                ) VALUES (?, ?, 'revoked', ?, ?, ?)
                """,
                (
                    self._id("IVE"),
                    invitation_id,
                    actor_user_id,
                    now,
                    self._canonical_json(
                        {"reason": "coordinator_revocation", "token_reusable": False}
                    ),
                ),
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
            connection.commit()
            updated = connection.execute(
                "SELECT * FROM wf_user_invitations WHERE invitation_id = ?",
                (invitation_id,),
            ).fetchone()
            return self._invitation_summary(updated)
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def invitation_for_token_hash(self, token_hash: str) -> dict[str, Any] | None:
        connection = self._connection()
        now = self._now()
        try:
            with connection:
                self._expire_pending_invitations(connection, now)
            row = connection.execute(
                "SELECT * FROM wf_user_invitations WHERE token_hash = ?",
                (token_hash,),
            ).fetchone()
            return self._invitation_summary(row) if row else None
        finally:
            connection.close()

    def activate_invitation(
        self,
        *,
        token_hash: str,
        password_salt: str,
        password_hash: str,
    ) -> str:
        connection = self._connection()
        now = self._now()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._expire_pending_invitations(connection, now)
            invitation = connection.execute(
                "SELECT * FROM wf_user_invitations WHERE token_hash = ?",
                (token_hash,),
            ).fetchone()
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
                """
                INSERT INTO wf_persons(
                    person_id, display_name, status, created_at, created_by_user_id
                ) VALUES (?, ?, 'active', ?, ?)
                """,
                (
                    person_id,
                    invitation["display_name"],
                    now,
                    invitation["created_by_user_id"],
                ),
            )
            connection.execute(
                """
                INSERT INTO wf_user_accounts(
                    user_id, person_id, username, password_salt, password_hash,
                    password_algorithm, status, status_version, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 'scrypt-n16384-r8-p1-v1', 'active', 1, ?, ?)
                """,
                (
                    user_id,
                    person_id,
                    invitation["username"],
                    password_salt,
                    password_hash,
                    now,
                    now,
                ),
            )
            for role_id in role_ids:
                connection.execute(
                    """
                    INSERT INTO wf_role_assignments(
                        role_assignment_id, user_id, role_id, effective_from,
                        effective_to, assignment_status, assigned_by_user_id, created_at
                    ) VALUES (?, ?, ?, ?, NULL, 'active', ?, ?)
                    """,
                    (
                        self._id("RLA"),
                        user_id,
                        role_id,
                        now,
                        invitation["created_by_user_id"],
                        now,
                    ),
                )
            connection.execute(
                """
                INSERT INTO wf_access_profiles(
                    user_id, access_version, updated_at, updated_by_user_id
                ) VALUES (?, 1, ?, ?)
                """,
                (user_id, now, invitation["created_by_user_id"]),
            )
            connection.executemany(
                """
                INSERT INTO wf_user_module_access(
                    user_id, module_id, allowed, updated_at, updated_by_user_id
                ) VALUES (?, ?, 1, ?, ?)
                """,
                [
                    (
                        user_id,
                        module_id,
                        now,
                        invitation["created_by_user_id"],
                    )
                    for module_id in module_ids
                ],
            )
            connection.execute(
                """
                INSERT INTO wf_module_access_events(
                    access_event_id, user_id, actor_user_id,
                    before_module_ids_json, after_module_ids_json,
                    access_version, reason, created_at
                ) VALUES (?, ?, ?, '[]', ?, 1, ?, ?)
                """,
                (
                    self._id("ACE"),
                    user_id,
                    invitation["created_by_user_id"],
                    self._canonical_json(module_ids),
                    "invitation_activation",
                    now,
                ),
            )
            changed = connection.execute(
                """
                UPDATE wf_user_invitations
                SET status = 'activated', activated_at = ?, activated_user_id = ?
                WHERE invitation_id = ? AND status = 'pending'
                """,
                (now, user_id, invitation["invitation_id"]),
            ).rowcount
            if changed != 1:
                raise WorkflowFoundationConflict(
                    "This invitation was activated by another request."
                )
            connection.execute(
                """
                INSERT INTO wf_invitation_events(
                    invitation_event_id, invitation_id, event_type,
                    actor_user_id, created_at, details_json
                ) VALUES (?, ?, 'activated', ?, ?, ?)
                """,
                (
                    self._id("IVE"),
                    invitation["invitation_id"],
                    user_id,
                    now,
                    self._canonical_json(
                        {
                            "user_id": user_id,
                            "person_id": person_id,
                            "token_reusable": False,
                        }
                    ),
                ),
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
            connection.commit()
            return user_id
        except sqlite3.IntegrityError as exc:
            connection.rollback()
            raise WorkflowFoundationConflict(
                "The invited username was activated elsewhere or now conflicts with an account."
            ) from exc
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def list_roles(self) -> list[dict[str, Any]]:
        connection = self._connection()
        try:
            rows = connection.execute(
                "SELECT * FROM wf_roles ORDER BY name, role_id"
            ).fetchall()
            return [self._role_summary(row) for row in rows]
        finally:
            connection.close()

    def list_definitions(self) -> list[dict[str, Any]]:
        connection = self._connection()
        try:
            rows = connection.execute(
                "SELECT * FROM wf_definitions ORDER BY definition_id, version"
            ).fetchall()
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
        finally:
            connection.close()

    def user_role_ids(self, user_id: str) -> set[str]:
        return {role["role_id"] for role in self.get_user(user_id)["roles"]}

    def _latest_assignee_id(
        self,
        connection: sqlite3.Connection,
        task_id: str,
    ) -> str | None:
        row = connection.execute(
            """
            SELECT assignee_user_id
            FROM wf_task_assignments
            WHERE task_id = ?
            ORDER BY rowid DESC
            LIMIT 1
            """,
            (task_id,),
        ).fetchone()
        return row["assignee_user_id"] if row else None

    def _task_summary(
        self,
        connection: sqlite3.Connection,
        row: sqlite3.Row,
    ) -> dict[str, Any]:
        assignee_id = self._latest_assignee_id(connection, row["task_id"])
        role_row = connection.execute(
            "SELECT * FROM wf_roles WHERE role_id = ?",
            (row["queue_role_id"],),
        ).fetchone()
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

    def _get_task_row(self, connection: sqlite3.Connection, task_id: str) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM wf_tasks WHERE task_id = ?", (task_id,)
        ).fetchone()
        if row is None:
            raise WorkflowFoundationNotFound(f"Workflow task {task_id} was not found.")
        return row

    def create_task(self, payload: dict[str, Any], actor_user_id: str) -> dict[str, Any]:
        connection = self._connection()
        now = self._now()
        task_id = self._id("TSK")
        correlation_id = self._id("COR")
        request_sha256 = hashlib.sha256(
            self._canonical_json(
                {"actor_user_id": actor_user_id, **payload}
            ).encode("utf-8")
        ).hexdigest()
        try:
            with connection:
                existing = connection.execute(
                    """
                    SELECT * FROM wf_tasks
                    WHERE created_by_user_id = ? AND idempotency_key = ?
                    """,
                    (actor_user_id, payload["idempotency_key"]),
                ).fetchone()
                if existing:
                    if existing["request_sha256"] != request_sha256:
                        raise WorkflowFoundationConflict(
                            "That task idempotency key was already used with a different request."
                        )
                    return self._task_summary(connection, existing)
                connection.execute(
                    """
                    INSERT INTO wf_tasks(
                        task_id, definition_id, definition_version, title,
                        description, capability, context_type, context_id,
                        context_label, queue_role_id, priority, state,
                        due_date, created_by_user_id, idempotency_key,
                        request_sha256, created_at, updated_at, version, assignment_effect,
                        authority_effect, execution_effect
                    ) VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?, ?,
                        ?, ?, ?, 1, 'work_ownership_only', 'none', 'none'
                    )
                    """,
                    (
                        task_id,
                        self.DEFINITION_ID,
                        self.DEFINITION_VERSION,
                        payload["title"],
                        payload["description"],
                        payload["capability"],
                        payload["context_type"],
                        payload["context_id"],
                        payload["context_label"],
                        payload["queue_role_id"],
                        payload["priority"],
                        payload.get("due_date"),
                        actor_user_id,
                        payload["idempotency_key"],
                        request_sha256,
                        now,
                        now,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO wf_task_events(
                        event_id, task_id, event_type, from_state, to_state,
                        actor_user_id, note, idempotency_key, task_version, created_at
                    ) VALUES (?, ?, 'task_created', NULL, 'open', ?, ?, ?, 1, ?)
                    """,
                    (
                        self._id("TEV"),
                        task_id,
                        actor_user_id,
                        "Task created from a governed context reference.",
                        f"create:{task_id}",
                        now,
                    ),
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
        except sqlite3.IntegrityError as exc:
            raise WorkflowFoundationConflict(
                "The task could not be created because its role, assignee, or idempotency evidence is invalid."
            ) from exc
        finally:
            connection.close()

    def _insert_notification(
        self,
        connection: sqlite3.Connection,
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
            """
            INSERT INTO wf_notifications(
                notification_id, recipient_user_id, task_id,
                notification_type, title, message, severity,
                created_at, read_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)
            """,
            (
                notification_id,
                recipient_user_id,
                task_id,
                notification_type,
                title,
                message,
                severity,
                created_at,
            ),
        )
        return notification_id

    def _insert_assignment(
        self,
        connection: sqlite3.Connection,
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
            """
            INSERT INTO wf_task_assignments(
                assignment_event_id, task_id, assignee_user_id,
                prior_assignee_user_id, assigned_by_user_id, assignment_type,
                note, idempotency_key, task_version, created_at, authority_effect
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'none')
            """,
            (
                self._id("ASN"),
                task_id,
                assignee_user_id,
                prior_assignee,
                assigned_by_user_id,
                assignment_type,
                note,
                idempotency_key,
                task_version,
                created_at,
            ),
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

    def get_task(self, task_id: str) -> dict[str, Any]:
        connection = self._connection()
        try:
            row = self._get_task_row(connection, task_id)
            task = self._task_summary(connection, row)
            assignment_rows = connection.execute(
                """
                SELECT * FROM wf_task_assignments
                WHERE task_id = ? ORDER BY rowid
                """,
                (task_id,),
            ).fetchall()
            event_rows = connection.execute(
                """
                SELECT * FROM wf_task_events
                WHERE task_id = ? ORDER BY rowid
                """,
                (task_id,),
            ).fetchall()
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
        finally:
            connection.close()

    def list_tasks(
        self,
        *,
        actor_user_id: str,
        coordinator: bool,
        mine: bool,
        capability: str | None,
        state: str | None,
    ) -> list[dict[str, Any]]:
        connection = self._connection()
        try:
            clauses: list[str] = []
            values: list[Any] = []
            if capability:
                clauses.append("t.capability = ?")
                values.append(capability)
            if state:
                clauses.append("t.state = ?")
                values.append(state)
            role_ids = self.user_role_ids(actor_user_id)
            if coordinator and not mine:
                pass
            elif mine:
                clauses.append(
                    """(
                        SELECT a.assignee_user_id
                        FROM wf_task_assignments a
                        WHERE a.task_id = t.task_id
                        ORDER BY a.rowid DESC
                        LIMIT 1
                    ) = ?"""
                )
                values.append(actor_user_id)
            else:
                placeholders = ",".join("?" for _ in role_ids) or "NULL"
                clauses.append(
                    f"""(
                        (
                            SELECT a.assignee_user_id
                            FROM wf_task_assignments a
                            WHERE a.task_id = t.task_id
                            ORDER BY a.rowid DESC
                            LIMIT 1
                        ) = ?
                        OR (
                            NOT EXISTS (
                                SELECT 1 FROM wf_task_assignments a2
                                WHERE a2.task_id = t.task_id
                            )
                            AND t.queue_role_id IN ({placeholders})
                        )
                    )"""
                )
                values.append(actor_user_id)
                values.extend(sorted(role_ids))
            where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
            rows = connection.execute(
                f"""
                SELECT t.* FROM wf_tasks t
                {where}
                ORDER BY
                    CASE t.priority
                        WHEN 'critical' THEN 1 WHEN 'high' THEN 2
                        WHEN 'medium' THEN 3 ELSE 4
                    END,
                    CASE WHEN t.due_date IS NULL THEN 1 ELSE 0 END,
                    t.due_date,
                    t.updated_at DESC,
                    t.task_id
                """,
                values,
            ).fetchall()
            return [self._task_summary(connection, row) for row in rows]
        finally:
            connection.close()

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
        connection = self._connection()
        now = self._now()
        correlation_id = self._id("COR")
        try:
            with connection:
                existing = connection.execute(
                    "SELECT * FROM wf_task_assignments WHERE idempotency_key = ?",
                    (idempotency_key,),
                ).fetchone()
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
                    return self.get_task(task_id)
                task = self._get_task_row(connection, task_id)
                if task["version"] != expected_version:
                    raise WorkflowFoundationConflict(
                        f"Task version changed. Expected {expected_version}; current version is {task['version']}."
                    )
                new_version = expected_version + 1
                connection.execute(
                    "UPDATE wf_tasks SET version = ?, updated_at = ? WHERE task_id = ? AND version = ?",
                    (new_version, now, task_id, expected_version),
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
        finally:
            connection.close()

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
        connection = self._connection()
        now = self._now()
        correlation_id = self._id("COR")
        try:
            with connection:
                existing = connection.execute(
                    "SELECT * FROM wf_task_events WHERE idempotency_key = ?",
                    (idempotency_key,),
                ).fetchone()
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
                    return self.get_task(task_id)
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
                    """
                    UPDATE wf_tasks
                    SET state = ?, version = ?, updated_at = ?
                    WHERE task_id = ? AND version = ?
                    """,
                    (target_state, new_version, now, task_id, expected_version),
                ).rowcount
                if changed != 1:
                    raise WorkflowFoundationConflict("The task changed during transition.")
                connection.execute(
                    """
                    INSERT INTO wf_task_events(
                        event_id, task_id, event_type, from_state, to_state,
                        actor_user_id, note, idempotency_key, task_version, created_at
                    ) VALUES (?, ?, 'task_state_changed', ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        self._id("TEV"),
                        task_id,
                        task["state"],
                        target_state,
                        actor_user_id,
                        note,
                        idempotency_key,
                        new_version,
                        now,
                    ),
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
        finally:
            connection.close()

    def list_notifications(self, user_id: str) -> list[dict[str, Any]]:
        connection = self._connection()
        try:
            rows = connection.execute(
                """
                SELECT * FROM wf_notifications
                WHERE recipient_user_id = ?
                ORDER BY created_at DESC, notification_id DESC
                LIMIT 250
                """,
                (user_id,),
            ).fetchall()
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
        finally:
            connection.close()

    def mark_notification_read(
        self,
        notification_id: str,
        actor_user_id: str,
    ) -> dict[str, Any]:
        connection = self._connection()
        now = self._now()
        try:
            with connection:
                row = connection.execute(
                    """
                    SELECT * FROM wf_notifications
                    WHERE notification_id = ? AND recipient_user_id = ?
                    """,
                    (notification_id, actor_user_id),
                ).fetchone()
                if row is None:
                    raise WorkflowFoundationNotFound(
                        f"Notification {notification_id} was not found for this user."
                    )
                if row["read_at"] is None:
                    connection.execute(
                        "UPDATE wf_notifications SET read_at = ? WHERE notification_id = ?",
                        (now, notification_id),
                    )
                    self._append_audit(
                        connection,
                        event_type="notification.read",
                        actor_user_id=actor_user_id,
                        subject_type="notification",
                        subject_id=notification_id,
                        correlation_id=self._id("COR"),
                        details={"task_id": row["task_id"], "delivery_scope": "in_app_local"},
                        occurred_at=now,
                    )
                updated = connection.execute(
                    "SELECT * FROM wf_notifications WHERE notification_id = ?",
                    (notification_id,),
                ).fetchone()
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
        finally:
            connection.close()

    def list_audit(
        self,
        *,
        subject_type: str | None = None,
        subject_id: str | None = None,
        limit: int = 250,
    ) -> list[dict[str, Any]]:
        connection = self._connection()
        try:
            clauses: list[str] = []
            values: list[Any] = []
            if subject_type:
                clauses.append("subject_type = ?")
                values.append(subject_type)
            if subject_id:
                clauses.append("subject_id = ?")
                values.append(subject_id)
            where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
            values.append(limit)
            rows = connection.execute(
                f"""
                SELECT * FROM wf_audit_events
                {where}
                ORDER BY rowid DESC LIMIT ?
                """,
                values,
            ).fetchall()
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
        finally:
            connection.close()

    def verify_audit_integrity(self) -> dict[str, Any]:
        connection = self._connection()
        try:
            rows = connection.execute(
                "SELECT * FROM wf_audit_events ORDER BY rowid"
            ).fetchall()
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
        finally:
            connection.close()

    def counts(self, user_id: str | None = None) -> dict[str, int]:
        connection = self._connection()
        try:
            users = int(connection.execute("SELECT COUNT(*) AS c FROM wf_user_accounts").fetchone()["c"])
            open_tasks = int(
                connection.execute(
                    "SELECT COUNT(*) AS c FROM wf_tasks WHERE state NOT IN ('completed', 'cancelled')"
                ).fetchone()["c"]
            )
            audit_records = int(connection.execute("SELECT COUNT(*) AS c FROM wf_audit_events").fetchone()["c"])
            unread = 0
            if user_id:
                unread = int(
                    connection.execute(
                        "SELECT COUNT(*) AS c FROM wf_notifications WHERE recipient_user_id = ? AND read_at IS NULL",
                        (user_id,),
                    ).fetchone()["c"]
                )
            return {
                "users": users,
                "open_tasks": open_tasks,
                "audit_records": audit_records,
                "unread_notifications": unread,
            }
        finally:
            connection.close()
