"""Platform Capability Registry tests (operational heartbeat) — AP-12."""
from saathi.capabilities import Capability, CapabilityRegistry, default_registry
from saathi.mission_control import MissionControlState


def test_maturity_is_furthest_stage_reached():
    assert Capability("x", "1.0").maturity == "planned"
    assert Capability("x", "1.0", designed=True).maturity == "designed"
    assert Capability("x", "1.0", designed=True, built=True).maturity == "built"
    assert Capability("x", "1.0", True, True, True, False).maturity == "tested"
    assert Capability("x", "1.0", True, True, True, True).maturity == "production"


def test_default_registry_reflects_current_state():
    r = default_registry()
    assert r.get("Storage Intelligence").maturity == "production"
    assert r.get("Model Router").maturity == "production"   # execution-path wired
    assert r.get("Memory").maturity == "built"              # not yet tested/production
    assert "Storage Intelligence" in r.production_ready()
    assert "Model Router" in r.production_ready()
    assert r.get("Runtime Governance Engine").maturity == "production"   # gate wired into execute_tool


def test_set_status_advances_capability():
    r = CapabilityRegistry()
    r.register(Capability("Memory", "0.9", designed=True, built=True))
    assert r.get("Memory").maturity == "built"
    r.set_status("Memory", tested=True)
    assert r.get("Memory").maturity == "tested"


def test_mission_control_snapshot_includes_capabilities():
    mc = MissionControlState()
    snap = mc.snapshot()
    assert "capabilities" in snap
    names = {c["name"] for c in snap["capabilities"]}
    assert "Storage Intelligence" in names and "Model Router" in names
    storage = next(c for c in snap["capabilities"] if c["name"] == "Storage Intelligence")
    assert storage["maturity"] == "production"
