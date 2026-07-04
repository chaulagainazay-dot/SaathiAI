"""KeyedBrowser — the self-healing bridge between workflows and the registry.

Workflows address elements by KEY ("youtube/publish"), not raw selectors. The
KeyedBrowser resolves each key through the Selector Registry (best-known first,
falling back to the page-object default), rewards the key on success (confidence
rises with repeated use), and penalizes + triggers Teach Mode on failure. That's
the loop that makes automation improve itself.
"""
from __future__ import annotations


class KeyedBrowser:
    def __init__(self, primitives, *, registry=None, keys=None, on_teach=None):
        self.b = primitives
        self.reg = registry
        self.keys = keys or {}
        self._on_teach = on_teach     # callable(key) -> opens a Teach session

    # resolve a key → selector: registry best-known, else page-object default
    def _sel(self, key: str) -> str:
        if self.reg is not None:
            best = self.reg.best(key)
            if best:
                return best
        return self.keys.get(key, key)

    def _run(self, key: str, fn):
        sel = self._sel(key)
        try:
            result = fn(sel)
            if self.reg is not None:
                self.reg.reward(key)          # success → confidence up
            return result
        except Exception:
            if self.reg is not None:
                self.reg.penalize(key)        # failure → confidence down
            if self._on_teach is not None:
                self._on_teach(key)           # hand off to Teach Mode
            raise

    # keyed primitives
    def wait_for(self, key: str, **kw): return self._run(key, lambda s: self.b.wait_for(s, **kw))
    def upload(self, key: str, path: str): return self._run(key, lambda s: self.b.upload(s, path))
    def fill(self, key: str, text: str): return self._run(key, lambda s: self.b.fill(s, text))
    def click(self, key: str): return self._run(key, lambda s: self.b.click(s))
    def exists(self, key: str) -> bool: return self.b.exists(self._sel(key))
    def find(self, key: str): return self.b.find(self._sel(key))

    # unkeyed passthroughs
    def goto(self, url: str): return self.b.goto(url)
    def click_selector(self, selector: str): return self.b.click(selector)  # dynamic selectors
    def capture(self): return self.b.capture()

    # run summary (delegate to the underlying primitives)
    @property
    def steps(self): return self.b.steps
    def log(self): return self.b.log()
    def timeline(self): return self.b.timeline()
