"""Infrastructure event emission (M5.1 sprint, Audit 3) — Model Router + Browser."""
from saathi.events import bus
from saathi.model_router import ModelLabel, ModelRouter, ProviderSpec
from saathi import llm
from saathi.browser import BrowserService, Tier
from saathi.browser.types import Page, Capabilities
from saathi.browser.base import BrowserTier


def _capture(names):
    seen = []
    unsubs = [bus.subscribe(n, lambda e, _n=n: seen.append(_n)) for n in names]
    return seen, lambda: [u() for u in unsubs]


def test_model_router_emits_selected():
    seen, off = _capture(["model.selected", "model.fallback", "model.failed"])
    try:
        r = ModelRouter(providers=[ProviderSpec("groq/x", frozenset({ModelLabel.STANDARD}),
                                                cost_per_1k=0, latency_tier=1, is_local=False)])
        llm.generate(ModelLabel.STANDARD, "hi", callers={"groq": lambda p, s, m, t: ("ok", "x", {})},
                     router=r, trace=False)
        assert "model.selected" in seen
    finally:
        off()


def test_model_router_emits_fallback_then_failure():
    seen, off = _capture(["model.selected", "model.fallback", "model.failed"])
    try:
        def boom(p, s, m, t): raise RuntimeError("down")
        r = ModelRouter(providers=[ProviderSpec("groq/x", frozenset({ModelLabel.STANDARD}),
                                                cost_per_1k=0, latency_tier=1, is_local=False)])
        try:
            llm.generate(ModelLabel.STANDARD, "hi", callers={"groq": boom}, router=r, trace=False)
        except RuntimeError:
            pass
        assert "model.fallback" in seen and "model.failed" in seen
    finally:
        off()


class _FakeTier(BrowserTier):
    def __init__(self, name, tier, page): self.name, self.tier, self._p = name, tier, page
    def capabilities(self): return Capabilities(fetch=True)
    def available(self): return True
    def open(self, url, *, timeout=30, session=None): return self._p


def test_browser_emits_started_and_finished():
    seen, off = _capture(["browser.started", "browser.finished"])
    try:
        svc = BrowserService(tiers=[_FakeTier("http", Tier.HTTP,
                                    Page(url="u", status=200, text="ok", tier=Tier.HTTP))])
        svc.open("http://x")
        assert "browser.started" in seen and "browser.finished" in seen
    finally:
        off()


def test_browser_emits_escalated_on_block():
    seen, off = _capture(["browser.blocked", "browser.escalated"])
    try:
        blocked = Page(url="u", status=403, blocked=True, tier=Tier.HTTP)
        ok = Page(url="u", status=200, text="ok", tier=Tier.PLAYWRIGHT)
        svc = BrowserService(tiers=[_FakeTier("http", Tier.HTTP, blocked),
                                    _FakeTier("playwright", Tier.PLAYWRIGHT, ok)])
        svc.open("http://x")
        assert "browser.blocked" in seen and "browser.escalated" in seen
    finally:
        off()
