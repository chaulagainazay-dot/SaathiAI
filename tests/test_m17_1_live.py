"""M17.1 live-validation tests. Live browser tests SKIP honestly when no
browser binary is present (dependency-blocked); unit tests always run."""
import pytest

from saathi.computer_agent import permissions, workspace
from saathi.computer_agent.browser_driver import browser_available, LiveBrowserDriver


HAS_BROWSER = browser_available()["available"]
skip_no_browser = pytest.mark.skipif(not HAS_BROWSER, reason="no browser binary (dependency-blocked)")


# ── unit: permissions / workspace / classification ──────────────────────────
def test_permission_summary_honest():
    s = permissions.summary()
    assert "live_browser_ready" in s and "live_desktop_ready" in s
    # desktop TCC is never auto-granted here
    assert s["live_desktop_ready"] is False
    d = s["detail"]
    assert d["accessibility"]["status"] == "user_action_required"


def test_workspace_confined_and_gitignored():
    info = workspace.create()
    assert info["confined"] is True and info["committed"] is False
    assert "computer-agent-pilot" in workspace.inspect()["root"]
    workspace.cleanup()


def test_workspace_cleanup_dry_run():
    workspace.create()
    dr = workspace.cleanup(dry_run=True)
    assert dr["dry_run"] is True and workspace.inspect()["exists"] is True
    workspace.cleanup()


def test_browser_availability_report():
    ba = browser_available()
    assert ba["status"] in ("available", "dependency_blocked")


def test_live_report_classifies_honestly():
    from saathi.computer_agent.live_report import build_report
    r = build_report()
    caps = r["capabilities"]
    # desktop is permission-blocked regardless of environment
    assert caps["finder_workflow"]["status"] == "permission-blocked"
    assert caps["authenticated_browser_workflow"]["status"] == "environment-blocked"
    for c in caps.values():
        assert c["status"] in ("live-browser-tested", "live_failed", "permission-blocked",
                               "dependency_blocked", "environment-blocked")


# ── live browser (skips honestly if no browser) ─────────────────────────────
@skip_no_browser
def test_live_browser_launch_and_close():
    d = LiveBrowserDriver()
    ev = d.launch("about:blank")
    assert ev.ok and ev.detail["loopback_only"] and ev.detail["profile_isolated"]
    close = d.close()
    assert close.detail["process_exited"] and close.detail["profile_cleaned"]


@skip_no_browser
def test_live_browser_dom_and_click():
    workspace.create()
    d = LiveBrowserDriver()
    d.launch(workspace.TEST_SITE.joinpath("index.html").as_uri())
    try:
        assert "Pilot" in d.title()
        assert d.query_exists("#submit") and not d.query_exists("#nope")
        assert d.fill("#name", "tester").ok
        assert d.click("#submit").ok
    finally:
        d.close()
        workspace.cleanup()


@skip_no_browser
def test_live_browser_workflow_through_gateway():
    from saathi.computer_agent.live_workflow import run_browser_smoke
    r = run_browser_smoke()
    assert r["status"] == "completed"
    steps = {s.get("step"): s for s in r["steps"]}
    assert steps["read_page"]["status"] == "success"
    assert steps["verify_confirmation"]["confirmed"] is True   # real navigation verified
    assert steps["sensitive_pause"]["status"] == "paused_for_user"
    assert r["replay_redacted"] is True
    workspace.cleanup()


@skip_no_browser
def test_live_screenshot_written_to_workspace_not_git():
    import os
    workspace.create()
    d = LiveBrowserDriver()
    d.launch(workspace.TEST_SITE.joinpath("index.html").as_uri())
    try:
        out = str(workspace.WORKSPACE / "downloads" / "t.png")
        ev = d.screenshot(out)
        assert ev.ok and os.path.exists(out) and ev.detail["bytes"] > 0
        assert "computer-agent-pilot" in out   # confined, git-ignored
    finally:
        d.close()
        workspace.cleanup()
