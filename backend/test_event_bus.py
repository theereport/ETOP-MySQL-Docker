import asyncio
from dataclasses import dataclass

from core.event_bus import EventBus, PlatformEvent


@dataclass(frozen=True, slots=True, kw_only=True)
class CustomerUpdatedEvent(PlatformEvent):
    customer_number: str
    customer_name: str


async def handle_customer_updated(
    event: CustomerUpdatedEvent,
) -> None:
    print(
        f"Customer updated: "
        f"{event.customer_number} - {event.customer_name}"
    )


async def main() -> None:
    bus = EventBus()

    bus.subscribe(
        CustomerUpdatedEvent,
        handle_customer_updated,
        priority=100,
    )

    await bus.start()

    result = await bus.publish(
        CustomerUpdatedEvent(
            customer_number="12345",
            customer_name="Example Customer",
            source="test",
        )
    )

    print("Succeeded:", result.succeeded)
    print("Subscribers:", result.subscriber_count)
    print("History:", len(bus.history()))
    print("Diagnostics:", bus.diagnostics())

    await bus.stop()


if __name__ == "__main__":
    asyncio.run(main())