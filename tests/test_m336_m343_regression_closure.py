"""M336–M343 — regression-debt closure guards.

These tests protect the M337 repairs from silently regressing back into either
of the two inherited root causes, and — more importantly — prove the repairs did
not weaken any safety behaviour:

  RC-A  Installation OUTPUTS (.venv, saathi-os/node_modules) were treated as
        host PREREQUISITES, so every private-alpha surface was blocked on any
        checkout where installation had not already been performed in place.
        The repair scopes those checks; it must not remove them, must not stop
        reporting them, and must still fail closed on the paths that spawn a
        server.

  RC-B  The release gate counted a bare PEM header as a leaked private key, so
        it blocked every release on its own safety machinery. The repair raises
        detector precision; a real key must still block the release.

Everything here is offline, localhost-only, and grants no authority.
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

from saathi.ops import release_gate as RG
from saathi.platform.private_alpha.prepare import INSTALLABLE_CHECKS, prepare

REPO = Path(__file__).resolve().parents[1]
LAUNCHER = REPO / "bin" / "saathi-local"


# ── RC-A · launcher preflight is role-conditional, not removed ───────────────
def _run_launcher(args, home, extra_env=None):
    env = {**os.environ, "SAATHI_LOCAL_HOME": str(home)}
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        ["bash", str(LAUNCHER), *args],
        capture_output=True, text=True, env=env, timeout=30,
    )


def test_launcher_still_fails_closed_when_backend_must_spawn_without_venv(tmp_path):
    """A FREE backend port means the launcher must spawn uvicorn itself.

    The venv check must still fire there and must still abort non-zero.
    """
    home = tmp_path / "saathi-home"
    r = _run_launcher(
        ["start"], home,
        extra_env={
            "SAATHI_REPO": str(tmp_path / "empty-repo"),
            "SAATHI_LOCAL_ASSESS_BACKEND": "free",
            "SAATHI_LOCAL_ASSESS_FRONTEND": "external-healthy 48062",
        },
    )
    assert r.returncode != 0
    assert "python venv missing" in r.stdout
    assert "environment not ready" in r.stdout
    assert "is ready" not in r.stdout


def test_launcher_still_fails_closed_when_frontend_must_spawn_without_node_modules(tmp_path):
    """A FREE frontend port means the launcher must spawn `npm run dev` itself."""
    home = tmp_path / "saathi-home"
    fake_repo = tmp_path / "fake-repo"
    (fake_repo / "saathi-os").mkdir(parents=True)
    (fake_repo / ".venv" / "bin").mkdir(parents=True)
    py = fake_repo / ".venv" / "bin" / "python"
    py.write_text("#!/usr/bin/env bash\nexit 0\n")
    py.chmod(0o755)
    r = _run_launcher(
        ["start"], home,
        extra_env={
            "SAATHI_REPO": str(fake_repo),
            "SAATHI_LOCAL_ASSESS_BACKEND": "external-healthy 1782",
            "SAATHI_LOCAL_ASSESS_FRONTEND": "free",
        },
    )
    assert r.returncode != 0
    assert "frontend deps missing" in r.stdout
    assert "is ready" not in r.stdout


def test_launcher_toolchain_checks_still_exist_in_source():
    """The repair scoped the checks; it must never have deleted them."""
    src = LAUNCHER.read_text(encoding="utf-8")
    assert "_check_backend_toolchain" in src
    assert "_check_frontend_toolchain" in src
    assert "python venv missing at .venv" in src
    assert "frontend deps missing" in src
    # Each spawn path is still guarded.
    assert src.count("_check_backend_toolchain ||") == 1
    assert src.count("_check_frontend_toolchain ||") == 1


def test_launcher_reuse_path_is_not_gated_on_build_artifacts(tmp_path):
    """Two healthy pre-existing processes are reused; nothing is spawned."""
    home = tmp_path / "saathi-home"
    r = _run_launcher(
        ["start"], home,
        extra_env={
            "SAATHI_REPO": str(tmp_path / "empty-repo"),
            "SAATHI_LOCAL_ASSESS_BACKEND": "external-healthy 1782",
            "SAATHI_LOCAL_ASSESS_FRONTEND": "external-healthy 48062",
        },
    )
    assert r.returncode == 0
    assert "SaathiOS localhost is ready" in r.stdout
    assert "python venv missing" not in r.stdout


def test_launcher_unrelated_occupant_blocker_is_reported_not_masked(tmp_path):
    """PID-safety refusal must be the reported reason, never hidden behind env."""
    home = tmp_path / "saathi-home"
    r = _run_launcher(
        ["start"], home,
        extra_env={
            "SAATHI_REPO": str(tmp_path / "empty-repo"),
            "SAATHI_LOCAL_ASSESS_BACKEND": "unrelated 99999",
        },
    )
    assert r.returncode != 0
    assert "UNRELATED PID 99999" in r.stdout
    assert "refusing to kill" in r.stdout
    assert "python venv missing" not in r.stdout


# ── RC-A · prepare() separates host prerequisites from installable outputs ───
def test_prepare_still_reports_installable_checks_with_remediation():
    """Scoping must not silence the checks or drop their remediation text."""
    rep = prepare(install_deps=False)
    by_name = {c["check"]: c for c in rep["checks"]}
    for name in INSTALLABLE_CHECKS:
        assert name in by_name, f"{name} check must still run"
        assert by_name[name]["installable"] is True
    # Whatever this machine's state, the two classes are reported separately.
    assert isinstance(rep["ok"], bool)
    assert isinstance(rep["install_complete"], bool)
    assert isinstance(rep["pending_install_steps"], list)
    if not rep["install_complete"]:
        assert rep["pending_install_steps"]
        assert rep["remediations"], "missing dependencies must carry remediation"
        for step in rep["pending_install_steps"]:
            assert by_name[step]["status"] == "FAIL", (
                "a pending install step must still be reported as FAIL, not downgraded"
            )


def test_prepare_host_prerequisites_still_gate_ok():
    """Non-installable required checks must still be able to clear `ok`."""
    rep = prepare(install_deps=False)
    hard_fails = [
        c for c in rep["checks"]
        if c["status"] == "FAIL" and c["required"] and not c["installable"]
    ]
    assert rep["ok"] is (not hard_fails)


def test_prepare_never_collects_secrets_or_authorizes_production():
    rep = prepare(install_deps=False)
    assert rep["production_authorized"] is False
    assert rep["public_exposure_authorized"] is False
    names = {c["check"] for c in rep["checks"]}
    assert {"secret_collection", "paid_providers", "production"} <= names


def test_certification_surfaces_install_completeness_as_its_own_check():
    """An incomplete installation must stay visible in the M165 gate report."""
    from saathi.platform.private_alpha.certification import (
        run_private_alpha_certification,
    )

    report = run_private_alpha_certification(write_evidence=False)
    names = {c["check"] for c in report["checks"]}
    assert "installation_prepare" in names
    assert "installation_complete" in names
    assert report["production_authorized"] is False
    assert report["public_exposure_authorized"] is False


# ── RC-B · release-gate private-key detector precision ──────────────────────
def test_bare_pem_marker_is_not_key_material():
    assert RG.pem_carries_key_material("-----BEGIN RSA PRIVATE KEY-----") is False
    assert RG.pem_carries_key_material(
        '{"private_key": "-----BEGIN RSA PRIVATE KEY-----\\nMIIE"}'
    ) is False
    assert RG.pem_carries_key_material(
        're.compile(r"-----BEGIN RSA PRIVATE KEY-----")'
    ) is False


@pytest.mark.parametrize(
    "header",
    [
        "-----BEGIN PRIVATE KEY-----",
        "-----BEGIN RSA PRIVATE KEY-----",
        "-----BEGIN EC PRIVATE KEY-----",
        "-----BEGIN OPENSSH PRIVATE KEY-----",
    ],
)
def test_real_pem_key_body_is_still_detected(header):
    """A genuine leaked key must still be classified as credential material."""
    body = "\n".join(["MIIEowIBAAKCAQEAxq7Uu2n0Zx3Yl9pQwK4vJ8sT1cR6dF0gH2iN5oP7qS9tU3vW" ] * 4)
    assert RG.pem_carries_key_material(f"{header}\n{body}\n-----END PRIVATE KEY-----") is True


def test_release_gate_still_blocks_on_a_real_committed_private_key(tmp_path, monkeypatch):
    """End-to-end: a credential-bearing hit must still return EXIT_SECURITY."""
    leaked = tmp_path / "leaked_key.py"
    body = "\n".join(["MIIEowIBAAKCAQEAxq7Uu2n0Zx3Yl9pQwK4vJ8sT1cR6dF0gH2iN5oP7qS9tU3vW"] * 4)
    leaked.write_text(
        'KEY = """-----BEGIN RSA PRIVATE KEY-----\n' + body + '\n-----END RSA PRIVATE KEY-----"""\n',
        encoding="utf-8",
    )

    class _Res:
        def __init__(self, hits):
            self.hits = hits

    class _Hit:
        rule = "private_key_block"

    monkeypatch.setattr(RG, "ROOT", tmp_path)
    monkeypatch.setattr(
        "saathi.ops.config_check.check_config",
        lambda: {"ok": True, "blocking": 0, "warnings": 0, "items": []},
    )
    monkeypatch.setattr(
        "saathi.repair.secrets_scan.scan_files",
        lambda paths: {str(leaked): _Res([_Hit()])},
    )
    monkeypatch.setattr(
        RG.subprocess, "run",
        lambda *a, **k: subprocess.CompletedProcess(a, 0, "leaked_key.py\n", ""),
    )
    code, report = RG.release_check(
        run_db=False, run_backup=False, run_storage=False, strict_dirty=False
    )
    assert code == RG.EXIT_SECURITY
    assert report["gates"]["secret_scan"]["clean"] is False
    assert report["gates"]["secret_scan"]["strong_hits"] >= 1


def test_release_gate_reports_non_material_markers_instead_of_hiding_them():
    """Excluded markers must remain visible in the gate report."""
    code, report = RG.release_check(strict_dirty=False)
    scan = report["gates"]["secret_scan"]
    assert code in (RG.EXIT_READY, RG.EXIT_WARN)
    assert scan["clean"] is True
    assert "non_material_markers" in scan
    for marker in scan["non_material_markers"]:
        assert marker["reason"] == "PEM header without key material"
        assert not re.search(r"[A-Za-z0-9+/=]{100,}", marker["file"])


def test_release_gate_did_not_widen_path_exclusions():
    """The repair must raise precision, not allowlist files or directories."""
    src = (REPO / "saathi" / "ops" / "release_gate.py").read_text(encoding="utf-8")
    assert 'not f.startswith(("tests/", "docs/"))' in src
    assert "broker_readiness" not in src
    assert "integration_assurance" not in src


# ── authority boundary — unchanged by this milestone ────────────────────────
def test_regression_closure_grants_no_authority():
    from saathi.platform.private_alpha.manifest import build_release_manifest

    manifest = build_release_manifest()
    assert manifest["production_authorized"] is False
    assert manifest["public_exposure_authorized"] is False
