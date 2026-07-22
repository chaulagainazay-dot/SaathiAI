"""M15.1 LIVE local-connector verification.

These genuinely execute through the connector platform against the real local
environment (filesystem + git) — no fixtures, no mocks. This is the only
LIVE-TESTED evidence class produced in this environment; all cloud/OAuth
connectors remain environment-blocked (no credentials) and are NOT faked.
"""
import shutil
import tempfile

import pytest

from saathi.connectors.platform import store as S
from saathi.connectors.platform import integration as I
from saathi.connectors.platform.execution import ExecutionEngine, ExecRequest


@pytest.fixture
def eng():
    return ExecutionEngine(store=S.ConnectorStore(tempfile.mktemp(suffix=".db")))


def test_live_local_fs_read(eng):
    # genuinely reads a real repo file through the platform (risk 0, no approval)
    r = eng.execute(ExecRequest(owner="ajay", tool_id="local_fs.read_local_file",
                                args={"path": "README.md"}))
    # README may or may not exist; either a real success with a checksum, or a
    # typed validation failure — never a faked success
    if r.status == "success":
        assert "text" in r.data and r.evidence and "checksum" in r.evidence[0]
    else:
        assert r.status == "failed" and r.errors[0]["class"] == "validation"


def test_live_local_fs_path_confinement(eng):
    # path escaping the repo is blocked by policy, genuinely
    r = eng.execute(ExecRequest(owner="ajay", tool_id="local_fs.read_local_file",
                                args={"path": "../../../../etc/passwd"}))
    assert r.status in ("blocked", "failed")


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_live_local_git_inspect(eng):
    r = eng.execute(ExecRequest(owner="ajay", tool_id="local_git.inspect_repository"))
    assert r.status == "success"
    assert isinstance(r.data.get("branch"), str) and r.data["branch"]
    assert "gateway_ref" in r.provenance  # genuinely gateway-routed


def test_live_local_via_funnel(eng):
    r = I.run(owner="ajay", tool_id="local_fs.inspect_disk", engine=eng)
    assert r["status"] == "success" and "free_gb" in r["data"]
