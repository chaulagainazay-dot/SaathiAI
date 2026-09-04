"""Model Router — capability-based LLM routing (SES-002).

The router knows only *capabilities*, never provider identity. Agents ask for a
label ("reasoning", "fast", "private"); the router picks the best available
provider by capability × cost × latency × privacy:

    Task → label → candidates that serve it → filter (privacy, cost, availability)
         → sort (preference) → ordered provider chain → execution

It does not care whether the destination is GPT, Gemini, Claude, Kimi, Ollama,
a local model, or a future one. Add a provider = one registry entry; no caller
changes (AP-02 provider abstraction, AP-10 capability reuse).

Reconciles with today's `tools/_llm_helper.ask_llm` (a hardcoded
OpenAI→Groq→Gemini chain): the router *produces* that ordering from capability
data instead of hardcoding it, and returns a fallback chain so the existing
try-next-on-failure pattern still works.

Testable in isolation (AP-12): the provider registry and availability checks
are injected; no network, no keys.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable


class ModelLabel(str, Enum):
    """The 7 SES-002 capability labels — agents specify intent, not model."""
    SCREENING = "screening"     # cheap/fast triage
    STANDARD = "standard"       # general-purpose
    REASONING = "reasoning"     # hard multi-step reasoning
    MULTIMODAL = "multimodal"   # images/audio in
    FAST = "fast"               # lowest latency
    LONG = "long"               # long context
    PRIVATE = "private"         # must stay local


class Privacy(str, Enum):
    CLOUD_OK = "cloud_ok"
    LOCAL_ONLY = "local_only"


class Prefer(str, Enum):
    COST = "cost"
    LATENCY = "latency"
    QUALITY = "quality"


@dataclass(frozen=True)
class ProviderSpec:
    name: str                       # e.g. "groq/llama-3.3-70b"
    capabilities: frozenset[ModelLabel]
    cost_per_1k: float              # relative $ (0 = free/local)
    latency_tier: int               # 1 = fastest … 3 = slowest
    is_local: bool                  # privacy: local models never leave the box
    quality_tier: int = 2           # 1 = highest quality … 3 = lowest


# Default registry — maps real providers to capabilities. Provider identity
# lives ONLY here; the rest of the platform speaks in labels.
DEFAULT_PROVIDERS: list[ProviderSpec] = [
    ProviderSpec("anthropic/claude", frozenset({ModelLabel.STANDARD, ModelLabel.REASONING,
                 ModelLabel.MULTIMODAL, ModelLabel.LONG}), cost_per_1k=6.0, latency_tier=2, is_local=False, quality_tier=1),
    ProviderSpec("openai/gpt-4o", frozenset({ModelLabel.STANDARD, ModelLabel.REASONING,
                 ModelLabel.MULTIMODAL, ModelLabel.LONG}), cost_per_1k=5.0, latency_tier=2, is_local=False, quality_tier=1),
    ProviderSpec("deepseek/deepseek-chat", frozenset({ModelLabel.STANDARD, ModelLabel.REASONING,
                 ModelLabel.LONG}), cost_per_1k=0.3, latency_tier=2, is_local=False, quality_tier=1),
    ProviderSpec("glm/glm-4.6", frozenset({ModelLabel.STANDARD, ModelLabel.REASONING,
                 ModelLabel.LONG}), cost_per_1k=0.5, latency_tier=2, is_local=False, quality_tier=2),
    ProviderSpec("qwen/qwen-2.5-72b", frozenset({ModelLabel.SCREENING, ModelLabel.STANDARD,
                 ModelLabel.LONG, ModelLabel.FAST}), cost_per_1k=0.4, latency_tier=2, is_local=False, quality_tier=2),
    # Gemini 3.5 Flash — the DEFAULT brain: free tier (cost 0), fast. Listed BEFORE
    # groq so it wins the cost/quality/latency tie (insertion order) and ranks first
    # for general work; Claude/GPT still win REASONING/QUALITY. Model = GEMINI_MODEL.
    ProviderSpec("gemini/3.5-flash", frozenset({ModelLabel.SCREENING, ModelLabel.STANDARD,
                 ModelLabel.MULTIMODAL, ModelLabel.LONG, ModelLabel.FAST}),
                 cost_per_1k=0.0, latency_tier=1, is_local=False, quality_tier=2),
    ProviderSpec("groq/llama-3.3-70b", frozenset({ModelLabel.SCREENING, ModelLabel.STANDARD,
                 ModelLabel.FAST}), cost_per_1k=0.0, latency_tier=1, is_local=False, quality_tier=2),
    # Kimi entries are candidates only. Provider policy is default-off and the
    # expensive K3 class requires approval before execution.
    ProviderSpec("kimi/kimi-k2.7-code", frozenset({ModelLabel.STANDARD, ModelLabel.REASONING,
                 ModelLabel.LONG}), cost_per_1k=4.0, latency_tier=2, is_local=False, quality_tier=1),
    ProviderSpec("kimi/kimi-k3", frozenset({ModelLabel.STANDARD, ModelLabel.REASONING,
                 ModelLabel.MULTIMODAL, ModelLabel.LONG}), cost_per_1k=15.0,
                 latency_tier=3, is_local=False, quality_tier=1),
    ProviderSpec("ollama/local", frozenset({ModelLabel.SCREENING, ModelLabel.STANDARD,
                 ModelLabel.FAST, ModelLabel.PRIVATE}), cost_per_1k=0.0, latency_tier=2, is_local=True, quality_tier=3),
]


def _always_available(_name: str) -> bool:
    return True


class ModelRouter:
    def __init__(
        self,
        providers: list[ProviderSpec] | None = None,
        is_available: Callable[[str], bool] = _always_available,
    ):
        self.providers = providers if providers is not None else DEFAULT_PROVIDERS
        self._available = is_available

    def route(
        self,
        label: ModelLabel,
        privacy: Privacy = Privacy.CLOUD_OK,
        max_cost: float | None = None,
        prefer: Prefer = Prefer.COST,
    ) -> list[ProviderSpec]:
        """Ordered fallback chain of providers that can serve ``label`` under the
        given constraints. Empty if nothing qualifies."""
        candidates = [
            p for p in self.providers
            if label in p.capabilities
            and self._available(p.name)
            and (privacy is not Privacy.LOCAL_ONLY or p.is_local)
            and (max_cost is None or p.cost_per_1k <= max_cost)
        ]
        if prefer is Prefer.LATENCY:
            candidates.sort(key=lambda p: (p.latency_tier, p.cost_per_1k))
        elif prefer is Prefer.QUALITY:
            candidates.sort(key=lambda p: (p.quality_tier, p.cost_per_1k))
        else:  # COST — on a cost tie, prefer higher quality then lower latency
            candidates.sort(key=lambda p: (p.cost_per_1k, p.quality_tier, p.latency_tier))
        return candidates

    def best(self, label: ModelLabel, **kw) -> ProviderSpec | None:
        chain = self.route(label, **kw)
        return chain[0] if chain else None


# Process-wide default router.
router = ModelRouter()
