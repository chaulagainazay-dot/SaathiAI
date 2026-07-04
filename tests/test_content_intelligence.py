"""Content Intelligence tests — analytics → verified knowledge → learning."""
import pytest
from saathi.content_intelligence import (
    ContentAnalytics, ContentIntelligence, normalize, length_bucket, hour_bucket,
)
from saathi.learning.registry import CapabilityImprovementRegistry


def _ci(tmp_path, imp=None, threshold=5, events=None, episodes=None):
    return ContentIntelligence(
        tmp_path / "ci.db", improvement_registry=imp, verify_threshold=threshold,
        min_lift=0.05, now=lambda: 1.0,
        publish=lambda n, p: (events if events is not None else []).append((n, p)),
        record_episode=lambda **kw: (episodes if episodes is not None else []).append(kw) or 1)


def _vid(vid, **kw):
    base = dict(hook_style="curiosity", thumbnail_style="blue", cta_style="subscribe",
                length_s=420, publish_hour=19, views=1000, impressions=8000,
                ctr=0.12, retention=0.55, watch_time_s=300, subscribers=20, rpm=8, revenue_usd=10)
    base.update(kw)
    return ContentAnalytics(video_id=vid, platform="youtube", **base)


# ── multi-platform normalization into one schema ───────────────────────────
def test_normalize_maps_platform_keys():
    yt = normalize("youtube", {"id": "v1", "views": 5000, "average_percentage_viewed": 0.6,
                               "estimated_revenue": 12, "hook": "question"})
    assert yt.video_id == "v1" and yt.views == 5000 and yt.retention == 0.6
    assert yt.revenue_usd == 12 and yt.hook_style == "question"
    tk = normalize("tiktok", {"media_id": "t9", "plays": 20000, "follows": 300})
    assert tk.video_id == "t9" and tk.views == 20000 and tk.subscribers == 300


def test_buckets():
    assert length_bucket(300) == "4-6m" and length_bucket(450) == "6-8m"
    assert hour_bucket(19) == "evening" and hour_bucket(8) == "morning"


# ── ingest stores, records episode, returns dream contribution ─────────────
def test_ingest_records_episode_and_dream(tmp_path):
    eps, evs = [], []
    ci = _ci(tmp_path, episodes=eps, events=evs)
    out = ci.ingest(_vid("v1", revenue_usd=100))
    assert out["dream_contribution_pct"] > 0
    assert eps[0]["intent"] == "content_analytics"
    assert evs[-1][0] == "content.analytics"


# ── cohort knowledge: a stronger hook cohort earns positive lift + verify ──
def test_knowledge_learns_cohort_lift_and_verifies(tmp_path):
    ci = _ci(tmp_path, threshold=5)
    # 6 curiosity videos with high CTR, 6 bold videos with low CTR
    for i in range(6):
        ci.ingest(_vid(f"c{i}", hook_style="curiosity", ctr=0.16))
    for i in range(6):
        ci.ingest(_vid(f"b{i}", hook_style="bold", ctr=0.06))
    ks = {k.value: k for k in ci.knowledge() if k.dimension == "hook"}
    assert ks["curiosity"].lift > 0 and ks["bold"].lift < 0
    assert ks["curiosity"].verified and ks["curiosity"].sample_count == 6
    recs = ci.recommendations()
    assert any("curiosity" in r for r in recs)


# ── verified knowledge is promoted into the M2 improvement pipeline ────────
def test_verified_knowledge_creates_improvement_proposal(tmp_path):
    imp = CapabilityImprovementRegistry(tmp_path / "imp.db", now=lambda: 1.0)
    ci = _ci(tmp_path, imp=imp, threshold=5)
    for i in range(6):
        ci.ingest(_vid(f"c{i}", hook_style="curiosity", ctr=0.18))
    for i in range(6):
        ci.ingest(_vid(f"b{i}", hook_style="bold", ctr=0.05))
    props = imp.by_capability("Autonomous Content Factory")
    assert any("curiosity" in p.improvement for p in props)


# ── comparative analysis: why A beat B ─────────────────────────────────────
def test_compare_identifies_winner_and_diffs(tmp_path):
    ci = _ci(tmp_path)
    ci.ingest(_vid("A", hook_style="curiosity", ctr=0.2, retention=0.6, thumbnail_style="blue"))
    ci.ingest(_vid("B", hook_style="bold", ctr=0.05, retention=0.4, thumbnail_style="orange"))
    r = ci.compare("A", "B")
    assert r["winner"] == "A"
    assert "hook_style" in r["differences"] and "thumbnail_style" in r["differences"]
    assert r["metric_winners"]["ctr"] == "A"


# ── leaderboard ranks by performance ───────────────────────────────────────
def test_leaderboard(tmp_path):
    ci = _ci(tmp_path)
    ci.ingest(_vid("low", ctr=0.05, retention=0.3))
    ci.ingest(_vid("high", ctr=0.2, retention=0.7))
    lb = ci.leaderboard()
    assert lb[0]["video_id"] == "high"


# ── executive briefing line is actionable ──────────────────────────────────
def test_content_briefing_is_actionable(tmp_path):
    ci = _ci(tmp_path, threshold=3)
    for i in range(4):
        ci.ingest(_vid(f"c{i}", hook_style="curiosity", ctr=0.17))
    for i in range(4):
        ci.ingest(_vid(f"b{i}", hook_style="bold", ctr=0.06))
    line = ci.content_briefing()
    assert "Repeat this format" in line
