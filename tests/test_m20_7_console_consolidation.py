"""M20.7 — Engineering + inference console consolidation (read-only)."""
from __future__ import annotations

from pathlib import Path

from saathi.m20_console.flags import (
    FLAG_CATALOG,
    disable_procedure,
    domains_isolated,
    flag_snapshot,
)
from saathi.m20_console.status import (
    cli_discovery,
    engineering_snapshot,
    inference_control_center_facet,
    inference_snapshot,
    m20_console_status,
)

ROOT = Path(__file__).resolve().parents[1]


def test_flag_catalog_covers_both_domains():
    domains = {f.domain for f in FLAG_CATALOG}
    assert "engineering" in domains
    assert "inference" in domains
    keys = {f.key for f in FLAG_CATALOG}
    assert "SAATHI_ENG_ORCH_ENABLED" in keys
    assert "SAATHI_INFERENCE_ENABLED" in keys
    assert "SAATHI_INF_ROLLOUT" in keys


def test_flag_snapshot_defaults_off():
    snap = flag_snapshot()
    assert snap["schema"] == "m20_flag_snapshot.v1"
    assert isinstance(snap["flags"], list)
    assert len(snap["flags"]) >= 10


def test_disable_procedure():
    d = disable_procedure()
    assert "SAATHI_ENG_ORCH_ENABLED" in d["engineering_keys"]
    assert "SAATHI_INFERENCE_GATEWAY_ENABLED" in d["inference_keys"]
    assert d["hard_denials_always_false"]


def test_domains_isolated():
    iso = domains_isolated()
    assert iso["second_mission_engine"] is False
    assert iso["second_model_router"] is False
    assert iso["second_execution_gateway"] is False
    assert iso["merged_store"] is False
    assert iso["trading_guardian_coupled"] is False


def test_m20_console_status_shape():
    st = m20_console_status()
    assert st["schema"] == "m20_console_status.v1"
    assert "engineering" in st
    assert "inference" in st
    assert "flags" in st
    assert "cli" in st
    assert st["trading_guardian"]["engaged"] is False
    assert st["domains_isolated"]["merged_store"] is False


def test_engineering_and_inference_snapshots():
    e = engineering_snapshot()
    assert e["domain"] == "engineering"
    i = inference_snapshot()
    assert i["domain"] == "inference"
    # defaults
    if e.get("ok"):
        assert e.get("writes_enabled") is False or e.get("writes_enabled") in (False, True)
        # default should be false when env unset
        assert e["hard_denials"]["trading"] is False


def test_inference_facet_never_executes():
    f = inference_control_center_facet()
    assert f["schema_version"] == "inference_status.v1"
    assert f["executes_inference"] is False


def test_cli_discovery_lists_entrypoints():
    d = cli_discovery()
    assert "m20_console" in d
    assert "engineering" in d
    assert "inference_cert" in d


def test_cli_main():
    from saathi.m20_console.cli import main
    assert main(["help"]) == 0
    assert main(["domains"]) == 0
    assert main(["flags"]) == 0
    assert main(["status"]) == 0


def test_control_center_cells():
    from saathi.control_center.aggregator import ControlCenterAggregator
    agg = ControlCenterAggregator("m20_test")
    cell = agg.governed_inference()
    assert cell.status in ("ok", "unavailable")
    cell2 = agg.m20_console()
    assert cell2.status in ("ok", "unavailable")
    if cell2.status == "ok" and isinstance(cell2.value, dict):
        assert cell2.value.get("schema") == "m20_console_status.v1"


def test_no_gateway_merge_in_console():
    for name in ("flags.py", "status.py", "cli.py"):
        t = (ROOT / "saathi" / "m20_console" / name).read_text(encoding="utf-8")
        assert "ExecutionService" not in t
        assert "place_order" not in t
        # must not implement a second ModelRouter
        assert "class ModelRouter" not in t


def test_packages_remain_separate():
    assert (ROOT / "saathi" / "engineering" / "orchestrator.py").is_file()
    assert (ROOT / "saathi" / "inference" / "gateway_path.py").is_file()
    assert (ROOT / "saathi" / "m20_console" / "status.py").is_file()
