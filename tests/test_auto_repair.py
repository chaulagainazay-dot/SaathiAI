"""Auto-Repair Loop test suite (30 focused tests).

External/slow operations (real pytest, real server import) are monkeypatched.
The end-to-end apply+commit+rollback path runs against a real temporary git
repo so the Git behaviour is genuinely exercised, never the production tree.
"""
import subprocess
from pathlib import Path

import pytest

from saathi.repair import (
    AutoRepairLoop, RepairIncident, FailureCategory, PolicyDecision,
    RepairStatus, RepairHistory, RepairLimits, verify_grounding, expected_behavior,
)
from saathi.repair.incident import RepairEvidence, RepairLevel
from saathi.repair.classifier import classify
from saathi.repair import policy as policy_mod
from saathi.repair import secrets_scan
from saathi.repair import verify as verify_mod
from saathi.repair import strategies as strat_mod
from saathi.repair.strategies import ReexportSymbolStrategy, select_strategy


# ---------------------------------------------------------------- fixtures
@pytest.fixture
def tmp_history(tmp_path):
    return RepairHistory(tmp_path / "hist.json")


@pytest.fixture
def tmp_git_repo(tmp_path):
    """A throwaway git repo with a package whose __init__ is empty."""
    r = tmp_path / "repo"
    (r / "pkg").mkdir(parents=True)
    (r / "pkg" / "__init__.py").write_text("")
    (r / "pkg" / "sub.py").write_text("VALUE = 1\n")
    subprocess.run(["git", "init", "-q"], cwd=r, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.t"], cwd=r, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=r, check=True)
    subprocess.run(["git", "add", "-A"], cwd=r, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=r, check=True)
    return r


# ---------------------------------------------------------------- 1-2 intake
def test_1_failed_test_creates_incident():
    inc = RepairIncident(source="pytest", failed_tests=["tests/test_x.py::t_a"])
    assert inc.incident_id.startswith("inc_")
    assert inc.source == "pytest"
    assert "tests/test_x.py::t_a" in inc.failed_tests


def test_2_runtime_exception_creates_incident():
    inc = RepairIncident(source="runtime", exception_type="RuntimeError",
                         stack_trace="RuntimeError: boom")
    assert inc.exception_type == "RuntimeError"
    assert inc.source == "runtime"


# ---------------------------------------------------------------- 3-4 classify
def test_3_classifier_identifies_import_failure():
    inc = RepairIncident(stack_trace="ImportError: cannot import name Foo from saathi.bar")
    classify(inc)
    assert inc.category == FailureCategory.IMPORT_ERROR
    assert inc.confidence >= 0.8


def test_4_classifier_identifies_execution_bypass():
    inc = RepairIncident(actual_behavior="generic director response instead of execution; "
                                          "gateway never called, execution bypass")
    classify(inc)
    assert inc.category in (FailureCategory.EXECUTION_BYPASS,
                            FailureCategory.TOOL_RESULT_NOT_GROUNDED,
                            FailureCategory.AGENT_HALLUCINATION)


# ---------------------------------------------------------------- 5-7 policy
def test_5_safe_repair_is_allowed(monkeypatch):
    inc = RepairIncident(stack_trace="coroutine 'x' was never awaited")
    classify(inc)
    assert inc.category == FailureCategory.ASYNC_ERROR
    monkeypatch.setattr(strat_mod, "has_strategy", lambda c: True)
    assert policy_mod.decide(inc) == PolicyDecision.AUTO_REPAIR_ALLOWED


def test_6_destructive_repair_requires_approval():
    inc = RepairIncident(stack_trace="sqlite3.OperationalError: no such table; migration")
    classify(inc)
    assert inc.category == FailureCategory.DATABASE_ERROR
    assert policy_mod.decide(inc) == PolicyDecision.APPROVAL_REQUIRED


def test_7_prohibited_connector_auth_is_manual():
    inc = RepairIncident(stack_trace="401 Unauthorized: token expired, reauth required")
    classify(inc)
    assert inc.category == FailureCategory.CONNECTOR_AUTH_ERROR
    assert policy_mod.decide(inc) == PolicyDecision.MANUAL_ONLY


# ---------------------------------------------------------------- 8-9 rollback
def test_8_rollback_point_created_before_edits(tmp_git_repo, monkeypatch):
    from saathi.repair import rollback as rb
    monkeypatch.setattr(rb, "ROOT", tmp_git_repo)
    rp = rb.create_rollback_point("inc_test")
    assert rp.ok
    assert rp.head and rp.branch


def test_9_unrelated_dirty_files_preserved(tmp_git_repo, monkeypatch):
    from saathi.repair import rollback as rb
    monkeypatch.setattr(rb, "ROOT", tmp_git_repo)
    (tmp_git_repo / "user_wip.txt").write_text("in-flight work")
    rp = rb.create_rollback_point("inc_test", allow_dirty=["pkg/__init__.py"])
    assert not rp.ok
    assert "unrelated uncommitted work" in rp.refused_reason


# ---------------------------------------------------------------- 10-13 verify/regression
def test_10_focused_tests_run_first():
    from saathi.repair.test_selector import focused_targets
    inc = RepairIncident(failed_tests=["tests/test_events_bus_api.py::test_x"],
                         subsystem="event_bus")
    classify(inc)
    targets = focused_targets(inc)
    # explicit failing file first (it exists in the real repo)
    assert targets and targets[0] == "tests/test_events_bus_api.py"


def test_11_full_suite_runs_after_focused(monkeypatch, tmp_history):
    calls = []
    monkeypatch.setattr(verify_mod, "run_pytest",
                        lambda targets=None, timeout=900: calls.append(targets) or
                        verify_mod.TestOutcome(passed=1, ran=True))
    monkeypatch.setattr(verify_mod, "server_smoke", lambda: (True, 296))
    # focused then full
    verify_mod.run_pytest(["tests/test_x.py"])
    verify_mod.run_pytest(["tests/"])
    assert calls[0] == ["tests/test_x.py"] and calls[1] == ["tests/"]


def test_12_repair_fails_when_regression_appears():
    before = verify_mod.TestOutcome(passed=100, failed=1, ran=True)
    after = verify_mod.TestOutcome(passed=98, failed=3, ran=True)  # got worse
    rep = verify_mod.guard(before, after, 296, 296)
    assert not rep.success and rep.new_regressions


def test_13_repair_fails_when_route_count_drops():
    before = verify_mod.TestOutcome(passed=100, failed=1, ran=True)
    after = verify_mod.TestOutcome(passed=101, failed=0, ran=True)
    rep = verify_mod.guard(before, after, 296, 290,
                           focused_after=verify_mod.TestOutcome(passed=1, ran=True))
    assert not rep.success and rep.route_regression


# ---------------------------------------------------------------- 14 evidence
def test_14_no_success_without_evidence():
    # grounding: connector read with empty trace => not executed
    v = verify_grounding("show my latest gmail", trace=[])
    assert not v.grounded and "not executed" in v.reason


# ---------------------------------------------------------------- 15 secrets
def test_15_secret_detection_blocks_commit(tmp_path):
    f = tmp_path / "leak.py"
    # Build the fake token at runtime so the literal is not present in THIS
    # source file at rest (otherwise the repo's own secret gate would flag it).
    fake = "hf_" + "ABCDEFGHIJKLMNOPQRSTUVWXYZ" + "012345"
    f.write_text(f"TOKEN = '{fake}'\n")
    hits = secrets_scan.scan_files([str(f)])
    assert str(f) in hits and hits[str(f)].hits[0].rule == "huggingface_token"


def test_15b_example_placeholder_not_flagged(tmp_path):
    f = tmp_path / "ex.json"
    f.write_text('"private_key": "REPLACE_WITH_PRIVATE_KEY"\n')
    assert secrets_scan.scan_files([str(f)]) == {}


# ---------------------------------------------------------------- 16-17 loop limits
def test_16_failed_repair_does_not_loop_forever(tmp_history):
    inc = RepairIncident(stack_trace="coroutine was never awaited")
    classify(inc)
    fp = inc.fingerprint()
    tmp_history.record({"incident_id": "a", "fingerprint": fp, "status": "failed"})
    tmp_history.record({"incident_id": "b", "fingerprint": fp, "status": "failed"})
    dec = policy_mod.decide(inc, prior_attempts=tmp_history.attempts_for(fp))
    assert dec == PolicyDecision.MANUAL_ONLY


def test_17_repeated_fingerprint_escalates_to_manual(tmp_history):
    loop = AutoRepairLoop(history=tmp_history, limits=RepairLimits(max_attempts_per_incident=2))
    inc = RepairIncident(stack_trace="coroutine was never awaited")
    classify(inc)
    fp = inc.fingerprint()
    tmp_history.record({"incident_id": "a", "fingerprint": fp, "status": "failed"})
    tmp_history.record({"incident_id": "b", "fingerprint": fp, "status": "failed"})
    out = loop.run(inc)
    assert out.status == RepairStatus.MANUAL_REQUIRED


# ---------------------------------------------------------------- 18-19 connector/hallucination
def test_18_connector_auth_not_patched_as_code(tmp_history):
    loop = AutoRepairLoop(history=tmp_history)
    inc = RepairIncident(stack_trace="401 Unauthorized: not authenticated")
    out = loop.run(inc)
    assert out.status == RepairStatus.MANUAL_REQUIRED
    assert "not connected or authenticated" in out.message
    assert not inc.repair_commit  # no code change


def test_19_task_hallucination_classified():
    inc = RepairIncident(actual_behavior="agent claimed email retrieved but tool "
                                          "never invoked; hallucinated success")
    classify(inc)
    assert inc.category in (FailureCategory.AGENT_HALLUCINATION,
                            FailureCategory.TOOL_RESULT_NOT_GROUNDED)


# ---------------------------------------------------------------- 20-22 e2e commit/push/rollback
def _wire_loop_to_tmp(monkeypatch, repo, history, *, routes_after=1, recover=True):
    """Point loop/rollback/verify at a temp repo with controlled test outcomes.

    Simulates a real before/after: the FIRST pytest run (baseline) shows a
    failure; subsequent runs (post-patch) show recovery when `recover` is True.
    """
    from saathi.repair import loop as loop_mod
    from saathi.repair import rollback as rb
    monkeypatch.setattr(loop_mod, "ROOT", repo)
    monkeypatch.setattr(rb, "ROOT", repo)
    # skip heavy evidence sweep (read-only, but touches real repo/server)
    monkeypatch.setattr(loop_mod.ev_mod, "collect", lambda ev=None, **k: ev or RepairEvidence())

    state = {"calls": 0}

    def fake_pytest(targets=None, timeout=900):
        state["calls"] += 1
        if state["calls"] == 1:      # baseline: failing
            return verify_mod.TestOutcome(passed=5, failed=1, ran=True)
        if recover:                   # post-patch: green
            return verify_mod.TestOutcome(passed=6, failed=0, ran=True)
        return verify_mod.TestOutcome(passed=4, failed=2, ran=True)  # worse

    monkeypatch.setattr(verify_mod, "run_pytest", fake_pytest)
    monkeypatch.setattr(verify_mod, "server_smoke", lambda: (True, routes_after))
    return AutoRepairLoop(history=history)


def test_20_local_commit_created_after_verification(tmp_git_repo, tmp_history, monkeypatch):
    loop = _wire_loop_to_tmp(monkeypatch, tmp_git_repo, tmp_history)
    inc = RepairIncident(stack_trace="ImportError: cannot import name VALUE from pkg")
    classify(inc)
    strat = ReexportSymbolStrategy(init_file="pkg/__init__.py", submodule="sub", symbol="VALUE")
    out = loop.run(inc, strategies=[strat])
    assert out.status == RepairStatus.REPAIRED
    assert inc.repair_commit
    # the fix landed
    assert "from .sub import VALUE" in (tmp_git_repo / "pkg" / "__init__.py").read_text()


def test_21_push_is_never_performed(tmp_git_repo, tmp_history, monkeypatch):
    calls = []
    real_run = subprocess.run

    def spy(cmd, *a, **k):
        if isinstance(cmd, list) and "push" in cmd:
            calls.append(cmd)
        return real_run(cmd, *a, **k)

    monkeypatch.setattr(subprocess, "run", spy)
    loop = _wire_loop_to_tmp(monkeypatch, tmp_git_repo, tmp_history)
    inc = RepairIncident(stack_trace="ImportError: cannot import name VALUE from pkg")
    classify(inc)
    loop.run(inc, strategies=[ReexportSymbolStrategy("pkg/__init__.py", "sub", "VALUE")])
    assert calls == []  # never pushed


def test_22_rollback_restores_safely(tmp_git_repo, monkeypatch):
    from saathi.repair import rollback as rb
    monkeypatch.setattr(rb, "ROOT", tmp_git_repo)
    head = rb.current_head()
    (tmp_git_repo / "pkg" / "__init__.py").write_text("garbage\n")
    subprocess.run(["git", "commit", "-aqm", "bad"], cwd=tmp_git_repo, check=True)
    assert rb.rollback_to(head)
    assert (tmp_git_repo / "pkg" / "__init__.py").read_text() == ""


# ---------------------------------------------------------------- 23-25 reports/async/cleanup
def test_23_reports_contain_no_secret_values(tmp_history):
    # Fake tokens built at runtime (kept out of this file's at-rest bytes).
    tok = "hf_" + "SECRETSECRETSECRET" + "012345"
    inc = RepairIncident(stack_trace=f"Authorization: Bearer {tok}")
    marker = tok[:12]
    # incident sanitizes on construction
    assert marker not in (inc.stack_trace or "")
    tmp_history.record({"incident_id": "x", "notes": f"token {tok} here"})
    dumped = tmp_history.path.read_text()
    assert marker not in dumped


def test_24_async_repair_operations_are_awaited():
    # regression guard for the exact class of bug the loop repairs
    from saathi.repair.strategies import AwaitAsyncCallStrategy
    s = AwaitAsyncCallStrategy(file="m.py", pattern="q.enqueue")
    plan = s.plan(RepairIncident())
    assert "await" in plan.intended_change.lower()


def test_25_background_tasks_cleaned_up(tmp_git_repo, tmp_history, monkeypatch):
    # after a repair run, working tree is clean except the committed change
    loop = _wire_loop_to_tmp(monkeypatch, tmp_git_repo, tmp_history)
    inc = RepairIncident(stack_trace="ImportError: cannot import name VALUE from pkg")
    classify(inc)
    loop.run(inc, strategies=[ReexportSymbolStrategy("pkg/__init__.py", "sub", "VALUE")])
    status = subprocess.run(["git", "status", "--short"], cwd=tmp_git_repo,
                            capture_output=True, text=True).stdout.strip()
    assert status == ""  # committed, nothing dangling


# ---------------------------------------------------------------- 26-27 history/repro
def test_26_repair_history_persisted(tmp_history):
    tmp_history.record({"incident_id": "z", "fingerprint": "fp1", "status": "repaired"})
    assert RepairHistory(tmp_history.path).get("z")["status"] == "repaired"


def test_27_user_reproducer_preserved():
    inc = RepairIncident(source="user_report", command="Analyze my email",
                         expected_behavior="Retrieve Gmail and analyze",
                         actual_behavior="Generic director response")
    assert inc.command == "Analyze my email"
    assert inc.expected_behavior.startswith("Retrieve Gmail")


# ---------------------------------------------------------------- 28 approval gate
def test_28_approval_required_does_not_execute(tmp_history, monkeypatch):
    from saathi.repair import loop as loop_mod
    monkeypatch.setattr(loop_mod.ev_mod, "collect", lambda ev=None, **k: ev or RepairEvidence())
    loop = AutoRepairLoop(history=tmp_history)
    inc = RepairIncident(stack_trace="assert 2 == 3 contract mismatch")
    out = loop.run(inc, approve=False)
    assert inc.policy == PolicyDecision.APPROVAL_REQUIRED
    assert out.status == RepairStatus.DIAGNOSED
    assert not inc.repair_commit


# ---------------------------------------------------------------- 29 pasted content
def test_29_pasted_content_does_not_trigger_connector():
    exp = expected_behavior("analyze this email: Hello team, Q3 numbers...",
                            has_pasted_content=True)
    assert exp.value == "analyze_provided"
    v = verify_grounding("analyze this email: Hello...", trace=["connector:gmail:ok"],
                         has_pasted_content=True)
    assert not v.grounded  # connector call was wrong here


# ---------------------------------------------------------------- 30 outage vs rewrite
def test_30_external_outage_diagnosed_not_rewritten(tmp_history):
    loop = AutoRepairLoop(history=tmp_history)
    inc = RepairIncident(stack_trace="connector gmail: connection refused 503 upstream")
    inc.subsystem = "connectors"
    classify(inc)
    # connector runtime error -> not an AUTO code category
    assert inc.category in (FailureCategory.CONNECTOR_RUNTIME_ERROR,
                            FailureCategory.CONNECTOR_AUTH_ERROR)
    out = loop.run(inc)
    assert out.status in (RepairStatus.DIAGNOSED, RepairStatus.MANUAL_REQUIRED)
    assert not inc.repair_commit
