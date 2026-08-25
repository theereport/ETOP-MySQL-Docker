"""
ETOP Platform Module Manager.

The ModuleManager discovers, validates, registers, starts, stops, enables,
disables, and diagnoses ETOP platform modules.

Modules communicate through platform services and events. They do not call
each other directly.
"""

from __future__ import annotations

import importlib
import inspect
import logging
import pkgutil
import time
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from threading import RLock
from typing import Any

from .event_bus import EventBus
from .module import (
    ModuleContext,
    ModuleDependencyError,
    ModuleDiagnostic,
    ModuleError,
    ModuleHealth,
    ModuleLifecycleError,
    ModuleState,
    PlatformModule,
)
from .service_registry import ServiceRegistry


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class _ModuleRecord:
    """Internal mutable state for one module."""

    module: PlatformModule
    state: ModuleState
    enabled: bool
    last_error: str | None = None
    health: ModuleHealth | None = None

    @property
    def name(self) -> str:
        return self.module.metadata.name


class ModuleManager:
    """
    Coordinates ETOP feature modules.

    The manager itself is suitable for registration as an eager singleton.
    """

    def __init__(
        self,
        services: ServiceRegistry,
        events: EventBus,
        *,
        settings: Mapping[str, Any] | None = None,
    ) -> None:
        self._services = services
        self._events = events
        self._settings = dict(settings or {})
        self._modules: dict[str, _ModuleRecord] = {}
        self._startup_order: list[str] = []
        self._lock = RLock()
        self._running = False

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._running

    @property
    def module_count(self) -> int:
        with self._lock:
            return len(self._modules)

    def register(
        self,
        module: PlatformModule,
        *,
        replace: bool = False,
    ) -> PlatformModule:
        """Register a module instance with the manager."""

        if not isinstance(module, PlatformModule):
            raise TypeError("module must inherit from PlatformModule.")

        name = module.metadata.name

        with self._lock:
            if name in self._modules and not replace:
                raise ModuleError(
                    f"Module '{name}' is already registered."
                )

            self._modules[name] = _ModuleRecord(
                module=module,
                state=(
                    ModuleState.DISCOVERED
                    if module.metadata.enabled
                    else ModuleState.DISABLED
                ),
                enabled=module.metadata.enabled,
            )

        logger.info(
            "Registered ETOP module %s (%s).",
            module.metadata.display_name,
            name,
        )

        return module

    def register_many(
        self,
        modules: Iterable[PlatformModule],
        *,
        replace: bool = False,
    ) -> None:
        """Register multiple module instances."""

        for module in modules:
            self.register(module, replace=replace)

    def contains(self, module_name: str) -> bool:
        """Return whether a module is registered."""

        with self._lock:
            return module_name in self._modules

    def get(self, module_name: str) -> PlatformModule:
        """Return a registered module instance."""

        with self._lock:
            record = self._modules.get(module_name)

        if record is None:
            raise ModuleError(
                f"Module '{module_name}' is not registered."
            )

        return record.module

    def enable(self, module_name: str) -> None:
        """Enable a registered module before startup."""

        with self._lock:
            record = self._require_record(module_name)

            if self._running:
                raise ModuleLifecycleError(
                    "Modules cannot be enabled while the manager is running."
                )

            record.enabled = True
            record.state = ModuleState.DISCOVERED
            record.last_error = None

    def disable(self, module_name: str) -> None:
        """Disable a registered module before startup."""

        with self._lock:
            record = self._require_record(module_name)

            if self._running:
                raise ModuleLifecycleError(
                    "Modules cannot be disabled while the manager is running."
                )

            record.enabled = False
            record.state = ModuleState.DISABLED
            record.last_error = None

    async def start(self) -> None:
        """
        Configure, register, and start all enabled modules.

        Dependencies are resolved before any module lifecycle work begins.
        """

        with self._lock:
            if self._running:
                return

        startup_order = self._resolve_startup_order()
        context = self._create_context()
        started: list[str] = []

        try:
            for module_name in startup_order:
                record = self._require_record(module_name)

                await self._run_module_step(
                    record,
                    ModuleState.REGISTERING,
                    "configure",
                    record.module.configure,
                    context,
                )
                await self._run_module_step(
                    record,
                    ModuleState.REGISTERING,
                    "register_services",
                    record.module.register_services,
                    context,
                )
                await self._run_module_step(
                    record,
                    ModuleState.REGISTERING,
                    "register_events",
                    record.module.register_events,
                    context,
                )

                record.state = ModuleState.REGISTERED

            for module_name in startup_order:
                record = self._require_record(module_name)

                await self._run_module_step(
                    record,
                    ModuleState.STARTING,
                    "start",
                    record.module.start,
                    context,
                )

                record.state = ModuleState.RUNNING
                record.last_error = None
                started.append(module_name)

                await self._events.publish_named(
                    "etop.module.started",
                    {
                        "module_name": record.name,
                        "display_name": (
                            record.module.metadata.display_name
                        ),
                        "version": record.module.metadata.version,
                    },
                    source="module_manager",
                )

            with self._lock:
                self._startup_order = startup_order
                self._running = True

            logger.info(
                "ETOP module manager started %s module(s).",
                len(startup_order),
            )

        except Exception:
            logger.exception("ETOP module startup failed.")

            await self._rollback_started_modules(
                started,
                context,
            )
            raise

    async def stop(self) -> None:
        """Stop running modules in reverse dependency order."""

        with self._lock:
            if not self._running and not self._startup_order:
                return

            shutdown_order = list(reversed(self._startup_order))

        context = self._create_context()
        failures: list[str] = []

        for module_name in shutdown_order:
            record = self._require_record(module_name)

            if record.state is not ModuleState.RUNNING:
                continue

            record.state = ModuleState.STOPPING

            try:
                await record.module.stop(context)
                record.state = ModuleState.STOPPED

                if self._events.is_running:
                    await self._events.publish_named(
                        "etop.module.stopped",
                        {
                            "module_name": record.name,
                            "display_name": (
                                record.module.metadata.display_name
                            ),
                            "version": record.module.metadata.version,
                        },
                        source="module_manager",
                    )

            except Exception as exc:
                record.state = ModuleState.FAILED
                record.last_error = str(exc)
                failures.append(f"{module_name}: {exc}")
                logger.exception(
                    "Failed stopping ETOP module %s.",
                    module_name,
                )

        with self._lock:
            self._running = False
            self._startup_order.clear()

        if failures:
            raise ModuleLifecycleError(
                "One or more modules failed during shutdown: "
                + "; ".join(failures)
            )

    async def async_close(self) -> None:
        """Kernel-compatible asynchronous cleanup method."""

        await self.stop()

    async def refresh_health(self) -> list[ModuleDiagnostic]:
        """Execute each enabled module health check."""

        context = self._create_context()

        with self._lock:
            records = list(self._modules.values())

        for record in records:
            if not record.enabled:
                record.health = None
                continue

            try:
                record.health = await record.module.health(context)
            except Exception as exc:
                record.health = ModuleHealth(
                    healthy=False,
                    message=str(exc),
                    details={
                        "exception_type": type(exc).__name__,
                    },
                )
                record.last_error = str(exc)

        return self.diagnostics()

    def diagnostics(self) -> list[ModuleDiagnostic]:
        """Return module diagnostics sorted by module name."""

        with self._lock:
            records = list(self._modules.values())

        diagnostics = [
            ModuleDiagnostic(
                name=record.name,
                display_name=record.module.metadata.display_name,
                version=record.module.metadata.version,
                state=record.state,
                enabled=record.enabled,
                dependencies=record.module.metadata.dependencies,
                description=record.module.metadata.description,
                tags=record.module.metadata.tags,
                healthy=(
                    record.health.healthy
                    if record.health is not None
                    else None
                ),
                health_message=(
                    record.health.message
                    if record.health is not None
                    else None
                ),
                last_error=record.last_error,
            )
            for record in records
        ]

        return sorted(
            diagnostics,
            key=lambda item: item.name.lower(),
        )

    def routes(self) -> list[Any]:
        """Collect API routers exposed by enabled modules."""

        routes: list[Any] = []

        with self._lock:
            records = list(self._modules.values())

        for record in records:
            if not record.enabled:
                continue

            routes.extend(record.module.routes())

        return routes

    def discover(
        self,
        package_name: str,
        *,
        class_name: str = "Module",
    ) -> list[PlatformModule]:
        """
        Discover module classes below a Python package.

        A discovered module file may either:

        - expose a class named ``Module`` by default, or
        - expose any concrete PlatformModule subclass when no named class is
          present.

        Discovery does not register modules automatically.
        """

        package = importlib.import_module(package_name)

        if not hasattr(package, "__path__"):
            raise ModuleError(
                f"Package '{package_name}' does not support discovery."
            )

        discovered: list[PlatformModule] = []

        for module_info in pkgutil.walk_packages(
            package.__path__,
            prefix=f"{package.__name__}.",
        ):
            imported = importlib.import_module(module_info.name)

            candidate = getattr(imported, class_name, None)

            if (
                inspect.isclass(candidate)
                and issubclass(candidate, PlatformModule)
                and candidate is not PlatformModule
            ):
                discovered.append(candidate())
                continue

            for value in vars(imported).values():
                if (
                    inspect.isclass(value)
                    and issubclass(value, PlatformModule)
                    and value is not PlatformModule
                    and value.__module__ == imported.__name__
                ):
                    discovered.append(value())

        unique: dict[str, PlatformModule] = {}

        for module in discovered:
            unique[module.metadata.name] = module

        return list(unique.values())

    def _resolve_startup_order(self) -> list[str]:
        """Topologically sort enabled modules by dependency."""

        with self._lock:
            enabled_records = {
                name: record
                for name, record in self._modules.items()
                if record.enabled
            }

        for name, record in enabled_records.items():
            for dependency in record.module.metadata.dependencies:
                dependency_record = enabled_records.get(dependency)

                if dependency_record is None:
                    raise ModuleDependencyError(
                        f"Module '{name}' requires enabled module "
                        f"'{dependency}'."
                    )

        permanent: set[str] = set()
        temporary: set[str] = set()
        ordered: list[str] = []

        def visit(name: str, chain: Sequence[str]) -> None:
            if name in permanent:
                return

            if name in temporary:
                cycle = " -> ".join([*chain, name])
                raise ModuleDependencyError(
                    f"Circular module dependency detected: {cycle}"
                )

            temporary.add(name)
            record = enabled_records[name]

            for dependency in record.module.metadata.dependencies:
                visit(dependency, [*chain, name])

            temporary.remove(name)
            permanent.add(name)
            ordered.append(name)

        for module_name in enabled_records:
            visit(module_name, [])

        return ordered

    async def _run_module_step(
        self,
        record: _ModuleRecord,
        state: ModuleState,
        operation_name: str,
        operation: Any,
        context: ModuleContext,
    ) -> None:
        """Execute one module lifecycle operation."""

        record.state = state
        started = time.perf_counter()

        try:
            result = operation(context)

            if inspect.isawaitable(result):
                await result

            logger.debug(
                "Module %s operation %s completed in %.3f ms.",
                record.name,
                operation_name,
                (time.perf_counter() - started) * 1000,
            )

        except Exception as exc:
            record.state = ModuleState.FAILED
            record.last_error = str(exc)

            raise ModuleLifecycleError(
                f"Module '{record.name}' failed during "
                f"'{operation_name}': {exc}"
            ) from exc

    async def _rollback_started_modules(
        self,
        started: Sequence[str],
        context: ModuleContext,
    ) -> None:
        """Stop modules that successfully started before a failure."""

        for module_name in reversed(started):
            record = self._require_record(module_name)

            try:
                await record.module.stop(context)
                record.state = ModuleState.STOPPED
            except Exception:
                record.state = ModuleState.FAILED
                logger.exception(
                    "Rollback failed for ETOP module %s.",
                    module_name,
                )

    def _create_context(self) -> ModuleContext:
        return ModuleContext(
            services=self._services,
            events=self._events,
            settings=self._settings,
        )

    def _require_record(self, module_name: str) -> _ModuleRecord:
        with self._lock:
            record = self._modules.get(module_name)

        if record is None:
            raise ModuleError(
                f"Module '{module_name}' is not registered."
            )

        return record