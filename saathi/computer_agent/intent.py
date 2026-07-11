"""M17 canonical ComputerActionIntent + layered interaction strategy.

Every desktop/browser action becomes a ComputerActionIntent before execution. It
records the interaction LAYER used (API > DOM/CDP > accessibility > OCR/vision >
coordinate) — coordinate is the least reliable and never the default when a
structured element exists. Each resolved element records its resolution method,
identity, confidence, role, DOM selector, bbox, frame id, and expected
postcondition.
"""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from enum import IntEnum


class InteractionLayer(IntEnum):
    """Strongest (1) to weakest (5). Prefer the lowest number available."""
    CONNECTOR_API = 1
    DOM_CDP = 2
    ACCESSIBILITY = 3
    OCR_VISION = 4
    COORDINATE = 5


def choose_layer(*, has_api: bool, has_dom: bool, has_ax: bool,
                 has_visual: bool) -> InteractionLayer:
    if has_api:
        return InteractionLayer.CONNECTOR_API
    if has_dom:
        return InteractionLayer.DOM_CDP
    if has_ax:
        return InteractionLayer.ACCESSIBILITY
    if has_visual:
        return InteractionLayer.OCR_VISION
    return InteractionLayer.COORDINATE


@dataclass
class ResolvedElement:
    resolution_method: str            # "dom" | "accessibility" | "ocr" | "coordinate"
    identity: str                     # selector / ax id / text anchor
    confidence: float = 0.0
    role: str = ""
    dom_selector: str = ""
    bbox: dict = field(default_factory=dict)
    frame_id: str = ""

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


@dataclass
class ComputerActionIntent:
    owner: str
    session_id: str
    app: str
    action_type: str                  # click | type | navigate | upload | ...
    tool_id: str                      # the connector tool that executes it
    risk: int
    layer: InteractionLayer
    window: str = ""
    origin: str = ""                  # browser tab origin
    element: ResolvedElement | None = None
    input_args: dict = field(default_factory=dict)
    precondition: str = ""
    postcondition: str = ""           # REQUIRED for mutating actions
    action_id: str = ""
    created_at: float = 0.0

    def __post_init__(self):
        self.action_id = self.action_id or "act_" + uuid.uuid4().hex[:12]
        self.created_at = self.created_at or time.time()

    def input_digest(self) -> str:
        # sanitized digest (never the raw sensitive value)
        basis = json.dumps({"tool": self.tool_id, "app": self.app,
                            "origin": self.origin,
                            "element": self.element.identity if self.element else "",
                            "args": {k: ("<redacted>" if _sensitive_key(k) else v)
                                     for k, v in self.input_args.items()}},
                           sort_keys=True, default=str)
        return hashlib.sha256(basis.encode()).hexdigest()[:24]

    def validate(self) -> list[str]:
        problems = []
        if self.risk >= 2 and not self.postcondition:
            problems.append("mutating action (risk>=2) must declare a postcondition")
        if self.layer == InteractionLayer.COORDINATE and self.element \
                and self.element.resolution_method != "coordinate":
            problems.append("coordinate layer used while a structured element exists")
        return problems

    def to_dict(self) -> dict:
        d = {k: getattr(self, k) for k in self.__dataclass_fields__ if k != "element"}
        d["layer"] = int(self.layer)
        d["element"] = self.element.to_dict() if self.element else None
        # sensitive args are NEVER serialized — only the digest represents them
        d["input_args"] = {k: ("<redacted>" if _sensitive_key(k) else v)
                           for k, v in self.input_args.items()}
        d["input_digest"] = self.input_digest()
        return d


def _sensitive_key(k: str) -> bool:
    kl = k.lower()
    return any(s in kl for s in ("password", "passwd", "otp", "mfa", "pin",
                                 "secret", "token", "recovery", "card", "cvv"))
