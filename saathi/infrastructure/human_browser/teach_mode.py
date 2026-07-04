"""Teach Mode loop — the teacher. Generic: any workflow reuses it.

    stuck → open()  ──operator──▶ take_control() → (you click) → submit_capture()
          → suggest() → confirm(selector) → [TEST FIRST] verify_and_learn() → learn()

State lives on the VM so the Automation Center drives it while the Mac Agent
captures the click. `learn()` writes the Selector Registry, versions (never
overwrites), and emits `selector.learned` → Episode → Learning Runtime.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum

from .teach import TeachCapture
from .teach_ai import suggest_selectors, best_confidence


class TeachState(str, Enum):
    PENDING = "pending"        # workflow paused, waiting for operator to take control
    CAPTURING = "capturing"    # operator has control, waiting for their click
    SUGGESTED = "suggested"    # capture + AI suggestions ready, awaiting confirm
    VERIFYING = "verifying"    # TEST FIRST in progress
    LEARNED = "learned"
    ABORTED = "aborted"


@dataclass
class TeachSession:
    id: str
    key: str
    workflow: str = ""
    reason: str = ""
    page_url: str = ""
    state: TeachState = TeachState.PENDING
    capture: dict | None = None
    suggestions: list = field(default_factory=list)
    chosen: str = ""
    confidence: float = 0.0
    created: float = field(default_factory=time.time)
    updated: float = field(default_factory=time.time)

    def as_dict(self) -> dict:
        d = asdict(self); d["state"] = self.state.value; return d


class TeachSessionStore:
    def __init__(self):
        self._s: dict[str, TeachSession] = {}
    def add(self, s: TeachSession): self._s[s.id] = s
    def get(self, sid: str) -> TeachSession | None: return self._s.get(sid)
    def pending(self) -> list[TeachSession]:
        return [s for s in self._s.values() if s.state not in (TeachState.LEARNED, TeachState.ABORTED)]
    def all(self) -> list[TeachSession]: return list(self._s.values())


class TeachMode:
    def __init__(self, *, store=None, registry=None, bus=None):
        self.store = store or TeachSessionStore()
        if registry is None:
            from .selector_registry import default_registry
            registry = default_registry()
        self.registry = registry
        self._bus = bus

    # ── the loop ────────────────────────────────────────────────────────
    def open(self, key: str, *, workflow: str = "", reason: str = "", page_url: str = "") -> TeachSession:
        s = TeachSession(id=uuid.uuid4().hex[:12], key=key, workflow=workflow,
                         reason=reason, page_url=page_url)
        self.store.add(s)
        self._emit("teach.requested", {"session": s.id, "key": key, "reason": reason})
        return s

    def take_control(self, sid: str) -> TeachSession:
        s = self._require(sid)
        s.state = TeachState.CAPTURING
        return self._touch(s)

    def submit_capture(self, sid: str, capture: TeachCapture, *, ask=None) -> TeachSession:
        s = self._require(sid)
        s.capture = asdict(capture)
        s.suggestions = suggest_selectors(capture, ask=ask)
        s.confidence = best_confidence(s.suggestions)
        s.chosen = s.suggestions[0]["selector"] if s.suggestions else ""
        s.state = TeachState.SUGGESTED
        return self._touch(s)

    def confirm(self, sid: str, *, selector: str | None = None) -> TeachSession:
        s = self._require(sid)
        if selector:
            s.chosen = selector
            match = next((x for x in s.suggestions if x["selector"] == selector), None)
            s.confidence = match["confidence"] if match else s.confidence
        return self._touch(s)

    def verify_and_learn(self, sid: str, *, verify_fn=None) -> TeachSession:
        """TEST FIRST: run verify_fn(chosen_selector) -> bool (click + vision).
        Learn only if it passes. If no verify_fn, learn directly."""
        s = self._require(sid)
        s.state = TeachState.VERIFYING
        self._touch(s)
        ok = True
        if verify_fn is not None:
            try:
                ok = bool(verify_fn(s.chosen))
            except Exception:
                ok = False
        if not ok:
            s.state = TeachState.SUGGESTED     # back to choose/retry
            return self._touch(s)
        return self.learn(sid)

    def learn(self, sid: str, *, operator: str = "Ajay") -> TeachSession:
        s = self._require(sid)
        if not s.chosen:
            raise ValueError("no selector chosen")
        strat = next((x["strategy"] for x in s.suggestions if x["selector"] == s.chosen), "taught")
        self.registry.learn(s.key, s.chosen, strategy=strat, confidence=max(0.9, s.confidence))
        s.state = TeachState.LEARNED
        self._touch(s)
        self._emit("selector.learned", {
            "workflow": s.workflow, "element": s.key, "selector": s.chosen,
            "confidence": round(s.confidence * 100), "operator": operator, "ok": True})
        return s

    def abort(self, sid: str) -> TeachSession:
        s = self._require(sid)
        s.state = TeachState.ABORTED
        return self._touch(s)

    # ── plumbing ────────────────────────────────────────────────────────
    def _require(self, sid: str) -> TeachSession:
        s = self.store.get(sid)
        if s is None:
            raise KeyError(f"no teach session {sid}")
        return s

    def _touch(self, s: TeachSession) -> TeachSession:
        s.updated = time.time(); return s

    def _emit(self, name: str, payload: dict) -> None:
        if self._bus is None:
            return
        try:
            self._bus.publish_sync(name, payload)
        except Exception:
            pass


_default = None
def default_teacher(bus=None) -> TeachMode:
    global _default
    if _default is None:
        _default = TeachMode(bus=bus)
    return _default
