"""M39.7 — Reproducibility & clean-environment validation tests (offline)."""
from __future__ import annotations

import json

import pytest

from saathi.credentials import m39_7 as m
from saathi.credentials import cli as credcli
from saathi.credentials.leakscan import is_clean


# ── reproducibility ──────────────────────────────────────────────────────────
def test_all_evidence_reproducible():
    r = m.reproduce_all()
    assert r["all_reproducible"] is True
    assert r["all_clean"] is True
    assert r["count"] == 5


@pytest.mark.parametrize("name", ["m39_1", "m39_2", "m39_3", "m39_4", "m39_5"])
def test_each_builder_reproducible(name):
    r = m.reproduce_evidence(name)
    assert r["reproducible"] is True and r["clean"] is True


def test_unknown_builder_not_reproducible():
    r = m.reproduce_evidence("m39_99")
    assert r["reproducible"] is False


def test_emit_and_reemit_byte_identical(tmp_path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    from saathi.credentials import m39_1
    m39_1.emit_m39_1_evidence(a)
    m39_1.emit_m39_1_evidence(b)
    for fa in sorted(a.glob("*.json")):
        fb = b / fa.name
        assert fa.read_bytes() == fb.read_bytes(), fa.name


# ── dependency self-containment ──────────────────────────────────────────────
def test_modules_self_contained():
    d = m.validate_dependencies()
    assert d["self_contained"] is True
    assert d["violations"] == []
    assert "saathi" in d["allowed_roots"]


def test_no_network_library_imported():
    d = m.validate_dependencies()
    banned = {"requests", "httpx", "urllib3", "aiohttp", "socket"}
    imported = {v.get("import", "").split(".")[0] for v in d["violations"]}
    assert not (imported & banned)


# ── CLI contract: documented commands actually run ───────────────────────────
_SAFE_READONLY_CMDS = [
    ["m39-preflight"],
    ["m39-1-diagnostics"],
    ["m39-1-plan", "--locator", "svc:acct"],
    ["m39-1-backend-availability", "--source-kind", "ENV_REFERENCE",
     "--env-var-name", "SAATHI_M397_MISSING"],
    ["m39-2-simulation-matrix"],
    ["m39-2-simulate-fault", "--mode", "throttle_429"],
    ["m39-3-prerequisites"],
    ["m39-3-framework"],
    ["m39-3-canary-decision"],
    ["m39-4-release-checklist"],
    ["m39-4-backward-compat"],
    ["m39-5-audit-contracts"],
    ["m39-5-alert-definitions"],
    ["m39-5-detect-alerts"],
    ["m39-5-incident-runbook"],
]


@pytest.mark.parametrize("argv", _SAFE_READONLY_CMDS, ids=lambda a: a[0])
def test_documented_command_runs(argv, capsys):
    rc = credcli.main(argv)
    assert isinstance(rc, int)
    assert rc in (0, 5)  # handled; never argparse "invalid choice" (SystemExit 2)


def test_contract_lists_all_documented():
    c = m.cli_contract()
    assert c["count"] == len(m.DOCUMENTED_CLI_COMMANDS)
    # spot-check representative commands per sub-milestone
    for cmd in ("m39-1-plan", "m39-2-simulation-matrix", "m39-3-canary-decision",
                "m39-4-backward-compat", "m39-5-detect-alerts"):
        assert cmd in c["commands"]


# ── evidence ─────────────────────────────────────────────────────────────────
def test_evidence_verdict_and_clean():
    ev = m.build_m39_7_evidence()
    assert ev["summary"]["verdict"] == "REPRODUCIBLE_AND_SELF_CONTAINED"
    for k, v in ev["summary"]["authorities"].items():
        assert v == "NOT GRANTED"
    for name, body in ev.items():
        assert is_clean(body), name


def test_evidence_emit(tmp_path):
    res = m.emit_m39_7_evidence(tmp_path)
    assert res["count"] == 4
    for p in res["written"]:
        assert is_clean(json.loads(open(p).read()))
