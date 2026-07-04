"""Platform Maturity — an honest mirror computed from real signals."""
from saathi.platform_maturity import snapshot
from saathi.infrastructure.human_browser.run_store import RunStore
from saathi.infrastructure.human_browser.selector_registry import SelectorRegistry
from saathi.infrastructure.connectors import ConnectorRegistry


def test_honest_zeros_when_nothing_has_run(tmp_path):
    m = snapshot(run_store=RunStore(db_path=str(tmp_path / "r.db")),
                 sel_registry=SelectorRegistry(db_path=str(tmp_path / "s.db")),
                 registry=ConnectorRegistry())
    assert m["infrastructure"] == 100          # built
    assert m["automation_success"] == 0        # no runs → unproven, not a fake 100
    assert m["applications"] == 0              # no app has used it yet
    assert m["learning_confidence"] == 0
    assert m["real_data"] == 0
    for k in ("revenue_today", "episodes_today", "knowledge_added", "human_overrides", "runs_today"):
        assert k in m


def test_reflects_real_activity(tmp_path):
    rs = RunStore(db_path=str(tmp_path / "r.db"))
    rs.record(capability="publish_video", ok=True, duration_ms=30000)
    rs.record(capability="publish_video", ok=True, duration_ms=40000)
    rs.record(capability="publish_video", ok=False, error="selector not found")
    sr = SelectorRegistry(db_path=str(tmp_path / "s.db"))
    sr.seed("youtube/publish", ["#a"]); sr.learn("youtube/publish", "#TAUGHT")

    m = snapshot(run_store=rs, sel_registry=sr, registry=ConnectorRegistry())
    assert m["runs_today"] == 3
    assert m["automation_success"] == 67       # 2 of 3
    assert m["applications"] > 0               # AI Studio has touched the platform
    assert m["knowledge_added"] == 1           # one human-taught element
    assert m["learning_confidence"] > 0        # the taught selector is verified


def test_real_data_tracks_authenticated_connectors(tmp_path, monkeypatch):
    from saathi.infrastructure.connectors import install_defaults
    monkeypatch.setenv("HUMAN_BROWSER_SECRET", "s")   # human_publish + filesystem/browser auth
    reg = install_defaults(ConnectorRegistry())
    m = snapshot(run_store=RunStore(db_path=str(tmp_path / "r.db")),
                 sel_registry=SelectorRegistry(db_path=str(tmp_path / "s.db")), registry=reg)
    assert 0 < m["real_data"] < 100            # some connectors live, not all → honest middle
