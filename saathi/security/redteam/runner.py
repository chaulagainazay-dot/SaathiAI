"""M15.2 deterministic red-team runner.

Loads the versioned corpus, runs each attack's deterministic probe against an
isolated in-process SaathiOS target, and produces normalized findings. This is
the AUTHORITATIVE path: pass/fail is decided by deterministic evidence only.
The optional HackAgent adversarial generator is advisory and separate.
"""
from __future__ import annotations

import time
from pathlib import Path

import yaml

from saathi.security.redteam.config import RedTeamConfig, Budget
from saathi.security.redteam.targets import SaathiTarget
from saathi.security.redteam.findings import Finding, summarize, Evidence
from saathi.security.redteam import probes as P

ROOT = Path(__file__).resolve().parent.parent.parent.parent
CORPUS = ROOT / "security" / "redteam" / "attacks" / "corpus.yaml"


def load_corpus(path: Path | None = None) -> dict:
    return yaml.safe_load((path or CORPUS).read_text())


def _severity_default(a: dict) -> str:
    return a.get("severity", "medium")


def run_suite(*, suite: str | None = None, config: RedTeamConfig | None = None,
              corpus_path: Path | None = None) -> dict:
    """Run all attacks (optionally filtered to a category `suite`). Fresh
    isolated target per attack so state never bleeds between probes."""
    config = config or RedTeamConfig()
    config.validate()
    corpus = load_corpus(corpus_path)
    budget: Budget = config.budget
    attacks = corpus.get("attacks", [])
    if suite:
        attacks = [a for a in attacks if a.get("category") == suite]
    attacks = attacks[: budget.max_attacks]

    findings: list[Finding] = []
    missing: list[str] = []
    started = time.time()
    for a in attacks:
        if time.time() - started > budget.max_runtime_sec:
            break
        aid = a["attack_id"]
        if aid not in P.PROBES:
            missing.append(aid)
            continue
        target = SaathiTarget(config)   # isolated per attack
        try:
            held, evidence = P.run_probe(aid, target)
        except Exception as e:
            held, evidence = False, {"probe_error": str(e)[:200]}
        findings.append(Finding(
            attack_id=aid, requirement_id=a.get("requirement", ""),
            category=a.get("category", ""), target=a.get("target", "inproc"),
            severity=_severity_default(a), boundary_held=bool(held),
            deterministic_evidence=evidence, component=a.get("component", ""),
            expected_behavior=a.get("expected", ""),
            actual_behavior=("boundary held" if held else "BOUNDARY FAILED"),
            evidence_class=Evidence.DETERMINISTIC.value,
            regression_test=f"tests/test_m15_2_security.py::test_{aid.lower().replace('-', '_')}"))

    summary = summarize(findings)
    summary["corpus_version"] = corpus.get("version")
    summary["suite"] = suite or "all"
    summary["missing_probes"] = missing
    summary["duration_sec"] = round(time.time() - started, 3)
    summary["adversarial_generator"] = {
        "status": "environment_blocked",
        "reason": "HackAgent + live judge model not available in this environment; "
                  "deterministic probes are authoritative",
    }
    return {"summary": summary, "findings": [f.to_dict() for f in findings]}


def run_all(config: RedTeamConfig | None = None) -> dict:
    return run_suite(suite=None, config=config)
