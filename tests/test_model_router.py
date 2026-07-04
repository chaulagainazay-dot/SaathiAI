"""Model Router tests (SES-002) — capability-based routing, AP-12.

The router selects by capability × cost × latency × privacy, never by provider
name. Tests inject a provider set + availability; no network, no keys.
"""
from saathi.model_router import (
    ModelRouter, ModelLabel, Privacy, Prefer, ProviderSpec, DEFAULT_PROVIDERS,
)


def test_private_label_routes_only_to_local():
    r = ModelRouter()
    chain = r.route(ModelLabel.PRIVATE)
    assert chain, "should find a local provider"
    assert all(p.is_local for p in chain)
    assert chain[0].name == "ollama/local"


def test_reasoning_prefers_capable_cloud_model():
    r = ModelRouter()
    best = r.best(ModelLabel.REASONING)
    assert best is not None
    assert ModelLabel.REASONING in best.capabilities   # serves reasoning
    assert not best.is_local                            # a capable cloud model
    # default preference is COST, so the cheapest reasoning-capable provider wins
    reasoning = [p for p in r.providers if ModelLabel.REASONING in p.capabilities]
    assert best.cost_per_1k == min(p.cost_per_1k for p in reasoning)


def test_cost_preference_orders_cheapest_first():
    r = ModelRouter()
    chain = r.route(ModelLabel.STANDARD, prefer=Prefer.COST)
    costs = [p.cost_per_1k for p in chain]
    assert costs == sorted(costs)         # cheapest first
    assert chain[0].cost_per_1k == 0.0    # a free provider wins on cost


def test_latency_preference_orders_fastest_first():
    r = ModelRouter()
    chain = r.route(ModelLabel.STANDARD, prefer=Prefer.LATENCY)
    tiers = [p.latency_tier for p in chain]
    assert tiers == sorted(tiers)


def test_max_cost_filters_expensive_providers():
    r = ModelRouter()
    chain = r.route(ModelLabel.STANDARD, max_cost=0.0)   # free only
    assert chain
    assert all(p.cost_per_1k == 0.0 for p in chain)


def test_availability_filters_unreachable_providers():
    # Only groq "available" → it must be the sole candidate even if others are cheaper/capable.
    r = ModelRouter(is_available=lambda name: name == "groq/llama-3.3-70b")
    chain = r.route(ModelLabel.STANDARD)
    assert [p.name for p in chain] == ["groq/llama-3.3-70b"]


def test_local_only_privacy_excludes_cloud_even_if_capable():
    r = ModelRouter()
    chain = r.route(ModelLabel.STANDARD, privacy=Privacy.LOCAL_ONLY)
    assert chain
    assert all(p.is_local for p in chain)


def test_unservable_label_returns_empty_chain():
    # A provider set with no reasoning-capable model → empty, not a crash.
    only_fast = [ProviderSpec("x/fast", frozenset({ModelLabel.FAST}), 0.0, 1, False)]
    r = ModelRouter(providers=only_fast)
    assert r.route(ModelLabel.REASONING) == []
    assert r.best(ModelLabel.REASONING) is None


def test_adding_a_provider_is_one_registry_entry():
    """A 'future model' plugs in with zero router changes (AP-10)."""
    future = DEFAULT_PROVIDERS + [
        ProviderSpec("kimi/k2", frozenset({ModelLabel.REASONING, ModelLabel.LONG}), 0.2, 1, False)
    ]
    r = ModelRouter(providers=future)
    # Now cheapest reasoning provider is the newcomer, not gpt-4o.
    assert r.best(ModelLabel.REASONING).name == "kimi/k2"
