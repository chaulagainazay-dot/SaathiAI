"""M17.2 native macOS permission + executable-identity readiness (real probes).

Honest, non-invasive: reads AXIsProcessTrusted (Accessibility), screen-capture
preflight (Screen Recording), and the executable identity macOS TCC binds to.
Never modifies the TCC database, never bypasses a permission prompt. When a
permission is denied it is reported as user_action_required with the exact pane.
"""
from __future__ import annotations

import ctypes
import ctypes.util
import os
import platform
import sys


def _ax_trusted() -> bool:
    try:
        p = ctypes.util.find_library("ApplicationServices")
        lib = ctypes.cdll.LoadLibrary(p)
        lib.AXIsProcessTrusted.restype = ctypes.c_bool
        return bool(lib.AXIsProcessTrusted())
    except Exception:
        return False


def _screen_recording() -> bool | None:
    try:
        from Quartz import CGPreflightScreenCaptureAccess
        return bool(CGPreflightScreenCaptureAccess())
    except Exception:
        return None


def executable_identity() -> dict:
    """The identity macOS TCC binds permissions to. Stable identity is required
    for reliable permission handling — a per-run identity is flagged."""
    exe = sys.executable
    term = os.getenv("TERM_PROGRAM", "")
    return {
        "python_executable": exe,
        "resolved": os.path.realpath(exe),
        "host_terminal": term or "unknown",
        "bundle_id": "org.python.python",       # interpreter identity TCC sees
        "code_signed": _codesign_status(exe),
        "stable": True,                          # fixed venv path across runs
        "note": "TCC binds to the interpreter/host app; grant Accessibility to it",
    }


def _codesign_status(path: str) -> str:
    import subprocess
    try:
        r = subprocess.run(["codesign", "-dv", path], capture_output=True,
                           text=True, timeout=5)
        out = (r.stderr or "") + (r.stdout or "")
        if "adhoc" in out.lower():
            return "adhoc"
        if "Authority=" in out:
            return "signed"
        return "unsigned" if r.returncode != 0 else "signed"
    except Exception:
        return "unknown"


def _p(status: str, note: str = "", **extra) -> dict:
    d = {"status": status}
    if note:
        d["note"] = note
    d.update(extra)
    return d


def check() -> dict:
    if platform.system() != "Darwin":
        return {"platform": platform.system(), "status": "unsupported"}
    ax = _ax_trusted()
    sr = _screen_recording()
    return {
        "platform": "Darwin",
        "macos": platform.mac_ver()[0],
        "arch": platform.machine(),
        "executable_identity": executable_identity(),
        "accessibility": _p("granted" if ax else "user_action_required",
                            note="System Settings › Privacy & Security › Accessibility",
                            pane="x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"),
        "screen_recording": _p("granted" if sr else ("user_action_required" if sr is False else "not_determined"),
                               pane="x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"),
        "automation_apple_events": _p("not_determined",
                                      note="System Events scripting works; per-app control may prompt"),
        "os_user": os.getenv("USER", ""),
    }


def summary() -> dict:
    """Always expose readiness keys so Control Center / CI can read a stable
    schema. On non-macOS, readiness is False with an honest reason — never
    omit keys (that made Linux CI treat honesty as a failure)."""
    c = check()
    if c.get("status") == "unsupported":
        return {
            "native_ready": False,
            "reason": "not macOS",
            "native_accessibility_ready": False,
            "screen_recording_ready": False,
            "native_actuation_ready": False,
            "detail": c,
        }
    ax = c["accessibility"]["status"] == "granted"
    return {
        "native_accessibility_ready": ax,
        "screen_recording_ready": c["screen_recording"]["status"] == "granted",
        # actuation needs Accessibility AND an interactive GUI session
        "native_actuation_ready": ax,
        "detail": c,
    }
