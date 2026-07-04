"""Browser profiles — one persistent Chrome profile per account, per person.

    profiles/ajay/{youtube,facebook,instagram,linkedin,reddit,twitter,gmail}/

Each dir is a real Chrome/Playwright persistent context (cookies, local &
session storage, fingerprint). Login happens once, interactively; every later
job reuses it. Lives only on the trusted Mac — never on the VM.
"""
from __future__ import annotations

from pathlib import Path


class ProfileStore:
    def __init__(self, root: str | None = None):
        self.root = Path(root) if root else (Path.home() / ".saathi" / "browser_profiles")

    def path(self, profile: str) -> Path:
        # "ajay/youtube" → <root>/ajay/youtube ; reject traversal
        parts = [p for p in profile.split("/") if p and p not in (".", "..")]
        if len(parts) != len([p for p in profile.split("/") if p]):
            raise ValueError(f"invalid profile name: {profile!r}")
        return self.root.joinpath(*parts)

    def ensure(self, profile: str) -> Path:
        p = self.path(profile)
        p.mkdir(parents=True, exist_ok=True)
        return p

    def exists(self, profile: str) -> bool:
        return self.path(profile).exists()

    def list(self) -> list[str]:
        if not self.root.exists():
            return []
        return sorted(str(d.relative_to(self.root)) for d in self.root.glob("*/*") if d.is_dir())
