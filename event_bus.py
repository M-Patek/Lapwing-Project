"""
Event Bus System for Lapwing
Decouples modules using publish/subscribe pattern.
"""
import asyncio
import logging
from typing import Dict, List, Callable, Any, Optional
from dataclasses import dataclass
from datetime import datetime
from enum import Enum, auto
import weakref


class EventType(Enum):
    """System event types"""
    # User interaction events
    USER_MESSAGE = auto()
    USER_SILENCE = auto()

    # Lapwing response events
    RESPONSE_GENERATED = auto()
    RESPONSE_SPOKEN = auto()

    # Emotional state events
    EII_CHANGED = auto()
    EMOTION_UPDATED = auto()

    # Memory events
    MEMORY_ADDED = auto()
    MEMORY_RETRIEVED = auto()
    MEMORY_CONSOLIDATED = auto()

    # Proactive events
    PROACTIVE_TRIGGERED = auto()
    PROACTIVE_MESSAGE_SENT = auto()
    GOAL_CREATED = auto()
    GOAL_COMPLETED = auto()

    # Dreaming events
    DREAM_STARTED = auto()
    DREAM_COMPLETED = auto()
    INSIGHT_GENERATED = auto()

    # World events
    WORLD_STATE_UPDATED = auto()
    TIME_CHANGED = auto()

    # System events
    CONFIG_RELOADED = auto()
    ERROR_OCCURRED = auto()
    SHUTDOWN_REQUESTED = auto()


@dataclass
class Event:
    """Event data structure"""
    type: EventType
    data: Dict[str, Any]
    timestamp: datetime
    source: Optional[str] = None

    @classmethod
    def create(cls, event_type: EventType, data: Dict[str, Any] = None, source: str = None):
        return cls(
            type=event_type,
            data=data or {},
            timestamp=datetime.now(),
            source=source
        )


class EventBus:
    """
    Central event bus for decoupled communication.

    Usage:
        # Subscribe to events
        event_bus.subscribe(EventType.EII_CHANGED, on_eii_changed)

        # Publish events
        await event_bus.publish(EventType.EII_CHANGED, {"eii": 65.5})

        # Or use decorators
        @event_bus.on(EventType.MEMORY_ADDED)
        async def handle_memory(event: Event):
            print(f"Memory added: {event.data}")
    """

    def __init__(self):
        # Map event type to list of handlers
        self._handlers: Dict[EventType, List[Callable]] = {}
        # Weak references for automatic cleanup
        self._weak_handlers: Dict[EventType, List[weakref.ref]] = {}
        # Event history (for debugging/replay)
        self._history: List[Event] = []
        self._max_history = 1000
        # Async queue for event processing
        self._queue: asyncio.Queue = asyncio.Queue()
        self._processing = False
        self._processor_task: Optional[asyncio.Task] = None

    async def start(self):
        """Start event processing loop"""
        if not self._processing:
            self._processing = True
            self._processor_task = asyncio.create_task(self._process_events())
            logging.info("[EventBus] Started")

    async def stop(self):
        """Stop event processing"""
        self._processing = False
        if self._processor_task:
            self._processor_task.cancel()
            try:
                await self._processor_task
            except asyncio.CancelledError:
                pass
        logging.info("[EventBus] Stopped")

    async def _process_events(self):
        """Background event processor"""
        while self._processing:
            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                await self._dispatch(event)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logging.error(f"[EventBus] Event processing error: {e}")

    async def _dispatch(self, event: Event):
        """Dispatch event to all handlers"""
        handlers = self._handlers.get(event.type, [])

        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            except Exception as e:
                logging.error(f"[EventBus] Handler error for {event.type}: {e}")

        # Clean up weak references
        weak_handlers = self._weak_handlers.get(event.type, [])
        for weak_ref in weak_handlers[:]:
            handler = weak_ref()
            if handler is None:
                weak_handlers.remove(weak_ref)
                continue
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            except Exception as e:
                logging.error(f"[EventBus] Weak handler error for {event.type}: {e}")

    async def publish(self, event_type: EventType, data: Dict[str, Any] = None, source: str = None):
        """
        Publish an event to the bus.

        Args:
            event_type: Type of event
            data: Event data dictionary
            source: Source module/component name
        """
        event = Event.create(event_type, data, source)

        # Add to history
        self._history.append(event)
        if len(self._history) > self._max_history:
            self._history.pop(0)

        # Queue for processing
        await self._queue.put(event)

        logging.debug(f"[EventBus] Published {event_type.name} from {source}")

    def subscribe(self, event_type: EventType, handler: Callable, weak: bool = False):
        """
        Subscribe to an event type.

        Args:
            event_type: Event type to subscribe to
            handler: Callback function (sync or async)
            weak: Use weak reference (allows automatic unsubscription when handler is garbage collected)
        """
        if weak:
            if event_type not in self._weak_handlers:
                self._weak_handlers[event_type] = []
            self._weak_handlers[event_type].append(weakref.ref(handler))
        else:
            if event_type not in self._handlers:
                self._handlers[event_type] = []
            self._handlers[event_type].append(handler)

        logging.debug(f"[EventBus] Subscribed {handler.__name__} to {event_type.name}")

    def unsubscribe(self, event_type: EventType, handler: Callable):
        """Unsubscribe from an event type"""
        if event_type in self._handlers:
            if handler in self._handlers[event_type]:
                self._handlers[event_type].remove(handler)

    def on(self, event_type: EventType, weak: bool = False):
        """
        Decorator for subscribing to events.

        Usage:
            @event_bus.on(EventType.EII_CHANGED)
            async def handle_eii_change(event: Event):
                print(f"EII: {event.data['eii']}")
        """
        def decorator(func: Callable):
            self.subscribe(event_type, func, weak)
            return func
        return decorator

    def get_history(self, event_type: Optional[EventType] = None, limit: int = 100) -> List[Event]:
        """Get event history"""
        events = self._history
        if event_type:
            events = [e for e in events if e.type == event_type]
        return events[-limit:]

    def clear_history(self):
        """Clear event history"""
        self._history.clear()


# Global event bus instance
_event_bus: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    """Get or create global event bus"""
    global _event_bus
    if _event_bus is None:
        _event_bus = EventBus()
    return _event_bus


# Convenience functions for common events

async def emit_user_message(message: str, source: str = "api"):
    """Emit user message event"""
    await get_event_bus().publish(
        EventType.USER_MESSAGE,
        {"message": message},
        source
    )


async def emit_response_generated(response: str, eii: float, source: str = "main"):
    """Emit response generated event"""
    await get_event_bus().publish(
        EventType.RESPONSE_GENERATED,
        {"response": response, "eii": eii},
        source
    )


async def emit_eii_changed(old_eii: float, new_eii: float, source: str = "emotional_state"):
    """Emit EII change event"""
    await get_event_bus().publish(
        EventType.EII_CHANGED,
        {"old_eii": old_eii, "new_eii": new_eii, "delta": new_eii - old_eii},
        source
    )


async def emit_memory_added(content: str, eii_snapshot: float, source: str = "memory"):
    """Emit memory added event"""
    await get_event_bus().publish(
        EventType.MEMORY_ADDED,
        {"content": content, "eii_snapshot": eii_snapshot},
        source
    )


async def emit_proactive_triggered(message: str, intent_type: str, source: str = "proactive"):
    """Emit proactive trigger event"""
    await get_event_bus().publish(
        EventType.PROACTIVE_TRIGGERED,
        {"message": message, "intent_type": intent_type},
        source
    )


# Example usage
if __name__ == "__main__":
    async def main():
        bus = get_event_bus()
        await bus.start()

        # Subscribe with decorator
        @bus.on(EventType.EII_CHANGED)
        async def on_eii_change(event: Event):
            print(f"EII changed: {event.data['old_eii']} -> {event.data['new_eii']}")

        # Subscribe with function
        def on_memory(event: Event):
            print(f"Memory: {event.data['content']}")

        bus.subscribe(EventType.MEMORY_ADDED, on_memory)

        # Publish events
        await emit_eii_changed(50.0, 65.5)
        await emit_memory_added("User likes cats", 60.0)

        # Wait for processing
        await asyncio.sleep(0.1)

        await bus.stop()

    asyncio.run(main())
