"""
ETOP platform health and module diagnostics endpoints.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from core import module_config
from core.event_bus import EventBus
from core.kernel import get_kernel
from core.module_manager import ModuleManager
from core.module_registry import module_registry


router = APIRouter(
    prefix="/api/v1",
    tags=["Platform"],
)


def _legacy_module_information() -> dict[str, Any]:
    """
    Return module information from the original FastAPI module registry.

    This remains during the migration so current legacy modules continue
    working until they are converted to PlatformModule implementations.
    """

    return {
        "summary": module_registry.summary(),
        "modules": module_registry.list_statuses(),
    }


def _module_discovery_information(
    discovery: Any,
) -> dict[str, Any]:
    """
    Return automatic platform-module discovery diagnostics.
    """

    if discovery is None:
        return {
            "completed": False,
            "discovered": 0,
            "scanned_packages": [],
            "skipped_packages": [],
            "failures": [],
        }

    return {
        "completed": True,
        "discovered": discovery.discovered_count,
        "scanned_packages": list(
            discovery.scanned_packages
        ),
        "skipped_packages": list(
            discovery.skipped_packages
        ),
        "failures": [
            {
                "package_name": failure.package_name,
                "error_type": failure.error_type,
                "message": failure.message,
            }
            for failure in discovery.failures
        ],
    }


@router.get("/modules")
def list_modules() -> dict[str, Any]:
    """
    Preserve the existing module endpoint response.

    Platform-module information is included without removing the legacy
    fields currently consumed by the frontend.
    """

    kernel = get_kernel()

    manager = kernel.services.try_resolve(
        ModuleManager,
    )

    platform_modules = (
        manager.diagnostics()
        if manager is not None
        else []
    )

    legacy = _legacy_module_information()

    return {
        **legacy,
        "module_toggles": module_config.all_states(),
        "platform_modules": [
            {
                "name": item.name,
                "display_name": item.display_name,
                "version": item.version,
                "state": item.state.value,
                "enabled": item.enabled,
                "dependencies": list(item.dependencies),
                "healthy": item.healthy,
                "health_message": item.health_message,
                "last_error": item.last_error,
            }
            for item in platform_modules
        ],
    }


@router.post("/modules/{module_key}/enable")
def enable_module(module_key: str) -> dict[str, Any]:
    """
    Turn a module on immediately (no restart required) and persist the
    choice so it stays on across restarts.
    """

    module_config.set_enabled(module_key, True)

    return {"key": module_key, "enabled": True}


@router.post("/modules/{module_key}/disable")
def disable_module(module_key: str) -> dict[str, Any]:
    """
    Turn a module off immediately (no restart required) and persist the
    choice so it stays off across restarts. Requests to the module's own
    routes will receive 503 until it is re-enabled.
    """

    module_config.set_enabled(module_key, False)

    return {"key": module_key, "enabled": False}


@router.get("/platform/health")
async def platform_health(
    request: Request,
) -> dict[str, Any]:
    """
    Return consolidated ETOP runtime health.
    """

    kernel = get_kernel()

    module_manager = kernel.services.try_resolve(
        ModuleManager,
    )

    if (
        module_manager is not None
        and module_manager.is_running
    ):
        await module_manager.refresh_health()

    event_bus = kernel.services.try_resolve(
        EventBus,
    )

    discovery = getattr(
        request.app.state,
        "etop_module_discovery",
        None,
    )

    return {
        **kernel.health(),
        "event_bus": (
            event_bus.diagnostics()
            if event_bus is not None
            else {
                "running": False,
                "status": "not_registered",
            }
        ),
        "module_discovery": (
            _module_discovery_information(discovery)
        ),
        "legacy_modules": (
            _legacy_module_information()
        ),
    }


@router.get("/platform/services")
def platform_services() -> dict[str, Any]:
    """
    Return non-sensitive service-registration diagnostics.
    """

    kernel = get_kernel()

    return {
        "registry_frozen": kernel.services.is_frozen,
        "services": [
            {
                "key": item.key,
                "lifetime": item.lifetime.value,
                "implementation": item.implementation,
                "initialized": item.initialized,
                "metadata": dict(item.metadata),
            }
            for item in kernel.services.describe()
        ],
    }


@router.get("/platform/events")
def platform_events() -> dict[str, Any]:
    """
    Return Event Bus diagnostics and recent event history.

    Event payloads are not retained by the Event Bus.
    """

    kernel = get_kernel()

    event_bus = kernel.services.try_resolve(
        EventBus,
    )

    if event_bus is None:
        return {
            "running": False,
            "diagnostics": {},
            "recent_events": [],
        }

    return {
        "running": event_bus.is_running,
        "diagnostics": event_bus.diagnostics(),
        "recent_events": [
            {
                "event_id": str(item.event_id),
                "event_name": item.event_name,
                "event_type": item.event_type,
                "source": item.source,
                "occurred_at": item.occurred_at.isoformat(),
                "published_at": item.published_at.isoformat(),
                "duration_ms": item.duration_ms,
                "subscriber_count": item.subscriber_count,
                "succeeded_count": item.succeeded_count,
                "failed_count": item.failed_count,
                "correlation_id": (
                    str(item.correlation_id)
                    if item.correlation_id
                    else None
                ),
                "causation_id": (
                    str(item.causation_id)
                    if item.causation_id
                    else None
                ),
            }
            for item in event_bus.history(limit=25)
        ],
    }