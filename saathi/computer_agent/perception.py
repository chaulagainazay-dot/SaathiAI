"""M17 canonical screen-understanding model.

One perception schema shared by every provider (Playwright/CDP/accessibility/
OCR/vision). A provider fills UIElements; the agent reasons over them. No
app-specific fields — semantic meaning is provider-derived, not hardcoded per app.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ElementType(str, Enum):
    WINDOW = "window"
    DIALOG = "dialog"
    TITLE_BAR = "title_bar"
    BUTTON = "button"
    INPUT = "input"
    DROPDOWN = "dropdown"
    MENU = "menu"
    CHECKBOX = "checkbox"
    RADIO = "radio"
    ICON = "icon"
    IMAGE = "image"
    TEXT = "text"
    TABLE = "table"
    CHART = "chart"
    TAB = "tab"
    URL = "url"
    NOTIFICATION = "notification"
    ERROR = "error"
    PROGRESS = "progress"
    LOADING = "loading"
    LINK = "link"
    UNKNOWN = "unknown"


@dataclass
class BBox:
    x: int = 0
    y: int = 0
    w: int = 0
    h: int = 0

    def center(self) -> tuple[int, int]:
        return (self.x + self.w // 2, self.y + self.h // 2)

    def to_dict(self) -> dict:
        return {"x": self.x, "y": self.y, "w": self.w, "h": self.h}


@dataclass
class UIElement:
    element_id: str
    type: ElementType
    bbox: BBox = field(default_factory=BBox)
    confidence: float = 0.0
    text: str = ""
    accessibility_id: str = ""
    semantic: str = ""            # provider-derived meaning ("submit login")
    clickable: bool = False
    editable: bool = False
    enabled: bool = True
    visible: bool = True
    focused: bool = False

    def to_dict(self) -> dict:
        d = {k: getattr(self, k) for k in self.__dataclass_fields__ if k != "bbox"}
        d["type"] = self.type.value
        d["bbox"] = self.bbox.to_dict()
        return d


@dataclass
class Screen:
    """A perceived surface (desktop frame or browser page)."""
    surface: str                  # "desktop" | "browser"
    app: str = ""                 # detected app / page title
    url: str = ""                 # browser only
    window_state: str = "unknown"
    elements: list = field(default_factory=list)
    loading: bool = False
    error_present: bool = False
    provider: str = ""
    captured_at: float = 0.0

    def find(self, *, text: str = "", type: ElementType | None = None,
             semantic: str = "") -> list[UIElement]:
        out = []
        for e in self.elements:
            if text and text.lower() not in (e.text or "").lower():
                continue
            if type and e.type != type:
                continue
            if semantic and semantic.lower() not in (e.semantic or "").lower():
                continue
            out.append(e)
        return out

    def to_dict(self) -> dict:
        return {"surface": self.surface, "app": self.app, "url": self.url,
                "window_state": self.window_state, "loading": self.loading,
                "error_present": self.error_present, "provider": self.provider,
                "captured_at": self.captured_at,
                "elements": [e.to_dict() for e in self.elements]}
