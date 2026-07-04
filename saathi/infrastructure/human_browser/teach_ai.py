"""AI understanding for Teach Mode — turn a raw click into robust selectors.

Instead of storing the exact clicked path, derive selectors ordered by
robustness (id > aria-label > role/text > css > xpath). A deterministic
heuristic from the captured element's own attributes is the base (aria-label is
usually the strongest, and the capture already has it); an optional multimodal
`ask` can re-rank / adjust confidence.
"""
from __future__ import annotations


def suggest_selectors(capture, *, ask=None) -> list[dict]:
    """[{selector, strategy, confidence}] best-first, derived from the capture."""
    tag = capture.tag or "*"
    out: list[dict] = []
    if capture.selector.startswith("#"):
        out.append({"selector": capture.selector, "strategy": "id", "confidence": 0.95})
    if capture.aria:
        aria = capture.aria.replace("'", "\\'")
        out.append({"selector": f"{tag}[aria-label='{aria}']", "strategy": "aria", "confidence": 0.9})
    if capture.text:
        out.append({"selector": f"{tag}:has-text(\"{capture.text[:30]}\")",
                    "strategy": "text", "confidence": 0.7})
    if capture.selector and not capture.selector.startswith("#"):
        out.append({"selector": capture.selector, "strategy": "css", "confidence": 0.6})

    # de-dupe by selector, keep highest confidence
    seen: dict[str, dict] = {}
    for s in out:
        if s["selector"] not in seen or s["confidence"] > seen[s["selector"]]["confidence"]:
            seen[s["selector"]] = s
    ranked = sorted(seen.values(), key=lambda s: -s["confidence"])

    # optional multimodal re-rank (best-effort; heuristic stands if it fails)
    if ask is not None and ranked:
        try:
            verdict = ask(capture, ranked)
            if isinstance(verdict, dict) and verdict.get("confidence"):
                ranked[0]["confidence"] = float(verdict["confidence"])
        except Exception:
            pass
    return ranked


def best_confidence(suggestions: list[dict]) -> float:
    return suggestions[0]["confidence"] if suggestions else 0.0
