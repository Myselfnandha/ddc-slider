from lumatray.core.events import EventBus, EventType


def test_event_bus():
    bus = EventBus()
    received = []

    def on_value_changed(**kwargs):
        received.append(kwargs)

    bus.subscribe(EventType.VALUE_CHANGED, on_value_changed)
    bus.emit(EventType.VALUE_CHANGED, display_id="test", feature="brightness", value=80)

    assert len(received) == 1
    assert received[0]["value"] == 80
    assert received[0]["feature"] == "brightness"

    bus.unsubscribe(EventType.VALUE_CHANGED, on_value_changed)
    bus.emit(EventType.VALUE_CHANGED, display_id="test", feature="brightness", value=90)
    # Shouldn't receive after unsubscribe
    assert len(received) == 1
