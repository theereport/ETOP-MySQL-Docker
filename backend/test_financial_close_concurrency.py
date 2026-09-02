from __future__ import annotations

import tempfile
import threading
import unittest
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import create_engine

from modules.financial_close.repository import (
    FinancialCloseConflict,
    FinancialCloseRepository,
)
from modules.financial_close.schemas import (
    CloseControlCreate,
    CloseCycleCreate,
    ClosePreparationCreate,
)
from modules.financial_close.service import FinancialCloseService
from modules.workflow_foundation.repository import WorkflowFoundationRepository
from modules.workflow_foundation.schemas import BootstrapRequest, LoginRequest, UserCreate
from modules.workflow_foundation.service import WorkflowFoundationService


class ControlEventHashChainConcurrencyTests(unittest.TestCase):
    """financial_close's audit hash-chain append (append_control_event) had
    no row-locking on its "read the prior chain tail" query, unlike
    payment_notes' identical hash-chain pattern (see
    tests/payment_notes/test_repository.py's
    test_two_route_activation_writers_form_one_valid_serial_chain for the
    established precedent this mirrors). Two concurrent appends to the same
    control could otherwise both compute the same next subject_version and
    previous_hash."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp.name) / "financial-close-concurrency.db"
        self.addCleanup(self.temp.cleanup)
        self.engine = create_engine(
            f"sqlite:///{self.database_path}",
            connect_args={"timeout": 10, "check_same_thread": False},
        )
        self.addCleanup(self.engine.dispose)
        self.clock = lambda: datetime(2026, 8, 7, 23, 30, tzinfo=UTC)
        tokens = iter(f"local-token-{index}" for index in range(1, 100))
        self.workflow_repository = WorkflowFoundationRepository(
            engine=self.engine,
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
        self.preparer = self.workflow_service.create_user(
            self.coordinator.token,
            UserCreate(
                username="preparer",
                display_name="Preparer",
                password="controlled-user-password",
            ),
        )
        self.reviewer = self.workflow_service.create_user(
            self.coordinator.token,
            UserCreate(
                username="reviewer",
                display_name="Reviewer",
                password="controlled-user-password",
            ),
        )
        self.preparer_token = self.workflow_service.login(
            LoginRequest(username="preparer", password="controlled-user-password")
        ).token

        counters: dict[str, int] = {}

        def id_factory(prefix: str) -> str:
            counters[prefix] = counters.get(prefix, 0) + 1
            return f"{prefix}-test-{counters[prefix]}"

        self.repository = FinancialCloseRepository(engine=self.engine)
        self.service = FinancialCloseService(
            repository=self.repository,
            workflow_service=self.workflow_service,
            clock=self.clock,
            id_factory=id_factory,
        )
        cycle = self.service.create_cycle(
            self.coordinator.token,
            CloseCycleCreate(
                entity_label="K&M Tire (operator supplied)",
                period_label="August 2026",
                period_start="2026-08-01",
                period_end="2026-08-31",
                target_completion_date="2026-09-08",
                description="Local evidence-readiness coordination only.",
                idempotency_key="cycle-concurrency",
            ),
        )
        self.cycle_id = cycle.cycle_id
        control = self.service.create_control(
            self.coordinator.token,
            self.cycle_id,
            CloseControlCreate(
                title="Prepare bank reconciliation evidence",
                description="Reference the locally retained support.",
                planned_date="2026-09-03",
                preparer_user_id=self.preparer.user_id,
                reviewer_user_id=self.reviewer.user_id,
                idempotency_key="control-concurrency",
            ),
        )
        self.control_id = control.control_id

    def test_two_concurrent_preparation_events_resolve_to_one_winner_and_a_clean_conflict(
        self,
    ) -> None:
        # Both racers act as if they loaded the control at version 1 (the
        # state right after creation) and submit concurrently - the
        # realistic scenario of two preparers' browser tabs both open to
        # the same not-yet-updated control. Exactly one must win; the
        # other must see a clean FinancialCloseConflict, never a raw
        # IntegrityError/500 from an un-serialized read of the chain tail.
        barrier = threading.Barrier(2)
        outcomes: list[str | Exception] = []
        lock = threading.Lock()

        def record_preparation(idempotency_key: str) -> None:
            try:
                barrier.wait()
                self.service.create_preparation(
                    self.preparer_token,
                    self.cycle_id,
                    self.control_id,
                    ClosePreparationCreate(
                        disposition="reference_recorded",
                        evidence_reference="local-note",
                        note=f"Concurrent write {idempotency_key}",
                        expected_control_version=1,
                        idempotency_key=idempotency_key,
                    ),
                )
                with lock:
                    outcomes.append("success")
            except FinancialCloseConflict as exc:
                with lock:
                    outcomes.append(exc)
            except Exception as exc:  # pragma: no cover - asserted below
                with lock:
                    outcomes.append(exc)

        threads = [
            threading.Thread(
                target=record_preparation, args=(f"preparation-{i}",)
            )
            for i in range(2)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        successes = [item for item in outcomes if item == "success"]
        conflicts = [
            item for item in outcomes if isinstance(item, FinancialCloseConflict)
        ]
        unexpected = [
            item
            for item in outcomes
            if item != "success" and not isinstance(item, FinancialCloseConflict)
        ]
        self.assertEqual(unexpected, [])
        self.assertEqual(len(successes), 1, outcomes)
        self.assertEqual(len(conflicts), 1, outcomes)

        integrity = self.repository.verify_control_chain(self.control_id)
        self.assertTrue(integrity["valid"], integrity)
        self.assertEqual(integrity["checked_records"], 2)


if __name__ == "__main__":
    unittest.main()
