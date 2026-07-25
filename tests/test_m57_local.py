"""M57 localhost daily-use hardening — backend certification.

Single-host heartbeat (refresh + expiry), local-readiness checks, and the
saathi-local launcher's safety contract (PID ownership, fail-closed on unrelated
listeners, safe stop, localhost-only, log redaction). Everything advisory,
localhost-only, additive.
"""
from __future__ import annotations

import json
import os
import subprocess

import pytest

from saathi.platform.cluster import (
    DEFAULT_HEARTBEAT_TIMEOUT_SEC,
    LOCAL_NODE_ID,
    ClusterCoordinator,
)
from saathi.platform.service import reset_platform_for_tests
from saathi.tool_runtime.registry import reset_registry_for_tests

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LAUNCHER = os.path.join(REPO_ROOT, "bin", "saathi-local")


@pytest.fixture()
def alpha(tmp_path):
    reset_registry_for_tests()
    platform = reset_platform_for_tests(tmp_path / "m57.db")
    owner = platform.bootstrap_owner_secure(
        email="owner@m57.local", name="Owner", password="OwnerPassw0rd!",
        org_name="M57 Org", workspace_name="M57 Workspace",
    )
    return platform, owner["token"], platform.require_context(owner["token"])


# ── single-host heartbeat ─────────────────────────────────────────────────────
def test_heartbeat_refresh_makes_node_local_healthy(alpha):
    platform, _, ctx = alpha
    c = ClusterCoordinator(platform)
    c.beat_local_node()
    nh = c.node_health(ctx)["nodes"][LOCAL_NODE_ID]
    assert nh["healthy"] is True
    assert nh["heartbeat_age_seconds"] < DEFAULT_HEARTBEAT_TIMEOUT_SEC


def test_heartbeat_expiry_makes_node_local_stale(alpha):
    platform, _, ctx = alpha
    c = ClusterCoordinator(platform)
    c.beat_local_node()
    # Simulate the process stopping: age the heartbeat past the timeout.
    nodes = c._nodes()
    nodes[LOCAL_NODE_ID]["last_heartbeat"] = c.clock.now() - (DEFAULT_HEARTBEAT_TIMEOUT_SEC + 30)
    c._save_nodes(nodes)
    nh = c.node_health(ctx)["nodes"][LOCAL_NODE_ID]
    assert nh["healthy"] is False


def test_heartbeat_grants_no_authority(alpha):
    platform, _, ctx = alpha
    c = ClusterCoordinator(platform)
    before = c.topology(ctx)
    c.beat_local_node()
    after = c.topology(ctx)
    # Heartbeat changes only liveness, never ownership/lease/runtime authority.
    assert before["execution_ownership"] == after["execution_ownership"]
    assert after["canonical_runtime"] == "PlatformAgentRuntime"
    assert after["registered_tool_authority"] == "ExecutionGateway"


# ── local readiness ───────────────────────────────────────────────────────────
def test_local_readiness_report_is_safe_and_advisory():
    from saathi.platform import local_readiness

    rep = local_readiness.report()
    assert rep["overall"] in ("READY", "READY_WITH_LIMITATIONS", "NOT_READY")
    assert rep["safety"]["production_authorized"] is False
    assert rep["safety"]["multi_host"] == "DISABLED"
    blob = json.dumps(rep).lower()
    for forbidden in ("password", "token", "secret", "db_path", "authorization"):
        assert forbidden not in blob
    names = {c["check"] for c in rep["checks"]}
    for required in ("local_launcher", "localhost_only_binding", "local_heartbeat", "node_local_healthy"):
        assert required in names


# ── launcher safety contract (static) ─────────────────────────────────────────
def test_launcher_exists_and_is_executable():
    assert os.path.isfile(LAUNCHER)
    assert os.access(LAUNCHER, os.X_OK)


def test_launcher_localhost_only_and_failclosed_guards():
    src = open(LAUNCHER, encoding="utf-8").read()
    # localhost-only: binds 127.0.0.1 / localhost, never binds 0.0.0.0.
    assert 'BFF_HOST="127.0.0.1"' in src
    assert "--host 0.0.0.0" not in src and "0.0.0.0:" not in src
    assert "ngrok" not in src.lower()
    # fail-closed on unrelated listeners; never blanket-kills by port alone.
    assert "refusing to kill" in src
    # stop targets only PID-file-owned processes.
    assert "_owned" in src and "BACKEND_PID" in src and "FRONTEND_PID" in src
    # explicit frontend API base.
    assert "NEXT_PUBLIC_SAATHI_API=" in src or 'NEXT_PUBLIC_SAATHI_API="$API_BASE"' in src
    # does not clobber the pre-existing com.saathi.local agent.
    assert "com.saathi.local-launcher" in src


def _run(args, home):
    env = {**os.environ, "SAATHI_LOCAL_HOME": str(home), "PATH": os.environ.get("PATH", "")}
    return subprocess.run(
        ["bash", LAUNCHER, *args], capture_output=True, text=True, env=env, timeout=30
    )


def test_launcher_status_and_stop_are_safe_noops(tmp_path):
    home = tmp_path / "saathi-home"
    # status with nothing owned → exit 0, reports localhost-only safety posture.
    r = _run(["status"], home)
    assert r.returncode == 0
    assert "localhost-only" in r.stdout
    assert "multi-host     DISABLED" in r.stdout
    # stop with no PID files → safe no-op, exit 0, touches nothing.
    r2 = _run(["stop"], home)
    assert r2.returncode == 0
    assert "owned processes only" in r2.stdout


def test_launcher_stale_pid_is_not_treated_as_owned(tmp_path):
    home = tmp_path / "saathi-home"
    (home / "run").mkdir(parents=True)
    # A stale PID file pointing at PID 1 (init) must never be treated as owned.
    (home / "run" / "backend.pid").write_text("1\nbackend\n")
    r = _run(["status"], home)
    assert r.returncode == 0
    # PID 1 is not a SaathiOS backend → status must not claim it as running backend.
    assert "pid=1 " not in r.stdout.replace("port", "")


def test_launcher_logs_have_no_secrets(tmp_path):
    home = tmp_path / "saathi-home"
    _run(["status"], home)
    _run(["stop"], home)
    launcher_log = home / "logs" / "launcher.log"
    if launcher_log.exists():
        content = launcher_log.read_text().lower()
        for forbidden in ("token", "password", "secret", "authorization"):
            assert forbidden not in content
