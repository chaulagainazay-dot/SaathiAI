"""Provider-parity + routing tests for the Model Router (Phase 1.1).

Guards the invariant that every provider registered in the router has a matching
executor in llm.DEFAULT_CALLERS and a resolvable availability rule — so adding a
provider can never silently become a route to nowhere.
"""
from saathi.model_router import DEFAULT_PROVIDERS, ModelRouter, ModelLabel, Prefer, Privacy
from saathi.llm import DEFAULT_CALLERS, env_availability


def _family(name: str) -> str:
    return name.split("/", 1)[0]


def test_every_provider_has_a_caller():
    families = {_family(p.name) for p in DEFAULT_PROVIDERS}
    assert families <= set(DEFAULT_CALLERS), f"providers without callers: {families - set(DEFAULT_CALLERS)}"


def test_every_provider_has_availability_rule():
    # env_availability must return a bool for every registered provider (never raise).
    for p in DEFAULT_PROVIDERS:
        assert isinstance(env_availability(p.name), bool)


def test_new_providers_are_registered():
    names = {p.name for p in DEFAULT_PROVIDERS}
    for expected in ("anthropic/claude", "deepseek/deepseek-chat", "glm/glm-4.6", "qwen/qwen-2.5-72b"):
        assert expected in names, f"missing provider {expected}"


def test_reasoning_chain_is_top_quality_first():
    chain = ModelRouter().route(ModelLabel.REASONING, prefer=Prefer.QUALITY)
    # top of a quality-preferred reasoning chain must be a quality-tier-1 model
    assert chain and chain[0].quality_tier == 1


def test_private_label_stays_local():
    chain = ModelRouter().route(ModelLabel.STANDARD, privacy=Privacy.LOCAL_ONLY)
    assert chain and all(p.is_local for p in chain)


def test_openrouter_key_gates_glm_deepseek_qwen(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    for name in ("glm/glm-4.6", "deepseek/deepseek-chat", "qwen/qwen-2.5-72b"):
        assert env_availability(name) is False
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-real")
    for name in ("glm/glm-4.6", "deepseek/deepseek-chat", "qwen/qwen-2.5-72b"):
        assert env_availability(name) is True
