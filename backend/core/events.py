from dataclasses import dataclass

from .event_bus import PlatformEvent


@dataclass(slots=True,frozen=True,kw_only=True)
class PlatformStartedEvent(PlatformEvent):
    version: str


@dataclass(slots=True,frozen=True,kw_only=True)
class PlatformStoppedEvent(PlatformEvent):
    version: str


@dataclass(slots=True,frozen=True,kw_only=True)
class ModuleLoadedEvent(PlatformEvent):
    module_name: str


@dataclass(slots=True,frozen=True,kw_only=True)
class ModuleUnloadedEvent(PlatformEvent):
    module_name: str