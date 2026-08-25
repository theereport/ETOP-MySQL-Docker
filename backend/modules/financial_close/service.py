from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import uuid4

from core.auth import AuthenticationRequired as WorkflowAuthenticationRequired
from modules.workflow_foundation.service import (
    WorkflowFoundationService,
    workflow_foundation_service,
)

from .repository import (
    FinancialCloseConflict,
    FinancialCloseIntegrityError,
    FinancialCloseNotFound,
    FinancialCloseRepository,
    financial_close_repository,
)
from .schemas import (
    CloseControlCounts,
    CloseControlCreate,
    CloseControlEventList,
    CloseControlSummary,
    CloseCycleCreate,
    CloseCycleDetail,
    CloseCycleListResponse,
    CloseCycleSummary,
    CloseCycleTemplateLineage,
    CloseEvent,
    CloseEventIntegrity,
    CloseIdentity,
    ClosePreparationCreate,
    CloseReviewCreate,
    CloseControlTemplateLineage,
    CloseTemplateCreate,
    CloseTemplateDetail,
    CloseTemplateEvent,
    CloseTemplateEventIntegrity,
    CloseTemplateInstantiate,
    CloseTemplateItem,
    CloseTemplateListResponse,
    CloseTemplateSummary,
    CloseTemplateVersion,
    CloseTemplateVersionCreate,
    FinancialCloseAuthorityBoundary,
    FinancialCloseDeferredCapability,
    FinancialCloseGovernance,
    FinancialCloseSourceCoverage,
)


class FinancialClosePermissionDenied(PermissionError):
    """The authenticated local identity may not perform the requested action."""


class FinancialCloseValidationError(ValueError):
    """The requested close-readiness evidence is internally inconsistent."""


def _utc_now() -> datetime:
    return datetime.now(UTC)


class FinancialCloseService:
    """Coordinate local close evidence without representing a financial close."""

    def __init__(
        self,
        *,
        repository: FinancialCloseRepository = financial_close_repository,
        workflow_service: WorkflowFoundationService = workflow_foundation_service,
        clock: Callable[[], datetime] = _utc_now,
        id_factory: Callable[[str], str] | None = None,
    ) -> None:
        self.repository = repository
        self.workflow_service = workflow_service
        self._clock = clock
        self._id_factory = id_factory or (
            lambda prefix: f"{prefix}-{uuid4().hex}"
        )
        self.repository.initialize()

    def _id(self, prefix: str) -> str:
        return self._id_factory(prefix)

    def _now(self) -> str:
        value = self._clock()
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).isoformat()

    @staticmethod
    def _identity(user: dict[str, Any]) -> dict[str, str]:
        return {
            "person_id": user["person_id"],
            "user_id": user["user_id"],
            "username": user["username"],
            "display_name": user["display_name"],
            "status": user["status"],
        }

    def _session(self, token: str) -> dict[str, Any]:
        session = self.workflow_service.session_for_token(token)
        current = self.workflow_service.repository.get_user(
            session["user"]["user_id"]
        )
        if current["status"] != "active":
            raise WorkflowAuthenticationRequired(
                "The authenticated local Workflow Foundation account is inactive."
            )
        return {**session, "user": current}

    @staticmethod
    def _role_ids(user: dict[str, Any]) -> set[str]:
        return {role["role_id"] for role in user.get("roles", [])}

    def _require_coordinator(self, session: dict[str, Any]) -> None:
        if "workflow_coordinator" not in self._role_ids(session["user"]):
            raise FinancialClosePermissionDenied(
                "Workflow Coordinator is required to configure local close-readiness work. "
                "This permission grants no close, approval, posting, or financial authority."
            )

    def _active_identity(self, user_id: str) -> dict[str, str]:
        users = {
            user["user_id"]: user
            for user in self.workflow_service.repository.list_users()
        }
        user = users.get(user_id)
        if user is None:
            raise FinancialCloseNotFound(
                f"Workflow Foundation user {user_id} was not found."
            )
        if user["status"] != "active":
            raise FinancialCloseValidationError(
                f"Workflow Foundation user {user_id} is not active."
            )
        return self._identity(user)

    @staticmethod
    def governance() -> FinancialCloseGovernance:
        return FinancialCloseGovernance(
            source_coverage=[
                FinancialCloseSourceCoverage(
                    key="local_close_control_evidence",
                    label="Local close control evidence",
                    status="available",
                    explanation=(
                        "Immutable cycle/control definitions and append-only preparation/review evidence are stored locally."
                    ),
                ),
                FinancialCloseSourceCoverage(
                    key="workflow_foundation_identity",
                    label="Verified local identities",
                    status="available",
                    explanation=(
                        "Preparer, reviewer, creator, and event actor identities come from authenticated local Workflow Foundation accounts."
                    ),
                ),
                FinancialCloseSourceCoverage(
                    key="local_planning_templates",
                    label="Local planning templates and calendar snapshots",
                    status="available_local_draft",
                    explanation=(
                        "Immutable user-authored template versions may propose planning dates and be manually snapshotted into a cycle; they are not approved accounting policy or an enterprise close calendar."
                    ),
                ),
                FinancialCloseSourceCoverage(
                    key="erp_general_ledger_period",
                    label="ERP general ledger and period status",
                    status="unavailable",
                    explanation=(
                        "No governed general-ledger balance, posting, or ERP period-state contract is connected in this increment."
                    ),
                ),
                FinancialCloseSourceCoverage(
                    key="reconciliation_and_journal_evidence",
                    label="Reconciliation and journal source evidence",
                    status="unavailable",
                    explanation=(
                        "Evidence references are operator-supplied references; ETOP does not yet retrieve or validate the underlying reconciliation or journal source."
                    ),
                ),
            ],
            authority=FinancialCloseAuthorityBoundary(
                statements=[
                    "A Workflow Foundation identity establishes local accountability only, not financial authority.",
                    "Evidence sufficient means sufficient for a later close review; it is not close certification or approval.",
                    "A local template version and calculated date are planning drafts only; neither establishes accounting policy, recurrence, SLA, or a required enterprise control.",
                    "No event closes books, changes an ERP period, approves or posts a journal, or writes to an ERP source.",
                ]
            ),
            deferred_capabilities=[
                FinancialCloseDeferredCapability(
                    key="erp_period_control",
                    label="ERP period control",
                    reason="Authoritative ERP period state and permitted close/reopen actions are not connected.",
                ),
                FinancialCloseDeferredCapability(
                    key="financial_close_authority",
                    label="Close certification and approval authority",
                    reason="Approved authority, delegation, segregation, and certification Decision Models are not configured.",
                ),
                FinancialCloseDeferredCapability(
                    key="source_backed_reconciliation",
                    label="Source-backed reconciliation and journal validation",
                    reason="Governed GL, subledger, reconciliation, and journal source contracts are not connected.",
                ),
                FinancialCloseDeferredCapability(
                    key="automated_escalation",
                    label="SLA, escalation, and external notification",
                    reason="Planned dates are local coordination dates, not approved SLA or escalation policy.",
                ),
                FinancialCloseDeferredCapability(
                    key="recurring_cycle_automation",
                    label="Recurring cycle generation",
                    reason="Templates require an explicit authenticated manual instantiation; no schedule creates cycles, tasks, or messages.",
                ),
            ],
        )

    def governance_for_token(self, token: str) -> FinancialCloseGovernance:
        self._session(token)
        return self.governance()

    def _template_item_records(
        self,
        *,
        template_id: str,
        version: int,
        items: list[Any],
    ) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for ordinal, item in enumerate(items, start=1):
            if item.preparer_user_id == item.reviewer_user_id:
                raise FinancialCloseValidationError(
                    "Every template item requires distinct active preparer and reviewer identities."
                )
            preparer = self._active_identity(item.preparer_user_id)
            reviewer = self._active_identity(item.reviewer_user_id)
            records.append(
                {
                    "item_id": self._id("FCI"),
                    "template_id": template_id,
                    "template_version": version,
                    "ordinal": ordinal,
                    "title": item.title,
                    "description": item.description,
                    "planned_offset_days": item.planned_offset_days,
                    "preparer": preparer,
                    "reviewer": reviewer,
                }
            )
        return records

    def create_template(
        self,
        token: str,
        payload: CloseTemplateCreate,
    ) -> CloseTemplateDetail:
        session = self._session(token)
        self._require_coordinator(session)
        actor = self._active_identity(session["user"]["user_id"])
        now = self._now()
        template_id = self._id("FCP")
        payload_json = payload.model_dump(mode="json")
        request_sha256 = self._request_hash(
            operation="financial_close.template_create",
            actor_user_id=actor["user_id"],
            context={},
            payload=payload_json,
        )
        template_record = {
            "template_id": template_id,
            "created_by": actor,
            "created_at": now,
            "idempotency_key": payload.idempotency_key,
            "request_sha256": request_sha256,
        }
        version_record = {
            "template_id": template_id,
            "version": 1,
            "title": payload.title,
            "description": payload.description,
            "change_note": "Initial local user-authored planning draft.",
            "created_by": actor,
            "created_at": now,
            "idempotency_key": payload.idempotency_key,
            "request_sha256": request_sha256,
            "previous_version_sha256": "0" * 64,
            "items": self._template_item_records(
                template_id=template_id,
                version=1,
                items=payload.items,
            ),
        }
        creation_event = {
            "event_id": self._id("FPE"),
            "template_id": template_id,
            "event_type": "template_created",
            "actor": actor,
            "occurred_at": now,
            "details": {
                "version": 1,
                "item_count": len(payload.items),
                "template_authority": "local_user_authored_planning_draft",
                "policy_effect": "none",
                "automation_effect": "none",
            },
            "idempotency_key": f"template-created:{template_id}",
            "request_sha256": request_sha256,
        }
        bundle = self.repository.create_template(
            template_record,
            version_record,
            creation_event,
        )
        return self._template_detail(bundle)

    def list_templates(self, token: str) -> CloseTemplateListResponse:
        self._session(token)
        items = [
            self._template_summary(bundle)
            for bundle in self.repository.list_templates()
        ]
        return CloseTemplateListResponse(items=items, total=len(items))

    def get_template(
        self,
        token: str,
        template_id: str,
    ) -> CloseTemplateDetail:
        self._session(token)
        return self._template_detail(self.repository.get_template(template_id))

    def create_template_version(
        self,
        token: str,
        template_id: str,
        payload: CloseTemplateVersionCreate,
    ) -> CloseTemplateDetail:
        session = self._session(token)
        self._require_coordinator(session)
        actor = self._active_identity(session["user"]["user_id"])
        current = self.repository.get_template(template_id)
        latest = current["versions"][-1]
        now = self._now()
        payload_json = payload.model_dump(mode="json")
        request_sha256 = self._request_hash(
            operation="financial_close.template_version_create",
            actor_user_id=actor["user_id"],
            context={"template_id": template_id},
            payload=payload_json,
        )
        next_version = int(latest["version"]) + 1
        version_record = {
            "template_id": template_id,
            "version": next_version,
            "title": payload.title,
            "description": payload.description,
            "change_note": payload.change_note,
            "created_by": actor,
            "created_at": now,
            "idempotency_key": payload.idempotency_key,
            "request_sha256": request_sha256,
            "previous_version_sha256": latest["version_sha256"],
            "items": self._template_item_records(
                template_id=template_id,
                version=next_version,
                items=payload.items,
            ),
        }
        version_event = {
            "event_id": self._id("FPE"),
            "template_id": template_id,
            "event_type": "template_version_created",
            "actor": actor,
            "occurred_at": now,
            "details": {
                "version": next_version,
                "previous_version": latest["version"],
                "previous_version_sha256": latest["version_sha256"],
                "item_count": len(payload.items),
                "change_note": payload.change_note,
                "policy_effect": "none",
                "automation_effect": "none",
            },
            "idempotency_key": f"template-version:{template_id}:{next_version}",
            "request_sha256": request_sha256,
        }
        bundle = self.repository.create_template_version(
            version_record,
            version_event,
            expected_latest_version=payload.expected_latest_version,
        )
        return self._template_detail(bundle)

    def instantiate_template(
        self,
        token: str,
        template_id: str,
        template_version: int,
        payload: CloseTemplateInstantiate,
    ) -> CloseCycleDetail:
        session = self._session(token)
        self._require_coordinator(session)
        actor = self._active_identity(session["user"]["user_id"])
        template = self.repository.get_template_version(
            template_id,
            template_version,
        )
        now = self._now()
        payload_json = payload.model_dump(mode="json")
        request_sha256 = self._request_hash(
            operation="financial_close.template_instantiate",
            actor_user_id=actor["user_id"],
            context={
                "template_id": template_id,
                "template_version": template_version,
                "template_version_sha256": template["version_sha256"],
            },
            payload=payload_json,
        )
        cycle_id = self._id("FCC")
        snapshot_id = self._id("FCS")
        calendar_anchor = payload.calendar_anchor_date
        controls: list[tuple[dict[str, Any], dict[str, Any]]] = []
        snapshot_items: list[dict[str, Any]] = []
        for source_item in template["items"]:
            current_preparer = self._active_identity(
                source_item["preparer_user_id"]
            )
            current_reviewer = self._active_identity(
                source_item["reviewer_user_id"]
            )
            if current_preparer["user_id"] == current_reviewer["user_id"]:
                raise FinancialCloseValidationError(
                    "Template instantiation requires distinct active preparer and reviewer identities for every item."
                )
            # Preserve the exact immutable version-authorship identity snapshots.
            # Current account activity is checked above and again under the write lock.
            preparer = dict(source_item["preparer"])
            reviewer = dict(source_item["reviewer"])
            planned_date = calendar_anchor + timedelta(
                days=int(source_item["planned_offset_days"])
            )
            control_id = self._id("FCT")
            control_payload = {
                "template_item_id": source_item["item_id"],
                "template_item_sha256": source_item["item_sha256"],
                "title": source_item["title"],
                "description": source_item["description"],
                "planned_offset_days": source_item["planned_offset_days"],
                "planned_date": planned_date.isoformat(),
                "preparer_user_id": preparer["user_id"],
                "reviewer_user_id": reviewer["user_id"],
            }
            control_request_sha256 = self._request_hash(
                operation="financial_close.template_control_snapshot",
                actor_user_id=actor["user_id"],
                context={
                    "cycle_id": cycle_id,
                    "snapshot_id": snapshot_id,
                    "template_id": template_id,
                    "template_version": template_version,
                },
                payload=control_payload,
            )
            control_record = {
                "control_id": control_id,
                "cycle_id": cycle_id,
                "title": source_item["title"],
                "description": source_item["description"],
                "planned_date": planned_date.isoformat(),
                "preparer": preparer,
                "reviewer": reviewer,
                "created_by": actor,
                "created_at": now,
                "idempotency_key": (
                    f"template-control:{snapshot_id}:{source_item['ordinal']}"
                ),
                "request_sha256": control_request_sha256,
            }
            control_event = {
                "event_id": self._id("FCE"),
                "cycle_id": cycle_id,
                "control_id": control_id,
                "event_type": "control_created",
                "actor": actor,
                "occurred_at": now,
                "details": {
                    "title": source_item["title"],
                    "planned_date": planned_date.isoformat(),
                    "preparer_user_id": preparer["user_id"],
                    "reviewer_user_id": reviewer["user_id"],
                    "template_snapshot_id": snapshot_id,
                    "template_id": template_id,
                    "template_version": template_version,
                    "template_item_id": source_item["item_id"],
                    "template_item_sha256": source_item["item_sha256"],
                    "planned_offset_days": source_item["planned_offset_days"],
                    "planning_date_rule": "calendar_anchor_plus_offset_days",
                    "authority_effect": "none",
                    "policy_effect": "none",
                    "close_effect": "none",
                },
                "idempotency_key": f"control-created:{control_id}",
                "request_sha256": control_request_sha256,
            }
            controls.append((control_record, control_event))
            snapshot_items.append(
                {
                    "ordinal": source_item["ordinal"],
                    "template_item_id": source_item["item_id"],
                    "template_item_sha256": source_item["item_sha256"],
                    "control_id": control_id,
                    "title": source_item["title"],
                    "description": source_item["description"],
                    "planned_offset_days": source_item["planned_offset_days"],
                    "planned_date": planned_date.isoformat(),
                    "preparer": preparer,
                    "reviewer": reviewer,
                }
            )
        snapshot_record = {
            "snapshot_id": snapshot_id,
            "cycle_id": cycle_id,
            "template_id": template_id,
            "template_version": template_version,
            "template_version_sha256": template["version_sha256"],
            "calendar_anchor_date": calendar_anchor.isoformat(),
            "snapshot": {
                "template_title": template["title"],
                "template_status": "local_user_authored_planning_draft",
                "planning_date_rule": "calendar_anchor_plus_offset_days",
                "calendar_anchor_date": calendar_anchor.isoformat(),
                "items": snapshot_items,
                "policy_effect": "none",
                "automation_effect": "none",
            },
            "created_by": actor,
            "created_at": now,
            "idempotency_key": payload.idempotency_key,
            "request_sha256": request_sha256,
        }
        snapshot_record["snapshot_sha256"] = (
            self.repository.cycle_template_snapshot_sha256(snapshot_record)
        )
        cycle_record = {
            "cycle_id": cycle_id,
            "entity_label": payload.entity_label,
            "period_label": payload.period_label,
            "period_start": payload.period_start.isoformat(),
            "period_end": payload.period_end.isoformat(),
            "target_completion_date": (
                payload.target_completion_date.isoformat()
                if payload.target_completion_date
                else None
            ),
            "description": payload.description,
            "created_by": actor,
            "created_at": now,
            "idempotency_key": payload.idempotency_key,
            "request_sha256": request_sha256,
        }
        cycle_event = {
            "event_id": self._id("FCE"),
            "cycle_id": cycle_id,
            "control_id": None,
            "event_type": "cycle_created",
            "actor": actor,
            "occurred_at": now,
            "details": {
                "entity_label": payload.entity_label,
                "period_label": payload.period_label,
                "period_start": payload.period_start.isoformat(),
                "period_end": payload.period_end.isoformat(),
                "target_completion_date": cycle_record["target_completion_date"],
                "template_snapshot_id": snapshot_id,
                "template_id": template_id,
                "template_version": template_version,
                "template_version_sha256": template["version_sha256"],
                "snapshot_sha256": snapshot_record["snapshot_sha256"],
                "calendar_anchor_date": calendar_anchor.isoformat(),
                "planning_date_rule": "calendar_anchor_plus_offset_days",
                "identity_source": "workflow_foundation_local_account",
                "erp_period_state": "unavailable",
                "policy_effect": "none",
                "automation_effect": "none",
                "close_effect": "none",
            },
            "idempotency_key": f"cycle-created:{cycle_id}",
            "request_sha256": request_sha256,
        }
        template_event = {
            "event_id": self._id("FPE"),
            "template_id": template_id,
            "event_type": "cycle_instantiated",
            "actor": actor,
            "occurred_at": now,
            "details": {
                "template_version": template_version,
                "template_version_sha256": template["version_sha256"],
                "snapshot_id": snapshot_id,
                "snapshot_sha256": snapshot_record["snapshot_sha256"],
                "cycle_id": cycle_id,
                "calendar_anchor_date": calendar_anchor.isoformat(),
                "planning_date_rule": "calendar_anchor_plus_offset_days",
                "manual_instantiation": True,
                "policy_effect": "none",
                "automation_effect": "none",
                "close_effect": "none",
            },
            "idempotency_key": f"template-cycle:{snapshot_id}",
            "request_sha256": request_sha256,
        }
        stored = self.repository.instantiate_template_cycle(
            cycle_record=cycle_record,
            cycle_event=cycle_event,
            control_records=controls,
            snapshot_record=snapshot_record,
            template_event=template_event,
        )
        return self._cycle_detail(stored)

    def _request_hash(
        self,
        *,
        operation: str,
        actor_user_id: str,
        context: dict[str, Any],
        payload: dict[str, Any],
    ) -> str:
        return self.repository.sha256(
            {
                "operation": operation,
                "actor_user_id": actor_user_id,
                "context": context,
                "payload": payload,
            }
        )

    def create_cycle(self, token: str, payload: CloseCycleCreate) -> CloseCycleDetail:
        session = self._session(token)
        self._require_coordinator(session)
        actor = self._active_identity(session["user"]["user_id"])
        now = self._now()
        payload_json = payload.model_dump(mode="json")
        request_sha256 = self._request_hash(
            operation="financial_close.cycle_create",
            actor_user_id=actor["user_id"],
            context={},
            payload=payload_json,
        )
        cycle_id = self._id("FCC")
        record = {
            "cycle_id": cycle_id,
            "entity_label": payload.entity_label,
            "period_label": payload.period_label,
            "period_start": payload.period_start.isoformat(),
            "period_end": payload.period_end.isoformat(),
            "target_completion_date": (
                payload.target_completion_date.isoformat()
                if payload.target_completion_date
                else None
            ),
            "description": payload.description,
            "created_by": actor,
            "created_at": now,
            "idempotency_key": payload.idempotency_key,
            "request_sha256": request_sha256,
        }
        creation_event = {
            "event_id": self._id("FCE"),
            "cycle_id": cycle_id,
            "control_id": None,
            "event_type": "cycle_created",
            "actor": actor,
            "occurred_at": now,
            "details": {
                "entity_label": payload.entity_label,
                "period_label": payload.period_label,
                "period_start": payload.period_start.isoformat(),
                "period_end": payload.period_end.isoformat(),
                "target_completion_date": record["target_completion_date"],
                "identity_source": "workflow_foundation_local_account",
                "erp_period_state": "unavailable",
                "close_effect": "none",
            },
            "idempotency_key": f"cycle-created:{cycle_id}",
            "request_sha256": request_sha256,
        }
        stored = self.repository.create_cycle(record, creation_event)
        return self._cycle_detail(stored)

    def list_cycles(self, token: str) -> CloseCycleListResponse:
        self._session(token)
        items = [self._cycle_summary(item) for item in self.repository.list_cycles()]
        return CloseCycleListResponse(
            items=items,
            total=len(items),
            governance=self.governance(),
        )

    def get_cycle(self, token: str, cycle_id: str) -> CloseCycleDetail:
        self._session(token)
        return self._cycle_detail(self.repository.get_cycle(cycle_id))

    def create_control(
        self,
        token: str,
        cycle_id: str,
        payload: CloseControlCreate,
    ) -> CloseControlSummary:
        session = self._session(token)
        self._require_coordinator(session)
        self.repository.get_cycle(cycle_id)
        if payload.preparer_user_id == payload.reviewer_user_id:
            raise FinancialCloseValidationError(
                "Preparer and reviewer must be distinct active Workflow Foundation users."
            )
        preparer = self._active_identity(payload.preparer_user_id)
        reviewer = self._active_identity(payload.reviewer_user_id)
        actor = self._active_identity(session["user"]["user_id"])
        now = self._now()
        payload_json = payload.model_dump(mode="json")
        request_sha256 = self._request_hash(
            operation="financial_close.control_create",
            actor_user_id=actor["user_id"],
            context={"cycle_id": cycle_id},
            payload=payload_json,
        )
        control_id = self._id("FCT")
        record = {
            "control_id": control_id,
            "cycle_id": cycle_id,
            "title": payload.title,
            "description": payload.description,
            "planned_date": payload.planned_date.isoformat() if payload.planned_date else None,
            "preparer": preparer,
            "reviewer": reviewer,
            "created_by": actor,
            "created_at": now,
            "idempotency_key": payload.idempotency_key,
            "request_sha256": request_sha256,
        }
        creation_event = {
            "event_id": self._id("FCE"),
            "cycle_id": cycle_id,
            "control_id": control_id,
            "event_type": "control_created",
            "actor": actor,
            "occurred_at": now,
            "details": {
                "title": payload.title,
                "planned_date": record["planned_date"],
                "preparer_user_id": preparer["user_id"],
                "reviewer_user_id": reviewer["user_id"],
                "identity_source": "workflow_foundation_local_account",
                "authority_effect": "none",
                "close_effect": "none",
            },
            "idempotency_key": f"control-created:{control_id}",
            "request_sha256": request_sha256,
        }
        stored = self.repository.create_control(record, creation_event)
        return self._control_summary(stored)

    def create_preparation(
        self,
        token: str,
        cycle_id: str,
        control_id: str,
        payload: ClosePreparationCreate,
    ) -> CloseControlSummary:
        session = self._session(token)
        control = self.repository.get_control(cycle_id, control_id)
        actor = self._identity(session["user"])
        if actor["user_id"] != control["preparer"]["user_id"]:
            raise FinancialClosePermissionDenied(
                "Only the exact active preparer assigned to this immutable control may record preparation evidence."
            )
        self._active_identity(actor["user_id"])
        payload_json = payload.model_dump(mode="json")
        request_sha256 = self._request_hash(
            operation="financial_close.preparation_record",
            actor_user_id=actor["user_id"],
            context={"cycle_id": cycle_id, "control_id": control_id},
            payload=payload_json,
        )
        now = self._now()
        event = {
            "event_id": self._id("FCE"),
            "cycle_id": cycle_id,
            "control_id": control_id,
            "event_type": "preparation_recorded",
            "actor": actor,
            "occurred_at": now,
            "details": {
                "disposition": payload.disposition,
                "evidence_reference": payload.evidence_reference,
                "note": payload.note,
                "expected_control_version": payload.expected_control_version,
                "evidence_source_status": "operator_supplied_unverified",
                "authority_effect": "none",
                "close_effect": "none",
            },
            "expected_version": payload.expected_control_version,
            "idempotency_key": payload.idempotency_key,
            "request_sha256": request_sha256,
        }
        self.repository.append_control_event(event)
        return self._control_summary(control)

    def create_review(
        self,
        token: str,
        cycle_id: str,
        control_id: str,
        payload: CloseReviewCreate,
    ) -> CloseControlSummary:
        session = self._session(token)
        control = self.repository.get_control(cycle_id, control_id)
        actor = self._identity(session["user"])
        if actor["user_id"] != control["reviewer"]["user_id"]:
            raise FinancialClosePermissionDenied(
                "Only the exact active reviewer assigned to this immutable control may record review evidence."
            )
        self._active_identity(actor["user_id"])
        payload_json = payload.model_dump(mode="json")
        request_sha256 = self._request_hash(
            operation="financial_close.review_record",
            actor_user_id=actor["user_id"],
            context={"cycle_id": cycle_id, "control_id": control_id},
            payload=payload_json,
        )
        existing = self.repository.get_event_by_idempotency(
            actor["user_id"], payload.idempotency_key
        )
        events = self.repository.list_events(cycle_id, control_id)
        if existing is None:
            latest_preparation = next(
                (
                    event
                    for event in reversed(events)
                    if event["event_type"] == "preparation_recorded"
                ),
                None,
            )
            if latest_preparation is None:
                raise FinancialCloseConflict(
                    "Review requires a current preparation event from the exact preparer."
                )
            if (
                payload.disposition == "evidence_sufficient"
                and latest_preparation["details"].get("disposition")
                != "reference_recorded"
            ):
                raise FinancialCloseConflict(
                    "Evidence sufficient requires the latest preparation to record an evidence reference."
                )
            review_after_latest = any(
                event["event_type"] == "review_recorded"
                and event["subject_version"] > latest_preparation["subject_version"]
                for event in events
            )
            if review_after_latest:
                raise FinancialCloseConflict(
                    "The latest preparation already has a current review. A new preparation is required before another review."
                )
        else:
            latest_preparation = None
        now = self._now()
        details: dict[str, object] = {
            "disposition": payload.disposition,
            "note": payload.note,
            "expected_control_version": payload.expected_control_version,
            "authority_effect": "none",
            "close_effect": "none",
            "approval_effect": "none",
        }
        if latest_preparation is not None:
            details.update(
                {
                    "reviewed_preparation_event_id": latest_preparation["event_id"],
                    "reviewed_preparation_version": latest_preparation["subject_version"],
                    "reviewed_preparation_record_hash": latest_preparation["record_hash"],
                }
            )
        event = {
            "event_id": self._id("FCE"),
            "cycle_id": cycle_id,
            "control_id": control_id,
            "event_type": "review_recorded",
            "actor": actor,
            "occurred_at": now,
            "details": details,
            "expected_version": payload.expected_control_version,
            "idempotency_key": payload.idempotency_key,
            "request_sha256": request_sha256,
        }
        self.repository.append_control_event(event)
        return self._control_summary(control)

    def get_control_events(
        self,
        token: str,
        cycle_id: str,
        control_id: str,
    ) -> CloseControlEventList:
        self._session(token)
        self.repository.get_control(cycle_id, control_id)
        items = [
            self._event_model(event)
            for event in self.repository.list_events(cycle_id, control_id)
        ]
        integrity = self.repository.verify_control_chain(control_id)
        return CloseControlEventList(
            items=items,
            integrity=CloseEventIntegrity.model_validate(integrity),
        )

    @staticmethod
    def _template_item_model(item: dict[str, Any]) -> CloseTemplateItem:
        return CloseTemplateItem(
            item_id=item["item_id"],
            template_id=item["template_id"],
            template_version=item["template_version"],
            ordinal=item["ordinal"],
            title=item["title"],
            description=item["description"],
            planned_offset_days=item["planned_offset_days"],
            preparer=CloseIdentity.model_validate(item["preparer"]),
            reviewer=CloseIdentity.model_validate(item["reviewer"]),
            item_sha256=item["item_sha256"],
        )

    def _template_version_model(
        self,
        version: dict[str, Any],
    ) -> CloseTemplateVersion:
        return CloseTemplateVersion(
            template_id=version["template_id"],
            version=version["version"],
            title=version["title"],
            description=version["description"],
            change_note=version["change_note"],
            status=version["status"],
            created_by=CloseIdentity.model_validate(version["created_by"]),
            created_at=version["created_at"],
            previous_version_sha256=version["previous_version_sha256"],
            version_sha256=version["version_sha256"],
            items=[self._template_item_model(item) for item in version["items"]],
        )

    @staticmethod
    def _template_event_model(event: dict[str, Any]) -> CloseTemplateEvent:
        return CloseTemplateEvent(
            event_id=event["event_id"],
            template_id=event["template_id"],
            event_type=event["event_type"],
            actor=CloseIdentity.model_validate(event["actor"]),
            occurred_at=event["occurred_at"],
            details=event["details"],
            sequence=event["sequence"],
            previous_hash=event["previous_hash"],
            record_hash=event["record_hash"],
        )

    def _template_summary(
        self,
        bundle: dict[str, Any],
    ) -> CloseTemplateSummary:
        template = bundle["template"]
        versions = bundle["versions"]
        latest = versions[-1]
        return CloseTemplateSummary(
            template_id=template["template_id"],
            title=latest["title"],
            description=latest["description"],
            latest_version=latest["version"],
            version_count=len(versions),
            item_count=len(latest["items"]),
            latest_version_sha256=latest["version_sha256"],
            created_by=CloseIdentity.model_validate(template["created_by"]),
            created_at=template["created_at"],
        )

    def _template_detail(
        self,
        bundle: dict[str, Any],
    ) -> CloseTemplateDetail:
        summary = self._template_summary(bundle)
        return CloseTemplateDetail(
            **summary.model_dump(),
            versions=[
                self._template_version_model(version)
                for version in bundle["versions"]
            ],
            events=[
                self._template_event_model(event)
                for event in bundle["events"]
            ],
            integrity=CloseTemplateEventIntegrity.model_validate(
                bundle["integrity"]
            ),
        )

    def _cycle_template_lineage(
        self,
        cycle_id: str,
    ) -> tuple[dict[str, Any] | None, CloseCycleTemplateLineage | None]:
        snapshot = self.repository.get_cycle_template_snapshot(cycle_id)
        if snapshot is None:
            return None, None
        template_version = self.repository.get_template_version(
            snapshot["template_id"],
            snapshot["template_version"],
        )
        if template_version["version_sha256"] != snapshot["template_version_sha256"]:
            raise FinancialCloseIntegrityError(
                f"Financial close cycle {cycle_id} no longer matches its immutable template version hash."
            )
        snapshot_payload = snapshot["snapshot"]
        self._validate_cycle_snapshot_binding(
            cycle_id,
            snapshot,
            template_version,
        )
        lineage = CloseCycleTemplateLineage(
            snapshot_id=snapshot["snapshot_id"],
            template_id=snapshot["template_id"],
            template_version=snapshot["template_version"],
            template_title=snapshot_payload["template_title"],
            template_version_sha256=snapshot["template_version_sha256"],
            calendar_anchor_date=snapshot["calendar_anchor_date"],
            instantiated_by=CloseIdentity.model_validate(snapshot["created_by"]),
            instantiated_at=snapshot["created_at"],
            snapshot_sha256=snapshot["snapshot_sha256"],
        )
        return snapshot, lineage

    @staticmethod
    def _validate_cycle_snapshot_binding(
        cycle_id: str,
        snapshot: dict[str, Any],
        template_version: dict[str, Any],
    ) -> None:
        payload = snapshot["snapshot"]
        source_items = template_version["items"]
        snapshot_items = payload.get("items")
        if (
            payload.get("template_title") != template_version["title"]
            or payload.get("template_status")
            != "local_user_authored_planning_draft"
            or payload.get("planning_date_rule")
            != "calendar_anchor_plus_offset_days"
            or payload.get("calendar_anchor_date")
            != snapshot["calendar_anchor_date"]
            or not isinstance(snapshot_items, list)
            or len(snapshot_items) != len(source_items)
        ):
            raise FinancialCloseIntegrityError(
                f"Financial close cycle {cycle_id} has inconsistent template snapshot metadata."
            )

        try:
            anchor = date.fromisoformat(snapshot["calendar_anchor_date"])
        except (TypeError, ValueError) as exc:
            raise FinancialCloseIntegrityError(
                f"Financial close cycle {cycle_id} has an invalid template calendar anchor."
            ) from exc

        seen_control_ids: set[str] = set()
        for source_item, item in zip(source_items, snapshot_items, strict=True):
            control_id = item.get("control_id")
            expected_date = (
                anchor + timedelta(days=int(source_item["planned_offset_days"]))
            ).isoformat()
            if (
                not isinstance(control_id, str)
                or not control_id
                or control_id in seen_control_ids
                or item.get("ordinal") != source_item["ordinal"]
                or item.get("template_item_id") != source_item["item_id"]
                or item.get("template_item_sha256")
                != source_item["item_sha256"]
                or item.get("title") != source_item["title"]
                or item.get("description") != source_item["description"]
                or item.get("planned_offset_days")
                != source_item["planned_offset_days"]
                or item.get("planned_date") != expected_date
                or item.get("preparer") != source_item["preparer"]
                or item.get("reviewer") != source_item["reviewer"]
            ):
                raise FinancialCloseIntegrityError(
                    f"Financial close cycle {cycle_id} does not exactly match template item ordinal {source_item['ordinal']}."
                )
            seen_control_ids.add(control_id)

    @staticmethod
    def _control_template_lineage(
        control: dict[str, Any],
        snapshot: dict[str, Any] | None,
    ) -> CloseControlTemplateLineage | None:
        if snapshot is None:
            return None
        item = next(
            (
                candidate
                for candidate in snapshot["snapshot"].get("items", [])
                if candidate.get("control_id") == control["control_id"]
            ),
            None,
        )
        if item is None:
            return None
        expected = {
            "title": control["title"],
            "description": control["description"],
            "planned_date": control["planned_date"],
            "preparer_user_id": control["preparer"]["user_id"],
            "reviewer_user_id": control["reviewer"]["user_id"],
        }
        observed = {
            "title": item.get("title"),
            "description": item.get("description"),
            "planned_date": item.get("planned_date"),
            "preparer_user_id": item.get("preparer", {}).get("user_id"),
            "reviewer_user_id": item.get("reviewer", {}).get("user_id"),
        }
        if observed != expected:
            raise FinancialCloseIntegrityError(
                f"Financial close control {control['control_id']} does not match its immutable template snapshot."
            )
        return CloseControlTemplateLineage(
            snapshot_id=snapshot["snapshot_id"],
            template_id=snapshot["template_id"],
            template_version=snapshot["template_version"],
            template_item_id=item["template_item_id"],
            template_item_sha256=item["template_item_sha256"],
            planned_offset_days=item["planned_offset_days"],
        )

    def _control_projection(
        self,
        events: list[dict[str, Any]],
    ) -> dict[str, Any]:
        latest_preparation = next(
            (
                event
                for event in reversed(events)
                if event["event_type"] == "preparation_recorded"
            ),
            None,
        )
        latest_review = next(
            (
                event
                for event in reversed(events)
                if event["event_type"] == "review_recorded"
            ),
            None,
        )
        if latest_preparation is None:
            return {
                "state": "not_started",
                "evidence_status": "not_recorded",
                "review_currency": "not_reviewed",
                "latest_preparation_at": None,
                "latest_review_at": latest_review["occurred_at"] if latest_review else None,
            }
        evidence_status = latest_preparation["details"].get("disposition")
        review_after_latest = (
            latest_review
            if latest_review
            and latest_review["subject_version"] > latest_preparation["subject_version"]
            else None
        )
        prior_review_exists = bool(latest_review and review_after_latest is None)
        if review_after_latest:
            review_currency = "current"
            state = (
                "evidence_sufficient"
                if review_after_latest["details"].get("disposition")
                == "evidence_sufficient"
                else "attention_required"
            )
        elif prior_review_exists:
            review_currency = "stale"
            state = (
                "stale"
                if evidence_status == "reference_recorded"
                else "attention_required"
            )
        else:
            review_currency = "not_reviewed"
            state = (
                "awaiting_review"
                if evidence_status == "reference_recorded"
                else "attention_required"
            )
        return {
            "state": state,
            "evidence_status": evidence_status,
            "review_currency": review_currency,
            "latest_preparation_at": latest_preparation["occurred_at"],
            "latest_review_at": latest_review["occurred_at"] if latest_review else None,
        }

    def _control_summary(self, control: dict[str, Any]) -> CloseControlSummary:
        integrity = self.repository.verify_control_chain(control["control_id"])
        if not integrity["valid"]:
            raise FinancialCloseIntegrityError(
                f"Financial close control {control['control_id']} failed its event-chain integrity check."
            )
        events = self.repository.list_events(control["cycle_id"], control["control_id"])
        if not events:
            raise FinancialCloseIntegrityError(
                f"Financial close control {control['control_id']} has no creation event."
            )
        projection = self._control_projection(events)
        latest = events[-1]
        snapshot, _ = self._cycle_template_lineage(control["cycle_id"])
        return CloseControlSummary(
            control_id=control["control_id"],
            cycle_id=control["cycle_id"],
            title=control["title"],
            description=control["description"],
            planned_date=control["planned_date"],
            preparer=CloseIdentity.model_validate(control["preparer"]),
            reviewer=CloseIdentity.model_validate(control["reviewer"]),
            state=projection["state"],
            evidence_status=projection["evidence_status"],
            review_currency=projection["review_currency"],
            version=latest["subject_version"],
            latest_preparation_at=projection["latest_preparation_at"],
            latest_review_at=projection["latest_review_at"],
            created_by=CloseIdentity.model_validate(control["created_by"]),
            created_at=control["created_at"],
            updated_at=latest["occurred_at"],
            template_lineage=self._control_template_lineage(control, snapshot),
        )

    @staticmethod
    def _cycle_readiness(counts: Counter[str], total: int) -> str:
        if total == 0 or counts["not_started"] == total:
            return "not_started"
        if counts["attention_required"] or counts["stale"]:
            return "attention_required"
        if counts["evidence_sufficient"] == total:
            return "evidence_ready"
        return "in_progress"

    def _cycle_summary(self, cycle: dict[str, Any]) -> CloseCycleSummary:
        cycle_integrity = self.repository.verify_cycle_chain(cycle["cycle_id"])
        if not cycle_integrity["valid"]:
            raise FinancialCloseIntegrityError(
                f"Financial close cycle {cycle['cycle_id']} failed its event-chain integrity check."
            )
        controls = [
            self._control_summary(control)
            for control in self.repository.list_controls(cycle["cycle_id"])
        ]
        states: Counter[str] = Counter(control.state for control in controls)
        all_events = self.repository.list_events(cycle["cycle_id"])
        counts = CloseControlCounts(
            total=len(controls),
            not_started=states["not_started"],
            awaiting_review=states["awaiting_review"],
            attention_required=states["attention_required"],
            evidence_sufficient=states["evidence_sufficient"],
            stale=states["stale"],
        )
        _, template_lineage = self._cycle_template_lineage(cycle["cycle_id"])
        return CloseCycleSummary(
            cycle_id=cycle["cycle_id"],
            entity_label=cycle["entity_label"],
            period_label=cycle["period_label"],
            period_start=cycle["period_start"],
            period_end=cycle["period_end"],
            target_completion_date=cycle["target_completion_date"],
            description=cycle["description"],
            created_by=CloseIdentity.model_validate(cycle["created_by"]),
            created_at=cycle["created_at"],
            version=max(1, len(all_events)),
            control_counts=counts,
            readiness=self._cycle_readiness(states, len(controls)),
            template_lineage=template_lineage,
        )

    def _cycle_detail(self, cycle: dict[str, Any]) -> CloseCycleDetail:
        summary = self._cycle_summary(cycle)
        raw_controls = self.repository.list_controls(cycle["cycle_id"])
        controls = [
            self._control_summary(control)
            for control in raw_controls
        ]
        snapshot = self.repository.get_cycle_template_snapshot(cycle["cycle_id"])
        if snapshot is not None:
            snapshotted_control_ids = {
                item.get("control_id")
                for item in snapshot["snapshot"].get("items", [])
            }
            current_control_ids = {control["control_id"] for control in raw_controls}
            if (
                None in snapshotted_control_ids
                or not snapshotted_control_ids.issubset(current_control_ids)
            ):
                raise FinancialCloseIntegrityError(
                    f"Financial close cycle {cycle['cycle_id']} is missing a control bound to its immutable template snapshot."
                )
        raw_events = self.repository.list_events(cycle["cycle_id"])
        evidence_sha256 = self.repository.sha256(
            {
                "cycle_definition_sha256": cycle["definition_sha256"],
                "control_definition_sha256": [
                    control["definition_sha256"]
                    for control in raw_controls
                ],
                "event_record_hashes": [event["record_hash"] for event in raw_events],
                "template_snapshot_sha256": (
                    snapshot["snapshot_sha256"] if snapshot else None
                ),
            }
        )
        return CloseCycleDetail(
            **summary.model_dump(),
            controls=controls,
            events=[self._event_model(event) for event in raw_events],
            evidence_sha256=evidence_sha256,
        )

    @staticmethod
    def _event_model(event: dict[str, Any]) -> CloseEvent:
        return CloseEvent(
            event_id=event["event_id"],
            cycle_id=event["cycle_id"],
            control_id=event["control_id"],
            event_type=event["event_type"],
            actor=CloseIdentity.model_validate(event["actor"]),
            occurred_at=event["occurred_at"],
            details=event["details"],
            previous_hash=event["previous_hash"],
            record_hash=event["record_hash"],
        )


financial_close_service = FinancialCloseService()


__all__ = [
    "FinancialCloseConflict",
    "FinancialCloseIntegrityError",
    "FinancialCloseNotFound",
    "FinancialClosePermissionDenied",
    "FinancialCloseService",
    "FinancialCloseValidationError",
    "financial_close_service",
]
