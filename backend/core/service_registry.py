"""
ETOP Platform Service Registry.

The service registry provides a centralized dependency-registration and
resolution mechanism for the ETOP platform.

Platform services and module services can be registered as:

- Existing instances
- Singleton factories
- Transient factories
- Aliases

The registry intentionally avoids importing FastAPI or business-specific
modules. It is a platform-level dependency that can be reused by API routes,
background jobs, automation workflows, intelligence engines, and tests.
"""

from __future__ import annotations

import inspect
import logging
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from threading import RLock
from typing import Any, Generic, TypeVar, cast


logger = logging.getLogger(__name__)

T = TypeVar("T")
ServiceKey = str | type[Any]
ServiceFactory = Callable[..., Any]


class ServiceLifetime(StrEnum):
    """Supported service lifetimes."""

    SINGLETON = "singleton"
    TRANSIENT = "transient"


class ServiceRegistryError(RuntimeError):
    """Base exception for service-registry failures."""


class ServiceAlreadyRegisteredError(ServiceRegistryError):
    """Raised when a service key is registered more than once."""

    def __init__(self, key: ServiceKey) -> None:
        self.key = key
        super().__init__(f"Service is already registered: {format_service_key(key)}")


class ServiceNotRegisteredError(ServiceRegistryError):
    """Raised when a requested service has not been registered."""

    def __init__(self, key: ServiceKey) -> None:
        self.key = key
        super().__init__(f"Service is not registered: {format_service_key(key)}")


class ServiceResolutionError(ServiceRegistryError):
    """Raised when a registered service cannot be created or resolved."""

    def __init__(
        self,
        key: ServiceKey,
        message: str,
        *,
        cause: Exception | None = None,
    ) -> None:
        self.key = key
        self.cause = cause
        super().__init__(
            f"Unable to resolve service {format_service_key(key)}: {message}"
        )


class CircularDependencyError(ServiceResolutionError):
    """Raised when service factories form a circular dependency."""

    def __init__(self, dependency_chain: list[ServiceKey]) -> None:
        self.dependency_chain = dependency_chain

        chain_text = " -> ".join(
            format_service_key(key) for key in dependency_chain
        )

        super().__init__(
            dependency_chain[-1],
            f"Circular dependency detected: {chain_text}",
        )


@dataclass(slots=True)
class ServiceDescriptor(Generic[T]):
    """
    Registration metadata for one service.

    Attributes:
        key:
            Registry key used to resolve the service.
        lifetime:
            Singleton or transient.
        factory:
            Callable used to construct the service.
        instance:
            Existing or cached singleton instance.
        implementation_type:
            Optional implementation class for diagnostics.
        metadata:
            Optional module or operational metadata.
    """

    key: ServiceKey
    lifetime: ServiceLifetime
    factory: ServiceFactory | None = None
    instance: T | None = None
    implementation_type: type[Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_initialized(self) -> bool:
        """Return whether a singleton instance currently exists."""

        return self.instance is not None

    @property
    def display_name(self) -> str:
        """Return a human-readable service name."""

        return format_service_key(self.key)


@dataclass(frozen=True, slots=True)
class ServiceRegistrationInfo:
    """Read-only service metadata suitable for diagnostics endpoints."""

    key: str
    lifetime: ServiceLifetime
    implementation: str | None
    initialized: bool
    metadata: Mapping[str, Any]


def format_service_key(key: ServiceKey) -> str:
    """Convert a service key into a readable value."""

    if isinstance(key, str):
        return key

    return f"{key.__module__}.{key.__qualname__}"


class ServiceRegistry:
    """
    Thread-safe ETOP dependency registry.

    A factory may accept either:

    - No arguments
    - One positional argument containing this registry

    Examples:

        registry.register_instance(DatabaseSettings, settings)

        registry.register_singleton(
            CustomerRepository,
            lambda services: CustomerRepository(
                database=services.resolve(DatabaseService)
            ),
        )

        registry.register_transient(
            CustomerApplicationService,
            lambda services: CustomerApplicationService(
                repository=services.resolve(CustomerRepository)
            ),
        )
    """

    def __init__(self) -> None:
        self._services: dict[ServiceKey, ServiceDescriptor[Any]] = {}
        self._aliases: dict[ServiceKey, ServiceKey] = {}
        self._resolution_stack: list[ServiceKey] = []
        self._lock = RLock()
        self._is_frozen = False

    @property
    def is_frozen(self) -> bool:
        """
        Return whether registrations are locked.

        Resolving services remains allowed after freezing.
        """

        return self._is_frozen

    def freeze(self) -> None:
        """
        Prevent additional service registrations.

        The ETOP kernel can call this after startup so modules cannot
        accidentally mutate the service graph at runtime.
        """

        with self._lock:
            self._is_frozen = True

        logger.info("Service registry frozen with %s services.", len(self))

    def unfreeze(self) -> None:
        """
        Allow registrations again.

        Intended primarily for controlled reloads and automated tests.
        """

        with self._lock:
            self._is_frozen = False

        logger.warning("Service registry has been unfrozen.")

    def register_instance(
        self,
        key: ServiceKey,
        instance: T,
        *,
        replace: bool = False,
        metadata: Mapping[str, Any] | None = None,
    ) -> T:
        """
        Register an existing singleton instance.

        Args:
            key:
                Interface type, implementation type, or string service key.
            instance:
                Existing service instance.
            replace:
                Replace an existing registration when True.
            metadata:
                Optional diagnostic information.

        Returns:
            The registered instance.
        """

        if instance is None:
            raise ValueError("A registered service instance cannot be None.")

        descriptor = ServiceDescriptor[T](
            key=key,
            lifetime=ServiceLifetime.SINGLETON,
            instance=instance,
            implementation_type=type(instance),
            metadata=dict(metadata or {}),
        )

        self._register_descriptor(descriptor, replace=replace)
        return instance

    def register_singleton(
        self,
        key: ServiceKey,
        factory: ServiceFactory | None = None,
        *,
        implementation_type: type[T] | None = None,
        replace: bool = False,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        """
        Register a lazily created singleton.

        Supply either a factory or an implementation type.

        When only an implementation type is supplied, the registry creates it
        by inspecting its constructor type annotations.
        """

        resolved_factory = self._prepare_factory(
            key=key,
            factory=factory,
            implementation_type=implementation_type,
        )

        descriptor = ServiceDescriptor[T](
            key=key,
            lifetime=ServiceLifetime.SINGLETON,
            factory=resolved_factory,
            implementation_type=implementation_type,
            metadata=dict(metadata or {}),
        )

        self._register_descriptor(descriptor, replace=replace)

    def register_transient(
        self,
        key: ServiceKey,
        factory: ServiceFactory | None = None,
        *,
        implementation_type: type[T] | None = None,
        replace: bool = False,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        """
        Register a service that is created on every resolution.

        Supply either a factory or an implementation type.
        """

        resolved_factory = self._prepare_factory(
            key=key,
            factory=factory,
            implementation_type=implementation_type,
        )

        descriptor = ServiceDescriptor[T](
            key=key,
            lifetime=ServiceLifetime.TRANSIENT,
            factory=resolved_factory,
            implementation_type=implementation_type,
            metadata=dict(metadata or {}),
        )

        self._register_descriptor(descriptor, replace=replace)

    def register_alias(
        self,
        alias: ServiceKey,
        target: ServiceKey,
        *,
        replace: bool = False,
    ) -> None:
        """
        Register an alternate key for an existing or future service.

        Example:

            registry.register_alias("database", DatabaseService)
        """

        with self._lock:
            self._ensure_mutable()

            if alias == target:
                raise ValueError("A service alias cannot reference itself.")

            if not replace and (alias in self._aliases or alias in self._services):
                raise ServiceAlreadyRegisteredError(alias)

            self._aliases[alias] = target

        logger.debug(
            "Registered service alias %s -> %s.",
            format_service_key(alias),
            format_service_key(target),
        )

    def resolve(self, key: type[T]) -> T:
        """Resolve a typed service."""

        return cast(T, self._resolve(key))

    def resolve_named(self, key: str) -> Any:
        """Resolve a service registered with a string key."""

        return self._resolve(key)

    def try_resolve(
        self,
        key: type[T],
        default: T | None = None,
    ) -> T | None:
        """Resolve a service or return a default when it is not registered."""

        try:
            return self.resolve(key)
        except ServiceNotRegisteredError:
            return default

    def try_resolve_named(
        self,
        key: str,
        default: Any = None,
    ) -> Any:
        """Resolve a named service or return a default value."""

        try:
            return self.resolve_named(key)
        except ServiceNotRegisteredError:
            return default

    def resolve_all(self, service_type: type[T]) -> list[T]:
        """
        Resolve all registrations compatible with a type.

        This supports provider discovery, such as retrieving every registered
        MetricsProvider implementation.
        """

        matching_keys: list[ServiceKey] = []

        with self._lock:
            for key, descriptor in self._services.items():
                implementation = descriptor.implementation_type

                if isinstance(key, type) and issubclass(key, service_type):
                    matching_keys.append(key)
                    continue

                if implementation is not None and issubclass(
                    implementation,
                    service_type,
                ):
                    matching_keys.append(key)
                    continue

                if descriptor.instance is not None and isinstance(
                    descriptor.instance,
                    service_type,
                ):
                    matching_keys.append(key)

        return [cast(T, self._resolve(key)) for key in matching_keys]

    def contains(self, key: ServiceKey) -> bool:
        """Return whether a key or alias has been registered."""

        with self._lock:
            return key in self._services or key in self._aliases

    def remove(self, key: ServiceKey) -> bool:
        """
        Remove a service or alias.

        Returns True if a registration was removed.
        """

        with self._lock:
            self._ensure_mutable()

            if key in self._aliases:
                del self._aliases[key]
                logger.debug("Removed service alias %s.", format_service_key(key))
                return True

            if key in self._services:
                del self._services[key]
                logger.debug("Removed service %s.", format_service_key(key))
                return True

            return False

    def clear(self) -> None:
        """Remove all services and aliases."""

        with self._lock:
            self._ensure_mutable()
            self._services.clear()
            self._aliases.clear()
            self._resolution_stack.clear()

        logger.info("Service registry cleared.")

    def registered_keys(self) -> tuple[ServiceKey, ...]:
        """
        Return the original concrete service keys in registration order.

        Unlike describe(), this preserves type-based keys instead of
        converting them into display strings.
        """

        with self._lock:
            return tuple(self._services.keys())

    def descriptors(self) -> tuple[ServiceDescriptor[Any], ...]:
        """
        Return registered service descriptors in registration order.

        This is intended for trusted platform lifecycle components such as
        the ETOP kernel. The returned tuple is a snapshot of the registry's
        descriptor collection; descriptor instances remain live so singleton
        initialization state is visible to the kernel.
        """

        with self._lock:
            return tuple(self._services.values())

    def initialize_eager_singletons(self) -> list[ServiceKey]:
        """
        Initialize singleton services marked with metadata {"eager": True}.

        Returns:
            Original service keys initialized during this call.
        """

        initialized_keys: list[ServiceKey] = []

        for descriptor in self.descriptors():
            if descriptor.lifetime is not ServiceLifetime.SINGLETON:
                continue

            if descriptor.instance is not None:
                continue

            if not bool(descriptor.metadata.get("eager", False)):
                continue

            self._resolve(descriptor.key)
            initialized_keys.append(descriptor.key)

        return initialized_keys

    def describe(self) -> list[ServiceRegistrationInfo]:
        """
        Return service metadata without resolving uninitialized services.

        This can later support the ETOP Control Center.
        """

        with self._lock:
            descriptions = [
                ServiceRegistrationInfo(
                    key=format_service_key(descriptor.key),
                    lifetime=descriptor.lifetime,
                    implementation=(
                        format_service_key(descriptor.implementation_type)
                        if descriptor.implementation_type is not None
                        else None
                    ),
                    initialized=descriptor.is_initialized,
                    metadata=dict(descriptor.metadata),
                )
                for descriptor in self._services.values()
            ]

        return sorted(descriptions, key=lambda item: item.key.lower())

    def shutdown(self) -> None:
        """
        Shut down initialized singleton services in reverse registration order.

        Supported cleanup methods:

        - async_close
        - close
        - shutdown
        - stop

        Async cleanup methods are not executed here because this registry is
        intentionally synchronous. The ETOP kernel will handle asynchronous
        lifecycle shutdown.
        """

        with self._lock:
            descriptors = list(reversed(self._services.values()))

        for descriptor in descriptors:
            instance = descriptor.instance

            if instance is None:
                continue

            for method_name in ("close", "shutdown", "stop"):
                method = getattr(instance, method_name, None)

                if callable(method):
                    try:
                        result = method()

                        if inspect.isawaitable(result):
                            logger.warning(
                                "Skipped asynchronous cleanup method %s on %s. "
                                "The ETOP kernel must await this service.",
                                method_name,
                                descriptor.display_name,
                            )
                        else:
                            logger.debug(
                                "Executed %s for service %s.",
                                method_name,
                                descriptor.display_name,
                            )
                    except Exception:
                        logger.exception(
                            "Service cleanup failed for %s.",
                            descriptor.display_name,
                        )

                    break

    def _register_descriptor(
        self,
        descriptor: ServiceDescriptor[Any],
        *,
        replace: bool,
    ) -> None:
        """Store a service descriptor."""

        with self._lock:
            self._ensure_mutable()

            if not replace and (
                descriptor.key in self._services
                or descriptor.key in self._aliases
            ):
                raise ServiceAlreadyRegisteredError(descriptor.key)

            self._services[descriptor.key] = descriptor

        logger.debug(
            "Registered %s service %s.",
            descriptor.lifetime.value,
            descriptor.display_name,
        )

    def _resolve(self, requested_key: ServiceKey) -> Any:
        """Internal service resolution implementation."""

        with self._lock:
            key = self._resolve_alias(requested_key)

            descriptor = self._services.get(key)
            if descriptor is None:
                raise ServiceNotRegisteredError(requested_key)

            if (
                descriptor.lifetime is ServiceLifetime.SINGLETON
                and descriptor.instance is not None
            ):
                return descriptor.instance

            if key in self._resolution_stack:
                dependency_chain = [*self._resolution_stack, key]
                raise CircularDependencyError(dependency_chain)

            self._resolution_stack.append(key)

            try:
                instance = self._create_instance(descriptor)

                if instance is None:
                    raise ServiceResolutionError(
                        key,
                        "The service factory returned None.",
                    )

                if descriptor.lifetime is ServiceLifetime.SINGLETON:
                    descriptor.instance = instance

                return instance
            finally:
                self._resolution_stack.pop()

    def _resolve_alias(self, requested_key: ServiceKey) -> ServiceKey:
        """Follow aliases while detecting alias loops."""

        key = requested_key
        visited: list[ServiceKey] = []

        while key in self._aliases:
            if key in visited:
                raise CircularDependencyError([*visited, key])

            visited.append(key)
            key = self._aliases[key]

        return key

    def _create_instance(
        self,
        descriptor: ServiceDescriptor[Any],
    ) -> Any:
        """Construct a service using its configured factory."""

        if descriptor.factory is None:
            raise ServiceResolutionError(
                descriptor.key,
                "No service factory or instance is available.",
            )

        try:
            return self._invoke_factory(descriptor.factory)
        except ServiceRegistryError:
            raise
        except Exception as exc:
            logger.exception(
                "Factory failed while creating service %s.",
                descriptor.display_name,
            )
            raise ServiceResolutionError(
                descriptor.key,
                str(exc),
                cause=exc,
            ) from exc

    def _invoke_factory(self, factory: ServiceFactory) -> Any:
        """
        Invoke a factory with zero arguments or the registry as one argument.
        """

        signature = inspect.signature(factory)
        parameters = list(signature.parameters.values())

        required_parameters = [
            parameter
            for parameter in parameters
            if parameter.default is inspect.Parameter.empty
            and parameter.kind
            in (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            )
        ]

        has_varargs = any(
            parameter.kind is inspect.Parameter.VAR_POSITIONAL
            for parameter in parameters
        )

        if not required_parameters and not has_varargs:
            return factory()

        if len(required_parameters) <= 1:
            return factory(self)

        raise TypeError(
            "Service factories must accept zero arguments or one registry "
            f"argument. Factory received {len(required_parameters)} required "
            "positional arguments."
        )

    def _prepare_factory(
        self,
        *,
        key: ServiceKey,
        factory: ServiceFactory | None,
        implementation_type: type[T] | None,
    ) -> ServiceFactory:
        """Validate or generate a service factory."""

        if factory is not None and implementation_type is not None:
            raise ValueError(
                "Provide either factory or implementation_type, not both."
            )

        if factory is not None:
            if not callable(factory):
                raise TypeError("Service factory must be callable.")

            return factory

        if implementation_type is not None:
            return self._build_constructor_factory(implementation_type)

        if isinstance(key, type):
            return self._build_constructor_factory(key)

        raise ValueError(
            "Named service registrations require a factory or "
            "implementation_type."
        )

    def _build_constructor_factory(
        self,
        implementation_type: type[T],
    ) -> ServiceFactory:
        """
        Create a factory using constructor type annotations.

        Constructor parameters without defaults must have concrete type
        annotations registered in the service registry.
        """

        def constructor_factory(registry: ServiceRegistry) -> T:
            signature = inspect.signature(implementation_type.__init__)
            keyword_arguments: dict[str, Any] = {}

            for parameter_name, parameter in signature.parameters.items():
                if parameter_name == "self":
                    continue

                if parameter.kind in (
                    inspect.Parameter.VAR_POSITIONAL,
                    inspect.Parameter.VAR_KEYWORD,
                ):
                    continue

                if parameter.annotation is inspect.Parameter.empty:
                    if parameter.default is not inspect.Parameter.empty:
                        continue

                    raise ServiceResolutionError(
                        implementation_type,
                        (
                            f"Constructor parameter '{parameter_name}' on "
                            f"{implementation_type.__qualname__} requires a "
                            "type annotation or a default value."
                        ),
                    )

                try:
                    keyword_arguments[parameter_name] = registry._resolve(
                        parameter.annotation
                    )
                except ServiceNotRegisteredError:
                    if parameter.default is not inspect.Parameter.empty:
                        continue

                    raise

            return implementation_type(**keyword_arguments)

        return constructor_factory

    def _ensure_mutable(self) -> None:
        """Raise when attempting registration changes after freezing."""

        if self._is_frozen:
            raise ServiceRegistryError(
                "The service registry is frozen and cannot be modified."
            )

    def __contains__(self, key: object) -> bool:
        """Support `key in registry`."""

        if not isinstance(key, (str, type)):
            return False

        return self.contains(key)

    def __len__(self) -> int:
        """Return the number of concrete service registrations."""

        with self._lock:
            return len(self._services)

    def __iter__(self) -> Iterator[ServiceRegistrationInfo]:
        """Iterate over diagnostic registration information."""

        return iter(self.describe())


_default_registry = ServiceRegistry()


def get_service_registry() -> ServiceRegistry:
    """
    Return ETOP's process-level default service registry.

    The platform kernel will eventually own and initialize this registry.
    Tests may create isolated ServiceRegistry instances instead.
    """

    return _default_registry


def reset_default_service_registry() -> ServiceRegistry:
    """
    Replace the process-level registry with a clean instance.

    Intended for test isolation and controlled development reloads.
    """

    global _default_registry

    _default_registry = ServiceRegistry()
    return _default_registry