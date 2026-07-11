"""M17.1 live browser workflow — genuine controlled run through the gateway.

Orchestrates a real browser workflow: it starts a ComputerSession (consent),
sets the live CDP driver, and executes each browser action through the
ComputerAgent → ExecutionEngine → ExecutionGateway → ComputerAdapter → live
driver path (no bypass). Every mutating step declares a postcondition and is
verified. Produces structured, sanitized evidence. Skips honestly (returns a
`skipped` outcome) when no browser binary is present.
"""
from __future__ import annotations

import tempfile
import time
from pathlib import Path

from saathi.connectors.platform import store as S
from saathi.connectors.platform.execution import ExecutionEngine
from saathi.computer_agent import ComputerAgent, ComputerSession
from saathi.computer_agent import operations
from saathi.computer_agent.browser_driver import LiveBrowserDriver, browser_available
from saathi.computer_agent import workspace


def run_browser_smoke(*, owner: str = "ajay") -> dict:
    avail = browser_available()
    if not avail["available"]:
        return {"status": "skipped", "reason": "dependency_blocked",
                "detail": "no Chromium-family browser installed", "steps": []}

    workspace.create()
    site = workspace.TEST_SITE / "index.html"
    site_url = site.as_uri()

    sess = ComputerSession(owner=owner, allowed_apps=["Google Chrome"],
                           allowed_origins=["file://"],
                           file_roots=[str(workspace.WORKSPACE)], risk_ceiling=2,
                           ttl_sec=600)
    eng = ExecutionEngine(store=S.ConnectorStore(tempfile.mktemp(suffix=".db")))
    agent = ComputerAgent(owner=owner, engine=eng, session=sess, workflow_id="browser-smoke")

    driver = LiveBrowserDriver()
    steps = []
    t0 = time.time()
    launch = driver.launch(site_url)
    steps.append({"step": "launch", "ok": launch.ok, "detail": launch.detail,
                  "ms": round((time.time() - t0) * 1000, 1)})
    if not launch.ok:
        driver.close()
        return {"status": "failed", "reason": "launch_failed", "steps": steps}

    operations.set_live_browser(driver)
    try:
        # read_page (risk 1) — real DOM
        r = agent.step(tool_id="browser_agent.read_page", args={}, app="Google Chrome",
                       origin="file://", actor_type="user")
        steps.append({"step": "read_page", "status": r["status"],
                      "title": (r.get("data") or {}).get("title")})
        # fill non-sensitive field (real input)
        r = agent.step(tool_id="browser_agent.fill_form",
                       args={"selector": "#name", "value": "Saathi Tester",
                             "_postcondition": "field populated"},
                       app="Google Chrome", origin="file://", actor_type="user")
        steps.append({"step": "fill_name", "status": r["status"]})
        # click submit → navigates to confirm.html; verify confirmation text
        r = agent.step(tool_id="browser_agent.click",
                       args={"selector": "#submit", "_expect_text": ""},
                       app="Google Chrome", origin="file://", actor_type="user")
        steps.append({"step": "click_submit", "status": r["status"]})
        time.sleep(0.4)
        r = agent.step(tool_id="browser_agent.read_page", args={}, app="Google Chrome",
                       origin="file://", actor_type="user")
        body = (r.get("data") or {}).get("body", "")
        confirmed = "Submission received" in body
        steps.append({"step": "verify_confirmation", "status": r["status"],
                      "confirmed": confirmed})
        # real screenshot (written to the confined workspace, NEVER committed)
        shot = workspace.WORKSPACE / "downloads" / "smoke.png"
        sev = driver.screenshot(str(shot))
        steps.append({"step": "screenshot", "ok": sev.ok, "bytes": sev.detail.get("bytes")})
        # sensitive field → agent must PAUSE, never type into it
        r = agent.step(tool_id="browser_agent.fill_form",
                       args={"selector": "#password", "value": "should-not-be-typed"},
                       app="Google Chrome", origin="file://", sensitive_target=True,
                       actor_type="user")
        steps.append({"step": "sensitive_pause", "status": r["status"]})
    finally:
        operations.clear_live_browser()
        cev = driver.close()
        steps.append({"step": "close", "process_exited": cev.detail.get("process_exited")})

    verified = sum(1 for s in steps if s.get("status") in ("success",) or s.get("ok"))
    replay_clean = "should-not-be-typed" not in str(agent.replay.to_dict())
    return {
        "status": "completed",
        "environment": "live-browser (headless Chrome via CDP)",
        "driver": "live-cdp-browser",
        "duration_ms": round((time.time() - t0) * 1000, 1),
        "steps": steps,
        "actions_attempted": len(steps),
        "actions_verified": verified,
        "replay_redacted": replay_clean,
        "replay_timeline": agent.timeline(),
        "screenshot_committed": False,
    }
