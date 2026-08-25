"""
ETOP Platform Event Bus.

The event bus provides loosely coupled communication between ETOP platform
services and modules.

Examples:

- Customer Intelligence publishes a customer-risk event.
- Automation Center subscribes and creates a workflow.
- Document Intelligence publishes an indexing-completed event.
- The user interface receives the updated status.
- Health services publish platform-status changes.

The event bus supports:

- Typed events
- Named events
- Synchronous and asynchronous subscribers
- Subscriber priority
- One-time subscriptions
- Error isolation
- Event history
- Event diagnostics
- Controlled startup and shutdown

The event bus does not contain business logic. It only transports events.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import time
from collections import deque
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from threading import RLock
from typing import Any, Generic, TypeVar, cast
from uuid import UUID, uuid4


logger = logging.getLogger(__name__)

TEvent = TypeVar("TEvent", bound="PlatformEvent")

EventHandler = Callable[
    [TEvent],
    None | Awaitable[None],
]


@dataclass(frozen=True, slots=True, kw_only=True)
class PlatformEvent:
    """
    Base class for ETOP platform events.

    Domain-specific events should inherit from this class.

    Example:

        @dataclass(frozen=True, slots=True, kw_only=True)
        class CustomerRiskChangedEvent(PlatformEvent):
            customer_number: str
            previous_score: float
            current_score: float
    """

    event_id: UUID = field(default_factory=uuid4)
    occurred_at: datetime = field(
        default_factory=lambda: datetime.now(UTC)
    )
    source: str = "etop"
    correlation_id: UUID | None = None
    causation_id: UUID | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def event_name(self) -> str:
        """Return the default event name."""

        return f"{self.__class__.__module__}.{self.__class__.__qualname__}"


@dataclass(frozen=True, slots=True, kw_only=True)
class NamedPlatformEvent(PlatformEvent):
    """
    Generic named event for cases where a dedicated event class is unnecessary.
    """

    name: str
    payload: Mapping[str, Any] = field(default_factory=dict)

    @property
    def event_name(self) -> str:
        """Return the supplied event name."""

        return self.name


@dataclass(frozen=True, slots=True)
class EventSubscription:
    """Public event-subscription information."""

    subscription_id: UUID
    event_type: type[PlatformEvent] | None
    event_name: str | None
    handler_name: str
    priority: int
    once: bool
    enabled: bool
    metadata: Mapping[str, Any]


@dataclass(slots=True)
class _SubscriptionRecord:
    """Internal event-subscription record."""

    subscription_id: UUID
    handler: Callable[[PlatformEvent], Any]
    event_type: type[PlatformEvent] | None = None
    event_name: str | None = None
    priority: int = 0
    once: bool = False
    enabled: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def handler_name(self) -> str:
        """Return a readable handler name."""

        return getattr(
            self.handler,
            "__qualname__",
            getattr(
                self.handler,
                "__name__",
                self.handler.__class__.__name__,
            ),
        )


@dataclass(frozen=True, slots=True)
class EventHandlerResult:
    """Execution result for one event handler."""

    subscription_id: UUID
    handler_name: str
    succeeded: bool
    duration_ms: float
    error: str | None = None
    exception_type: str | None = None


@dataclass(frozen=True, slots=True)
class EventPublicationResult:
    """Result of publishing one event."""

    event_id: UUID
    event_name: str
    published_at: datetime
    duration_ms: float
    subscriber_count: int
    succeeded_count: int
    failed_count: int
    handler_results: tuple[EventHandlerResult, ...]

    @property
    def succeeded(self) -> bool:
        """Return whether every matching handler succeeded."""

        return self.failed_count == 0


@dataclass(frozen=True, slots=True)
class EventHistoryEntry:
    """Diagnostic history entry for one published event."""

    event_id: UUID
    event_name: str
    event_type: str
    source: str
    occurred_at: datetime
    published_at: datetime
    duration_ms: float
    subscriber_count: int
    succeeded_count: int
    failed_count: int
    correlation_id: UUID | None
    causation_id: UUID | None


class EventBusError(RuntimeError):
    """Base exception for event-bus failures."""


class EventBusStoppedError(EventBusError):
    """Raised when publishing through a stopped event bus."""

    def __init__(self) -> None:
        super().__init__("The ETOP event bus is not running.")


class InvalidSubscriptionError(EventBusError):
    """Raised when a subscription is invalid."""


class EventPublicationError(EventBusError):
    """Raised when one or more handlers fail and strict publishing is enabled."""

    def __init__(
        self,
        result: EventPublicationResult,
    ) -> None:
        self.result = result

        super().__init__(
            f"Event '{result.event_name}' completed with "
            f"{result.failed_count} failed handler(s)."
        )


class EventBus:
    """
    Thread-safe asynchronous ETOP event bus.

    Subscribers can listen by event type:

        bus.subscribe(CustomerRiskChangedEvent, handler)

    Or by event name:

        bus.subscribe_named("customer.risk.changed", handler)

    Event handlers execute in priority order. Higher priority values execute
    first.

    By default, handler failures are isolated and included in the publication
    result. Set raise_on_error=True to raise EventPublicationError after all
    handlers complete.
    """

    def __init__(
        self,
        *,
        history_limit: int = 500,
        concurrent_handlers: bool = False,
    ) -> None:
        if history_limit < 0:
            raise ValueError("history_limit cannot be negative.")

        self._subscriptions: dict[UUID, _SubscriptionRecord] = {}
        self._history: deque[EventHistoryEntry] = deque(
            maxlen=history_limit or None
        )

        self._history_limit = history_limit
        self._concurrent_handlers = concurrent_handlers

        self._lock = RLock()
        self._running = False
        self._published_count = 0
        self._failed_handler_count = 0

    @property
    def is_running(self) -> bool:
        """Return whether the event bus accepts publications."""

        with self._lock:
            return self._running

    @property
    def subscription_count(self) -> int:
        """Return the number of active and inactive subscriptions."""

        with self._lock:
            return len(self._subscriptions)

    @property
    def published_count(self) -> int:
        """Return the total number of published events."""

        with self._lock:
            return self._published_count

    @property
    def failed_handler_count(self) -> int:
        """Return the total number of failed handler executions."""

        with self._lock:
            return self._failed_handler_count

    async def start(self) -> None:
        """Start the event bus."""

        with self._lock:
            if self._running:
                return

            self._running = True

        logger.info(
            "ETOP event bus started with %s subscription(s).",
            self.subscription_count,
        )

    async def stop(self) -> None:
        """Stop the event bus."""

        with self._lock:
            if not self._running:
                return

            self._running = False

        logger.info("ETOP event bus stopped.")

    async def async_close(self) -> None:
        """Kernel-compatible asynchronous cleanup method."""

        await self.stop()

    def subscribe(
        self,
        event_type: type[TEvent],
        handler: EventHandler[TEvent],
        *,
        priority: int = 0,
        once: bool = False,
        enabled: bool = True,
        metadata: Mapping[str, Any] | None = None,
    ) -> UUID:
        """
        Subscribe a handler to an event type.

        A subscriber registered for PlatformEvent receives every event.
        """

        if not inspect.isclass(event_type):
            raise InvalidSubscriptionError(
                "event_type must be an event class."
            )

        if not issubclass(event_type, PlatformEvent):
            raise InvalidSubscriptionError(
                "event_type must inherit from PlatformEvent."
            )

        return self._add_subscription(
            handler=cast(Callable[[PlatformEvent], Any], handler),
            event_type=event_type,
            priority=priority,
            once=once,
            enabled=enabled,
            metadata=metadata,
        )

    def subscribe_named(
        self,
        event_name: str,
        handler: EventHandler[PlatformEvent],
        *,
        priority: int = 0,
        once: bool = False,
        enabled: bool = True,
        metadata: Mapping[str, Any] | None = None,
    ) -> UUID:
        """Subscribe a handler to an exact event name."""

        normalized_name = event_name.strip()

        if not normalized_name:
            raise InvalidSubscriptionError(
                "event_name cannot be blank."
            )

        return self._add_subscription(
            handler=handler,
            event_name=normalized_name,
            priority=priority,
            once=once,
            enabled=enabled,
            metadata=metadata,
        )

    def unsubscribe(self, subscription_id: UUID) -> bool:
        """
        Remove a subscription.

        Returns True when a subscription was removed.
        """

        with self._lock:
            removed = self._subscriptions.pop(
                subscription_id,
                None,
            )

        if removed is None:
            return False

        logger.debug(
            "Removed event subscription %s for handler %s.",
            subscription_id,
            removed.handler_name,
        )

        return True

    def enable(self, subscription_id: UUID) -> bool:
        """Enable a subscription."""

        return self._set_subscription_enabled(
            subscription_id,
            True,
        )

    def disable(self, subscription_id: UUID) -> bool:
        """Disable a subscription without removing it."""

        return self._set_subscription_enabled(
            subscription_id,
            False,
        )

    def clear_subscriptions(self) -> None:
        """Remove all event subscriptions."""

        with self._lock:
            self._subscriptions.clear()

        logger.info("All ETOP event subscriptions were removed.")

    def subscriptions(self) -> list[EventSubscription]:
        """Return subscription diagnostics."""

        with self._lock:
            records = list(self._subscriptions.values())

        result = [
            EventSubscription(
                subscription_id=record.subscription_id,
                event_type=record.event_type,
                event_name=record.event_name,
                handler_name=record.handler_name,
                priority=record.priority,
                once=record.once,
                enabled=record.enabled,
                metadata=dict(record.metadata),
            )
            for record in records
        ]

        return sorted(
            result,
            key=lambda item: (
                -item.priority,
                item.handler_name.lower(),
            ),
        )

    async def publish(
        self,
        event: TEvent,
        *,
        raise_on_error: bool = False,
    ) -> EventPublicationResult:
        """
        Publish an event to matching subscribers.

        Handler failures are isolated by default. Every matching handler is
        given an opportunity to execute even when another handler fails.
        """

        if not isinstance(event, PlatformEvent):
            raise TypeError(
                "Published events must inherit from PlatformEvent."
            )

        if not self.is_running:
            raise EventBusStoppedError()

        publication_started = time.perf_counter()
        published_at = datetime.now(UTC)

        subscriptions = self._matching_subscriptions(event)

        if self._concurrent_handlers:
            handler_results = await self._execute_concurrently(
                event,
                subscriptions,
            )
        else:
            handler_results = await self._execute_sequentially(
                event,
                subscriptions,
            )

        duration_ms = round(
            (time.perf_counter() - publication_started) * 1000,
            3,
        )

        succeeded_count = sum(
            1 for result in handler_results if result.succeeded
        )
        failed_count = len(handler_results) - succeeded_count

        result = EventPublicationResult(
            event_id=event.event_id,
            event_name=event.event_name,
            published_at=published_at,
            duration_ms=duration_ms,
            subscriber_count=len(handler_results),
            succeeded_count=succeeded_count,
            failed_count=failed_count,
            handler_results=tuple(handler_results),
        )

        self._record_publication(
            event=event,
            result=result,
        )

        logger.debug(
            "Published event %s to %s handler(s) in %.3f ms.",
            event.event_name,
            result.subscriber_count,
            result.duration_ms,
        )

        if raise_on_error and failed_count:
            raise EventPublicationError(result)

        return result

    async def publish_named(
        self,
        event_name: str,
        payload: Mapping[str, Any] | None = None,
        *,
        source: str = "etop",
        correlation_id: UUID | None = None,
        causation_id: UUID | None = None,
        metadata: Mapping[str, Any] | None = None,
        raise_on_error: bool = False,
    ) -> EventPublicationResult:
        """Create and publish a generic named event."""

        event = NamedPlatformEvent(
            name=event_name,
            payload=dict(payload or {}),
            source=source,
            correlation_id=correlation_id,
            causation_id=causation_id,
            metadata=dict(metadata or {}),
        )

        return await self.publish(
            event,
            raise_on_error=raise_on_error,
        )

    def history(
        self,
        *,
        limit: int | None = None,
        event_name: str | None = None,
    ) -> list[EventHistoryEntry]:
        """
        Return recent event history, newest first.

        Event payloads are intentionally not retained in history to reduce
        memory use and avoid storing sensitive business data.
        """

        with self._lock:
            entries = list(reversed(self._history))

        if event_name is not None:
            entries = [
                entry
                for entry in entries
                if entry.event_name == event_name
            ]

        if limit is not None:
            if limit < 0:
                raise ValueError("limit cannot be negative.")

            entries = entries[:limit]

        return entries

    def clear_history(self) -> None:
        """Clear retained event history."""

        with self._lock:
            self._history.clear()

    def diagnostics(self) -> dict[str, Any]:
        """Return event-bus health and usage information."""

        subscriptions = self.subscriptions()

        return {
            "running": self.is_running,
            "subscriptions": len(subscriptions),
            "enabled_subscriptions": sum(
                1
                for subscription in subscriptions
                if subscription.enabled
            ),
            "published_events": self.published_count,
            "failed_handlers": self.failed_handler_count,
            "history_entries": len(self.history()),
            "history_limit": self._history_limit,
            "concurrent_handlers": self._concurrent_handlers,
        }

    def _add_subscription(
        self,
        *,
        handler: Callable[[PlatformEvent], Any],
        event_type: type[PlatformEvent] | None = None,
        event_name: str | None = None,
        priority: int,
        once: bool,
        enabled: bool,
        metadata: Mapping[str, Any] | None,
    ) -> UUID:
        """Validate and store a subscription."""

        if not callable(handler):
            raise InvalidSubscriptionError(
                "Event handler must be callable."
            )

        if event_type is None and event_name is None:
            raise InvalidSubscriptionError(
                "A subscription requires an event type or event name."
            )

        subscription_id = uuid4()

        record = _SubscriptionRecord(
            subscription_id=subscription_id,
            handler=handler,
            event_type=event_type,
            event_name=event_name,
            priority=priority,
            once=once,
            enabled=enabled,
            metadata=dict(metadata or {}),
        )

        with self._lock:
            self._subscriptions[subscription_id] = record

        logger.debug(
            "Registered event subscription %s for handler %s.",
            subscription_id,
            record.handler_name,
        )

        return subscription_id

    def _set_subscription_enabled(
        self,
        subscription_id: UUID,
        enabled: bool,
    ) -> bool:
        """Update the enabled state of a subscription."""

        with self._lock:
            record = self._subscriptions.get(subscription_id)

            if record is None:
                return False

            record.enabled = enabled
            return True

    def _matching_subscriptions(
        self,
        event: PlatformEvent,
    ) -> list[_SubscriptionRecord]:
        """Return enabled subscriptions matching an event."""

        with self._lock:
            subscriptions = list(self._subscriptions.values())

        matching = [
            subscription
            for subscription in subscriptions
            if subscription.enabled
            and (
                (
                    subscription.event_type is not None
                    and isinstance(event, subscription.event_type)
                )
                or (
                    subscription.event_name is not None
                    and subscription.event_name == event.event_name
                )
            )
        ]

        return sorted(
            matching,
            key=lambda subscription: -subscription.priority,
        )

    async def _execute_sequentially(
        self,
        event: PlatformEvent,
        subscriptions: list[_SubscriptionRecord],
    ) -> list[EventHandlerResult]:
        """Execute matching subscribers one at a time."""

        results: list[EventHandlerResult] = []

        for subscription in subscriptions:
            result = await self._execute_handler(
                event,
                subscription,
            )
            results.append(result)

        return results

    async def _execute_concurrently(
        self,
        event: PlatformEvent,
        subscriptions: list[_SubscriptionRecord],
    ) -> list[EventHandlerResult]:
        """Execute matching subscribers concurrently."""

        if not subscriptions:
            return []

        return list(
            await asyncio.gather(
                *[
                    self._execute_handler(event, subscription)
                    for subscription in subscriptions
                ]
            )
        )

    async def _execute_handler(
        self,
        event: PlatformEvent,
        subscription: _SubscriptionRecord,
    ) -> EventHandlerResult:
        """Execute one synchronous or asynchronous handler."""

        started = time.perf_counter()

        try:
            result = subscription.handler(event)

            if inspect.isawaitable(result):
                await cast(Awaitable[Any], result)

            duration_ms = round(
                (time.perf_counter() - started) * 1000,
                3,
            )

            handler_result = EventHandlerResult(
                subscription_id=subscription.subscription_id,
                handler_name=subscription.handler_name,
                succeeded=True,
                duration_ms=duration_ms,
            )

        except Exception as exc:
            duration_ms = round(
                (time.perf_counter() - started) * 1000,
                3,
            )

            with self._lock:
                self._failed_handler_count += 1

            logger.exception(
                "Event handler %s failed while processing %s.",
                subscription.handler_name,
                event.event_name,
            )

            handler_result = EventHandlerResult(
                subscription_id=subscription.subscription_id,
                handler_name=subscription.handler_name,
                succeeded=False,
                duration_ms=duration_ms,
                error=str(exc),
                exception_type=type(exc).__name__,
            )

        finally:
            if subscription.once:
                self.unsubscribe(subscription.subscription_id)

        return handler_result

    def _record_publication(
        self,
        *,
        event: PlatformEvent,
        result: EventPublicationResult,
    ) -> None:
        """Record publication diagnostics."""

        entry = EventHistoryEntry(
            event_id=event.event_id,
            event_name=event.event_name,
            event_type=(
                f"{event.__class__.__module__}."
                f"{event.__class__.__qualname__}"
            ),
            source=event.source,
            occurred_at=event.occurred_at,
            published_at=result.published_at,
            duration_ms=result.duration_ms,
            subscriber_count=result.subscriber_count,
            succeeded_count=result.succeeded_count,
            failed_count=result.failed_count,
            correlation_id=event.correlation_id,
            causation_id=event.causation_id,
        )

        with self._lock:
            self._published_count += 1

            if self._history_limit > 0:
                self._history.append(entry)