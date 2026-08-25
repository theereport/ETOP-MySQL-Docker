"""
ETOP Platform Module Contracts.

Defines the contracts, metadata, states, diagnostics, and lifecycle hooks used
by ETOP feature modules.

A platform module is responsible for its own:

- Metadata
- Service registrations
- Event subscriptions
- Startup
- Shutdown
- Health reporting

The kernel does not need to know individual feature modules. The
ModuleManager coordinates them through this contract.
"""

from __future__ import annotations

from abc import ABC
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from .event_bus import EventBus
from .service_registry import ServiceRegistry


class ModuleState(StrEnum):
    """Supported ETOP module lifecycle states."""

    DISCOVERED = "discovered"
    REGISTERING = "registering"
    REGISTERED = "registered"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    DISABLED = "disabled"
    FAILED = "failed"


class ModuleError(RuntimeError):
    """Base exception for ETOP module failures."""


class ModuleDependencyError(ModuleError):
    """Raised when a module dependency cannot be satisfied."""


class ModuleLifecycleError(ModuleError):
    """Raised when a module lifecycle operation fails."""


@dataclass(frozen=True, slots=True)
class ModuleMetadata:
    """
    Immutable identifying information for one ETOP module.

    Attributes:
        name:
            Unique machine-readable module identifier.
        display_name:
            Human-readable name shown in diagnostics and administration UI.
        version:
            Module version.
        description:
            Brief module purpose.
        dependencies:
            Other module names that must start first.
        enabled:
            Default enabled state.
        tags:
            Optional discovery and grouping labels.
    """

    name: str
    display_name: str
    version: str = "0.1.0"
    description: str = ""
    dependencies: tuple[str, ...] = ()
    enabled: bool = True
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        normalized_name = self.name.strip()

        if not normalized_name:
            raise ValueError("Module name cannot be blank.")

        if normalized_name != self.name:
            object.__setattr__(self, "name", normalized_name)

        if not self.display_name.strip():
            raise ValueError("Module display_name cannot be blank.")

        if self.name in self.dependencies:
            raise ValueError(
                f"Module '{self.name}' cannot depend on itself."
            )


@dataclass(slots=True)
class ModuleContext:
    """
    Shared platform resources provided to every module lifecycle method.
    """

    services: ServiceRegistry
    events: EventBus
    settings: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ModuleHealth:
    """Health result returned by a module."""

    healthy: bool
    message: str = "Healthy"
    details: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ModuleDiagnostic:
    """Read-only module information suitable for health APIs."""

    name: str
    display_name: str
    version: str
    state: ModuleState
    enabled: bool
    dependencies: tuple[str, ...]
    description: str
    tags: tuple[str, ...]
    healthy: bool | None
    health_message: str | None
    last_error: str | None


class PlatformModule(ABC):
    """
    Base class for ETOP platform modules.

    Override only the lifecycle methods needed by the module.

    Recommended order:

        configure()
        register_services()
        register_events()
        start()
        health()
        stop()
    """

    metadata: ModuleMetadata

    def __init__(self) -> None:
        if not isinstance(getattr(self, "metadata", None), ModuleMetadata):
            raise TypeError(
                f"{self.__class__.__qualname__} must define a "
                "ModuleMetadata class attribute named 'metadata'."
            )

    async def configure(self, context: ModuleContext) -> None:
        """Validate or consume module configuration."""

    async def register_services(self, context: ModuleContext) -> None:
        """Register module-owned services."""

    async def register_events(self, context: ModuleContext) -> None:
        """Register module event subscriptions."""

    async def start(self, context: ModuleContext) -> None:
        """Start module runtime behavior."""

    async def stop(self, context: ModuleContext) -> None:
        """Stop module runtime behavior."""

    async def health(self, context: ModuleContext) -> ModuleHealth:
        """Return current module health."""

        return ModuleHealth(healthy=True)

    def routes(self) -> Sequence[Any]:
        """
        Return API routers exposed by the module.

        The core module framework intentionally uses Any here so it remains
        independent of FastAPI. The API host may later validate router types.
        """

        return ()