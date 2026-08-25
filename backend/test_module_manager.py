import asyncio

from core.event_bus import EventBus
from core.module import (
    ModuleContext,
    ModuleHealth,
    ModuleMetadata,
    PlatformModule,
)
from core.module_manager import ModuleManager
from core.service_registry import ServiceRegistry


class DataModule(PlatformModule):
    metadata = ModuleMetadata(
        name="data",
        display_name="Enterprise Data",
        version="1.0.0",
    )

    async def start(self, context: ModuleContext) -> None:
        print("Data module started")

    async def stop(self, context: ModuleContext) -> None:
        print("Data module stopped")


class DashboardModule(PlatformModule):
    metadata = ModuleMetadata(
        name="dashboard",
        display_name="Executive Dashboard",
        version="1.0.0",
        dependencies=("data",),
    )

    async def start(self, context: ModuleContext) -> None:
        print("Dashboard module started")

    async def stop(self, context: ModuleContext) -> None:
        print("Dashboard module stopped")

    async def health(self, context: ModuleContext) -> ModuleHealth:
        return ModuleHealth(
            healthy=True,
            message="Dashboard ready",
        )


async def main() -> None:
    services = ServiceRegistry()
    events = EventBus()

    await events.start()

    manager = ModuleManager(
        services=services,
        events=events,
    )

    manager.register(DashboardModule())
    manager.register(DataModule())

    await manager.start()

    print("Running:", manager.is_running)
    print("Modules:", manager.module_count)

    diagnostics = await manager.refresh_health()

    for item in diagnostics:
        print(
            item.name,
            item.state.value,
            item.healthy,
            item.health_message,
        )

    await manager.stop()
    await events.stop()


if __name__ == "__main__":
    asyncio.run(main())