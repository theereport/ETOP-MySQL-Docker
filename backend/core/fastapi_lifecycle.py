"""
FastAPI lifecycle integration for the ETOP platform kernel.

This module connects FastAPI startup and shutdown to the framework-agnostic
ETOPKernel and registers platform modules before the ModuleManager starts.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from data.database import initialize_database
from .module_discovery import (
    ModuleDiscoveryResult,
    discover_platform_modules,
)

from .database import MaddenDatabase, madden_database
from .event_bus import EventBus
from .events import PlatformStartedEvent, PlatformStoppedEvent
from .kernel import ETOPKernel, get_kernel
from .module_manager import ModuleManager


logger = logging.getLogger(__name__)

_configured_application_ids: set[int] = set()


async def register_existing_application_services(
    kernel: ETOPKernel,
) -> None:
    """
    Register services that already exist in the application.

    Phase 2A continues using the current shared MaddenDatabase instance.
    """

    services = kernel.services

    if not services.contains(MaddenDatabase):
        kernel.register_instance(
            MaddenDatabase,
            madden_database,
            metadata={
                "component": "database",
                "database": "madden",
                "access": "read_only",
                "source": "existing_application",
            },
        )

    if not services.contains("etop.database.madden"):
        services.register_alias(
            "etop.database.madden",
            MaddenDatabase,
        )

    initialize_database()

    logger.info(
        "Existing ETOP application services registered with the kernel."
    )


def create_platform_module_registration_hook(
    app: FastAPI,
):
    """
    Create a startup hook that discovers and registers ETOP modules.

    Document Intelligence remains excluded because it is still managed by the
    legacy module registry during the migration period.
    """

    async def register_platform_modules(
        kernel: ETOPKernel,
    ) -> None:
        manager = kernel.resolve(ModuleManager)

        discovery = discover_platform_modules(
            "modules",
            excluded_modules={
                "document_intelligence",
            },
            strict=False,
        )

        app.state.etop_module_discovery = discovery

        registered_count = 0
        route_count = 0

        registered_route_ids: set[int] = getattr(
            app.state,
            "etop_registered_router_ids",
            set(),
        )

        for platform_module in discovery.modules:
            module_name = platform_module.metadata.name

            if not manager.contains(module_name):
                manager.register(platform_module)
                registered_count += 1

            registered_module = manager.get(module_name)

            for router in registered_module.routes():
                router_id = id(router)

                if router_id in registered_route_ids:
                    continue

                app.include_router(router)
                registered_route_ids.add(router_id)
                route_count += 1

        app.state.etop_registered_router_ids = (
            registered_route_ids
        )

        if discovery.failures:
            for failure in discovery.failures:
                logger.error(
                    "ETOP module discovery failure: package=%s, "
                    "type=%s, message=%s",
                    failure.package_name,
                    failure.error_type,
                    failure.message,
                )

        logger.info(
            "ETOP module discovery completed: "
            "discovered=%s, registered=%s, routes=%s, "
            "skipped=%s, failures=%s.",
            discovery.discovered_count,
            registered_count,
            route_count,
            len(discovery.skipped_packages),
            discovery.failure_count,
        )

    return register_platform_modules


def configure_kernel_lifecycle(
    kernel: ETOPKernel,
    app: FastAPI,
) -> None:
    """
    Add ETOP application startup hooks once per FastAPI application instance.
    """

    application_id = id(app)

    if application_id in _configured_application_ids:
        return

    kernel.add_startup_hook(
        register_existing_application_services,
    )

    kernel.add_startup_hook(
        create_platform_module_registration_hook(app),
    )

    _configured_application_ids.add(application_id)


@asynccontextmanager
async def etop_lifespan(
    app: FastAPI,
) -> AsyncIterator[None]:
    """
    Start and stop the ETOP platform with the FastAPI application.
    """

    kernel = get_kernel()

    configure_kernel_lifecycle(
        kernel,
        app,
    )

    await kernel.start()

    event_bus = kernel.resolve(EventBus)

    app.state.etop_kernel = kernel
    app.state.services = kernel.services
    app.state.event_bus = event_bus

    try:
        await event_bus.publish(
            PlatformStartedEvent(
                version=kernel.version,
                source="fastapi",
                metadata={
                    "application": app.title,
                    "api_version": app.version,
                },
            )
        )

        logger.info(
            "FastAPI application is running under ETOP kernel version %s.",
            kernel.version,
        )

        yield

    finally:
        try:
            if event_bus.is_running:
                await event_bus.publish(
                    PlatformStoppedEvent(
                        version=kernel.version,
                        source="fastapi",
                        metadata={
                            "application": app.title,
                            "api_version": app.version,
                        },
                    )
                )

        except Exception:
            logger.exception(
                "Unable to publish the ETOP platform-stopped event."
            )

        await kernel.stop()

        logger.info(
            "FastAPI application shutdown completed through the ETOP kernel."
        )