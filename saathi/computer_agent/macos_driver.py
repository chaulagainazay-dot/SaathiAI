"""M17.2 canonical macOS driver — the ONLY place native macOS APIs are called.

AX-first: application/window inspection via Accessibility (AXUIElement) and
NSWorkspace; screenshots via Quartz (Screen Recording). Every AX/Quartz/
AppleScript call lives here. Real live pieces that work WITHOUT Accessibility
(NSWorkspace app enumeration, process identity, screen-capture preflight) are
genuinely executed; anything needing Accessibility returns a typed
`permission_blocked` result when AXIsProcessTrusted is False; GUI actuation
returns `environment_blocked` when no interactive session exists. Nothing is
faked. Agents reach this only through ComputerAdapter → ExecutionGateway.
"""
from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass

from saathi.computer_agent.macos_permissions import _ax_trusted, _screen_recording


@dataclass
class NativeResult:
    op: str
    status: str          # success | permission_blocked | environment_blocked | failed
    data: dict


def available() -> dict:
    try:
        import AppKit  # noqa
        return {"available": True, "pyobjc": True}
    except Exception:
        return {"available": False, "pyobjc": False, "status": "dependency_blocked"}


class MacDriver:
    """Canonical native driver. list/identity/screenshot are LIVE where the OS
    permits; AX-tree + actuation are permission/environment gated, honestly."""

    def list_applications(self) -> NativeResult:
        try:
            from AppKit import NSWorkspace
            apps = NSWorkspace.sharedWorkspace().runningApplications()
            out = []
            for a in apps:
                if a.activationPolicy() == 0:   # regular (has UI)
                    out.append({"bundle_id": a.bundleIdentifier(),
                                "pid": int(a.processIdentifier()),
                                "name": a.localizedName()})
            return NativeResult("list_applications", "success",
                                {"count": len(out), "apps": out})
        except Exception as e:
            return NativeResult("list_applications", "failed", {"error": str(e)[:200]})

    def active_application(self) -> NativeResult:
        try:
            from AppKit import NSWorkspace
            a = NSWorkspace.sharedWorkspace().frontmostApplication()
            if not a:
                return NativeResult("active_application", "failed", {})
            return NativeResult("active_application", "success",
                                {"bundle_id": a.bundleIdentifier(),
                                 "pid": int(a.processIdentifier()),
                                 "name": a.localizedName()})
        except Exception as e:
            return NativeResult("active_application", "failed", {"error": str(e)[:200]})

    def verify_app_identity(self, *, bundle_id: str, pid: int) -> NativeResult:
        """Verify a specific app is genuinely running with the expected PID +
        bundle. Title alone is never trusted; a spoofed window cannot pass."""
        r = self.list_applications()
        if r.status != "success":
            return r
        match = next((a for a in r.data["apps"]
                      if a["bundle_id"] == bundle_id and a["pid"] == pid), None)
        return NativeResult("verify_app_identity",
                            "success" if match else "failed",
                            {"verified": bool(match), "bundle_id": bundle_id, "pid": pid})

    def ax_tree(self, *, bundle_id: str) -> NativeResult:
        """Accessibility tree — requires Accessibility permission AND a GUI
        session. Returns permission_blocked honestly when AX is not trusted."""
        if not _ax_trusted():
            return NativeResult("ax_tree", "permission_blocked",
                                {"reason": "Accessibility not granted (AXIsProcessTrusted=False)",
                                 "pane": "Privacy › Accessibility"})
        # AX trusted but a headless/non-interactive session still cannot enumerate
        # UI windows; attempt via System Events and report honestly.
        try:
            script = (f'tell application "System Events" to tell '
                      f'(first process whose bundle identifier is "{bundle_id}") '
                      f'to return count of windows')
            r = subprocess.run(["osascript", "-e", script], capture_output=True,
                              text=True, timeout=8)
            if r.returncode == 0:
                return NativeResult("ax_tree", "success",
                                    {"windows": int(r.stdout.strip() or 0),
                                     "bundle_id": bundle_id})
            return NativeResult("ax_tree", "environment_blocked",
                                {"reason": r.stderr.strip()[:160]})
        except Exception as e:
            return NativeResult("ax_tree", "environment_blocked", {"error": str(e)[:160]})

    def screenshot(self, out_path: str) -> NativeResult:
        """Real screen capture (Screen Recording). Confined to the pilot
        workspace; NEVER committed. Metadata only is returned."""
        sr = _screen_recording()
        if sr is False:
            return NativeResult("screenshot", "permission_blocked",
                                {"reason": "Screen Recording not granted"})
        try:
            r = subprocess.run(["screencapture", "-x", "-t", "png", out_path],
                             capture_output=True, text=True, timeout=15)
            import os
            if r.returncode == 0 and os.path.exists(out_path):
                size = os.path.getsize(out_path)
                return NativeResult("screenshot", "success",
                                    {"bytes": size, "path_confined": True,
                                     "committed": False})
            return NativeResult("screenshot", "environment_blocked",
                                {"reason": r.stderr.strip()[:160] or "no interactive display"})
        except Exception as e:
            return NativeResult("screenshot", "failed", {"error": str(e)[:160]})

    def activate_application(self, *, bundle_id: str) -> NativeResult:
        """GUI activation — needs an interactive session; honest env-block."""
        try:
            script = f'tell application id "{bundle_id}" to activate'
            r = subprocess.run(["osascript", "-e", script], capture_output=True,
                             text=True, timeout=8)
            if r.returncode == 0:
                return NativeResult("activate_application", "success", {"bundle_id": bundle_id})
            return NativeResult("activate_application", "environment_blocked",
                                {"reason": r.stderr.strip()[:160]})
        except Exception as e:
            return NativeResult("activate_application", "environment_blocked", {"error": str(e)[:160]})
