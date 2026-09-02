from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import unquote, urlsplit

from sqlalchemy import create_engine

from modules.workflow_foundation.access_policy import required_modules_for_path
from modules.workflow_foundation.repository import (
    WorkflowFoundationConflict,
    WorkflowFoundationNotFound,
    WorkflowFoundationRepository,
)
from modules.workflow_foundation.schemas import (
    AdminPasswordSet,
    BootstrapRequest,
    InvitationActivationRequest,
    InvitationCreate,
    InvitationTokenRequest,
    InvitationRevokeRequest,
    LoginRequest,
    ModuleAccessReplace,
    PasswordResetActivationRequest,
    PasswordResetTokenRequest,
    TaskAssignmentCreate,
    TaskCreate,
    TaskTransitionCreate,
    UserCreate,
    UserStatusChange,
)
from modules.workflow_foundation.service import (
    WorkflowAuthenticationRequired,
    WorkflowFoundationService,
    WorkflowPermissionDenied,
)


class WorkflowFoundationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp.name) / "workflow-foundation.db"
        self.engine = create_engine(f"sqlite:///{self.database_path}")

        self.repository = WorkflowFoundationRepository(
            engine=self.engine,
            clock=lambda: datetime(2026, 8, 7, 17, 30, tzinfo=UTC),
        )
        self.service = WorkflowFoundationService(
            repository=self.repository,
            clock=lambda: datetime(2026, 8, 7, 17, 30, tzinfo=UTC),
        )
        self.coordinator = self.service.bootstrap(
            BootstrapRequest(
                username="josh",
                display_name="Test Coordinator One",
                password="controlled-local-password",
            )
        )

    def tearDown(self) -> None:
        self.engine.dispose()
        self.temp.cleanup()

    def create_user(
        self,
        username: str,
        role_id: str,
    ):
        return self.service.create_user(
            self.coordinator.token,
            UserCreate(
                username=username,
                display_name=username.replace("_", " ").title(),
                password="controlled-user-password",
                role_ids=[role_id],
            ),
        )

    def login(self, username: str) -> str:
        return self.service.login(
            LoginRequest(
                username=username,
                password="controlled-user-password",
            )
        ).token

    def test_bootstrap_authenticates_local_account_without_authority(self) -> None:
        status = self.service.bootstrap_status()
        self.assertFalse(status.bootstrap_required)
        self.assertEqual(status.account_count, 1)
        self.assertEqual(
            self.coordinator.user.authentication_assurance,
            "local_credential",
        )
        self.assertEqual(self.coordinator.user.authority_status, "not_configured")
        self.assertEqual(
            self.coordinator.user.roles[0].authority_effect,
            "none",
        )
        self.assertFalse(self.coordinator.user.roles[0].decision_authority)
        with self.assertRaises(WorkflowFoundationConflict):
            self.service.bootstrap(
                BootstrapRequest(
                    username="second",
                    display_name="Second User",
                    password="controlled-local-password",
                )
            )

    def test_login_rejects_invalid_password_and_session_survives_service_reload(self) -> None:
        with self.assertRaises(WorkflowAuthenticationRequired):
            self.service.login(
                LoginRequest(username="josh", password="test-incorrect-password")
            )
        logged_in = self.service.login(
            LoginRequest(
                username="josh",
                password="controlled-local-password",
            )
        )
        reloaded = WorkflowFoundationService(
            repository=WorkflowFoundationRepository(
                engine=self.engine,
                clock=lambda: datetime(2026, 8, 7, 17, 31, tzinfo=UTC),
            ),
            clock=lambda: datetime(2026, 8, 7, 17, 31, tzinfo=UTC),
        )
        session = reloaded.current_session(logged_in.token)
        self.assertEqual(session.user.username, "josh")

    def test_login_locks_out_after_threshold_failed_attempts(self) -> None:
        for _ in range(self.service.LOGIN_LOCKOUT_THRESHOLD):
            with self.assertRaises(WorkflowAuthenticationRequired) as raised:
                self.service.login(
                    LoginRequest(username="josh", password="wrong-password")
                )
            self.assertIn(
                "username or password", str(raised.exception)
            )

        # The threshold-th failure just set the lockout - the *next*
        # attempt is what should see it, even with the correct password,
        # proving lockout blocks the account, not just repeated wrong
        # guesses.
        with self.assertRaises(WorkflowAuthenticationRequired) as raised:
            self.service.login(
                LoginRequest(
                    username="josh", password="controlled-local-password"
                )
            )
        self.assertIn("Too many failed sign-in attempts", str(raised.exception))

    def test_login_lockout_expires_after_duration(self) -> None:
        for _ in range(self.service.LOGIN_LOCKOUT_THRESHOLD):
            with self.assertRaises(WorkflowAuthenticationRequired):
                self.service.login(
                    LoginRequest(username="josh", password="wrong-password")
                )

        later = WorkflowFoundationService(
            repository=WorkflowFoundationRepository(
                engine=self.engine,
                clock=lambda: datetime(2026, 8, 7, 17, 46, tzinfo=UTC),
            ),
            clock=lambda: datetime(2026, 8, 7, 17, 46, tzinfo=UTC),
        )
        session = later.login(
            LoginRequest(
                username="josh", password="controlled-local-password"
            )
        )
        self.assertEqual(session.user.username, "josh")

    def test_successful_login_clears_prior_failed_attempts(self) -> None:
        for _ in range(self.service.LOGIN_LOCKOUT_THRESHOLD - 1):
            with self.assertRaises(WorkflowAuthenticationRequired):
                self.service.login(
                    LoginRequest(username="josh", password="wrong-password")
                )

        # One below the threshold, then a real login - should succeed and
        # reset the counter rather than carrying those near-threshold
        # failures forward.
        self.service.login(
            LoginRequest(
                username="josh", password="controlled-local-password"
            )
        )

        with self.assertRaises(WorkflowAuthenticationRequired) as raised:
            self.service.login(
                LoginRequest(username="josh", password="wrong-password")
            )
        self.assertIn("username or password", str(raised.exception))

    def test_login_lockout_applies_to_nonexistent_usernames_too(self) -> None:
        # Tracked identically for a real vs. fake username - the lockout
        # response must never be a signal of whether the account exists.
        for _ in range(self.service.LOGIN_LOCKOUT_THRESHOLD):
            with self.assertRaises(WorkflowAuthenticationRequired):
                self.service.login(
                    LoginRequest(
                        username="no-such-user", password="anything-at-all"
                    )
                )

        with self.assertRaises(WorkflowAuthenticationRequired) as raised:
            self.service.login(
                LoginRequest(
                    username="no-such-user", password="anything-else"
                )
            )
        self.assertIn("Too many failed sign-in attempts", str(raised.exception))

    def test_only_coordinator_can_create_local_accounts(self) -> None:
        observer = self.create_user("observer", "workflow_observer")
        observer_token = self.login("observer")
        with self.assertRaises(WorkflowPermissionDenied):
            self.service.create_user(
                observer_token,
                UserCreate(
                    username="blocked",
                    display_name="Blocked User",
                    password="controlled-user-password",
                    role_ids=["workflow_observer"],
                ),
            )
        self.assertEqual(observer.roles[0].role_id, "workflow_observer")

    def test_coordinator_without_security_module_cannot_create_accounts(self) -> None:
        limited_coordinator = self.service.create_user(
            self.coordinator.token,
            UserCreate(
                username="limited_coordinator",
                display_name="Limited Coordinator",
                password="controlled-user-password",
                role_ids=["workflow_coordinator"],
                module_ids=["dashboard", "work_management"],
            ),
        )
        limited_token = self.login("limited_coordinator")
        with self.assertRaises(WorkflowPermissionDenied):
            self.service.create_user(
                limited_token,
                UserCreate(
                    username="bypass_blocked",
                    display_name="Bypass Blocked",
                    password="controlled-user-password",
                    role_ids=["workflow_observer"],
                    module_ids=["accounts_payable"],
                ),
            )
        with self.assertRaises(WorkflowPermissionDenied):
            self.service.list_users(limited_token)
        with self.assertRaises(WorkflowPermissionDenied):
            self.service.audit_events(
                limited_token,
                subject_type=None,
                subject_id=None,
                limit=10,
            )
        with self.assertRaises(WorkflowPermissionDenied):
            self.service.verify_audit(limited_token)
        self.assertEqual(limited_coordinator.roles[0].role_id, "workflow_coordinator")

    def test_assigned_ap_task_is_durable_not_authority_and_not_execution(self) -> None:
        ap_user = self.create_user("ap_user", "ap_professional")
        task = self.service.create_task(
            self.coordinator.token,
            TaskCreate(
                title="Review invoice exception",
                description="Follow up on saved AP exception evidence.",
                capability="accounts_payable",
                context_type="ap_invoice",
                context_id="ap-invoice-123",
                context_label="Invoice 123",
                queue_role_id="ap_professional",
                assignee_user_id=ap_user.user_id,
                priority="high",
                due_date="2026-08-10",
                idempotency_key="task-create-ap-123",
            ),
        )
        self.assertEqual(task.assignment_effect, "work_ownership_only")
        self.assertEqual(task.authority_effect, "none")
        self.assertEqual(task.execution_effect, "none")
        ap_token = self.login("ap_user")
        queue = self.service.list_tasks(
            ap_token,
            mine=True,
            capability="accounts_payable",
            state=None,
        )
        self.assertEqual(queue.total, 1)
        notification = self.service.notifications(ap_token)
        self.assertEqual(notification.unread_count, 1)
        transitioned = self.service.transition_task(
            ap_token,
            task.task_id,
            TaskTransitionCreate(
                target_state="in_progress",
                note="Evidence review started.",
                expected_version=task.version,
                idempotency_key="task-transition-ap-123-started",
            ),
        )
        self.assertEqual(transitioned.state, "in_progress")
        self.assertEqual(transitioned.version, 2)
        with self.assertRaises(WorkflowFoundationConflict):
            self.service.transition_task(
                ap_token,
                task.task_id,
                TaskTransitionCreate(
                    target_state="completed",
                    note="Stale request.",
                    expected_version=task.version,
                    idempotency_key="task-transition-ap-123-stale",
                ),
            )

    def test_role_queue_claim_and_visibility_are_enforced(self) -> None:
        credit_user = self.create_user("credit_user", "credit_professional")
        self.create_user("ap_user", "ap_professional")
        task = self.service.create_task(
            self.coordinator.token,
            TaskCreate(
                title="Review credit evidence",
                description="Review the current partial exposure evidence.",
                capability="credit_risk",
                context_type="customer",
                context_id="680741",
                context_label="Customer 680741",
                queue_role_id="credit_professional",
                priority="medium",
                idempotency_key="task-create-credit-680741",
            ),
        )
        credit_token = self.login("credit_user")
        ap_token = self.login("ap_user")
        credit_queue = self.service.list_tasks(
            credit_token, mine=False, capability="credit_risk", state=None
        )
        ap_queue = self.service.list_tasks(
            ap_token, mine=False, capability="credit_risk", state=None
        )
        self.assertEqual(credit_queue.total, 1)
        self.assertEqual(ap_queue.total, 0)
        claimed = self.service.assign_task(
            credit_token,
            task.task_id,
            TaskAssignmentCreate(
                assignee_user_id=credit_user.user_id,
                note="Claiming the role-eligible work item.",
                expected_version=task.version,
                idempotency_key="task-claim-credit-680741",
            ),
        )
        self.assertEqual(claimed.assignee.user_id, credit_user.user_id)
        self.assertEqual(claimed.assignments[-1].assignment_type, "claim")
        self.assertEqual(claimed.assignments[-1].authority_effect, "none")

    def test_idempotent_create_and_transition_do_not_duplicate_history(self) -> None:
        credit_user = self.create_user("credit_user", "credit_professional")
        payload = TaskCreate(
            title="Review recommendation evidence",
            description="No decision or order action.",
            capability="credit_risk",
            context_type="order_recommendation",
            context_id="recommendation-1",
            context_label="Recommendation 1",
            queue_role_id="credit_professional",
            assignee_user_id=credit_user.user_id,
            priority="medium",
            idempotency_key="task-create-recommendation-1",
        )
        first = self.service.create_task(self.coordinator.token, payload)
        repeated = self.service.create_task(self.coordinator.token, payload)
        self.assertEqual(first.task_id, repeated.task_id)
        with self.assertRaises(WorkflowFoundationConflict):
            self.service.create_task(
                self.coordinator.token,
                payload.model_copy(update={"title": "Different governed request"}),
            )
        credit_token = self.login("credit_user")
        transition = TaskTransitionCreate(
            target_state="in_progress",
            note="Starting evidence review.",
            expected_version=first.version,
            idempotency_key="task-transition-recommendation-1",
        )
        once = self.service.transition_task(credit_token, first.task_id, transition)
        twice = self.service.transition_task(credit_token, first.task_id, transition)
        self.assertEqual(once.version, twice.version)
        self.assertEqual(len(twice.events), 2)
        with self.assertRaises(WorkflowFoundationConflict):
            self.service.transition_task(
                credit_token,
                first.task_id,
                transition.model_copy(update={"note": "Conflicting request reuse."}),
            )

    def test_append_only_evidence_and_hash_chain_detect_tampering(self) -> None:
        credit_user = self.create_user("credit_user", "credit_professional")
        task = self.service.create_task(
            self.coordinator.token,
            TaskCreate(
                title="Preserve audit evidence",
                description="Exercise append-only assignment history.",
                capability="credit_risk",
                context_type="customer",
                context_id="100",
                context_label="Customer 100",
                queue_role_id="credit_professional",
                assignee_user_id=credit_user.user_id,
                priority="low",
                idempotency_key="task-create-audit-100",
            ),
        )
        integrity = self.service.verify_audit(self.coordinator.token)
        self.assertTrue(integrity.valid)
        # Append-only is enforced by convention in the repository layer (it
        # never issues UPDATE/DELETE against these tables), not by a DB
        # trigger - MySQL trigger creation needs a privilege the etop
        # account doesn't have. This simulates an out-of-band tamper (e.g.
        # a bug or a direct SQL edit) to prove the hash chain still
        # catches it even without DB-level enforcement.
        connection = sqlite3.connect(self.database_path)
        try:
            connection.execute(
                "UPDATE wf_audit_events SET details_json = '{}' WHERE sequence = 1"
            )
            connection.commit()
        finally:
            connection.close()
        broken = self.repository.verify_audit_integrity()
        self.assertFalse(broken["valid"])
        self.assertIsNotNone(broken["first_invalid_audit_id"])

    def test_invitation_token_is_hashed_expiring_single_use_and_activates_access(self) -> None:
        invitation = self.service.create_invitation(
            self.coordinator.token,
            InvitationCreate(
                username="invited_ap",
                display_name="Invited AP User",
                role_ids=["ap_professional"],
                module_ids=["dashboard", "accounts_payable"],
                expires_in_hours=24,
            ),
        )
        token = unquote(urlsplit(invitation.invitation_link).fragment.removeprefix("invite="))
        self.assertGreaterEqual(len(token), 32)
        connection = sqlite3.connect(self.database_path)
        try:
            stored = connection.execute(
                "SELECT token_hash FROM wf_user_invitations WHERE invitation_id = ?",
                (invitation.invitation_id,),
            ).fetchone()[0]
            self.assertNotEqual(stored, token)
            self.assertEqual(len(stored), 64)
        finally:
            connection.close()

        preview = self.service.preview_invitation(InvitationTokenRequest(token=token))
        self.assertEqual(preview.username, "invited_ap")
        activated = self.service.activate_invitation(
            InvitationActivationRequest(
                token=token,
                password="invited-controlled-password",
            )
        )
        self.assertEqual(
            activated.permissions.module_ids,
            ["accounts_payable", "dashboard"],
        )
        self.service.authorize_module_access(
            activated.token, ("accounts_payable",)
        )
        with self.assertRaises(WorkflowPermissionDenied):
            self.service.authorize_module_access(activated.token, ("credit_risk",))
        with self.assertRaises(WorkflowFoundationConflict):
            self.service.activate_invitation(
                InvitationActivationRequest(
                    token=token,
                    password="another-controlled-password",
                )
            )

    def test_expired_invitation_fails_closed_and_records_terminal_status(self) -> None:
        invitation = self.service.create_invitation(
            self.coordinator.token,
            InvitationCreate(
                username="expired_user",
                display_name="Expired User",
                role_ids=["workflow_observer"],
                module_ids=["dashboard"],
                expires_in_hours=1,
            ),
        )
        token = unquote(urlsplit(invitation.invitation_link).fragment.removeprefix("invite="))
        later = datetime(2026, 8, 7, 19, 0, tzinfo=UTC)
        self.repository._clock = lambda: later
        self.service._clock = lambda: later
        with self.assertRaises(WorkflowFoundationConflict):
            self.service.preview_invitation(InvitationTokenRequest(token=token))
        stored = next(
            item
            for item in self.service.invitations(self.coordinator.token).items
            if item.invitation_id == invitation.invitation_id
        )
        self.assertEqual(stored.status, "expired")

    def test_coordinator_can_revoke_pending_invitation_once(self) -> None:
        invitation = self.service.create_invitation(
            self.coordinator.token,
            InvitationCreate(
                username="revoked_user",
                display_name="Revoked User",
                role_ids=["workflow_observer"],
                module_ids=["dashboard"],
            ),
        )
        token = unquote(urlsplit(invitation.invitation_link).fragment.removeprefix("invite="))
        revoked = self.service.revoke_invitation(
            self.coordinator.token,
            invitation.invitation_id,
            InvitationRevokeRequest(expected_status="pending"),
        )
        self.assertEqual(revoked.status, "revoked")
        with self.assertRaises(WorkflowFoundationConflict):
            self.service.preview_invitation(InvitationTokenRequest(token=token))
        with self.assertRaises(WorkflowFoundationConflict):
            self.service.revoke_invitation(
                self.coordinator.token,
                invitation.invitation_id,
                InvitationRevokeRequest(expected_status="pending"),
            )
        events = self.repository.list_audit(
            subject_type="user_invitation",
            subject_id=invitation.invitation_id,
            limit=10,
        )
        self.assertTrue(
            any(event["event_type"] == "identity.invitation_revoked" for event in events)
        )

    def test_password_reset_link_is_hashed_expiring_single_use_and_revokes_sessions(
        self,
    ) -> None:
        user = self.create_user("reset_user", "workflow_observer")
        user_token = self.login("reset_user")
        reset = self.service.request_password_reset(
            self.coordinator.token, user.user_id
        )
        token = unquote(
            urlsplit(reset.reset_link).fragment.removeprefix("reset-password=")
        )
        self.assertGreaterEqual(len(token), 32)
        connection = sqlite3.connect(self.database_path)
        try:
            stored = connection.execute(
                "SELECT token_hash FROM wf_password_reset_tokens WHERE reset_id = ?",
                (reset.reset_id,),
            ).fetchone()[0]
            self.assertNotEqual(stored, token)
            self.assertEqual(len(stored), 64)
        finally:
            connection.close()

        preview = self.service.preview_password_reset(
            PasswordResetTokenRequest(token=token)
        )
        self.assertEqual(preview.username, "reset_user")

        activated = self.service.activate_password_reset(
            PasswordResetActivationRequest(
                token=token,
                password="reset-controlled-password",
            )
        )
        self.assertEqual(activated.user.user_id, user.user_id)

        with self.assertRaises(WorkflowAuthenticationRequired):
            self.service.current_session(user_token)
        with self.assertRaises(WorkflowAuthenticationRequired):
            self.service.login(
                LoginRequest(
                    username="reset_user",
                    password="controlled-user-password",
                )
            )
        self.assertEqual(
            self.service.login(
                LoginRequest(
                    username="reset_user",
                    password="reset-controlled-password",
                )
            ).user.user_id,
            user.user_id,
        )
        with self.assertRaises(WorkflowFoundationConflict):
            self.service.activate_password_reset(
                PasswordResetActivationRequest(
                    token=token,
                    password="another-controlled-password",
                )
            )
        events = self.repository.list_audit(
            subject_type="user_account",
            subject_id=user.user_id,
            limit=10,
        )
        self.assertTrue(
            any(
                event["event_type"] == "identity.password_reset_completed"
                for event in events
            )
        )

    def test_expired_password_reset_fails_closed(self) -> None:
        user = self.create_user("expiring_reset_user", "workflow_observer")
        reset = self.service.request_password_reset(
            self.coordinator.token, user.user_id
        )
        token = unquote(
            urlsplit(reset.reset_link).fragment.removeprefix("reset-password=")
        )
        later = datetime(2026, 8, 8, 19, 0, tzinfo=UTC)
        self.repository._clock = lambda: later
        self.service._clock = lambda: later
        with self.assertRaises(WorkflowFoundationConflict):
            self.service.preview_password_reset(PasswordResetTokenRequest(token=token))

    def test_unrecognized_password_reset_token_is_not_found(self) -> None:
        with self.assertRaises(WorkflowFoundationNotFound):
            self.service.preview_password_reset(
                PasswordResetTokenRequest(token="x" * 32)
            )

    def test_admin_can_reset_own_password_via_link(self) -> None:
        reset = self.service.request_password_reset(
            self.coordinator.token, self.coordinator.user.user_id
        )
        token = unquote(
            urlsplit(reset.reset_link).fragment.removeprefix("reset-password=")
        )
        activated = self.service.activate_password_reset(
            PasswordResetActivationRequest(
                token=token,
                password="coordinator-new-password",
            )
        )
        self.assertEqual(activated.user.user_id, self.coordinator.user.user_id)

    def test_admin_can_set_password_directly_with_version_conflict_check(self) -> None:
        user = self.create_user("direct_set_user", "workflow_observer")
        user_token = self.login("direct_set_user")
        profile = next(
            item
            for item in self.service.security_users(self.coordinator.token).users
            if item.user.user_id == user.user_id
        )
        self.assertEqual(profile.credential_version, 1)
        with self.assertRaises(WorkflowFoundationConflict):
            self.service.set_user_password(
                self.coordinator.token,
                user.user_id,
                AdminPasswordSet(
                    new_password="stale-version-password",
                    expected_version=profile.credential_version + 1,
                ),
            )
        updated = self.service.set_user_password(
            self.coordinator.token,
            user.user_id,
            AdminPasswordSet(
                new_password="admin-set-password",
                expected_version=profile.credential_version,
            ),
        )
        self.assertEqual(updated.credential_version, 2)
        with self.assertRaises(WorkflowAuthenticationRequired):
            self.service.current_session(user_token)
        self.assertEqual(
            self.service.login(
                LoginRequest(
                    username="direct_set_user",
                    password="admin-set-password",
                )
            ).user.user_id,
            user.user_id,
        )

    def test_module_toggles_are_versioned_and_new_modules_default_deny(self) -> None:
        user = self.create_user("module_user", "workflow_observer")
        profile = next(
            item
            for item in self.service.security_users(self.coordinator.token).users
            if item.user.user_id == user.user_id
        )
        updated = self.service.replace_user_module_access(
            self.coordinator.token,
            user.user_id,
            ModuleAccessReplace(
                module_ids=["dashboard", "accounts_payable"],
                expected_version=profile.access_version,
            ),
        )
        self.assertEqual(
            updated.configured_module_ids,
            ["accounts_payable", "dashboard"],
        )
        with self.assertRaises(WorkflowFoundationConflict):
            self.service.replace_user_module_access(
                self.coordinator.token,
                user.user_id,
                ModuleAccessReplace(
                    module_ids=["dashboard"],
                    expected_version=profile.access_version,
                ),
            )
        connection = sqlite3.connect(self.database_path)
        try:
            connection.execute(
                """
                INSERT INTO wf_modules(
                    module_id, name, description, module_group,
                    default_access, status, authority_effect, created_at
                ) VALUES ('future_module', 'Future Module', 'Test registration',
                          'System', 0, 'active', 'none', ?)
                """,
                (datetime(2026, 8, 7, 17, 30, tzinfo=UTC).isoformat(),),
            )
            connection.commit()
        finally:
            connection.close()
        permissions = self.repository.get_permissions(user.user_id)
        self.assertNotIn("future_module", permissions["module_ids"])

    def test_suspend_revokes_sessions_and_reactivate_allows_new_login(self) -> None:
        user = self.create_user("lifecycle_user", "workflow_observer")
        user_token = self.login("lifecycle_user")
        profile = next(
            item
            for item in self.service.security_users(self.coordinator.token).users
            if item.user.user_id == user.user_id
        )
        suspended = self.service.change_user_status(
            self.coordinator.token,
            user.user_id,
            UserStatusChange(
                status="inactive",
                expected_version=profile.status_version,
            ),
        )
        self.assertEqual(suspended.user.status, "inactive")
        with self.assertRaises(WorkflowAuthenticationRequired):
            self.service.current_session(user_token)
        reactivated = self.service.change_user_status(
            self.coordinator.token,
            user.user_id,
            UserStatusChange(
                status="active",
                expected_version=suspended.status_version,
            ),
        )
        self.assertEqual(reactivated.user.status, "active")
        self.assertEqual(
            self.service.login(
                LoginRequest(
                    username="lifecycle_user",
                    password="controlled-user-password",
                )
            ).user.user_id,
            user.user_id,
        )
        self.assertTrue(self.service.verify_audit(self.coordinator.token).valid)

    def test_last_active_security_coordinator_is_protected_transactionally(self) -> None:
        coordinator_profile = next(
            item
            for item in self.service.security_users(self.coordinator.token).users
            if item.user.user_id == self.coordinator.user.user_id
        )
        with self.assertRaises(WorkflowFoundationConflict):
            self.repository.replace_module_access(
                user_id=self.coordinator.user.user_id,
                module_ids=[
                    module_id
                    for module_id in coordinator_profile.configured_module_ids
                    if module_id != "security_administration"
                ],
                expected_version=coordinator_profile.access_version,
                actor_user_id=self.coordinator.user.user_id,
            )
        with self.assertRaises(WorkflowFoundationConflict):
            self.repository.change_user_status(
                user_id=self.coordinator.user.user_id,
                status="inactive",
                expected_version=coordinator_profile.status_version,
                actor_user_id=self.coordinator.user.user_id,
            )
        self.assertEqual(self.repository.active_security_coordinator_count(), 1)

    def test_backend_route_policy_covers_current_modules_and_fails_closed(self) -> None:
        self.assertIsNone(
            required_modules_for_path(
                "/api/v1/workflow-foundation/invitations/activate"
            )
        )
        self.assertEqual(
            required_modules_for_path("/api/v1/accounts-payable/overview"),
            ("accounts_payable",),
        )
        self.assertEqual(
            required_modules_for_path("/api/v1/payment-notes/runs"),
            ("payment_notes",),
        )
        self.assertEqual(
            required_modules_for_path("/api/v1/payment-notes-archive"),
            (),
        )
        self.assertEqual(
            required_modules_for_path(
                "/api/v1/documents/jobs/JOB-1/lockbox/review"
            ),
            ("lockbox",),
        )
        self.assertEqual(
            required_modules_for_path("/api/v1/workflow-foundation/security/users"),
            ("security_administration",),
        )
        self.assertEqual(
            required_modules_for_path("/api/v1/modules"),
            ("dashboard",),
        )
        self.assertEqual(
            required_modules_for_path("/api/v1/platform/health"),
            ("dashboard",),
        )
        self.assertEqual(
            required_modules_for_path("/api/test/open-invoices"),
            ("cash_application", "lockbox"),
        )
        self.assertEqual(
            required_modules_for_path("/api/v1/customer-intelligence/summary"),
            ("customer_360",),
        )
        self.assertEqual(
            required_modules_for_path("/knowledge/reindex/status"),
            ("knowledge_base",),
        )
        self.assertEqual(required_modules_for_path("/api/v1/future-module"), ())


if __name__ == "__main__":
    unittest.main()
