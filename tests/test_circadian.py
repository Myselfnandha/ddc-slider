import datetime
from lumatray.services.automation_engine import automation_engine


def test_circadian_evaluation():
    from lumatray.storage.config_store import DEFAULT_CONFIG, config_store
    config_store.set("circadian_waypoints", DEFAULT_CONFIG["circadian_waypoints"], auto_save=False)

    # Test at 10:00 AM (Daylight waypoint: 100% brightness, 75% contrast, 6500K)
    dt_day = datetime.datetime(2026, 10, 23, 10, 0, 0)
    br, co, ct = automation_engine.evaluate_circadian_target(now=dt_day)
    assert br == 100
    assert co == 75
    assert ct == 6500

    # Test at 23:00 (Late Night waypoint: 25% brightness, 45% contrast, 2700K)
    dt_night = datetime.datetime(2026, 10, 23, 23, 0, 0)
    br, co, ct = automation_engine.evaluate_circadian_target(now=dt_night)
    assert br == 25
    assert co == 45
    assert ct == 2700

    # Test smooth interpolation between Morning (07:30) and Daylight (10:00)
    dt_mid = datetime.datetime(2026, 10, 23, 8, 45, 0)
    br_mid, co_mid, ct_mid = automation_engine.evaluate_circadian_target(now=dt_mid)
    # Intermediate values should be bounded between 70 and 100
    assert 70 < br_mid < 100
    assert 65 < co_mid < 75
    assert 5000 < ct_mid < 6500


def test_auto_mode_toggle():
    from lumatray.core.events import EventType, events

    received = []
    events.subscribe(EventType.AUTOMATION_STATE_CHANGED, lambda enabled, **kw: received.append(enabled))

    # Test set_enabled
    automation_engine.set_enabled(False)
    assert not automation_engine.is_enabled()
    assert received[-1] is False

    # Test toggle
    new_state = automation_engine.toggle_auto_mode()
    assert new_state is True
    assert automation_engine.is_enabled()
    assert received[-1] is True

    # Toggle back to off
    new_state = automation_engine.toggle_auto_mode()
    assert new_state is False
    assert not automation_engine.is_enabled()

    # Restore on
    automation_engine.set_enabled(True)
    assert automation_engine.is_enabled()

