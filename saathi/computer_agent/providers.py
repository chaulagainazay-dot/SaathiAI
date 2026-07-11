"""M17 provider abstraction — perception + actuation backends.

Providers are pluggable adapters (Playwright, Chrome DevTools, macOS
Accessibility, Windows UI Automation, Linux AT-SPI, OCR/Tesseract, OpenCV,
vision-LLM). Each is OPTIONAL: when its dependency / runtime is absent the
provider reports `environment_blocked` and the harness runs deterministic. NO
live desktop is captured or controlled here without an installed provider — this
avoids reading a real user's screen. Availability is honest, never faked.
"""
from __future__ import annotations

import shutil
import time
from dataclasses import dataclass

from saathi.computer_agent.perception import Screen, UIElement, ElementType, BBox


class ComputerProvider:
    name = "base"
    surface = "desktop"

    def available(self) -> dict:
        return {"available": False, "status": "environment_blocked"}

    def perceive(self, **kw) -> Screen:  # pragma: no cover
        raise NotImplementedError

    def actuate(self, *, action: str, args: dict) -> dict:  # pragma: no cover
        raise NotImplementedError


class DeterministicProvider(ComputerProvider):
    """Fixture provider — the authoritative test backend. Returns a synthetic
    but well-formed Screen and records actuation intents without touching any
    real desktop/browser."""
    name = "deterministic"

    def __init__(self, surface: str = "desktop"):
        self.surface = surface

    def available(self) -> dict:
        return {"available": True, "status": "deterministic"}

    def perceive(self, *, fixture: str = "login", **kw) -> Screen:
        els = [
            UIElement("el_title", ElementType.TITLE_BAR, BBox(0, 0, 800, 30),
                      0.99, text="Example App"),
            UIElement("el_user", ElementType.INPUT, BBox(100, 100, 200, 30),
                      0.95, text="", semantic="username field", editable=True,
                      clickable=True),
            UIElement("el_pass", ElementType.INPUT, BBox(100, 150, 200, 30),
                      0.95, text="", semantic="password field", editable=True,
                      clickable=True),
            UIElement("el_submit", ElementType.BUTTON, BBox(100, 200, 120, 36),
                      0.97, text="Sign in", semantic="submit login",
                      clickable=True, enabled=True),
        ]
        err = fixture == "error"
        if err:
            els.append(UIElement("el_err", ElementType.ERROR, BBox(100, 250, 300, 24),
                                 0.9, text="Invalid credentials", semantic="error dialog"))
        return Screen(surface=self.surface, app="Example App",
                      url="https://localhost/login" if self.surface == "browser" else "",
                      window_state="normal", elements=els, error_present=err,
                      provider=self.name, captured_at=time.time())

    def actuate(self, *, action: str, args: dict) -> dict:
        # records the intent; deterministic "did it happen" result
        return {"provider": self.name, "action": action,
                "target": args.get("target"), "applied": True,
                "note": "deterministic actuation (no real desktop touched)"}


# provider registry with honest availability probes (never install, never network)
def _probe_import(mod: str) -> bool:
    try:
        __import__(mod)
        return True
    except Exception:
        return False


def provider_availability() -> dict:
    """Honest per-backend availability. Absent → environment_blocked."""
    return {
        "playwright": _status(_probe_import("playwright")),
        "chrome_devtools_cdp": _status(False),   # requires a running CDP endpoint
        "macos_accessibility": _status(shutil.which("osascript") is not None
                                       and _probe_import("ApplicationServices"),
                                       note="needs Accessibility permission"),
        "windows_ui_automation": _status(_probe_import("uiautomation")),
        "linux_atspi": _status(_probe_import("pyatspi")),
        "ocr_tesseract": _status(shutil.which("tesseract") is not None),
        "opencv": _status(_probe_import("cv2")),
        "vision_llm": _status(False, note="requires vision model credentials"),
        "deterministic": {"available": True, "status": "deterministic"},
    }


def _status(ok: bool, note: str = "") -> dict:
    d = {"available": bool(ok),
         "status": "available" if ok else "environment_blocked"}
    if note:
        d["note"] = note
    return d


def default_provider(surface: str = "desktop") -> ComputerProvider:
    # live providers are env-blocked here → deterministic is the safe default.
    return DeterministicProvider(surface=surface)
