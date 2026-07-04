"""M5.1 Sprint · Audit 7 — Failure Injection / graceful degradation.

Every infrastructure layer must degrade gracefully, never crash the platform:
  - a dead model → fall back down the chain, or a clean error (never a hang)
  - a blocked/crashing browser tier → escalate; all-fail → BrowserError
  - a connector without creds / rate-limited → typed error + event, not a stack trace
  - speech unavailable → null drivers → the keyboard path keeps working
  - a failing reasoning brain → conversation.failed event + surfaced error
These are the deterministic, credential-free proofs of "graceful under failure".
"""
import httpx
import pytest

from saathi.events import EventBus
from saathi.model_router import ModelLabel, ModelRouter, ProviderSpec
from saathi import llm


def _router(*names):
    return ModelRouter(providers=[
        ProviderSpec(n, frozenset({ModelLabel.STANDARD}), cost_per_1k=i, latency_tier=1,
                     is_local=False) for i, n in enumerate(names)])


# ── Model Router ─────────────────────────────────────────────────────────────
def test_dead_primary_falls_back_to_healthy_provider():
    def dead(p, s, m, t): raise RuntimeError("openrouter down")
    def ok(p, s, m, t): return ("recovered", "claude", {})
    res = llm.generate(ModelLabel.STANDARD, "hi", router=_router("openrouter/x", "anthropic/claude"),
                       callers={"openrouter": dead, "anthropic": ok}, trace=False)
    assert res.text == "recovered" and res.provider == "anthropic/claude"


def test_all_models_down_raises_clean_not_hang():
    def dead(p, s, m, t): raise RuntimeError("down")
    with pytest.raises(RuntimeError, match="All providers failed"):
        llm.generate(ModelLabel.STANDARD, "hi", router=_router("groq/x"),
                     callers={"groq": dead}, trace=False)


def test_missing_caller_is_skipped_not_fatal():
    def ok(p, s, m, t): return ("ok", "b", {})
    # first provider's family has no caller registered → skipped, second serves
    res = llm.generate(ModelLabel.STANDARD, "hi", router=_router("mystery/x", "groq/y"),
                       callers={"groq": ok}, trace=False)
    assert res.provider == "groq/y"


# ── Browser Service ──────────────────────────────────────────────────────────
def test_browser_crash_then_block_then_success():
    from saathi.browser import BrowserService, Tier
    from saathi.browser.types import Page, Capabilities
    from saathi.browser.base import BrowserTier

    class T(BrowserTier):
        def __init__(self, name, tier, page=None, boom=False):
            self.name, self.tier, self._p, self._boom = name, tier, page, boom
        def capabilities(self): return Capabilities(fetch=True)
        def available(self): return True
        def open(self, url, *, timeout=30, session=None):
            if self._boom: raise RuntimeError("tier crashed")
            return self._p
    svc = BrowserService(tiers=[
        T("http", Tier.HTTP, boom=True),                                    # crash
        T("playwright", Tier.PLAYWRIGHT, Page(url="u", status=403, blocked=True)),  # blocked
        T("camofox", Tier.CAMOFOX, Page(url="u", status=200, text="ok")),   # succeeds
    ])
    assert svc.open("http://x").ok


def test_browser_all_tiers_fail_raises_browsererror():
    from saathi.browser import BrowserService, BrowserError, Tier
    from saathi.browser.types import Capabilities
    from saathi.browser.base import BrowserTier

    class Dead(BrowserTier):
        name, tier = "http", Tier.HTTP
        def capabilities(self): return Capabilities(fetch=True)
        def available(self): return True
        def open(self, url, *, timeout=30, session=None): raise RuntimeError("boom")
    with pytest.raises(BrowserError):
        BrowserService(tiers=[Dead()]).open("http://x")


# ── Connectors ───────────────────────────────────────────────────────────────
def test_expired_token_is_auth_required_not_crash():
    from saathi.infrastructure.connectors import GitHubConnector, Status
    def h(req): return httpx.Response(401, json={"message": "Bad credentials"})
    gh = GitHubConnector(token="ghp_expired", transport=httpx.MockTransport(h))
    assert gh.health().status is Status.AUTH_REQUIRED   # degraded, not exception


def test_rate_limited_execute_emits_event_and_raises():
    from saathi.infrastructure.connectors import (
        ConnectorRegistry, ConnectorEvent, RateLimited, TelegramConnector)
    bus_events = []
    class Bus:
        def publish_sync(self, n, p): bus_events.append(n)
    def h(req): return httpx.Response(429, json={"ok": False})
    reg = ConnectorRegistry(bus=Bus())
    reg.register(TelegramConnector(token="1:a", chat_id="9", transport=httpx.MockTransport(h)))
    with pytest.raises(RateLimited):
        reg.execute(capability="send_text", connector_id="telegram", text="hi")
    assert ConnectorEvent.RATE_LIMITED.value in bus_events


def test_no_healthy_connector_gives_clean_error():
    from saathi.infrastructure.connectors import ConnectorRegistry, ConnectorError, GitHubConnector
    reg = ConnectorRegistry()
    reg.register(GitHubConnector(token=""))              # unauthenticated → unusable
    with pytest.raises(ConnectorError):
        reg.execute(capability="get_user")


# ── Speech / Conversation ────────────────────────────────────────────────────
def test_speech_unavailable_falls_back_to_null_drivers():
    from saathi.infrastructure.conversation.speech import best_stt, best_tts, EchoStt, SilentTts
    # the guaranteed-available fallbacks keep the pipeline alive with no audio stack
    assert EchoStt().transcribe("hello") == "hello"
    assert isinstance(SilentTts().synthesize("hi"), bytes)
    # selection never crashes and never returns an unavailable driver
    assert best_stt().available() and best_tts().available()


def test_failing_stt_emits_voice_failed():
    from saathi.infrastructure.conversation import VoiceAdapter, VoiceEvent
    from saathi.infrastructure.conversation.speech import SttDriver, SilentTts
    seen = []
    class Bus:
        def publish_sync(self, n, p): seen.append(n)
    class BadStt(SttDriver):
        name = "bad"
        def available(self): return True
        def transcribe(self, audio, *, locale="en"): raise RuntimeError("mic died")
    v = VoiceAdapter(stt=BadStt(), tts=SilentTts(), bus=Bus())
    with pytest.raises(RuntimeError):
        v.listen("x")
    assert VoiceEvent.INTERRUPTED.value not in seen and VoiceEvent.FAILED.value in seen


def test_failing_brain_emits_conversation_failed():
    from saathi.infrastructure.conversation import ConversationEngine, ConversationEvent
    seen = []
    class Bus:
        def publish_sync(self, n, p): seen.append(n)
    eng = ConversationEngine(brain=lambda m, s: (_ for _ in ()).throw(RuntimeError("brain down")),
                             commands=lambda m, s: None, bus=Bus())
    with pytest.raises(RuntimeError):
        eng.handle(eng.session("x"), message="hello")
    assert ConversationEvent.FAILED.value in seen
