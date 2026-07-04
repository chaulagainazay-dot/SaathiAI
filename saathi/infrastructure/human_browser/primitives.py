"""Reusable browser primitives — the vocabulary every workflow is built from.

`goto/click/fill/upload/wait_for/find/exists/press/select/retry/capture`. The
Browser Driver knows nothing about YouTube; workflows compose these primitives
against page objects. Every primitive records a Step (and fires an optional
`on_step` sink) so the whole run is an explainable, replayable event log —
`browser.goto/click/upload/…/failed` → Episodes.
"""
from __future__ import annotations

import base64
import time
from dataclasses import dataclass, field, asdict


class BrowserActionError(Exception): ...


@dataclass
class Step:
    action: str
    target: str = ""
    ok: bool = True
    detail: str = ""
    at: float = field(default_factory=time.time)

    def as_dict(self) -> dict:
        return asdict(self)


class BrowserPrimitives:
    """Thin, event-emitting wrapper over a Playwright `page`."""

    def __init__(self, page, *, on_step=None, default_timeout_ms: int = 30000):
        self.page = page
        self.steps: list[Step] = []
        self._on_step = on_step
        self._t = default_timeout_ms

    # ── event plumbing ──────────────────────────────────────────────────
    def _emit(self, step: Step) -> None:
        self.steps.append(step)
        if self._on_step:
            try:
                self._on_step(step)
            except Exception:
                pass   # a telemetry sink must never break the run

    def _do(self, action: str, target: str, fn, *, detail: str = ""):
        try:
            result = fn()
            self._emit(Step(action, target, True, detail))
            return result
        except Exception as e:
            self._emit(Step(action, target, False, str(e)[:120]))
            raise BrowserActionError(f"{action}({target!r}) failed: {e}") from e

    # ── primitives ──────────────────────────────────────────────────────
    def goto(self, url: str):
        return self._do("goto", url, lambda: self.page.goto(url, wait_until="domcontentloaded"))

    def click(self, selector: str):
        return self._do("click", selector, lambda: self.page.click(selector, timeout=self._t))

    def fill(self, selector: str, text: str):
        return self._do("fill", selector, lambda: self.page.fill(selector, text, timeout=self._t),
                        detail=text[:60])

    def upload(self, selector: str, path: str):
        return self._do("upload", path,
                        lambda: self.page.set_input_files(selector, path, timeout=self._t))

    def wait_for(self, selector: str, *, timeout_ms: int | None = None, state: str = "visible"):
        # state="attached" for hidden-but-present elements (e.g. file inputs)
        return self._do("wait_for", selector,
                        lambda: self.page.wait_for_selector(selector, timeout=timeout_ms or self._t,
                                                            state=state))

    def press(self, key: str):
        return self._do("press", key, lambda: self.page.keyboard.press(key))

    def select(self, selector: str, value: str):
        return self._do("select", f"{selector}={value}",
                        lambda: self.page.select_option(selector, value))

    def find(self, selector: str):
        return self.page.query_selector(selector)

    def exists(self, selector: str) -> bool:
        return self.page.query_selector(selector) is not None

    def retry(self, fn, *, attempts: int = 3, delay: float = 0.5):
        last = None
        for i in range(attempts):
            try:
                return fn()
            except Exception as e:
                last = e
                self._emit(Step("retry", getattr(fn, "__name__", "fn"), False, f"attempt {i+1}: {e}"[:120]))
                time.sleep(delay)
        raise BrowserActionError(f"retry exhausted after {attempts}: {last}")

    def capture(self) -> str:
        png = self.page.screenshot()
        self._emit(Step("capture", "screenshot", True))
        return base64.b64encode(png).decode()

    # ── run summary ─────────────────────────────────────────────────────
    def log(self) -> list[dict]:
        return [s.as_dict() for s in self.steps]

    def timeline(self) -> list[dict]:
        """Human-readable ordered timeline for debugging + the Episode:
        [{clock, elapsed_ms, action, target, ok, detail}] — 'exactly where and
        why' a run went, without opening logs."""
        t0 = self.steps[0].at if self.steps else 0.0
        out = []
        for s in self.steps:
            clock = time.strftime("%H:%M:%S", time.localtime(s.at))
            out.append({"clock": clock, "elapsed_ms": round((s.at - t0) * 1000),
                        "action": s.action, "target": s.target[:80],
                        "ok": s.ok, "detail": s.detail})
        return out
