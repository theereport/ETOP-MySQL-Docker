import asyncio

from core.event_bus import EventBus
from core.kernel import ETOPKernel
from core.module import ModuleContext, ModuleMetadata, PlatformModule
from core.module_manager import ModuleManager
from core.service_registry import ServiceRegistry


class ExampleModule(PlatformModule):
    metadata = ModuleMetadata(
        name="example",
        display_name="Example Module",
        version="1.0.0",
    )

    async def start(self, context: ModuleContext) -> None:
        print("Example module started")

    async def stop(self, context: ModuleContext) -> None:
        print("Example module stopped")


async def register_example_module(kernel: ETOPKernel) -> None:
    manager = kernel.resolve(ModuleManager)
    manager.register(ExampleModule())


async def main() -> None:
    registry = ServiceRegistry()
    kernel = ETOPKernel(service_registry=registry)

    kernel.add_startup_hook(register_example_module)

    await kernel.start()

    event_bus = kernel.resolve(EventBus)
    module_manager = kernel.resolve(ModuleManager)

    print("Kernel ready:", kernel.is_ready)
    print("Event bus running:", event_bus.is_running)
    print("Module manager running:", module_manager.is_running)
    print("Module count:", module_manager.module_count)
    print("Module state:", module_manager.diagnostics()[0].state.value)

    health = kernel.health()
    print("Health modules:", health["modules"]["registered"])

    await kernel.stop()

    print("Kernel state:", kernel.state.value)
    print("Event bus running:", event_bus.is_running)
    print("Module manager running:", module_manager.is_running)


if __name__ == "__main__":
    asyncio.run(main())