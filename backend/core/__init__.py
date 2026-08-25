"""
ETOP platform core exports.
"""

from .kernel import (
    ETOPKernel,
    KernelDiagnostics,
    KernelError,
    KernelShutdownError,
    KernelStartupError,
    KernelState,
    KernelStateError,
    LifecycleTiming,
    ShutdownFailure,
    get_kernel,
    reset_kernel,
)
from .service_registry import (
    CircularDependencyError,
    ServiceAlreadyRegisteredError,
    ServiceLifetime,
    ServiceNotRegisteredError,
    ServiceRegistry,
    ServiceRegistryError,
    ServiceResolutionError,
    get_service_registry,
    reset_default_service_registry,
)

from .event_bus import (
    EventBus,
    EventBusError,
    EventBusStoppedError,
    EventHandlerResult,
    EventHistoryEntry,
    EventPublicationError,
    EventPublicationResult,
    EventSubscription,
    InvalidSubscriptionError,
    NamedPlatformEvent,
    PlatformEvent,
)

from .events import (
    ModuleLoadedEvent,
    ModuleUnloadedEvent,
    PlatformStartedEvent,
    PlatformStoppedEvent,
)

from .module import (
    ModuleContext,
    ModuleDependencyError,
    ModuleDiagnostic,
    ModuleError,
    ModuleHealth,
    ModuleLifecycleError,
    ModuleMetadata,
    ModuleState,
    PlatformModule,
)

from .module_discovery import (
    ModuleDiscoveryFailure,
    ModuleDiscoveryResult,
    discover_platform_modules,
)

from .module_manager import ModuleManager




__all__ = [
    "CircularDependencyError",
    "ETOPKernel",
    "KernelDiagnostics",
    "KernelError",
    "KernelShutdownError",
    "KernelStartupError",
    "KernelState",
    "KernelStateError",
    "LifecycleTiming",
    "ServiceAlreadyRegisteredError",
    "ServiceLifetime",
    "ServiceNotRegisteredError",
    "ServiceRegistry",
    "ServiceRegistryError",
    "ServiceResolutionError",
    "ShutdownFailure",
    "get_kernel",
    "get_service_registry",
    "reset_default_service_registry",
    "reset_kernel",
    "EventBus",
    "EventBusError",
    "EventBusStoppedError",
    "EventHandlerResult",
    "EventHistoryEntry",
    "EventPublicationError",
    "EventPublicationResult",
    "EventSubscription",
    "InvalidSubscriptionError",
    "NamedPlatformEvent",
    "PlatformEvent",
    "ModuleContext",
    "ModuleDependencyError",
    "ModuleDiagnostic",
    "ModuleError",
    "ModuleHealth",
    "ModuleLifecycleError",
    "ModuleLoadedEvent",
    "ModuleManager",
    "ModuleMetadata",
    "ModuleState",
    "ModuleUnloadedEvent",
    "PlatformModule",
    "PlatformStartedEvent",
    "PlatformStoppedEvent",
    "ModuleDiscoveryFailure",
    "ModuleDiscoveryResult",
    "discover_platform_modules",
]