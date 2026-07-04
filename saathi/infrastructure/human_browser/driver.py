"""HumanBrowser contract — the four-plus methods every backend implements.

Nobody above this knows whether it's Playwright, Camofox, or Chrome DevTools
driving a real logged-in profile. Departments call the Connector Registry; the
registry routes to a human-browser-backed connector only when API and headless
browser modes are unavailable (lowest priority), exactly like the Model Router.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

# capabilities a human-browser backend understands
CAPS = frozenset({"open", "login", "click", "type", "upload", "screenshot",
                  "download", "wait", "publish_video", "close"})


class HumanBrowser(ABC):
    """Runs on the trusted Mac against a real, already-logged-in Chrome profile."""

    @abstractmethod
    def available(self) -> bool: ...

    @abstractmethod
    def execute(self, capability: str, *, profile: str = "", **payload) -> dict:
        """Perform one capability against `profile`'s real browser session,
        returning a JSON-able result dict."""

    # ergonomic wrappers (all route through execute)
    def open(self, url, *, profile=""): return self.execute("open", profile=profile, url=url)
    def login(self, service, *, profile=""): return self.execute("login", profile=profile, service=service)
    def click(self, selector, *, profile=""): return self.execute("click", profile=profile, selector=selector)
    def upload(self, path, *, selector="input[type=file]", profile=""):
        return self.execute("upload", profile=profile, path=path, selector=selector)
    def screenshot(self, *, profile=""): return self.execute("screenshot", profile=profile)
    def download(self, url, dest, *, profile=""):
        return self.execute("download", profile=profile, url=url, dest=dest)
    def close(self, *, profile=""): return self.execute("close", profile=profile)
