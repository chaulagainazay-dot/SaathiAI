"""M15 spec-driven delivery governance tests."""
import json
from pathlib import Path

from saathi.specs import traceability as T
from saathi.specs import cli

ROOT = T.ROOT
TRACE = ROOT / "specs" / "m15-universal-connectors" / "traceability.json"


def test_constitution_present():
    assert (ROOT / ".specify" / "memory" / "constitution.md").exists()
    txt = (ROOT / ".specify" / "memory" / "constitution.md").read_text()
    assert "Single Execution Boundary" in txt


def test_cli_commands(capsys):
    assert cli.main(["version"]) == 0
    assert cli.main(["health"]) == 0
    assert cli.main(["converge", str(TRACE)]) == 0


def test_traceability_complete():
    doc = T.load_traceability(TRACE)
    problems = T.validate_traceability(doc)
    assert problems == [], problems
    assert len(doc["requirements"]) >= 19


def test_convergence_gate(tmp_path):
    # a requirement pointing at a missing artifact must fail the gate
    bad = {"milestone": "MX", "constitution_version": "1.0",
           "requirements": [{"id": "MX-CONN-001", "text": "x",
                             "artifact": "does/not/exist.py",
                             "test": "does/not/exist.py::t"}]}
    p = tmp_path / "t.json"
    p.write_text(json.dumps(bad))
    res = T.converge(p)
    assert res["verdict"] == "NOT_CONVERGED" and res["problems"]
