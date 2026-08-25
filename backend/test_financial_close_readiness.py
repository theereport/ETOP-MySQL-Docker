from __future__ import annotations

import ast
import sqlite3
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from modules.financial_close.repository import (
    FinancialCloseConflict,
    FinancialCloseIntegrityError,
    FinancialCloseRepository,
)
from modules.financial_close.schemas import (
    CloseControlCreate,
    CloseCycleCreate,
    ClosePreparationCreate,
    CloseReviewCreate,
    CloseTemplateCreate,
    CloseTemplateInstantiate,
    CloseTemplateItemCreate,
    CloseTemplateVersionCreate,
)
from modules.financial_close.service import (
    FinancialClosePermissionDenied,
    FinancialCloseService,
    FinancialCloseValidationError,
)
from modules.workflow_foundation.repository import WorkflowFoundationRepository
from modules.workflow_foundation.schemas import (
    BootstrapRequest,
    LoginRequest,
    UserCreate,
)
from modules.workflow_foundation.service import (
    WorkflowAuthenticationRequired,
    WorkflowFoundationService,
)


class FinancialCloseReadinessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp.name) / "financial-close.db"

        def connection_factory() -> sqlite3.Connection:
            return sqlite3.connect(
                self.database_path,
                timeout=30,
                check_same_thread=False,
            )

        self.connection_factory = connection_factory
        self.clock = lambda: datetime(2026, 8, 7, 23, 30, tzinfo=UTC)
        tokens = iter(f"local-token-{index}" for index in range(1, 100))
        self.workflow_repository = WorkflowFoundationRepository(
            connection_factory=connection_factory,
            clock=self.clock,
        )
        self.workflow_service = WorkflowFoundationService(
            repository=self.workflow_repository,
            clock=self.clock,
            token_factory=lambda: next(tokens),
        )
        self.coordinator = self.workflow_service.bootstrap(
            BootstrapRequest(
                username="coordinator",
                display_name="Close Coordinator",
                password="controlled-local-password",
            )
        )
        self.preparer = self._create_user("preparer")
        self.reviewer = self._create_user("reviewer")
        self.outsider = self._create_user("outsider")
        self.preparer_token = self._login("preparer")
        self.reviewer_token = self._login("reviewer")
        self.outsider_token = self._login("outsider")

        counters: dict[str, int] = {}

        def id_factory(prefix: str) -> str:
            counters[prefix] = counters.get(prefix, 0) + 1
            return f"{prefix}-test-{counters[prefix]}"

        self.repository = FinancialCloseRepository(
            connection_factory=connection_factory,
        )
        self.service = FinancialCloseService(
            repository=self.repository,
            workflow_service=self.workflow_service,
            clock=self.clock,
            id_factory=id_factory,
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _create_user(self, username: str):
        return self.workflow_service.create_user(
            self.coordinator.token,
            UserCreate(
                username=username,
                display_name=username.title(),
                password="controlled-user-password",
                role_ids=["workflow_observer"],
            ),
        )

    def _login(self, username: str) -> str:
        return self.workflow_service.login(
            LoginRequest(
                username=username,
                password="controlled-user-password",
            )
        ).token

    def _create_cycle(self, *, idempotency_key: str = "cycle-august-2026"):
        return self.service.create_cycle(
            self.coordinator.token,
            CloseCycleCreate(
                entity_label="K&M Tire (operator supplied)",
                period_label="August 2026",
                period_start="2026-08-01",
                period_end="2026-08-31",
                target_completion_date="2026-09-08",
                description="Local evidence-readiness coordination only.",
                idempotency_key=idempotency_key,
            ),
        )

    def _create_control(self, cycle_id: str, *, key: str = "control-bank-rec"):
        return self.service.create_control(
            self.coordinator.token,
            cycle_id,
            CloseControlCreate(
                title="Prepare bank reconciliation evidence",
                description="Reference the locally retained support.",
                planned_date="2026-09-03",
                preparer_user_id=self.preparer.user_id,
                reviewer_user_id=self.reviewer.user_id,
                idempotency_key=key,
            ),
        )

    def _template_items(self):
        return [
            CloseTemplateItemCreate(
                title="Prepare bank reconciliation evidence",
                description="Local source-reference planning draft.",
                planned_offset_days=-1,
                preparer_user_id=self.preparer.user_id,
                reviewer_user_id=self.reviewer.user_id,
            ),
            CloseTemplateItemCreate(
                title="Review cash clearing evidence",
                description="No accounting-policy or certification effect.",
                planned_offset_days=2,
                preparer_user_id=self.preparer.user_id,
                reviewer_user_id=self.reviewer.user_id,
            ),
        ]

    def _create_template(self, *, key: str = "template-month-end-local"):
        return self.service.create_template(
            self.coordinator.token,
            CloseTemplateCreate(
                title="Month-end local planning draft",
                description="User-authored planning structure only.",
                items=self._template_items(),
                idempotency_key=key,
            ),
        )

    def test_cycle_is_idempotent_immutable_and_never_represents_books_closed(self) -> None:
        cycle = self._create_cycle()
        self.assertEqual(cycle.entity_label, "K&M Tire (operator supplied)")
        self.assertEqual(cycle.readiness, "not_started")
        self.assertEqual(cycle.erp_period_state, "unavailable")
        self.assertEqual(cycle.close_effect, "none")
        self.assertEqual(cycle.control_counts.total, 0)
        self.assertEqual(len(cycle.events), 1)

        repeated = self._create_cycle()
        self.assertEqual(repeated.cycle_id, cycle.cycle_id)
        self.assertEqual(repeated.version, 1)
        with self.assertRaises(FinancialCloseConflict):
            self.service.create_cycle(
                self.coordinator.token,
                CloseCycleCreate(
                    entity_label="Different entity",
                    period_label="August 2026",
                    period_start="2026-08-01",
                    period_end="2026-08-31",
                    description="Conflicting reuse.",
                    idempotency_key="cycle-august-2026",
                ),
            )

        governance = self.service.governance_for_token(self.coordinator.token)
        self.assertEqual(governance.contract_version, "financial-close-readiness.v1")
        self.assertEqual(governance.erp_period_state, "unavailable")
        self.assertEqual(governance.books_close_state, "unavailable")
        self.assertFalse(governance.authority.erp_write)
        self.assertEqual(governance.authority.approval_effect, "none")
        self.assertEqual(governance.authority.posting_effect, "none")

        connection = self.connection_factory()
        try:
            connection.execute("PRAGMA foreign_keys = ON;")
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "UPDATE fc_cycles SET period_label = 'Changed' WHERE cycle_id = ?",
                    (cycle.cycle_id,),
                )
            connection.rollback()
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "DELETE FROM fc_cycles WHERE cycle_id = ?", (cycle.cycle_id,)
                )
        finally:
            connection.close()

    def test_only_coordinator_configures_cycles_and_distinct_active_users(self) -> None:
        with self.assertRaises(FinancialClosePermissionDenied):
            self.service.create_cycle(
                self.outsider_token,
                CloseCycleCreate(
                    entity_label="K&M Tire",
                    period_label="Blocked cycle",
                    period_start="2026-08-01",
                    period_end="2026-08-31",
                    description="",
                    idempotency_key="blocked-cycle-create",
                ),
            )
        cycle = self._create_cycle()
        with self.assertRaises(FinancialCloseValidationError):
            self.service.create_control(
                self.coordinator.token,
                cycle.cycle_id,
                CloseControlCreate(
                    title="Invalid same-person control",
                    description="",
                    preparer_user_id=self.preparer.user_id,
                    reviewer_user_id=self.preparer.user_id,
                    idempotency_key="same-user-control",
                ),
            )

        inactive = self._create_user("inactive_user")
        connection = self.connection_factory()
        try:
            connection.execute(
                "UPDATE wf_user_accounts SET status = 'inactive' WHERE user_id = ?",
                (inactive.user_id,),
            )
            connection.commit()
        finally:
            connection.close()
        with self.assertRaises(FinancialCloseValidationError):
            self.service.create_control(
                self.coordinator.token,
                cycle.cycle_id,
                CloseControlCreate(
                    title="Inactive preparer control",
                    description="",
                    preparer_user_id=inactive.user_id,
                    reviewer_user_id=self.reviewer.user_id,
                    idempotency_key="inactive-user-control",
                ),
            )

        control = self._create_control(cycle.cycle_id)
        self.assertEqual(control.state, "not_started")
        self.assertEqual(control.evidence_status, "not_recorded")
        self.assertEqual(control.review_currency, "not_reviewed")
        self.assertEqual(control.version, 1)
        self.assertNotEqual(control.preparer.user_id, control.reviewer.user_id)
        self.assertEqual(control.authority_effect, "none")
        self.assertEqual(control.close_effect, "none")

    def test_preparation_review_staleness_and_idempotency_are_controlled(self) -> None:
        cycle = self._create_cycle()
        control = self._create_control(cycle.cycle_id)
        with self.assertRaises(ValidationError):
            ClosePreparationCreate(
                disposition="reference_recorded",
                note="Reference omitted.",
                expected_control_version=1,
                idempotency_key="prep-no-reference",
            )
        with self.assertRaises(FinancialClosePermissionDenied):
            self.service.create_preparation(
                self.reviewer_token,
                cycle.cycle_id,
                control.control_id,
                ClosePreparationCreate(
                    disposition="reference_recorded",
                    evidence_reference="reconciliation://bank/august",
                    note="Wrong actor.",
                    expected_control_version=1,
                    idempotency_key="prep-wrong-actor",
                ),
            )

        preparation = ClosePreparationCreate(
            disposition="reference_recorded",
            evidence_reference="reconciliation://bank/august",
            note="Prepared and tied locally; reference is operator supplied.",
            expected_control_version=1,
            idempotency_key="prep-bank-august-v1",
        )
        awaiting = self.service.create_preparation(
            self.preparer_token,
            cycle.cycle_id,
            control.control_id,
            preparation,
        )
        self.assertEqual(awaiting.state, "awaiting_review")
        self.assertEqual(awaiting.evidence_status, "reference_recorded")
        self.assertEqual(awaiting.version, 2)

        with self.assertRaises(FinancialCloseConflict):
            self.service.create_preparation(
                self.preparer_token,
                cycle.cycle_id,
                control.control_id,
                ClosePreparationCreate(
                    disposition="reference_recorded",
                    evidence_reference="reconciliation://bank/stale-version",
                    note="A stale optimistic version must not append.",
                    expected_control_version=1,
                    idempotency_key="prep-bank-stale-version",
                ),
            )

        repeated = self.service.create_preparation(
            self.preparer_token,
            cycle.cycle_id,
            control.control_id,
            preparation,
        )
        self.assertEqual(repeated.version, 2)
        self.assertEqual(
            len(
                self.service.get_control_events(
                    self.coordinator.token, cycle.cycle_id, control.control_id
                ).items
            ),
            2,
        )
        with self.assertRaises(FinancialCloseConflict):
            self.service.create_preparation(
                self.preparer_token,
                cycle.cycle_id,
                control.control_id,
                preparation.model_copy(update={"note": "Conflicting key reuse."}),
            )

        reviewed = self.service.create_review(
            self.reviewer_token,
            cycle.cycle_id,
            control.control_id,
            CloseReviewCreate(
                disposition="evidence_sufficient",
                note="Evidence is sufficient for later close review only.",
                expected_control_version=2,
                idempotency_key="review-bank-august-v1",
            ),
        )
        self.assertEqual(reviewed.state, "evidence_sufficient")
        self.assertEqual(reviewed.review_currency, "current")
        self.assertEqual(reviewed.version, 3)

        stale = self.service.create_preparation(
            self.preparer_token,
            cycle.cycle_id,
            control.control_id,
            ClosePreparationCreate(
                disposition="reference_recorded",
                evidence_reference="reconciliation://bank/august-revised",
                note="Revised evidence reference supersedes the reviewed preparation.",
                expected_control_version=3,
                idempotency_key="prep-bank-august-v2",
            ),
        )
        self.assertEqual(stale.state, "stale")
        self.assertEqual(stale.review_currency, "stale")
        self.assertEqual(stale.version, 4)
        self.assertEqual(
            self.service.get_cycle(self.coordinator.token, cycle.cycle_id).readiness,
            "attention_required",
        )
        rereviewed = self.service.create_review(
            self.reviewer_token,
            cycle.cycle_id,
            control.control_id,
            CloseReviewCreate(
                disposition="evidence_sufficient",
                note="Reviewed the revised latest preparation, without closing books.",
                expected_control_version=4,
                idempotency_key="review-bank-august-v2",
            ),
        )
        self.assertEqual(rereviewed.state, "evidence_sufficient")
        self.assertEqual(rereviewed.review_currency, "current")

    def test_missing_or_unavailable_evidence_can_be_reviewed_but_not_sufficient(self) -> None:
        cycle = self._create_cycle()
        control = self._create_control(cycle.cycle_id)
        missing = self.service.create_preparation(
            self.preparer_token,
            cycle.cycle_id,
            control.control_id,
            ClosePreparationCreate(
                disposition="missing",
                note="Bank support has not yet been received.",
                expected_control_version=1,
                idempotency_key="prep-bank-missing",
            ),
        )
        self.assertEqual(missing.state, "attention_required")
        self.assertEqual(missing.evidence_status, "missing")
        with self.assertRaises(FinancialCloseConflict):
            self.service.create_review(
                self.reviewer_token,
                cycle.cycle_id,
                control.control_id,
                CloseReviewCreate(
                    disposition="evidence_sufficient",
                    note="Cannot be sufficient without a reference.",
                    expected_control_version=2,
                    idempotency_key="review-missing-sufficient",
                ),
            )

        reviewed = self.service.create_review(
            self.reviewer_token,
            cycle.cycle_id,
            control.control_id,
            CloseReviewCreate(
                disposition="needs_information",
                note="Obtain and reference the missing support.",
                expected_control_version=2,
                idempotency_key="review-missing-needs-info",
            ),
        )
        self.assertEqual(reviewed.state, "attention_required")
        self.assertEqual(reviewed.review_currency, "current")
        self.assertEqual(reviewed.version, 3)

        unavailable = self.service.create_preparation(
            self.preparer_token,
            cycle.cycle_id,
            control.control_id,
            ClosePreparationCreate(
                disposition="unavailable",
                note="Source system is unavailable; no source fact is inferred.",
                expected_control_version=3,
                idempotency_key="prep-bank-unavailable",
            ),
        )
        self.assertEqual(unavailable.state, "attention_required")
        self.assertEqual(unavailable.review_currency, "stale")
        deferred = self.service.create_review(
            self.reviewer_token,
            cycle.cycle_id,
            control.control_id,
            CloseReviewCreate(
                disposition="deferred",
                note="Defer evidence review until the source is restored.",
                expected_control_version=4,
                idempotency_key="review-bank-deferred",
            ),
        )
        self.assertEqual(deferred.state, "attention_required")
        self.assertEqual(deferred.review_currency, "current")

    def test_preparer_can_append_a_correction_before_review(self) -> None:
        cycle = self._create_cycle()
        control = self._create_control(cycle.cycle_id)
        first = self.service.create_preparation(
            self.preparer_token,
            cycle.cycle_id,
            control.control_id,
            ClosePreparationCreate(
                disposition="reference_recorded",
                evidence_reference="report://mistyped-reference",
                note="Initial reference.",
                expected_control_version=1,
                idempotency_key="prep-reference-initial",
            ),
        )
        self.assertEqual(first.state, "awaiting_review")
        corrected = self.service.create_preparation(
            self.preparer_token,
            cycle.cycle_id,
            control.control_id,
            ClosePreparationCreate(
                disposition="reference_recorded",
                evidence_reference="report://correct-reference",
                note="Append-only correction before review.",
                expected_control_version=2,
                idempotency_key="prep-reference-corrected",
            ),
        )
        self.assertEqual(corrected.state, "awaiting_review")
        self.assertEqual(corrected.version, 3)
        reviewed = self.service.create_review(
            self.reviewer_token,
            cycle.cycle_id,
            control.control_id,
            CloseReviewCreate(
                disposition="evidence_sufficient",
                note="Reviewed the corrected latest preparation.",
                expected_control_version=3,
                idempotency_key="review-corrected-reference",
            ),
        )
        self.assertEqual(reviewed.state, "evidence_sufficient")
        events = self.repository.list_events(cycle.cycle_id, control.control_id)
        self.assertEqual(
            events[-1]["details"]["reviewed_preparation_event_id"],
            events[-2]["event_id"],
        )

    def test_cycle_chain_and_redundant_identity_fields_are_hash_bound(self) -> None:
        cycle = self._create_cycle()
        control = self._create_control(cycle.cycle_id)
        connection = self.connection_factory()
        try:
            connection.execute("DROP TRIGGER fc_cycles_no_update")
            connection.execute("DROP TRIGGER fc_controls_no_update")
            connection.execute("DROP TRIGGER fc_events_no_update")

            connection.execute(
                "UPDATE fc_cycles SET created_by_user_id = ? WHERE cycle_id = ?",
                (self.outsider.user_id, cycle.cycle_id),
            )
            connection.commit()
            with self.assertRaises(FinancialCloseIntegrityError):
                self.repository.get_cycle(cycle.cycle_id)
            connection.execute("DROP TRIGGER IF EXISTS fc_cycles_no_update")
            connection.execute(
                "UPDATE fc_cycles SET created_by_user_id = ? WHERE cycle_id = ?",
                (self.coordinator.user.user_id, cycle.cycle_id),
            )

            connection.execute(
                "UPDATE fc_cycles SET idempotency_key = 'tampered-cycle-key' WHERE cycle_id = ?",
                (cycle.cycle_id,),
            )
            connection.commit()
            with self.assertRaises(FinancialCloseIntegrityError):
                self.repository.get_cycle(cycle.cycle_id)
            connection.execute("DROP TRIGGER IF EXISTS fc_cycles_no_update")
            connection.execute(
                "UPDATE fc_cycles SET idempotency_key = 'cycle-august-2026' WHERE cycle_id = ?",
                (cycle.cycle_id,),
            )

            original_cycle_request = connection.execute(
                "SELECT request_sha256 FROM fc_cycles WHERE cycle_id = ?",
                (cycle.cycle_id,),
            ).fetchone()[0]
            connection.execute(
                "UPDATE fc_cycles SET request_sha256 = ? WHERE cycle_id = ?",
                ("f" * 64, cycle.cycle_id),
            )
            connection.commit()
            with self.assertRaises(FinancialCloseIntegrityError):
                self.repository.get_cycle(cycle.cycle_id)
            connection.execute("DROP TRIGGER IF EXISTS fc_cycles_no_update")
            connection.execute(
                "UPDATE fc_cycles SET request_sha256 = ? WHERE cycle_id = ?",
                (original_cycle_request, cycle.cycle_id),
            )

            for column, replacement, original in (
                (
                    "preparer_user_id",
                    self.outsider.user_id,
                    self.preparer.user_id,
                ),
                (
                    "reviewer_user_id",
                    self.outsider.user_id,
                    self.reviewer.user_id,
                ),
                (
                    "created_by_user_id",
                    self.outsider.user_id,
                    self.coordinator.user.user_id,
                ),
            ):
                connection.execute("DROP TRIGGER IF EXISTS fc_controls_no_update")
                connection.execute(
                    f"UPDATE fc_control_items SET {column} = ? WHERE control_id = ?",
                    (replacement, control.control_id),
                )
                connection.commit()
                with self.assertRaises(FinancialCloseIntegrityError):
                    self.repository.get_control(cycle.cycle_id, control.control_id)
                connection.execute("DROP TRIGGER IF EXISTS fc_controls_no_update")
                connection.execute(
                    f"UPDATE fc_control_items SET {column} = ? WHERE control_id = ?",
                    (original, control.control_id),
                )

            original_control_request = connection.execute(
                "SELECT request_sha256 FROM fc_control_items WHERE control_id = ?",
                (control.control_id,),
            ).fetchone()[0]
            connection.execute("DROP TRIGGER IF EXISTS fc_controls_no_update")
            connection.execute(
                "UPDATE fc_control_items SET request_sha256 = ? WHERE control_id = ?",
                ("e" * 64, control.control_id),
            )
            connection.commit()
            with self.assertRaises(FinancialCloseIntegrityError):
                self.repository.get_control(cycle.cycle_id, control.control_id)
            connection.execute("DROP TRIGGER IF EXISTS fc_controls_no_update")
            connection.execute(
                "UPDATE fc_control_items SET request_sha256 = ? WHERE control_id = ?",
                (original_control_request, control.control_id),
            )

            connection.execute("DROP TRIGGER IF EXISTS fc_events_no_update")
            connection.execute(
                """
                UPDATE fc_control_events SET actor_user_id = ?
                WHERE cycle_id = ? AND control_id IS NULL
                """,
                (self.outsider.user_id, cycle.cycle_id),
            )
            connection.commit()
            cycle_integrity = self.repository.verify_cycle_chain(cycle.cycle_id)
            self.assertFalse(cycle_integrity["valid"])
            with self.assertRaises(FinancialCloseIntegrityError):
                self.service.list_cycles(self.coordinator.token)
            with self.assertRaises(FinancialCloseIntegrityError):
                self.service.create_control(
                    self.coordinator.token,
                    cycle.cycle_id,
                    CloseControlCreate(
                        title="Control beneath a tampered cycle",
                        description="Must not be persisted.",
                        preparer_user_id=self.preparer.user_id,
                        reviewer_user_id=self.reviewer.user_id,
                        idempotency_key="control-under-tampered-cycle",
                    ),
                )
            connection.execute("DROP TRIGGER IF EXISTS fc_events_no_update")
            connection.execute(
                """
                UPDATE fc_control_events SET actor_user_id = ?
                WHERE control_id = ? AND subject_version = 1
                """,
                (self.outsider.user_id, control.control_id),
            )
            connection.commit()
            control_integrity = self.repository.verify_control_chain(control.control_id)
            self.assertFalse(control_integrity["valid"])
        finally:
            connection.close()

    def test_events_are_append_only_hash_chained_and_tampering_is_detected(self) -> None:
        cycle = self._create_cycle()
        control = self._create_control(cycle.cycle_id)
        self.service.create_preparation(
            self.preparer_token,
            cycle.cycle_id,
            control.control_id,
            ClosePreparationCreate(
                disposition="reference_recorded",
                evidence_reference="report://close-support/1",
                note="Prepared.",
                expected_control_version=1,
                idempotency_key="prep-chain-check",
            ),
        )
        events = self.service.get_control_events(
            self.coordinator.token, cycle.cycle_id, control.control_id
        )
        self.assertTrue(events.integrity.valid)
        self.assertEqual(events.integrity.checked_records, 2)
        self.assertEqual(events.items[1].previous_hash, events.items[0].record_hash)

        connection = self.connection_factory()
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "DELETE FROM fc_control_events WHERE control_id = ?",
                    (control.control_id,),
                )
            connection.rollback()
            connection.execute("DROP TRIGGER fc_events_no_update")
            connection.execute(
                """
                UPDATE fc_control_events
                SET details_json = '{"tampered":true}'
                WHERE control_id = ? AND subject_version = 2
                """,
                (control.control_id,),
            )
            connection.commit()
        finally:
            connection.close()
        broken = self.repository.verify_control_chain(control.control_id)
        self.assertFalse(broken["valid"])
        self.assertIsNotNone(broken["first_invalid_event_id"])
        with self.assertRaises(FinancialCloseIntegrityError):
            self.service.get_cycle(self.coordinator.token, cycle.cycle_id)

    def test_inactive_authenticated_session_is_rejected_directly(self) -> None:
        cycle = self._create_cycle()
        connection = self.connection_factory()
        try:
            connection.execute(
                "UPDATE wf_user_accounts SET status = 'inactive' WHERE user_id IN (?, ?)",
                (self.outsider.user_id, self.coordinator.user.user_id),
            )
            connection.commit()
        finally:
            connection.close()
        with self.assertRaises(WorkflowAuthenticationRequired):
            self.service.list_cycles(self.outsider_token)
        with self.assertRaises(WorkflowAuthenticationRequired):
            self.service.create_cycle(
                self.coordinator.token,
                CloseCycleCreate(
                    entity_label="K&M Tire",
                    period_label="Inactive coordinator",
                    period_start="2026-09-01",
                    period_end="2026-09-30",
                    description="",
                    idempotency_key="inactive-coordinator-cycle",
                ),
            )
        with self.assertRaises(WorkflowAuthenticationRequired):
            self.service.create_control(
                self.coordinator.token,
                cycle.cycle_id,
                CloseControlCreate(
                    title="Inactive coordinator control",
                    description="",
                    preparer_user_id=self.preparer.user_id,
                    reviewer_user_id=self.reviewer.user_id,
                    idempotency_key="inactive-coordinator-control",
                ),
            )

    def test_templates_are_local_immutable_versioned_drafts_and_do_not_auto_create_cycles(self) -> None:
        self.assertEqual(self.service.list_cycles(self.coordinator.token).total, 0)
        with self.assertRaises(FinancialClosePermissionDenied):
            self.service.create_template(
                self.outsider_token,
                CloseTemplateCreate(
                    title="Blocked planning template",
                    description="",
                    items=self._template_items(),
                    idempotency_key="blocked-template-create",
                ),
            )

        template = self._create_template()
        self.assertEqual(template.latest_version, 1)
        self.assertEqual(template.version_count, 1)
        self.assertEqual(template.item_count, 2)
        self.assertEqual(
            template.status,
            "local_user_authored_planning_draft",
        )
        self.assertEqual(template.policy_effect, "none")
        self.assertEqual(template.automation_effect, "none")
        self.assertTrue(template.integrity.valid)
        self.assertEqual(self.service.list_cycles(self.coordinator.token).total, 0)

        repeated = self._create_template()
        self.assertEqual(repeated.template_id, template.template_id)
        self.assertEqual(repeated.latest_version, 1)

        version_one_hash = template.versions[0].version_sha256
        version_two = self.service.create_template_version(
            self.coordinator.token,
            template.template_id,
            CloseTemplateVersionCreate(
                title="Month-end local planning draft",
                description="Second immutable local draft.",
                change_note="Move the cash-clearing planning offset only.",
                items=[
                    self._template_items()[0],
                    self._template_items()[1].model_copy(
                        update={"planned_offset_days": 3}
                    ),
                ],
                expected_latest_version=1,
                idempotency_key="template-month-end-v2",
            ),
        )
        self.assertEqual(version_two.latest_version, 2)
        self.assertEqual(version_two.versions[0].version_sha256, version_one_hash)
        self.assertEqual(
            version_two.versions[1].previous_version_sha256,
            version_one_hash,
        )
        self.assertNotEqual(
            version_two.versions[1].version_sha256,
            version_one_hash,
        )
        with self.assertRaises(FinancialCloseConflict):
            self.service.create_template_version(
                self.coordinator.token,
                template.template_id,
                CloseTemplateVersionCreate(
                    title="Stale template edit",
                    description="",
                    change_note="Must fail against stale expected version.",
                    items=self._template_items(),
                    expected_latest_version=1,
                    idempotency_key="template-stale-version-attempt",
                ),
            )

        connection = self.connection_factory()
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    """
                    UPDATE fc_template_versions SET title = 'Changed'
                    WHERE template_id = ? AND version = 1
                    """,
                    (template.template_id,),
                )
            connection.rollback()
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "DELETE FROM fc_template_items WHERE template_id = ?",
                    (template.template_id,),
                )
        finally:
            connection.close()

    def test_manual_template_instantiation_snapshots_exact_version_and_dates(self) -> None:
        template = self._create_template()
        request = CloseTemplateInstantiate(
            entity_label="K&M Tire (operator supplied)",
            period_label="September 2026",
            period_start="2026-09-01",
            period_end="2026-09-30",
            calendar_anchor_date="2026-10-05",
            target_completion_date="2026-10-08",
            description="Manual instantiation from an exact local draft.",
            idempotency_key="instantiate-september-2026",
        )
        cycle = self.service.instantiate_template(
            self.coordinator.token,
            template.template_id,
            1,
            request,
        )
        self.assertEqual(cycle.control_counts.total, 2)
        self.assertEqual(cycle.readiness, "not_started")
        self.assertEqual(cycle.erp_period_state, "unavailable")
        self.assertIsNotNone(cycle.template_lineage)
        self.assertEqual(cycle.template_lineage.template_version, 1)
        self.assertEqual(
            cycle.template_lineage.template_version_sha256,
            template.versions[0].version_sha256,
        )
        self.assertEqual(
            cycle.template_lineage.planning_date_rule,
            "calendar_anchor_plus_offset_days",
        )
        self.assertEqual(
            [control.planned_date.isoformat() for control in cycle.controls],
            ["2026-10-04", "2026-10-07"],
        )
        self.assertTrue(all(control.template_lineage for control in cycle.controls))
        self.assertEqual(
            [control.template_lineage.planned_offset_days for control in cycle.controls],
            [-1, 2],
        )

        repeated = self.service.instantiate_template(
            self.coordinator.token,
            template.template_id,
            1,
            request,
        )
        self.assertEqual(repeated.cycle_id, cycle.cycle_id)
        self.assertEqual(self.service.list_cycles(self.coordinator.token).total, 1)

        changed = self.service.create_template_version(
            self.coordinator.token,
            template.template_id,
            CloseTemplateVersionCreate(
                title="Changed future local draft",
                description="Existing cycle must stay on version one.",
                change_note="Change a future control title and date offset.",
                items=[
                    self._template_items()[0].model_copy(
                        update={
                            "title": "Future version bank support",
                            "planned_offset_days": 9,
                        }
                    )
                ],
                expected_latest_version=1,
                idempotency_key="template-future-version",
            ),
        )
        self.assertEqual(changed.latest_version, 2)
        preserved = self.service.get_cycle(
            self.coordinator.token,
            cycle.cycle_id,
        )
        self.assertEqual(preserved.template_lineage.template_version, 1)
        self.assertEqual(
            [control.title for control in preserved.controls],
            [
                "Prepare bank reconciliation evidence",
                "Review cash clearing evidence",
            ],
        )
        self.assertEqual(
            [control.planned_date.isoformat() for control in preserved.controls],
            ["2026-10-04", "2026-10-07"],
        )

        first_control = preserved.controls[0]
        prepared = self.service.create_preparation(
            self.preparer_token,
            preserved.cycle_id,
            first_control.control_id,
            ClosePreparationCreate(
                disposition="reference_recorded",
                evidence_reference="local://september-bank-support",
                note="Increment 1 evidence behavior remains available.",
                expected_control_version=1,
                idempotency_key="template-cycle-preparation",
            ),
        )
        self.assertEqual(prepared.state, "awaiting_review")
        reviewed = self.service.create_review(
            self.reviewer_token,
            preserved.cycle_id,
            first_control.control_id,
            CloseReviewCreate(
                disposition="evidence_sufficient",
                note="Local evidence review only.",
                expected_control_version=2,
                idempotency_key="template-cycle-review",
            ),
        )
        self.assertEqual(reviewed.state, "evidence_sufficient")

    def test_template_and_snapshot_history_is_append_only_and_tamper_evident(self) -> None:
        template = self._create_template()
        cycle = self.service.instantiate_template(
            self.coordinator.token,
            template.template_id,
            1,
            CloseTemplateInstantiate(
                entity_label="K&M Tire",
                period_label="October 2026",
                period_start="2026-10-01",
                period_end="2026-10-31",
                calendar_anchor_date="2026-11-04",
                description="",
                idempotency_key="instantiate-october-2026",
            ),
        )
        current = self.service.get_template(
            self.coordinator.token,
            template.template_id,
        )
        self.assertTrue(current.integrity.valid)
        self.assertEqual(
            [event.event_type for event in current.events],
            ["template_created", "cycle_instantiated"],
        )

        connection = self.connection_factory()
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    """
                    UPDATE fc_cycle_template_snapshots
                    SET calendar_anchor_date = '2026-11-05'
                    WHERE cycle_id = ?
                    """,
                    (cycle.cycle_id,),
                )
            connection.rollback()
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "DELETE FROM fc_template_events WHERE template_id = ?",
                    (template.template_id,),
                )
            connection.rollback()
            connection.execute("DROP TRIGGER fc_cycle_template_snapshots_no_update")
            connection.execute(
                """
                UPDATE fc_cycle_template_snapshots
                SET snapshot_json = '{"tampered":true}'
                WHERE cycle_id = ?
                """,
                (cycle.cycle_id,),
            )
            connection.commit()
        finally:
            connection.close()
        with self.assertRaises(FinancialCloseIntegrityError):
            self.service.get_cycle(self.coordinator.token, cycle.cycle_id)

    def test_inactive_template_assignment_blocks_instantiation_without_partial_cycle(self) -> None:
        template = self._create_template()
        connection = self.connection_factory()
        try:
            connection.execute(
                "UPDATE wf_user_accounts SET status = 'inactive' WHERE user_id = ?",
                (self.preparer.user_id,),
            )
            connection.commit()
        finally:
            connection.close()
        with self.assertRaises(FinancialCloseValidationError):
            self.service.instantiate_template(
                self.coordinator.token,
                template.template_id,
                1,
                CloseTemplateInstantiate(
                    entity_label="K&M Tire",
                    period_label="November 2026",
                    period_start="2026-11-01",
                    period_end="2026-11-30",
                    calendar_anchor_date="2026-12-04",
                    description="",
                    idempotency_key="blocked-inactive-instantiation",
                ),
            )
        self.assertEqual(self.service.list_cycles(self.coordinator.token).total, 0)

    def test_instantiation_revalidates_active_identities_inside_atomic_write(self) -> None:
        template = self._create_template(key="template-identity-race")
        original = self.repository.instantiate_template_cycle

        def deactivate_then_begin(**kwargs):
            connection = self.connection_factory()
            try:
                connection.execute(
                    "UPDATE wf_user_accounts SET status = 'inactive' WHERE user_id = ?",
                    (self.preparer.user_id,),
                )
                connection.commit()
            finally:
                connection.close()
            return original(**kwargs)

        self.repository.instantiate_template_cycle = deactivate_then_begin
        with self.assertRaises(FinancialCloseConflict):
            self.service.instantiate_template(
                self.coordinator.token,
                template.template_id,
                1,
                CloseTemplateInstantiate(
                    entity_label="K&M Tire",
                    period_label="Identity race",
                    period_start="2026-11-01",
                    period_end="2026-11-30",
                    calendar_anchor_date="2026-12-04",
                    description="",
                    idempotency_key="blocked-identity-race",
                ),
            )
        self.assertEqual(self.service.list_cycles(self.coordinator.token).total, 0)

    def test_snapshot_read_rejects_rehashed_item_binding_forgery(self) -> None:
        template = self._create_template(key="template-snapshot-binding")
        cycle = self.service.instantiate_template(
            self.coordinator.token,
            template.template_id,
            1,
            CloseTemplateInstantiate(
                entity_label="K&M Tire",
                period_label="Snapshot binding",
                period_start="2026-11-01",
                period_end="2026-11-30",
                calendar_anchor_date="2026-12-04",
                description="",
                idempotency_key="snapshot-binding-cycle",
            ),
        )
        snapshot = self.repository.get_cycle_template_snapshot(cycle.cycle_id)
        snapshot["snapshot"]["items"][0]["template_item_sha256"] = "f" * 64
        snapshot["snapshot_sha256"] = (
            self.repository.cycle_template_snapshot_sha256(snapshot)
        )

        connection = self.connection_factory()
        connection.row_factory = sqlite3.Row
        try:
            event_row = connection.execute(
                """
                SELECT * FROM fc_template_events
                WHERE template_id = ? AND event_type = 'cycle_instantiated'
                """,
                (template.template_id,),
            ).fetchone()
            event = self.repository._decode_template_event(event_row)
            event["details"]["snapshot_sha256"] = snapshot["snapshot_sha256"]
            event_hash = self.repository.sha256(
                self.repository._template_event_basis(event)
            )
            connection.execute(
                "DROP TRIGGER fc_cycle_template_snapshots_no_update"
            )
            connection.execute("DROP TRIGGER fc_template_events_no_update")
            connection.execute(
                """
                UPDATE fc_cycle_template_snapshots
                SET snapshot_json = ?, snapshot_sha256 = ? WHERE cycle_id = ?
                """,
                (
                    self.repository.canonical_json(snapshot["snapshot"]),
                    snapshot["snapshot_sha256"],
                    cycle.cycle_id,
                ),
            )
            connection.execute(
                """
                UPDATE fc_template_events
                SET details_json = ?, record_hash = ? WHERE event_id = ?
                """,
                (
                    self.repository.canonical_json(event["details"]),
                    event_hash,
                    event["event_id"],
                ),
            )
            connection.commit()
        finally:
            connection.close()

        with self.assertRaises(FinancialCloseIntegrityError):
            self.service.get_cycle(self.coordinator.token, cycle.cycle_id)

    def test_template_integrity_rejects_deleted_valid_chain_tail(self) -> None:
        template = self._create_template(key="template-tail-binding")
        self.service.create_template_version(
            self.coordinator.token,
            template.template_id,
            CloseTemplateVersionCreate(
                title="Second immutable version",
                description="",
                change_note="Append a second version for tail validation.",
                items=self._template_items(),
                expected_latest_version=1,
                idempotency_key="template-tail-version-two",
            ),
        )
        connection = self.connection_factory()
        try:
            connection.execute("DROP TRIGGER fc_template_events_no_delete")
            connection.execute(
                """
                DELETE FROM fc_template_events
                WHERE template_id = ? AND event_type = 'template_version_created'
                """,
                (template.template_id,),
            )
            connection.commit()
        finally:
            connection.close()

        with self.assertRaises(FinancialCloseIntegrityError):
            self.service.get_template(
                self.coordinator.token,
                template.template_id,
            )

    def test_router_exposes_only_bounded_readiness_and_manual_planning_operations(self) -> None:
        api_path = Path(__file__).parent / "modules" / "financial_close" / "router.py"
        api_tree = ast.parse(api_path.read_text(encoding="utf-8"))
        actual: set[tuple[str, str]] = set()
        for node in ast.walk(api_tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                if not (
                    isinstance(decorator, ast.Call)
                    and isinstance(decorator.func, ast.Attribute)
                    and isinstance(decorator.func.value, ast.Name)
                    and decorator.func.value.id == "router"
                    and decorator.func.attr in {"get", "post", "put", "patch", "delete"}
                    and decorator.args
                    and isinstance(decorator.args[0], ast.Constant)
                    and isinstance(decorator.args[0].value, str)
                ):
                    continue
                actual.add(
                    (
                        f"/api/v1/financial-close{decorator.args[0].value}",
                        decorator.func.attr.upper(),
                    )
                )
        expected = {
            ("/api/v1/financial-close/governance", "GET"),
            ("/api/v1/financial-close/templates", "GET"),
            ("/api/v1/financial-close/templates", "POST"),
            ("/api/v1/financial-close/templates/{template_id}", "GET"),
            (
                "/api/v1/financial-close/templates/{template_id}/versions",
                "POST",
            ),
            (
                "/api/v1/financial-close/templates/{template_id}/versions/{template_version}/instantiate",
                "POST",
            ),
            ("/api/v1/financial-close/cycles", "GET"),
            ("/api/v1/financial-close/cycles", "POST"),
            ("/api/v1/financial-close/cycles/{cycle_id}", "GET"),
            (
                "/api/v1/financial-close/cycles/{cycle_id}/controls",
                "POST",
            ),
            (
                "/api/v1/financial-close/cycles/{cycle_id}/controls/{control_id}/preparations",
                "POST",
            ),
            (
                "/api/v1/financial-close/cycles/{cycle_id}/controls/{control_id}/reviews",
                "POST",
            ),
            (
                "/api/v1/financial-close/cycles/{cycle_id}/controls/{control_id}/events",
                "GET",
            ),
        }
        self.assertEqual(actual, expected)
        route_text = " ".join(path for path, _method in actual).lower()
        for forbidden in (
            "approve",
            "certify",
            "close-books",
            "close-period",
            "reopen",
            "post",
            "notify",
            "automate",
            "erp",
            "ledger",
        ):
            self.assertNotIn(forbidden, route_text)


if __name__ == "__main__":
    unittest.main()
