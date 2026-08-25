from __future__ import annotations

import sqlite3
import tempfile
import unittest
from hashlib import sha256
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch
from urllib.parse import unquote, urlsplit

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from modules.workflow_foundation import router as workflow_api
from modules.workflow_foundation.access_control import ModuleAccessMiddleware
from modules.workflow_foundation.repository import WorkflowFoundationRepository
from modules.workflow_foundation.schemas import BootstrapRequest, InvitationCreate
from modules.workflow_foundation.service import (
    WorkflowAuthenticationRequired,
    WorkflowFoundationService,
)


class SecurityAccessApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        database_path = Path(self.temp.name) / "security-access-api.db"

        def connection_factory() -> sqlite3.Connection:
            return sqlite3.connect(database_path, timeout=30, check_same_thread=False)

        clock = lambda: datetime(2026, 8, 7, 17, 30, tzinfo=UTC)
        self.service = WorkflowFoundationService(
            repository=WorkflowFoundationRepository(
                connection_factory=connection_factory,
                clock=clock,
            ),
            clock=clock,
            app_url="http://127.0.0.1:5173",
        )
        self.coordinator = self.service.bootstrap(
            BootstrapRequest(
                username="coordinator",
                display_name="Security Coordinator",
                password="controlled-local-password",
            )
        )

        self.original_api_service = workflow_api.workflow_foundation_service
        workflow_api.workflow_foundation_service = self.service

        app = FastAPI()

        @app.get("/health")
        def health() -> dict[str, str]:
            return {"status": "ok"}

        @app.get("/api/v1/accounts-payable/probe")
        def accounts_payable_probe() -> dict[str, bool]:
            return {"allowed": True}

        @app.get("/api/v1/credit-risk/probe")
        def credit_risk_probe() -> dict[str, bool]:
            return {"allowed": True}

        @app.get("/api/v1/payment-notes/probe")
        def payment_notes_probe() -> dict[str, bool]:
            return {"allowed": True}

        @app.get("/api/v1/future-module/probe")
        def future_probe() -> dict[str, bool]:
            return {"allowed": True}

        app.include_router(workflow_api.router)
        app.add_middleware(
            ModuleAccessMiddleware,
            authorization_service=self.service,
        )
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["http://127.0.0.1:5173"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        self.client = TestClient(app, base_url="http://127.0.0.1")

    def tearDown(self) -> None:
        self.client.close()
        workflow_api.workflow_foundation_service = self.original_api_service
        self.temp.cleanup()

    def test_public_bootstrap_health_and_cors_preflight_do_not_require_session(self) -> None:
        self.assertEqual(self.client.get("/health").status_code, 200)
        bootstrap = self.client.get(
            "/api/v1/workflow-foundation/bootstrap-status"
        )
        self.assertEqual(bootstrap.status_code, 200)
        self.assertFalse(bootstrap.json()["bootstrap_required"])

        preflight = self.client.options(
            "/api/v1/accounts-payable/probe",
            headers={
                "Origin": "http://127.0.0.1:5173",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization",
            },
        )
        self.assertEqual(preflight.status_code, 200)
        self.assertEqual(
            preflight.headers["access-control-allow-origin"],
            "http://127.0.0.1:5173",
        )
        self.assertEqual(
            preflight.headers["access-control-allow-credentials"],
            "true",
        )

    def test_invite_public_routes_issue_cookie_and_server_enforces_modules(self) -> None:
        invitation = self.service.create_invitation(
            self.coordinator.token,
            InvitationCreate(
                username="invited_ap",
                display_name="Invited AP",
                role_ids=["ap_professional"],
                module_ids=["accounts_payable"],
                expires_in_hours=24,
            ),
        )
        token = unquote(
            urlsplit(invitation.invitation_link).fragment.removeprefix("invite=")
        )
        preview = self.client.post(
            "/api/v1/workflow-foundation/invitations/preview",
            json={"token": token},
        )
        self.assertEqual(preview.status_code, 200)
        activated = self.client.post(
            "/api/v1/workflow-foundation/invitations/activate",
            json={
                "token": token,
                "password": "invited-controlled-password",
            },
        )
        self.assertEqual(activated.status_code, 201)
        cookie = activated.headers["set-cookie"]
        self.assertIn("etop_local_session=", cookie)
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=strict", cookie)

        # TestClient retains the HttpOnly cookie just as a browser does for direct
        # file/export navigation where JavaScript cannot add a bearer header.
        self.assertEqual(
            self.client.get("/api/v1/accounts-payable/probe").status_code,
            200,
        )
        denied = self.client.get("/api/v1/credit-risk/probe")
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(denied.json()["detail"]["code"], "module_access_denied")

        payment_notes_denied = self.client.get("/api/v1/payment-notes/probe")
        self.assertEqual(payment_notes_denied.status_code, 403)
        self.assertEqual(
            payment_notes_denied.json()["detail"]["code"],
            "module_access_denied",
        )

        unknown = self.client.get("/api/v1/future-module/probe")
        self.assertEqual(unknown.status_code, 403)
        self.assertEqual(unknown.json()["detail"]["code"], "module_access_unmapped")

    def test_missing_session_and_security_administration_are_denied(self) -> None:
        isolated_client = TestClient(
            self.client.app,
            base_url="http://127.0.0.1",
        )
        try:
            unauthenticated = isolated_client.get(
                "/api/v1/accounts-payable/probe"
            )
            self.assertEqual(unauthenticated.status_code, 401)
            self.assertEqual(
                unauthenticated.json()["detail"]["code"],
                "workflow_authentication_required",
            )
        finally:
            isolated_client.close()

        coordinator = self.client.get(
            "/api/v1/workflow-foundation/security/users",
            headers={"Authorization": f"Bearer {self.coordinator.token}"},
        )
        self.assertEqual(coordinator.status_code, 200)

    def test_environment_specific_cookie_name_and_domain_are_honored(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "ETOP_COOKIE_NAME": "etop_test_session_8001",
                "ETOP_COOKIE_DOMAIN": "127.0.0.1",
                "ETOP_APP_URL": "http://127.0.0.1:5174",
            },
            clear=False,
        ):
            login = self.client.post(
                "/api/v1/workflow-foundation/sessions",
                json={
                    "username": "coordinator",
                    "password": "controlled-local-password",
                },
            )
            self.assertEqual(login.status_code, 200)
            cookie = login.headers["set-cookie"]
            self.assertIn("etop_test_session_8001=", cookie)
            self.assertIn("Domain=127.0.0.1", cookie)
            self.assertEqual(
                self.client.get("/api/v1/accounts-payable/probe").status_code,
                200,
            )

    def test_signed_session_hash_is_namespace_isolated_and_invite_uses_app_url(self) -> None:
        database_path = Path(self.temp.name) / "signed-session.db"

        def connection_factory() -> sqlite3.Connection:
            return sqlite3.connect(database_path, timeout=30, check_same_thread=False)

        clock = lambda: datetime(2026, 8, 7, 17, 30, tzinfo=UTC)
        with patch.dict(
            "os.environ",
            {
                "ETOP_APP_URL": "http://127.0.0.1:5174",
                "ETOP_SESSION_SIGNING_SECRET": "test-only-secret-with-at-least-32-characters",
                "ETOP_SESSION_NAMESPACE": "test-port-8001",
            },
            clear=False,
        ):
            signed_service = WorkflowFoundationService(
                repository=WorkflowFoundationRepository(
                    connection_factory=connection_factory,
                    clock=clock,
                ),
                clock=clock,
            )
            session = signed_service.bootstrap(
                BootstrapRequest(
                    username="signed_coordinator",
                    display_name="Signed Coordinator",
                    password="controlled-local-password",
                )
            )
            invitation = signed_service.create_invitation(
                session.token,
                InvitationCreate(
                    username="test_link_user",
                    display_name="Test Link User",
                    role_ids=["workflow_observer"],
                    module_ids=["dashboard"],
                ),
            )
        self.assertTrue(
            invitation.invitation_link.startswith("http://127.0.0.1:5174/#invite=")
        )
        connection = connection_factory()
        try:
            stored_hash = connection.execute(
                "SELECT token_hash FROM wf_sessions ORDER BY issued_at LIMIT 1"
            ).fetchone()[0]
        finally:
            connection.close()
        self.assertNotEqual(stored_hash, sha256(session.token.encode()).hexdigest())

        other_namespace = WorkflowFoundationService(
            repository=WorkflowFoundationRepository(
                connection_factory=connection_factory,
                clock=clock,
            ),
            clock=clock,
            session_signing_secret="test-only-secret-with-at-least-32-characters",
            session_namespace="different-environment",
        )
        with self.assertRaises(WorkflowAuthenticationRequired) as error:
            other_namespace.current_session(session.token)
        self.assertIn("missing, expired, or signed out", str(error.exception))


if __name__ == "__main__":
    unittest.main()
