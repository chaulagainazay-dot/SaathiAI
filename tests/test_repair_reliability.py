"""Tests for the reliability extensions: manifest, baseline, known-failure
registry, journal, and CLI mode contracts (exit codes, safety)."""
import json
from pathlib import Path

import pytest

from saathi.repair import verify as verify_mod
from saathi.repair.manifest import (
    load_manifest, run_critical_checks, validate_node_id, MANIFEST_PATH,
)
from saathi.repair.baseline import read_baseline, update_baseline
from saathi.repair.known_failures import KnownFailures, signature
from saathi.repair.journal import write_run_report, latest_report
from saathi.repair import cli


# ── manifest ───────────────────────────────────────────────────────────────
def test_manifest_loads_and_targets_exist():
    checks = load_manifest()
    assert len(checks) >= 8
    ids = {c.id for c in checks}
    assert "bff.payload_contract" in ids and "events.public_bus_api" in ids
    root = Path(__file__).resolve().parent.parent
    for c in checks:
        for t in c.targets:
            assert (root / t.split("::")[0]).exists(), f"missing target {t}"


def test_node_id_validation_blocks_shell_metacharacters():
    assert validate_node_id("tests/test_bff.py::test_payload_has_full_contract")
    assert not validate_node_id("tests/x.py; rm -rf /")
    assert not validate_node_id("$(evil)")
    assert not validate_node_id("a && b")


def test_critical_checks_run_with_injected_runner():
    calls = []

    def fake_runner(targets):
        calls.append(targets)
        return verify_mod.TestOutcome(passed=1, failed=0, ran=True)

    res = run_critical_checks(runner=fake_runner)
    assert calls, "runner was not invoked"
    assert "server.import" in res
    assert isinstance(res["_all_ok"], bool)


def test_critical_checks_blocking_failure_flips_all_ok(monkeypatch):
    def failing_runner(targets):
        return verify_mod.TestOutcome(passed=0, failed=1, ran=True)
    monkeypatch.setattr(verify_mod, "server_smoke", lambda: (True, 297))
    res = run_critical_checks(runner=failing_runner)
    assert res["_all_ok"] is False


# ── baseline ───────────────────────────────────────────────────────────────
def test_baseline_refuses_partial_success(tmp_path):
    with pytest.raises(ValueError):
        update_baseline(branch="b", commit="c", passed=1, failed=0, skipped=0,
                        collection_errors=0, duration_sec=1.0, server_import=True,
                        route_count=1, path=tmp_path / "b.json", full_success=False)


def test_baseline_updates_only_after_full_success(tmp_path):
    p = tmp_path / "b.json"
    data = update_baseline(branch="milestone/x", commit="abc123", passed=900,
                           failed=0, skipped=1, collection_errors=0,
                           duration_sec=390.0, server_import=True,
                           route_count=297, path=p, full_success=True)
    saved = read_baseline(p)
    assert saved["passed"] == 900 and saved["route_count"] == 297
    assert saved["commit"] == "abc123" and "timestamp" in saved
    assert data == saved


# ── known-failure registry ─────────────────────────────────────────────────
def test_registry_new_recurring_resolved_returned(tmp_path):
    reg = KnownFailures(tmp_path / "kf.json")
    fail = {"node_id": "tests/t.py::t_a", "exception_type": "AssertionError",
            "assertion": "assert 2 == 3", "subsystem": "bff"}
    r1 = reg.observe([fail])
    assert r1["new"] == ["tests/t.py::t_a"]
    r2 = reg.observe([fail])
    assert r2["recurring"] == ["tests/t.py::t_a"]
    r3 = reg.observe([])                       # failure disappeared
    assert r3["resolved"] == ["tests/t.py::t_a"]
    r4 = reg.observe([fail])                   # repaired failure returns
    assert r4["returned"] == ["tests/t.py::t_a"]


def test_registry_signature_change_detected(tmp_path):
    reg = KnownFailures(tmp_path / "kf.json")
    reg.observe([{"node_id": "tests/t.py::t_b", "exception_type": "KeyError",
                  "assertion": "x"}])
    r = reg.observe([{"node_id": "tests/t.py::t_b", "exception_type": "TypeError",
                      "assertion": "y"}])
    assert r["signature_changed"] == ["tests/t.py::t_b"]


def test_signature_is_stable_and_normalized():
    a = signature("tests/t.py::x", "AssertionError", "assert 2 == 3")
    b = signature("tests/t.py::x", "AssertionError", "  assert 2 == 3  ")
    assert a == b and len(a) == 16


# ── journal ────────────────────────────────────────────────────────────────
def test_journal_writes_json_and_md(tmp_path):
    j, m = write_run_report({"incident_id": "inc_x", "status": "repaired",
                             "files_changed": ["saathi/bff.py"],
                             "tests": {"passed": 10}}, directory=tmp_path)
    assert j.exists() and m.exists()
    data = json.loads(j.read_text())
    assert data["incident_id"] == "inc_x"
    assert "inc_x" in m.read_text()


def test_journal_redacts_secrets(tmp_path):
    tok = "hf_" + "JOURNALSECRETJOURNAL" + "012345"
    j, m = write_run_report({"incident_id": "inc_y",
                             "message": f"leak {tok} end"}, directory=tmp_path)
    assert tok not in j.read_text() and tok not in m.read_text()


def test_latest_report_returns_most_recent(tmp_path):
    write_run_report({"incident_id": "first"}, directory=tmp_path)
    import time as _t; _t.sleep(1.1)  # distinct second-resolution stamp
    write_run_report({"incident_id": "second"}, directory=tmp_path)
    assert latest_report(tmp_path)["incident_id"] == "second"


# ── CLI contracts ──────────────────────────────────────────────────────────
def test_cli_invalid_command_exit_2():
    assert cli.main(["definitely-not-a-command"]) == cli.EXIT_BAD_COMMAND


def test_cli_repair_rejects_bad_node_id():
    assert cli.main(["repair", "--test", "x; rm -rf /"]) == cli.EXIT_BAD_COMMAND


def test_cli_loop_bounds_max_cycles():
    assert cli.main(["loop", "--max-cycles", "0"]) == cli.EXIT_BAD_COMMAND
    assert cli.main(["loop", "--max-cycles", "99"]) == cli.EXIT_BAD_COMMAND


def test_cli_loop_refuses_dirty_tree(monkeypatch):
    from saathi.repair import rollback as rb
    monkeypatch.setattr(rb, "dirty_files", lambda: ["user_wip.py"])
    assert cli.main(["loop", "--max-cycles", "2"]) == cli.EXIT_UNSAFE_TREE


def test_cli_inspect_is_read_only(monkeypatch, tmp_path):
    """inspect must not modify the repo: hash the repair package before/after."""
    import hashlib, glob
    def digest():
        h = hashlib.sha1()
        for f in sorted(glob.glob("saathi/repair/*.py")):
            h.update(Path(f).read_bytes())
        return h.hexdigest()
    before = digest()
    # avoid heavy server import inside inspect
    from saathi.repair import evidence as ev_mod
    from saathi.repair.incident import RepairEvidence
    monkeypatch.setattr(ev_mod, "collect",
                        lambda ev=None, **k: (ev or RepairEvidence()))
    rc = cli.main(["inspect"])
    assert rc == cli.EXIT_OK
    assert digest() == before


def test_cli_repair_passing_node_exits_zero(monkeypatch):
    monkeypatch.setattr(verify_mod, "run_pytest",
                        lambda targets=None, timeout=900:
                        verify_mod.TestOutcome(passed=1, failed=0, ran=True))
    assert cli.main(["repair", "--test", "tests/test_bff.py::test_payload_has_full_contract"]) == cli.EXIT_OK
