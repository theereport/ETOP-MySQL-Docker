"""
Customer 360 ETOP platform module.

This module adapts the existing Customer 360 implementation to the ETOP
PlatformModule lifecycle without changing its current API, service, repository,
or response contracts.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from core.module import (
    ModuleContext,
    ModuleHealth,
    ModuleMetadata,
    PlatformModule,
)

from .router import router
from .repository import CustomerRepository, customer_repository
from .service import CustomerService, customer_service


class Module(PlatformModule):
    """
    Customer 360 platform module.
    """

    metadata = ModuleMetadata(
        name="customer_360",
        display_name="Customer 360",
        version="0.3.0",
        description=(
            "Provides customer search, customer account summaries, "
            "credit exposure, aging, sales, and customer profile data."
        ),
        dependencies=(),
        enabled=True,
        tags=(
            "customer",
            "credit",
            "sales",
            "accounts-receivable",
        ),
    )

    async def register_services(
        self,
        context: ModuleContext,
    ) -> None:
        """
        Register the existing Customer 360 service instances.

        Phase 2A intentionally reuses the existing instances so the migration
        does not create duplicate repositories or service objects.
        """

        services = context.services

        if not services.contains(CustomerRepository):
            services.register_instance(
                CustomerRepository,
                customer_repository,
                metadata={
                    "module": self.metadata.name,
                    "component": "repository",
                    "database": "madden",
                    "access": "read_only",
                },
            )

        if not services.contains(CustomerService):
            services.register_instance(
                CustomerService,
                customer_service,
                metadata={
                    "module": self.metadata.name,
                    "component": "application_service",
                },
            )

        if not services.contains("etop.customer_360.repository"):
            services.register_alias(
                "etop.customer_360.repository",
                CustomerRepository,
            )

        if not services.contains("etop.customer_360.service"):
            services.register_alias(
                "etop.customer_360.service",
                CustomerService,
            )

    async def start(
        self,
        context: ModuleContext,
    ) -> None:
        """
        Validate that required Customer 360 services can be resolved.
        """

        context.services.resolve(CustomerRepository)
        context.services.resolve(CustomerService)

    async def health(
        self,
        context: ModuleContext,
    ) -> ModuleHealth:
        """
        Report module registration health without running a live customer query.
        """

        repository = context.services.try_resolve(
            CustomerRepository,
        )

        service = context.services.try_resolve(
            CustomerService,
        )

        if repository is None:
            return ModuleHealth(
                healthy=False,
                message="Customer repository is not registered.",
            )

        if service is None:
            return ModuleHealth(
                healthy=False,
                message="Customer service is not registered.",
            )

        return ModuleHealth(
            healthy=True,
            message="Customer 360 services are registered and ready.",
            details={
                "repository": type(repository).__name__,
                "service": type(service).__name__,
                "routes": len(router.routes),
            },
        )

    def routes(self) -> Sequence[Any]:
        """
        Return the existing Customer 360 FastAPI router.
        """

        return (router,)