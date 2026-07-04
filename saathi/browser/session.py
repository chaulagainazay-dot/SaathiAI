"""Browser Session Manager (Phase 1.2.5) — cookies, login state, profiles.

Departments say `browser.open(url, session="youtube")` and never think about
cookies or logging in twice. A named session persists its cookie jar and (for
real-browser tiers) Playwright `storage_state` to disk, so login survives across
processes. Future-friendly: `origin`/`profile` fields leave room for rotating
identities and CAPTCHA state.

Persistence is injectable (root dir), so tests use a tmp dir — no global state.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class SessionState:
    name: str
    cookies: list[dict] = field(default_factory=list)   # Playwright-style cookie dicts
    storage_state: dict = field(default_factory=dict)    # Playwright storageState blob
    origin: str = ""                                     # e.g. https://youtube.com
    profile: str = ""                                    # reserved: rotating identities
    updated_at: float = 0.0

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)

    @classmethod
    def from_json(cls, raw: str) -> "SessionState":
        d = json.loads(raw)
        return cls(**{k: d.get(k, getattr(cls(name=d["name"]), k)) for k in
                      ("name", "cookies", "storage_state", "origin", "profile", "updated_at")})


class SessionManager:
    """Named, disk-backed browser sessions."""

    def __init__(self, root: str | Path | None = None):
        self.root = Path(root) if root else (Path.home() / ".saathi" / "browser_sessions")

    def _path(self, name: str) -> Path:
        safe = "".join(c for c in name if c.isalnum() or c in "-_.")
        return self.root / f"{safe}.json"

    def exists(self, name: str) -> bool:
        return self._path(name).exists()

    def load(self, name: str) -> SessionState:
        """Return the saved session, or a fresh empty one if none exists."""
        p = self._path(name)
        if p.exists():
            try:
                return SessionState.from_json(p.read_text())
            except Exception:
                pass  # corrupt file → start clean rather than crash a department
        return SessionState(name=name)

    def save(self, state: SessionState) -> None:
        state.updated_at = time.time()
        self.root.mkdir(parents=True, exist_ok=True)
        self._path(state.name).write_text(state.to_json())

    def list(self) -> list[str]:
        if not self.root.exists():
            return []
        return sorted(p.stem for p in self.root.glob("*.json"))

    def delete(self, name: str) -> bool:
        p = self._path(name)
        if p.exists():
            p.unlink()
            return True
        return False


# ── httpx cookie bridge (used by the HTTP tier) ─────────────────────────────
def to_httpx_cookies(state: SessionState):
    """Build an httpx.Cookies jar from a session's cookie dicts."""
    import httpx
    jar = httpx.Cookies()
    for c in state.cookies:
        name, value = c.get("name"), c.get("value")
        if name is None:
            continue
        jar.set(name, value or "", domain=c.get("domain", ""), path=c.get("path", "/"))
    return jar


def capture_httpx_cookies(state: SessionState, client) -> None:
    """Write a client's post-request cookie jar back into the session."""
    out: list[dict] = []
    for c in client.cookies.jar:
        out.append({"name": c.name, "value": c.value,
                    "domain": c.domain or "", "path": c.path or "/"})
    if out:
        state.cookies = out
