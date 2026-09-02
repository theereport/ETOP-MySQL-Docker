"""
Integration test for FastAPI and ETOP kernel lifecycle.
"""

import sys

import pytest
from fastapi.testclient import TestClient

# A handful of other test files (e.g. test_ap_vendor_spend_intelligence.py)
# replace sys.modules["core"]/["core.database"] with a minimal fake module
# at import time and never restore it - fine for their own narrow needs,
# but if pytest collects one of those files first (alphabetically, several
# do), importing `main` below (which transitively imports the real
# core.database through its startup initialize_database() call) would
# silently get their fake stub instead of the real module. Force a real
# one regardless of collection order.
for _stale in ("core", "core.database"):
    if _stale in sys.modules and not hasattr(sys.modules[_stale], "__file__"):
        del sys.modules[_stale]

from core.event_bus import EventBus
from core.kernel import KernelState, get_kernel
from core.module_manager import ModuleManager
from main import app


@pytest.mark.skip(
    reason=(
        "ETOPKernel/ModuleManager are intentionally not wired into main.py's "
        "lifespan — see ADR-005 in docs/Architecture/Architecture Decisions.md. "
        "module_registry (per-module failure isolation) is the canonical "
        "registration mechanism today; this test documents possible future "
        "kernel-based lifecycle wiring, not current behavior."
    )
)
def test_fastapi_uses_etop_kernel_lifecycle() -> None:
    kernel = get_kernel()

    with TestClient(app) as client:
        assert kernel.state is KernelState.RUNNING
        assert kernel.is_ready is True

        event_bus = kernel.resolve(EventBus)
        module_manager = kernel.resolve(ModuleManager)

        assert event_bus.is_running is True
        assert module_manager.is_running is True

        response = client.get(
            "/api/v1/platform/health",
        )

        assert response.status_code == 200

        payload = response.json()

        assert payload["platform"] == "ETOP"
        assert payload["state"] == "running"
        assert payload["ready"] is True
        assert payload["event_bus"]["running"] is True

        event_response = client.get(
            "/api/v1/platform/events",
        )

        assert event_response.status_code == 200

        event_payload = event_response.json()

        event_names = [
            item["event_name"]
            for item in event_payload["recent_events"]
        ]

        assert any(
            "PlatformStartedEvent" in name
            for name in event_names
        )

    assert kernel.state is KernelState.STOPPED