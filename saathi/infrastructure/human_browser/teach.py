"""Teach Mode — the system learns to use websites by watching you once.

When a primitive can't find an element, the run pauses and hands you the browser.
You click the real element; the Mac Agent captures everything about it; you
confirm; it becomes a high-confidence entry in the Selector Registry. No code
change, no redeploy — future runs improve.

`capture_element` (Playwright, Mac-side) is guarded; `learn_from_capture` (the
knowledge write) is pure and tested.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TeachRequest:
    """Raised when automation is stuck and needs a human to demonstrate."""
    key: str                          # "youtube/publish"
    prompt: str                       # "I couldn't find the Publish button. Click it."
    page_url: str = ""
    screenshot_b64: str = ""


@dataclass
class TeachCapture:
    """Everything captured when the human clicks the real element."""
    key: str
    selector: str                     # best CSS selector for the clicked element
    xpath: str = ""
    aria: str = ""
    text: str = ""
    tag: str = ""
    bbox: dict = field(default_factory=dict)
    nearby_labels: list = field(default_factory=list)
    dom_snippet: str = ""
    screenshot_b64: str = ""


def learn_from_capture(registry, capture: TeachCapture, *, confirmed: bool = True):
    """Write a confirmed capture into the Selector Registry (Knowledge Graph)."""
    if not confirmed or not capture.selector:
        return None
    strategy = ("id" if capture.selector.startswith("#")
                else "aria" if "aria-label" in capture.selector
                else "css")
    return registry.learn(capture.key, capture.selector, strategy=strategy, source="taught")


# ── live capture (Mac-side, guarded) ────────────────────────────────────────
# Injected into the page: builds a robust selector for the next element clicked.
_CAPTURE_JS = r"""
() => new Promise((resolve) => {
  const cssPath = (el) => {
    if (el.id) return '#' + CSS.escape(el.id);
    const al = el.getAttribute('aria-label');
    if (al) return el.tagName.toLowerCase() + "[aria-label='" + al.replace(/'/g,"\\'") + "']";
    const parts = [];
    while (el && el.nodeType === 1 && parts.length < 5) {
      let s = el.tagName.toLowerCase();
      if (el.className && typeof el.className === 'string')
        s += '.' + el.className.trim().split(/\s+/).slice(0,2).join('.');
      parts.unshift(s); el = el.parentElement;
    }
    return parts.join(' > ');
  };
  const onClick = (e) => {
    e.preventDefault(); e.stopPropagation();
    const el = e.target;
    document.removeEventListener('click', onClick, true);
    const r = el.getBoundingClientRect();
    resolve({
      selector: cssPath(el),
      aria: el.getAttribute('aria-label') || '',
      text: (el.innerText || '').slice(0, 60),
      tag: el.tagName.toLowerCase(),
      bbox: {x: r.x, y: r.y, w: r.width, h: r.height},
      dom_snippet: el.outerHTML.slice(0, 300),
    });
  };
  document.addEventListener('click', onClick, true);
})
"""


def capture_element(page, key: str, *, timeout_ms: int = 120000) -> TeachCapture:  # pragma: no cover
    """Wait for the human to click the real element in a headed Chrome, capture it."""
    data = page.evaluate(_CAPTURE_JS)   # resolves on the user's next click
    return TeachCapture(key=key, selector=data.get("selector", ""),
                        aria=data.get("aria", ""), text=data.get("text", ""),
                        tag=data.get("tag", ""), bbox=data.get("bbox", {}),
                        dom_snippet=data.get("dom_snippet", ""))
