"""Repair 2 regression guard for the module-level Event Bus API.

Root cause guarded here: `saathi/events/__init__.py` re-imported the SQLite
submodule `saathi.events.bus`, which rebound the package attribute `bus` to
that MODULE and shadowed the fabric singleton INSTANCE. Producers and tests
do `from saathi.events import bus` expecting the instance (subscribe / publish
/ publish_sync). These tests assert the instance is what resolves, plus the
subscribe() lifecycle behaviours.
"""

import asyncio
import types

from saathi.events import bus


def test_bus_is_fabric_instance_not_module():
    """`from saathi.events import bus` must yield the fabric instance."""
    assert not isinstance(bus, types.ModuleType)
    for attr in ("subscribe", "publish", "publish_sync"):
        assert callable(getattr(bus, attr)), f"bus missing {attr}"


def test_subscribe_returns_unsub_and_cleans_up():
    seen = []
    unsub = bus.subscribe("t2.cleanup", lambda e: seen.append(e.name))
    assert callable(unsub)
    asyncio.run(bus.publish("t2.cleanup", {}))
    assert seen == ["t2.cleanup"]
    unsub()
    asyncio.run(bus.publish("t2.cleanup", {}))
    assert seen == ["t2.cleanup"]  # no delivery after unsubscribe (no leak)


def test_duplicate_subscriptions_both_fire():
    hits = []
    u1 = bus.subscribe("t2.dup", lambda e: hits.append("a"))
    u2 = bus.subscribe("t2.dup", lambda e: hits.append("b"))
    try:
        asyncio.run(bus.publish("t2.dup", {}))
        assert sorted(hits) == ["a", "b"]
    finally:
        u1(); u2()


def test_sync_and_async_handlers_delivered():
    order = []

    async def ahandler(e):
        order.append("async")

    us = bus.subscribe("t2.mix", lambda e: order.append("sync"))
    ua = bus.subscribe("t2.mix", ahandler)
    try:
        report = asyncio.run(bus.publish("t2.mix", {}))
        assert report.delivered == 2
        assert set(order) == {"sync", "async"}
    finally:
        us(); ua()


def test_handler_exception_isolated():
    good = []

    def boom(e):
        raise RuntimeError("bad handler")

    ub = bus.subscribe("t2.err", boom)
    ug = bus.subscribe("t2.err", lambda e: good.append(1))
    try:
        report = asyncio.run(bus.publish("t2.err", {}))
        assert good == [1]              # good handler still ran
        assert report.delivered == 1
        assert len(report.errors) == 1  # bad handler captured, not raised
    finally:
        ub(); ug()


def test_specific_before_wildcard_ordering():
    order = []
    us = bus.subscribe("t2.order", lambda e: order.append("specific"))
    uw = bus.subscribe("*", lambda e: order.append("wildcard"))
    try:
        asyncio.run(bus.publish("t2.order", {}))
        assert order == ["specific", "wildcard"]
    finally:
        us(); uw()


def test_publish_sync_outside_loop():
    seen = []
    u = bus.subscribe("t2.psync", lambda e: seen.append(e.payload.get("v")))
    try:
        report = bus.publish_sync("t2.psync", {"v": 42})
        assert seen == [42]
        assert report.ok
    finally:
        u()
