"""M15.2 harness unit tests — config guards, redaction, findings, baseline, CLI."""
import json
import tempfile
from pathlib import Path

import pytest

from saathi.security.redteam import config as C
from saathi.security.redteam.config import RedTeamConfig, TargetNotAuthorized
from saathi.security.redteam.findings import Finding, summarize, Severity
from saathi.security.redteam import baseline, hackagent
from saathi.security.redteam import cli


# ── target authorization / production blocking ──────────────────────────────
@pytest.mark.parametrize("bad", [
    "https://api.production.com", "http://www.example.com", "https://saathi.prod.io",
    "http://10.0.0.5:8765", "https://something.ai",
])
def test_production_targets_blocked(bad):
    with pytest.raises(TargetNotAuthorized):
        C.assert_target_authorized(bad)


@pytest.mark.parametrize("ok", ["inproc", "http://localhost:8765", "http://127.0.0.1:9000"])
def test_local_targets_allowed(ok):
    C.assert_target_authorized(ok)  # no raise


def test_cloud_sync_cannot_be_enabled():
    cfg = RedTeamConfig(cloud_sync=True)
    with pytest.raises(TargetNotAuthorized):
        cfg.validate()


def test_default_mode_local_no_cloud():
    cfg = RedTeamConfig()
    cfg.validate()
    assert cfg.mode == "local" and cfg.cloud_sync is False


# ── secret redaction ────────────────────────────────────────────────────────
def test_redaction_of_secrets():
    r = C.redact("here token=abc123 and password: hunter2 done")
    assert "abc123" not in r and "hunter2" not in r and "[REDACTED]" in r


def test_redact_obj_recursive():
    o = C.redact_obj({"a": ["bearer=xyz", {"k": "api_key=zzz"}]})
    blob = json.dumps(o)
    assert "xyz" not in blob and "zzz" not in blob


def test_envvar_value_redacted():
    r = C.redact("GITHUB_TOKEN=ghp_supersecretvalue")
    assert "ghp_supersecretvalue" not in r


# ── finding model: deterministic authoritative, judge advisory ──────────────
def test_finding_confirmed_only_when_boundary_fails():
    held = Finding(attack_id="X-1", requirement_id="M15-2-PI-001", category="c",
                   target="inproc", severity="high", boundary_held=True)
    failed = Finding(attack_id="X-2", requirement_id="M15-2-PI-001", category="c",
                     target="inproc", severity="critical", boundary_held=False)
    assert held.is_confirmed_vuln() is False
    assert failed.is_confirmed_vuln() is True


def test_judge_opinion_does_not_confirm():
    # a judge saying "vulnerable" while the boundary held is NOT a confirmed vuln
    f = Finding(attack_id="X-3", requirement_id="M15-2-PI-001", category="c",
                target="inproc", severity="high", boundary_held=True,
                judge_assessment={"verdict": "vulnerable", "confidence": 0.9})
    assert f.is_confirmed_vuln() is False


def test_summary_release_blocking():
    fs = [
        Finding(attack_id="a", requirement_id="r", category="c", target="t",
                severity="critical", boundary_held=False),
        Finding(attack_id="b", requirement_id="r", category="c", target="t",
                severity="low", boundary_held=False),
        Finding(attack_id="c", requirement_id="r", category="c", target="t",
                severity="high", boundary_held=True),
    ]
    s = summarize(fs)
    assert s["confirmed_vulnerabilities"] == 2
    assert s["release_blocking"] == 1  # only the critical (low not blocking)


def test_finding_to_dict_redacts():
    f = Finding(attack_id="a", requirement_id="r", category="c", target="t",
                severity="low", boundary_held=False,
                deterministic_evidence={"leak": "token=abc123"})
    assert "abc123" not in json.dumps(f.to_dict())


# ── hackagent: absent → environment_blocked, cannot be enabled ──────────────
def test_hackagent_environment_blocked():
    a = hackagent.availability()
    assert a["status"] in ("environment_blocked", "available", "version_mismatch_blocked")
    assert a["cloud_sync"] is False
    if a["status"] != "available":
        with pytest.raises(RuntimeError):
            hackagent.guard_enabled(True)


# ── baseline generation + compare ───────────────────────────────────────────
def test_baseline_generate_and_compare(tmp_path):
    p = tmp_path / "baseline.json"
    doc = baseline.generate(path=p)
    assert doc["totals"]["release_blocking"] == 0
    assert "fingerprints" in doc
    cmp = baseline.compare(path=p)
    assert cmp["status"] == "compared" and cmp["regression"] is False


# ── CLI exit codes ──────────────────────────────────────────────────────────
def test_cli_health_and_run_exit_codes(capsys):
    assert cli.main(["health"]) == 0
    assert cli.main(["list-attacks"]) == 0
    assert cli.main(["run"]) == 0            # 0 = no release-blocking findings
    assert cli.main(["bogus"]) == 2
