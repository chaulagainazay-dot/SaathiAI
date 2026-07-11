"""M15.2 deterministic security suite — AUTHORITATIVE regression protection.

Every attack in the corpus runs its deterministic probe against a real isolated
SaathiOS boundary and must hold. A failure here is a confirmed vulnerability.
Individual named tests (test_iso_001, ...) match the regression_test ids in the
corpus so a specific boundary regression is pinpointed.
"""
import pytest

from saathi.security.redteam.config import RedTeamConfig
from saathi.security.redteam.targets import SaathiTarget
from saathi.security.redteam import probes as P
from saathi.security.redteam.runner import run_all, load_corpus


def _target():
    return SaathiTarget(RedTeamConfig())


@pytest.mark.parametrize("attack_id", sorted(P.PROBES.keys()))
def test_probe_boundary_holds(attack_id):
    held, evidence = P.run_probe(attack_id, _target())
    assert held is True, f"{attack_id} boundary FAILED: {evidence}"


def test_full_suite_no_release_blocking():
    res = run_all()
    s = res["summary"]
    assert s["release_blocking"] == 0, s["release_blocking_ids"]
    assert s["confirmed_vulnerabilities"] == 0
    assert s["missing_probes"] == []


def test_every_corpus_attack_has_a_probe():
    corpus = load_corpus()
    for a in corpus["attacks"]:
        assert a["attack_id"] in P.PROBES, f"no probe for {a['attack_id']}"


# named regression tests (stable ids referenced by corpus regression_test)
def test_iso_001():  # cross-user execution must be blocked (the remediated gap)
    held, ev = P.run_probe("ISO-001", _target())
    assert held, ev


def test_approval_001():
    held, ev = P.run_probe("APPROVAL-001", _target())
    assert held, ev


def test_secret_001():
    held, ev = P.run_probe("SECRET-001", _target())
    assert held, ev


def test_mcp_001():
    held, ev = P.run_probe("MCP-001", _target())
    assert held, ev


def test_retry_001():
    held, ev = P.run_probe("RETRY-001", _target())
    assert held, ev
