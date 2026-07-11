"""M17.1 permission + dependency readiness — honest, non-invasive probes.

Reports what is actually available WITHOUT triggering or bypassing macOS
permission prompts and WITHOUT installing anything. macOS TCC permissions
(Accessibility / Screen Recording / Automation) cannot be queried silently, so
they are reported `user_action_required` unless a harmless probe proves them.
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess


def _p(status: str, note: str = "", **extra) -> dict:
    d = {"status": status}
    if note:
        d["note"] = note
    d.update(extra)
    return d


def check() -> dict:
    from saathi.computer_agent.browser_driver import browser_available
    ba = browser_available()
    return {
        "os": {"platform": platform.system(), "release": platform.mac_ver()[0] or platform.release()},
        # browser control via headless CDP needs NO macOS permission
        "browser_control_headless": _p("granted" if ba["available"] else "dependency_blocked",
                                       path=ba.get("path")),
        "playwright_browser": _p(_playwright_status(),
                                 note="playwright browser binary (optional; not installed here)"),
        "chrome_devtools_cdp": _p("granted" if ba["available"] else "dependency_blocked",
                                  note="loopback CDP only"),
        # native desktop actuation needs TCC permission — cannot self-grant
        "accessibility": _p("user_action_required",
                            note="grant in System Settings › Privacy › Accessibility"),
        "screen_recording": _p("user_action_required",
                               note="grant in System Settings › Privacy › Screen Recording"),
        "automation_apple_events": _p(_apple_events_status(),
                                      note="Automation permission; osascript probe"),
        # dependencies
        "tesseract_ocr": _p("granted" if shutil.which("tesseract") else "dependency_blocked"),
        "opencv": _p("granted" if _importable("cv2") else "dependency_blocked"),
        "displays": _displays(),
        "screen_locked": _p("not_determined", note="cannot detect without private API"),
        "os_user": _p("granted", value=os.getenv("USER", "")),
    }


def _importable(mod: str) -> bool:
    try:
        __import__(mod); return True
    except Exception:
        return False


def _playwright_status() -> str:
    if not _importable("playwright"):
        return "dependency_blocked"
    # package present but browser binary may be absent
    try:
        from playwright.sync_api import sync_playwright  # noqa
        return "not_determined"
    except Exception:
        return "dependency_blocked"


def _apple_events_status() -> str:
    # do NOT trigger a permission prompt aggressively; a plain 'System Events'
    # count is a light probe. In a sandbox this typically fails → blocked.
    if platform.system() != "Darwin" or not shutil.which("osascript"):
        return "unsupported"
    return "user_action_required"


def _displays() -> dict:
    if platform.system() != "Darwin":
        return _p("not_determined")
    try:
        out = subprocess.run(["system_profiler", "SPDisplaysDataType"],
                             capture_output=True, text=True, timeout=8).stdout
        n = out.count("Resolution:")
        return _p("granted", count=max(n, 1))
    except Exception:
        return _p("not_determined")


def summary() -> dict:
    c = check()
    live_browser = c["browser_control_headless"]["status"] == "granted"
    return {"live_browser_ready": live_browser,
            "live_desktop_ready": False,   # TCC permissions not granted here
            "detail": c}
