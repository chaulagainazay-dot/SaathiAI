"""Model Router execution-path tests (SES-002) — AP-12.

`generate()` routes by capability and executes; providers are injected fake
callers, so no network/keys. Covers quality-first ordering, fallback down the
chain, private-only routing, and the no-provider error.
"""
import pytest

from saathi.llm import generate, LLMResult
from saathi.model_router import ModelRouter, ModelLabel, Privacy, Prefer


def _all_available(_name):
    return True


def _router():
    return ModelRouter(is_available=_all_available)


def test_quality_preference_picks_openai_first():
    calls = []

    def mk(name):
        def caller(prompt, system, mt, to):
            calls.append(name)
            return f"reply-from-{name}", f"{name}-model", {}
        return caller

    callers = {"openai": mk("openai"), "groq": mk("groq"), "gemini": mk("gemini"), "ollama": mk("ollama")}
    res = generate(ModelLabel.STANDARD, "hi", router=_router(), callers=callers,
                   prefer=Prefer.QUALITY, trace=False)
    assert isinstance(res, LLMResult)
    assert res.provider == "openai/gpt-4o"     # quality_tier 1 wins
    assert calls == ["openai"]                  # no fallback needed


def test_fallback_to_next_provider_on_error():
    def boom(*a):
        raise RuntimeError("provider down")

    def ok(prompt, system, mt, to):
        return "recovered", "groq-model", {}

    # openai fails → chain falls to the next capable provider
    callers = {"openai": boom, "groq": ok, "gemini": ok, "ollama": ok}
    res = generate(ModelLabel.STANDARD, "hi", router=_router(), callers=callers,
                   prefer=Prefer.QUALITY, trace=False)
    assert res.text == "recovered"
    assert res.provider != "openai/gpt-4o"


def test_private_routes_only_to_local_provider():
    used = []

    def mk(name):
        def caller(p, s, mt, to):
            used.append(name)
            return "ok", name, {}
        return caller

    callers = {k: mk(k) for k in ("openai", "groq", "gemini", "ollama")}
    res = generate(ModelLabel.PRIVATE, "secret", router=_router(), callers=callers,
                   privacy=Privacy.LOCAL_ONLY, trace=False)
    assert res.provider == "ollama/local"
    assert used == ["ollama"]                   # cloud providers never called


def test_no_available_provider_raises():
    # No provider available at all → clear error, not a silent None.
    r = ModelRouter(is_available=lambda n: False)
    with pytest.raises(RuntimeError, match="No available provider"):
        generate(ModelLabel.STANDARD, "hi", router=r, callers={}, trace=False)


def test_all_providers_fail_raises():
    def boom(*a):
        raise RuntimeError("x")
    callers = {k: boom for k in ("openai", "groq", "gemini", "ollama")}
    with pytest.raises(RuntimeError, match="All providers failed"):
        generate(ModelLabel.STANDARD, "hi", router=_router(), callers=callers, trace=False)
