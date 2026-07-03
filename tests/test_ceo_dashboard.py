"""CEO Dashboard tests (M3 Phase A) — event-first daily operating view, AP-12/13.

Everything is fed by the Event Fabric; nothing is polled. Honest sections:
unwired streams read 0, not faked.
"""
from saathi.events import EventBus
from saathi.ceo_dashboard import CEODashboard


def _wired():
    bus = EventBus()
    dash = CEODashboard()
    dash.register(bus)
    return bus, dash


def test_publishing_and_learning_aggregate_from_events():
    bus, dash = _wired()
    bus.publish_sync("publish.completed", {"platform": "youtube"})
    bus.publish_sync("publish.completed", {"platform": "tiktok"})
    bus.publish_sync("publish.blocked", {"reasons": "no seo"})
    bus.publish_sync("knowledge.promoted", {"knowledge_id": 1})
    bus.publish_sync("knowledge.review_enqueued", {"review_id": 1})
    bus.publish_sync("learning.lesson_extracted", {"category": "network"})
    snap = dash.snapshot()
    assert snap["ai_studio"] == {"published": 2, "blocked": 1, "renders": 0}
    assert snap["learning"]["promoted"] == 1
    assert snap["learning"]["pending_reviews"] == 1
    assert snap["learning"]["lessons"] == 1


def test_knowledge_graph_and_docs_aggregate():
    bus, dash = _wired()
    bus.publish_sync("kg.node_created", {})
    bus.publish_sync("kg.node_created", {})
    bus.publish_sync("kg.edge_created", {})
    bus.publish_sync("doc.proposal_created", {"target": "Brain.md"})
    snap = dash.snapshot()
    assert snap["knowledge_graph"] == {"nodes": 2, "edges": 1}
    assert snap["documentation"]["proposals"] == 1


def test_storage_events_surface_in_infrastructure_and_notifications():
    bus, dash = _wired()
    bus.publish_sync("storage_critical", {"disk_pct": 0.97})
    snap = dash.snapshot()
    assert snap["infrastructure"]["emergency"] is True
    assert snap["infrastructure"]["rendering_paused"] is True
    assert any("CRITICAL" in n for n in snap["notifications"])


def test_dream_meter_honest_until_revenue_connected():
    bus, dash = _wired()
    snap = dash.snapshot()
    assert snap["dream"]["connected"] is False
    assert snap["dream"]["revenue_total"] == 0.0
    assert "not yet connected" in dash.briefing()
    # once revenue is wired
    dash.record_revenue(143.0)
    assert dash.snapshot()["dream"]["connected"] is True
    assert dash.goal_progress > 0


def test_briefing_reads_like_a_ceo_briefing():
    bus, dash = _wired()
    bus.publish_sync("publish.completed", {})
    bus.publish_sync("knowledge.promoted", {})
    bus.publish_sync("kg.node_created", {})
    text = dash.briefing(name="Ajay")
    assert text.startswith("Good morning Ajay.")
    assert "AI Studio: 1 published" in text
    assert "Dream:" in text
    assert "$7,938,839" in text     # goal rounded to nearest dollar for the briefing
