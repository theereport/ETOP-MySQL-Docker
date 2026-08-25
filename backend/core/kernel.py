"""

ETOP Platform Kernel.

The kernel owns the application lifecycle for the ETOP backend.

Responsibilities:

- Manage platform startup and shutdown
- Own the service registry
- Register foundational platform services
- Run startup and shutdown hooks
- Track platform readiness and health
- Initialize registered singleton services
- Gracefully close synchronous and asynchronous services
- Provide consistent lifecycle diagnostics

The kernel is intentionally independent of FastAPI. FastAPI will later call
the kernel from its lifespan handler, but background jobs, command-line tools,
tests, and future desktop services can use the same kernel directly.
"""

from __future__ import annotations

import inspect
import logging
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from threading import RLock
from typing import Any, TypeVar, cast

from .event_bus import EventBus
from .module_manager import ModuleManager

from .service_registry import (
    ServiceLifetime,
    ServiceRegistry,
    ServiceRegistryError,
    get_service_registry,
)


logger = logging.getLogger(__name__)

T = TypeVar("T")

LifecycleHook = Callable[
    ["ETOPKernel"],
    None | Awaitable[None],
]


class KernelState(StrEnum):
    """Supported ETOP kernel lifecycle states."""

    CREATED = "created"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"


class KernelError(RuntimeError):
    """Base exception for ETOP kernel failures."""


class KernelStateError(KernelError):
    """Raised when a lifecycle operation is invalid for the current state."""

    def __init__(
        self,
        operation: str,
        current_state: KernelState,
    ) -> None:
        self.operation = operation
        self.current_state = current_state

        super().__init__(
            f"Cannot perform kernel operation '{operation}' while the kernel "
            f"is in state '{current_state.value}'."
        )


class KernelStartupError(KernelError):
    """Raised when ETOP fails during startup."""

    def __init__(
        self,
        message: str,
        *,
        cause: Exception | None = None,
    ) -> None:
        self.cause = cause
        super().__init__(message)


class KernelShutdownError(KernelError):
    """Raised when ETOP encounters one or more shutdown failures."""

    def __init__(
        self,
        failures: Sequence["ShutdownFailure"],
    ) -> None:
        self.failures = tuple(failures)

        failure_summary = "; ".join(
            f"{failure.service_name}: {failure.message}"
            for failure in self.failures
        )

        super().__init__(
            f"ETOP shutdown completed with {len(self.failures)} failure(s): "
            f"{failure_summary}"
        )


@dataclass(frozen=True, slots=True)
class ShutdownFailure:
    """Information about a service or hook that failed during shutdown."""

    service_name: str
    operation: str
    message: str
    exception_type: str


@dataclass(frozen=True, slots=True)
class LifecycleTiming:
    """Timing information for a lifecycle step."""

    name: str
    duration_ms: float
    succeeded: bool
    error: str | None = None


@dataclass(slots=True)
class KernelDiagnostics:
    """
    Current ETOP platform lifecycle diagnostics.

    This structure can later be returned by a Control Center or health API.
    """

    state: KernelState = KernelState.CREATED
    version: str = "0.4.1"
    started_at: datetime | None = None
    stopped_at: datetime | None = None
    startup_duration_ms: float | None = None
    shutdown_duration_ms: float | None = None
    last_error: str | None = None
    lifecycle_timings: list[LifecycleTiming] = field(default_factory=list)

    @property
    def is_ready(self) -> bool:
        """Return whether the platform is ready to serve requests."""

        return self.state is KernelState.RUNNING

    @property
    def uptime_seconds(self) -> float | None:
        """Return the current runtime in seconds."""

        if self.started_at is None:
            return None

        end_time = self.stopped_at or datetime.now(UTC)
        return max(
            0.0,
            (end_time - self.started_at).total_seconds(),
        )

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-compatible diagnostic data."""

        return {
            "state": self.state.value,
            "version": self.version,
            "ready": self.is_ready,
            "started_at": (
                self.started_at.isoformat()
                if self.started_at is not None
                else None
            ),
            "stopped_at": (
                self.stopped_at.isoformat()
                if self.stopped_at is not None
                else None
            ),
            "startup_duration_ms": self.startup_duration_ms,
            "shutdown_duration_ms": self.shutdown_duration_ms,
            "uptime_seconds": self.uptime_seconds,
            "last_error": self.last_error,
            "lifecycle_timings": [
                {
                    "name": timing.name,
                    "duration_ms": timing.duration_ms,
                    "succeeded": timing.succeeded,
                    "error": timing.error,
                }
                for timing in self.lifecycle_timings
            ],
        }


class ETOPKernel:
    """
    ETOP platform lifecycle coordinator.

    Example:

        kernel = ETOPKernel()

        kernel.add_startup_hook(register_platform_services)
        kernel.add_startup_hook(load_modules)

        await kernel.start()

        if kernel.is_ready:
            ...

        await kernel.stop()
    """

    def __init__(
        self,
        *,
        service_registry: ServiceRegistry | None = None,
        version: str = "0.4.1",
        freeze_registry_after_startup: bool = True,
    ) -> None:
        self._service_registry = service_registry or get_service_registry()
        self._diagnostics = KernelDiagnostics(version=version)

        self._startup_hooks: list[LifecycleHook] = []
        self._shutdown_hooks: list[LifecycleHook] = []

        self._freeze_registry_after_startup = freeze_registry_after_startup

        self._state_lock = RLock()
        self._startup_completed = False
        self._shutdown_completed = False

    @property
    def services(self) -> ServiceRegistry:
        """Return the kernel-owned service registry."""

        return self._service_registry

    @property
    def state(self) -> KernelState:
        """Return the current lifecycle state."""

        return self._diagnostics.state

    @property
    def diagnostics(self) -> KernelDiagnostics:
        """Return current lifecycle diagnostics."""

        return self._diagnostics

    @property
    def is_ready(self) -> bool:
        """Return whether ETOP is ready to serve application requests."""

        return self._diagnostics.is_ready

    @property
    def version(self) -> str:
        """Return the current ETOP platform version."""

        return self._diagnostics.version

    def add_startup_hook(
        self,
        hook: LifecycleHook,
        *,
        prepend: bool = False,
    ) -> None:
        """
        Register a startup hook.

        Startup hooks execute in registration order unless prepended.
        """

        self._validate_hook(hook)

        if prepend:
            self._startup_hooks.insert(0, hook)
        else:
            self._startup_hooks.append(hook)

    def add_shutdown_hook(
        self,
        hook: LifecycleHook,
        *,
        prepend: bool = False,
    ) -> None:
        """
        Register a shutdown hook.

        Shutdown hooks execute in reverse registration order so dependencies
        are normally stopped before the services they depend upon.
        """

        self._validate_hook(hook)

        if prepend:
            self._shutdown_hooks.insert(0, hook)
        else:
            self._shutdown_hooks.append(hook)

    def register_instance(
        self,
        key: str | type[T],
        instance: T,
        *,
        replace: bool = False,
        metadata: Mapping[str, Any] | None = None,
    ) -> T:
        """Register an existing service through the kernel."""

        return self._service_registry.register_instance(
            key,
            instance,
            replace=replace,
            metadata=metadata,
        )

    def register_singleton(
        self,
        key: str | type[T],
        factory: Callable[..., T] | None = None,
        *,
        implementation_type: type[T] | None = None,
        replace: bool = False,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        """Register a singleton service through the kernel."""

        self._service_registry.register_singleton(
            key,
            factory,
            implementation_type=implementation_type,
            replace=replace,
            metadata=metadata,
        )

    def register_transient(
        self,
        key: str | type[T],
        factory: Callable[..., T] | None = None,
        *,
        implementation_type: type[T] | None = None,
        replace: bool = False,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        """Register a transient service through the kernel."""

        self._service_registry.register_transient(
            key,
            factory,
            implementation_type=implementation_type,
            replace=replace,
            metadata=metadata,
        )

    def resolve(self, service_type: type[T]) -> T:
        """Resolve a typed service from the platform registry."""

        return self._service_registry.resolve(service_type)

    def resolve_named(self, service_name: str) -> Any:
        """Resolve a named service from the platform registry."""

        return self._service_registry.resolve_named(service_name)

    async def start(self) -> None:
        """
        Start the ETOP platform.

        Startup sequence:

        1. Validate lifecycle state
        2. Register the kernel itself
        3. Execute startup hooks
        4. Initialize eager singleton services
        5. Start foundational platform services
        6. Freeze the service registry
        7. Mark ETOP as ready
        """

        with self._state_lock:
            if self.state is KernelState.RUNNING:
                logger.debug("ETOP kernel is already running.")
                return

            if self.state not in {
                KernelState.CREATED,
                KernelState.STOPPED,
                KernelState.FAILED,
            }:
                raise KernelStateError("start", self.state)

            self._set_state(KernelState.STARTING)
            self._diagnostics.last_error = None
            self._diagnostics.stopped_at = None
            self._diagnostics.lifecycle_timings.clear()
            self._shutdown_completed = False

        start_time = time.perf_counter()

        logger.info(
            "Starting ETOP platform version %s.",
            self.version,
        )

        try:
            await self._run_timed_step(
                "register_kernel_services",
                self._register_kernel_services,
            )

            await self._run_hooks(
                self._startup_hooks,
                phase_name="startup_hook",
                reverse=False,
            )

            await self._run_timed_step(
                "initialize_eager_singletons",
                self._initialize_eager_singletons,
            )

            await self._run_timed_step(
                "start_platform_services",
                self._start_platform_services,
            )

            if self._freeze_registry_after_startup:
                await self._run_timed_step(
                    "freeze_service_registry",
                    self._freeze_registry,
                )

            elapsed_ms = (time.perf_counter() - start_time) * 1000

            with self._state_lock:
                self._diagnostics.started_at = datetime.now(UTC)
                self._diagnostics.startup_duration_ms = round(elapsed_ms, 3)
                self._startup_completed = True
                self._set_state(KernelState.RUNNING)

            logger.info(
                "ETOP platform started successfully in %.3f ms with %s "
                "registered services.",
                elapsed_ms,
                len(self._service_registry),
            )

        except Exception as exc:
            elapsed_ms = (time.perf_counter() - start_time) * 1000

            with self._state_lock:
                self._diagnostics.startup_duration_ms = round(elapsed_ms, 3)
                self._diagnostics.last_error = str(exc)
                self._set_state(KernelState.FAILED)

            logger.exception(
                "ETOP platform startup failed after %.3f ms.",
                elapsed_ms,
            )

            await self._rollback_failed_startup()

            if isinstance(exc, KernelStartupError):
                raise

            raise KernelStartupError(
                f"ETOP platform startup failed: {exc}",
                cause=exc,
            ) from exc

    async def stop(
        self,
        *,
        raise_on_error: bool = False,
    ) -> None:
        """
        Stop the ETOP platform gracefully.

        Shutdown sequence:

        1. Mark the platform as stopping
        2. Execute shutdown hooks in reverse order
        3. Close initialized singleton services
        4. Mark the platform as stopped

        Args:
            raise_on_error:
                Raise KernelShutdownError when cleanup failures occur.
                The default logs failures and completes shutdown.
        """

        with self._state_lock:
            if self.state in {
                KernelState.CREATED,
                KernelState.STOPPED,
            }:
                logger.debug(
                    "ETOP kernel does not require shutdown from state %s.",
                    self.state.value,
                )
                return

            if self.state is KernelState.STOPPING:
                logger.debug("ETOP kernel shutdown is already in progress.")
                return

            if self._shutdown_completed:
                return

            self._set_state(KernelState.STOPPING)

        start_time = time.perf_counter()
        failures: list[ShutdownFailure] = []

        logger.info("Stopping ETOP platform.")

        hook_failures = await self._run_shutdown_hooks()
        failures.extend(hook_failures)

        service_failures = await self._shutdown_services()
        failures.extend(service_failures)

        elapsed_ms = (time.perf_counter() - start_time) * 1000

        with self._state_lock:
            self._diagnostics.stopped_at = datetime.now(UTC)
            self._diagnostics.shutdown_duration_ms = round(elapsed_ms, 3)
            self._shutdown_completed = True
            self._set_state(KernelState.STOPPED)

            if failures:
                self._diagnostics.last_error = (
                    f"Shutdown completed with {len(failures)} failure(s)."
                )

        if failures:
            for failure in failures:
                logger.error(
                    "Shutdown failure for %s during %s: %s",
                    failure.service_name,
                    failure.operation,
                    failure.message,
                )

            logger.warning(
                "ETOP platform stopped in %.3f ms with %s cleanup failure(s).",
                elapsed_ms,
                len(failures),
            )

            if raise_on_error:
                raise KernelShutdownError(failures)
        else:
            logger.info(
                "ETOP platform stopped successfully in %.3f ms.",
                elapsed_ms,
            )

    async def restart(self) -> None:
        """Stop and restart the ETOP platform."""

        await self.stop()

        if self._service_registry.is_frozen:
            self._service_registry.unfreeze()

        await self.start()

    def health(self) -> dict[str, Any]:
        """
        Return platform health information suitable for an API response.
        """

        service_descriptions = self._service_registry.describe()

        singleton_count = sum(
            1
            for service in service_descriptions
            if service.lifetime is ServiceLifetime.SINGLETON
        )

        transient_count = sum(
            1
            for service in service_descriptions
            if service.lifetime is ServiceLifetime.TRANSIENT
        )

        initialized_count = sum(
            1
            for service in service_descriptions
            if service.initialized
        )

        module_manager = self._service_registry.try_resolve(
            ModuleManager
        )

        module_diagnostics = (
            module_manager.diagnostics()
            if module_manager is not None
            else []
        )

        return {
            "platform": "ETOP",
            **self._diagnostics.to_dict(),
            "services": {
                "registered": len(service_descriptions),
                "singletons": singleton_count,
                "transients": transient_count,
                "initialized": initialized_count,
                "registry_frozen": self._service_registry.is_frozen,
            },
            "modules": {
                "registered": len(module_diagnostics),
                "running": sum(
                    1
                    for module in module_diagnostics
                    if module.state.value == "running"
                ),
                "failed": sum(
                    1
                    for module in module_diagnostics
                    if module.state.value == "failed"
                ),
                "items": [
                    {
                        "name": module.name,
                        "display_name": module.display_name,
                        "version": module.version,
                        "state": module.state.value,
                        "enabled": module.enabled,
                        "dependencies": list(module.dependencies),
                        "healthy": module.healthy,
                        "health_message": module.health_message,
                        "last_error": module.last_error,
                    }
                    for module in module_diagnostics
                ],
            },
        }

    async def _register_kernel_services(self) -> None:
        """Register core kernel services if they are not already present."""

        if self._service_registry.is_frozen:
            self._service_registry.unfreeze()

        if not self._service_registry.contains(ETOPKernel):
            self._service_registry.register_instance(
                ETOPKernel,
                self,
                metadata={
                    "component": "platform_core",
                    "version": self.version,
                },
            )

        if not self._service_registry.contains(ServiceRegistry):
            self._service_registry.register_instance(
                ServiceRegistry,
                self._service_registry,
                metadata={
                    "component": "platform_core",
                },
            )

        if not self._service_registry.contains(EventBus):
            self._service_registry.register_singleton(
                EventBus,
                implementation_type=EventBus,
                metadata={
                    "component": "platform_core",
                    "eager": True,
                },
            )

        if not self._service_registry.contains(ModuleManager):
            self._service_registry.register_singleton(
                ModuleManager,
                lambda registry: ModuleManager(
                    services=registry.resolve(ServiceRegistry),
                    events=registry.resolve(EventBus),
                ),
                metadata={
                    "component": "platform_core",
                    "eager": True,
                },
            )

        if not self._service_registry.contains("etop.kernel"):
            self._service_registry.register_alias(
                "etop.kernel",
                ETOPKernel,
            )

        if not self._service_registry.contains("etop.services"):
            self._service_registry.register_alias(
                "etop.services",
                ServiceRegistry,
            )

        if not self._service_registry.contains("etop.events"):
            self._service_registry.register_alias(
                "etop.events",
                EventBus,
            )

        if not self._service_registry.contains("etop.modules"):
            self._service_registry.register_alias(
                "etop.modules",
                ModuleManager,
            )

    async def _initialize_eager_singletons(self) -> None:
        """
        Initialize singleton services marked for eager startup.

        Eager initialization is handled by the service registry so original
        type and string registration keys are preserved.
        """

        try:
            initialized_keys = (
                self._service_registry.initialize_eager_singletons()
            )

            for service_key in initialized_keys:
                logger.debug(
                    "Eagerly initialized service %s.",
                    self._format_service_key(service_key),
                )

        except ServiceRegistryError as exc:
            raise KernelStartupError(
                f"Unable to initialize eager services: {exc}",
                cause=exc,
            ) from exc

    async def _start_platform_services(self) -> None:
        """
        Start foundational services in dependency order.

        The EventBus must start before the ModuleManager because modules may
        publish lifecycle events while they start.
        """

        event_bus = self._service_registry.try_resolve(EventBus)

        if event_bus is not None and not event_bus.is_running:
            await event_bus.start()

        module_manager = self._service_registry.try_resolve(ModuleManager)

        if module_manager is not None and not module_manager.is_running:
            await module_manager.start()

    async def _freeze_registry(self) -> None:
        """Freeze the service registry after successful startup."""

        if not self._service_registry.is_frozen:
            self._service_registry.freeze()

    async def _run_hooks(
        self,
        hooks: Sequence[LifecycleHook],
        *,
        phase_name: str,
        reverse: bool,
    ) -> None:
        """Execute lifecycle hooks with diagnostics."""

        hook_sequence = list(hooks)

        if reverse:
            hook_sequence.reverse()

        for index, hook in enumerate(hook_sequence, start=1):
            hook_name = self._get_callable_name(hook)
            step_name = f"{phase_name}:{index}:{hook_name}"

            await self._run_timed_step(
                step_name,
                lambda current_hook=hook: self._invoke_hook(current_hook),
            )

    async def _run_shutdown_hooks(self) -> list[ShutdownFailure]:
        """Execute shutdown hooks while collecting failures."""

        failures: list[ShutdownFailure] = []

        for hook in reversed(self._shutdown_hooks):
            hook_name = self._get_callable_name(hook)
            start_time = time.perf_counter()

            try:
                await self._invoke_hook(hook)

                self._diagnostics.lifecycle_timings.append(
                    LifecycleTiming(
                        name=f"shutdown_hook:{hook_name}",
                        duration_ms=round(
                            (time.perf_counter() - start_time) * 1000,
                            3,
                        ),
                        succeeded=True,
                    )
                )
            except Exception as exc:
                self._diagnostics.lifecycle_timings.append(
                    LifecycleTiming(
                        name=f"shutdown_hook:{hook_name}",
                        duration_ms=round(
                            (time.perf_counter() - start_time) * 1000,
                            3,
                        ),
                        succeeded=False,
                        error=str(exc),
                    )
                )

                failures.append(
                    ShutdownFailure(
                        service_name=hook_name,
                        operation="shutdown_hook",
                        message=str(exc),
                        exception_type=type(exc).__name__,
                    )
                )

                logger.exception(
                    "ETOP shutdown hook failed: %s",
                    hook_name,
                )

        return failures

    async def _shutdown_services(self) -> list[ShutdownFailure]:
        """
        Shut down initialized singleton services in reverse registration order.
        """

        failures: list[ShutdownFailure] = []

        descriptors = list(self._service_registry.descriptors())
        descriptors.reverse()

        for descriptor in descriptors:
            instance = descriptor.instance

            if instance is None:
                continue

            if instance is self:
                continue

            if instance is self._service_registry:
                continue

            service_name = self._format_service_key(descriptor.key)

            failure = await self._shutdown_service_instance(
                service_name,
                instance,
            )

            if failure is not None:
                failures.append(failure)

        return failures

    async def _shutdown_service_instance(
        self,
        service_name: str,
        instance: Any,
    ) -> ShutdownFailure | None:
        """
        Execute the first supported cleanup method on a service.

        Supported methods, in order:

        - async_close
        - close
        - shutdown
        - stop
    """

        cleanup_methods = (
            "async_close",
            "close",
            "shutdown",
            "stop",
        )

        for method_name in cleanup_methods:
            method = getattr(instance, method_name, None)

            if not callable(method):
                continue

            start_time = time.perf_counter()

            try:
                result = method()

                if inspect.isawaitable(result):
                    await cast(Awaitable[Any], result)

                self._diagnostics.lifecycle_timings.append(
                    LifecycleTiming(
                        name=f"service_shutdown:{service_name}:{method_name}",
                        duration_ms=round(
                            (time.perf_counter() - start_time) * 1000,
                            3,
                        ),
                        succeeded=True,
                    )
                )

                logger.debug(
                    "Shut down service %s using %s.",
                    service_name,
                    method_name,
                )

                return None

            except Exception as exc:
                self._diagnostics.lifecycle_timings.append(
                    LifecycleTiming(
                        name=f"service_shutdown:{service_name}:{method_name}",
                        duration_ms=round(
                            (time.perf_counter() - start_time) * 1000,
                            3,
                        ),
                        succeeded=False,
                        error=str(exc),
                    )
                )

                logger.exception(
                    "Failed to shut down service %s using %s.",
                    service_name,
                    method_name,
                )

                return ShutdownFailure(
                    service_name=service_name,
                    operation=method_name,
                    message=str(exc),
                    exception_type=type(exc).__name__,
                )

        return None

    async def _rollback_failed_startup(self) -> None:
        """
        Attempt cleanup after a partial startup failure.

        Rollback failures are logged but do not replace the startup exception.
        """

        logger.warning("Rolling back partially started ETOP services.")

        try:
            if self._service_registry.is_frozen:
                self._service_registry.unfreeze()

            await self._run_shutdown_hooks()
            await self._shutdown_services()
        except Exception:
            logger.exception("ETOP startup rollback encountered an error.")

    async def _run_timed_step(
        self,
        step_name: str,
        operation: Callable[[], Any | Awaitable[Any]],
    ) -> Any:
        """Execute and time one lifecycle operation."""

        start_time = time.perf_counter()

        try:
            result = operation()

            if inspect.isawaitable(result):
                result = await cast(Awaitable[Any], result)

            elapsed_ms = (time.perf_counter() - start_time) * 1000

            self._diagnostics.lifecycle_timings.append(
                LifecycleTiming(
                    name=step_name,
                    duration_ms=round(elapsed_ms, 3),
                    succeeded=True,
                )
            )

            logger.debug(
                "Kernel lifecycle step %s completed in %.3f ms.",
                step_name,
                elapsed_ms,
            )

            return result

        except Exception as exc:
            elapsed_ms = (time.perf_counter() - start_time) * 1000

            self._diagnostics.lifecycle_timings.append(
                LifecycleTiming(
                    name=step_name,
                    duration_ms=round(elapsed_ms, 3),
                    succeeded=False,
                    error=str(exc),
                )
            )

            logger.exception(
                "Kernel lifecycle step %s failed after %.3f ms.",
                step_name,
                elapsed_ms,
            )

            raise

    async def _invoke_hook(
        self,
        hook: LifecycleHook,
    ) -> None:
        """Execute a synchronous or asynchronous lifecycle hook."""

        result = hook(self)

        if inspect.isawaitable(result):
            await cast(Awaitable[None], result)

    def _set_state(self, state: KernelState) -> None:
        """Set the lifecycle state and write a debug log."""

        previous_state = self._diagnostics.state
        self._diagnostics.state = state

        logger.debug(
            "ETOP kernel state changed from %s to %s.",
            previous_state.value,
            state.value,
        )

    @staticmethod
    def _validate_hook(hook: LifecycleHook) -> None:
        """Validate lifecycle hook registration."""

        if not callable(hook):
            raise TypeError("Lifecycle hook must be callable.")

    @staticmethod
    def _get_callable_name(callback: Callable[..., Any]) -> str:
        """Return a readable callback name."""

        return getattr(
            callback,
            "__qualname__",
            getattr(callback, "__name__", callback.__class__.__name__),
        )

    @staticmethod
    def _format_service_key(key: str | type[Any]) -> str:
        """Format a service key without importing registry internals."""

        if isinstance(key, str):
            return key

        return f"{key.__module__}.{key.__qualname__}"


_default_kernel: ETOPKernel | None = None
_default_kernel_lock = RLock()


def get_kernel() -> ETOPKernel:
    """
    Return the process-level ETOP kernel.

    The kernel is created lazily so importing core modules has no startup
    side effects.
    """

    global _default_kernel

    with _default_kernel_lock:
        if _default_kernel is None:
            _default_kernel = ETOPKernel()

        return _default_kernel


def reset_kernel(
    *,
    service_registry: ServiceRegistry | None = None,
    version: str = "0.4.1",
) -> ETOPKernel:
    """
    Replace the process-level ETOP kernel.

    Intended for tests and controlled development reloads. Callers should stop
    the existing kernel before resetting it.
    """

    global _default_kernel

    with _default_kernel_lock:
        _default_kernel = ETOPKernel(
            service_registry=service_registry,
            version=version,
        )

        return _default_kernel