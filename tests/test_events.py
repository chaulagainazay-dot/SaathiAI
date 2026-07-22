"""Event Fabric tests (SES-012 lightweight form) — AP-12.

Covers sync + async handlers, wildcard subscription, unsubscribe, failure
isolation (one raising handler doesn't stop delivery to others), and the
Disk Watchdog publishing storage_critical/storage_warning through a bus.
"""
import pytest

from saathi.events import EventBus, WILDCARD
from saathi.events import STORAGE_WARNING, STORAGE_CRITICAL
from saathi.storage import StorageDB, DiskWatchdog, DiskUsage


@pytest.mark.asyncio
async def test_sync_and_async_handlers_both_receive():
    bus = EventBus()
    seen = []
    bus.subscribe("render_started", lambda e: seen.append(("sync", e.payload)))

    async def ahandler(e):
        seen.append(("async", e.payload))

    bus.subscribe("render_started", ahandler)
    report = await bus.publish("render_started", {"job_id": "j1"})
    assert report.ok
    assert report.delivered == 2
    assert ("sync", {"job_id": "j1"}) in seen
    assert ("async", {"job_id": "j1"}) in seen


@pytest.mark.asyncio
async def test_wildcard_and_unsubscribe():
    bus = EventBus()
    allseen = []
    unsub = bus.subscribe(WILDCARD, lambda e: allseen.append(e.name))
    await bus.publish("a")
    await bus.publish("b")
    assert allseen == ["a", "b"]
    unsub()
    await bus.publish("c")
    assert allseen == ["a", "b"]   # no longer receiving


@pytest.mark.asyncio
async def test_failure_isolation():
    bus = EventBus()
    delivered = []

    def bad(e):
        raise ValueError("boom")

    bus.subscribe("x", bad)
    bus.subscribe("x", lambda e: delivered.append(e.name))
    report = await bus.publish("x")
    assert delivered == ["x"]          # good handler still ran
    assert not report.ok
    assert len(report.errors) == 1
    assert isinstance(report.errors[0][1], ValueError)


def test_publish_sync_outside_loop():
    bus = EventBus()
    got = []
    bus.subscribe("ping", lambda e: got.append(e.name))
    report = bus.publish_sync("ping", {"n": 1})
    assert report.delivered == 1
    assert got == ["ping"]


def test_watchdog_publishes_storage_events_through_bus(tmp_path):
    bus = EventBus()
    events = []
    bus.subscribe(WILDCARD, lambda e: events.append(e.name))

    db = StorageDB(str(tmp_path / "s.db"))
    wd = DiskWatchdog(
        db,
        usage_reader=lambda: DiskUsage(total=100, used=98, free=2),  # 98% → critical
        publish=bus.publish_sync,
    )
    wd.check()
    assert STORAGE_CRITICAL in events

    # recover then re-fill to 92% → warning
    wd2 = DiskWatchdog(
        db,
        usage_reader=lambda: DiskUsage(total=100, used=92, free=8),
        publish=bus.publish_sync,
    )
    wd2.check()
    assert STORAGE_WARNING in events
