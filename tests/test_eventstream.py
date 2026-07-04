"""Live event stream tests (M5.1 Sprint 2) — enrichment + real events reach SSE."""
import asyncio
import json

from saathi.eventstream import dept_for, enrich, sse_stream
from saathi.events import bus


def test_dept_routing():
    assert dept_for("trade.executed") == "FINANCE"
    assert dept_for("video.published") == "AI STUDIO"
    assert dept_for("learning.completed") == "LEARNING"
    assert dept_for("something.unknown") == "MISSION"     # fallback


def test_enrich_makes_events_actionable():
    ev = enrich("trade.executed", {"symbol": "TAO", "pnl_usd": 320})
    assert ev["dept"] == "FINANCE"
    assert "TAO" in ev["title"]
    assert ev["action"]                                    # every notification offers a decision
    # explicit payload title/action is respected
    ev2 = enrich("travel.lead", {"dept": "TRAVEL", "title": "Call the lead", "action": "Call"})
    assert ev2["title"] == "Call the lead" and ev2["action"] == "Call"


def test_stream_emits_connect_then_demo_beats():
    async def run():
        frames = []
        gen = sse_stream(demo=True, demo_interval=0.05)
        async for frame in gen:
            frames.append(frame)
            if len(frames) >= 3:
                await gen.aclose()
                break
        return frames
    frames = asyncio.run(run())
    first = json.loads(frames[0].removeprefix("data: ").strip())
    assert first["name"] == "stream.connected"
    later = [json.loads(f.removeprefix("data: ").strip()) for f in frames[1:]]
    assert all("name" in e for e in later)                 # demo beats flowing


def test_real_published_event_reaches_stream():
    async def run():
        gen = sse_stream(demo=False, demo_interval=5.0)
        # consume the connect frame
        await gen.__anext__()
        # publish a real event on the fabric
        await bus.publish("revenue.recorded", {"amount_usd": 171, "dept": "CAFETERIA"})
        frame = await asyncio.wait_for(gen.__anext__(), timeout=2)
        await gen.aclose()
        return json.loads(frame.removeprefix("data: ").strip())
    ev = asyncio.run(run())
    assert ev["name"] == "revenue.recorded"
    assert ev["dept"] == "CAFETERIA"
    assert "171" in ev["title"]
