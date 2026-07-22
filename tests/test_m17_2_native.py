"""M17.2 native macOS — unit + live-desktop (skip honestly by permission)."""
import os
import platform
import tempfile

import pytest

from saathi.computer_agent import macos_permissions as P
from saathi.computer_agent.macos_driver import MacDriver, available
from saathi.computer_agent import native_ops, workspace
from saathi.connectors.platform import registry as R

IS_MAC = platform.system() == "Darwin"
HAS_PYOBJC = available().get("available", False)
AX_TRUSTED = P._ax_trusted() if IS_MAC else False

skip_no_pyobjc = pytest.mark.skipif(not HAS_PYOBJC, reason="PyObjC unavailable (dependency-blocked)")
skip_no_ax = pytest.mark.skipif(not AX_TRUSTED, reason="Accessibility not granted (permission-blocked)")


# ── unit / classification (always run) ──────────────────────────────────────
def test_permission_summary_honest():
    s = P.summary()
    assert "native_accessibility_ready" in s and "native_actuation_ready" in s
    # actuation readiness mirrors Accessibility grant (never claimed without it)
    assert s.get("native_actuation_ready") == s.get("native_accessibility_ready")


def test_executable_identity_stable():
    ident = P.executable_identity()
    assert ident["stable"] is True and ident["code_signed"] in ("signed", "adhoc", "unsigned", "unknown")


def test_native_ops_registered_gateway_routed():
    assert R.get_connector("macos") is not None
    assert R.get_tool("macos.inspect_applications").risk_class == 0
    # actuation ops carry a verification flag
    assert R.get_tool("macos.finder_create_folder").input_schema.get("require_verification")


def test_native_workspace_confined_no_symlink():
    info = workspace.native_create()
    assert info["confined"] and info["committed"] is False and info["symlink_free"]
    assert "computer-agent-pilot" in info["root"]
    workspace.native_cleanup()


def test_native_report_classifies_honestly():
    from saathi.computer_agent.native_report import build_report
    r = build_report()
    if r.get("status") == "dependency_blocked":
        pytest.skip("pyobjc unavailable")
    caps = r["capabilities"]
    # actuation is never claimed live unless Accessibility is granted
    if not AX_TRUSTED:
        assert caps["finder_workflow"]["status"] in ("permission-blocked", "environment-blocked")
    for c in caps.values():
        assert c["status"] in ("live-desktop-tested", "live_failed", "permission-blocked",
                               "environment-blocked", "dependency-blocked")


# ── live-desktop reads (real macOS; skip if no pyobjc) ──────────────────────
@skip_no_pyobjc
def test_live_application_enumeration():
    r = MacDriver().list_applications()
    assert r.status == "success" and r.data["count"] >= 1
    assert all("bundle_id" in a and "pid" in a for a in r.data["apps"])


@skip_no_pyobjc
def test_live_identity_verification_rejects_spoofed_pid():
    d = MacDriver()
    apps = d.list_applications().data["apps"]
    good = d.verify_app_identity(bundle_id=apps[0]["bundle_id"], pid=apps[0]["pid"])
    bad = d.verify_app_identity(bundle_id=apps[0]["bundle_id"], pid=987654)
    assert good.data["verified"] and not bad.data["verified"]


@skip_no_pyobjc
def test_ax_tree_permission_gated_honestly():
    r = MacDriver().ax_tree(bundle_id="com.apple.finder")
    # honest: success only if AX trusted; else permission/environment blocked
    if AX_TRUSTED:
        assert r.status in ("success", "environment_blocked")
    else:
        assert r.status == "permission_blocked"


@skip_no_pyobjc
def test_live_screenshot_confined_and_deleted():
    workspace.native_create()
    out = str(workspace.NATIVE / "_t.png")
    r = MacDriver().screenshot(out)
    if r.status == "success":
        assert r.data["bytes"] > 0 and r.data["committed"] is False
        assert "computer-agent-pilot" in out
        os.remove(out)
    else:
        assert r.status in ("permission_blocked", "environment_blocked")
    workspace.native_cleanup()
