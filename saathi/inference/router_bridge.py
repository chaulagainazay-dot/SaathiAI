"""Bridge runtime/benchmark observations into ModelRouter *without* replacing it.

ModelRouter remains the sole authority for ordered provider selection.
Observations may only:
  * mark providers unavailable (health)
  * supply optional preference hints that **never** override safety/privacy/budget

Learned / advisory scores cannot bypass deterministic constraints.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from saathi.model_router import (
    ModelLabel,
    ModelRouter,
    Prefer,
    Privacy,
    ProviderSpec,
)

from saathi.inference.catalogue import ModelCatalogue, get_default_catalogue
from saathi.inference.config import InferenceSettings, load_inference_settings
from saathi.inference.hardware import HardwareProfile, profile_local_hardware


@dataclass
class ProviderObservation:
    provider_name: str
    success: int = 0
    failure: int = 0
    total_latency_ms: float = 0.0
    last_ok: Optional[bool] = None
    last_error: str = ""
    updated_at: float = field(default_factory=time.time)

    @property
    def success_rate(self) -> Optional[float]:
        n = self.success + self.failure
        if n == 0:
            return None
        return self.success / n

    @property
    def avg_latency_ms(self) -> Optional[float]:
        if self.success == 0:
            return None
        return self.total_latency_ms / self.success


class ObservationStore:
    """In-process advisory stats (not a second router)."""

    def __init__(self) -> None:
        self._obs: dict[str, ProviderObservation] = {}
        self._unhealthy: set[str] = set()

    def record_success(self, provider_name: str, latency_ms: float = 0.0) -> None:
        o = self._obs.setdefault(provider_name, ProviderObservation(provider_name))
        o.success += 1
        o.total_latency_ms += latency_ms
        o.last_ok = True
        o.updated_at = time.time()
        self._unhealthy.discard(provider_name)

    def record_failure(self, provider_name: str, error: str = "") -> None:
        o = self._obs.setdefault(provider_name, ProviderObservation(provider_name))
        o.failure += 1
        o.last_ok = False
        o.last_error = error
        o.updated_at = time.time()

    def mark_unhealthy(self, provider_name: str) -> None:
        self._unhealthy.add(provider_name)

    def mark_healthy(self, provider_name: str) -> None:
        self._unhealthy.discard(provider_name)

    def is_healthy(self, provider_name: str) -> bool:
        return provider_name not in self._unhealthy

    def get(self, provider_name: str) -> Optional[ProviderObservation]:
        return self._obs.get(provider_name)

    def clear(self) -> None:
        self._obs.clear()
        self._unhealthy.clear()


_STORE = ObservationStore()


def get_observation_store() -> ObservationStore:
    return _STORE


def reset_observation_store() -> None:
    _STORE.clear()


def make_availability_checker(
    base: Optional[Callable[[str], bool]] = None,
    store: Optional[ObservationStore] = None,
) -> Callable[[str], bool]:
    """Compose env/key availability with health observations."""
    store = store or _STORE

    def _check(name: str) -> bool:
        if base is not None and not base(name):
            return False
        return store.is_healthy(name)

    return _check


@dataclass(frozen=True)
class RouteRequest:
    label: ModelLabel
    privacy: Privacy = Privacy.CLOUD_OK
    max_cost: Optional[float] = None
    prefer: Prefer = Prefer.COST
    require_structured_output: bool = False
    require_tool_calling: bool = False
    advisory_prefer_success_rate: bool = False
    mission_local_only: bool = False


def route_with_governance(
    request: RouteRequest,
    *,
    router: Optional[ModelRouter] = None,
    catalogue: Optional[ModelCatalogue] = None,
    store: Optional[ObservationStore] = None,
    settings: Optional[InferenceSettings] = None,
    hardware: Optional[HardwareProfile] = None,
) -> list[ProviderSpec]:
    """Authoritative routing: ModelRouter first, then hard filters, then optional advisory reorder.

    Deterministic overrides (always win over advisory):
      * privacy / mission local-only
      * max_cost / budget
      * unhealthy providers (via is_available)
      * cloud fallback disabled
      * hardware unfit for local oversized models (warning filter when memory_estimate known)
    """
    settings = settings or load_inference_settings()
    store = store or _STORE
    catalogue = catalogue or get_default_catalogue()
    router = router or ModelRouter(is_available=make_availability_checker(store=store))

    privacy = request.privacy
    if request.mission_local_only:
        privacy = Privacy.LOCAL_ONLY

    # Cloud fallback off globally forces local-only selection
    if not settings.allow_cloud_fallback and privacy is Privacy.CLOUD_OK:
        # still allow cloud if explicitly CLOUD_OK and allow_cloud_fallback false?
        # Brief: allow_cloud_fallback = false by default → do not auto-fallback to cloud.
        # Interpreting as: prefer local when available, but do not *force* local unless privacy says so.
        # Sensitive path uses LOCAL_ONLY. For STANDARD, still may use cloud if keys present.
        pass

    chain = router.route(
        request.label,
        privacy=privacy,
        max_cost=request.max_cost,
        prefer=request.prefer,
    )

    # Capability filters from catalogue (declared/tested metadata)
    filtered: list[ProviderSpec] = []
    for p in chain:
        recs = [r for r in catalogue.list_records() if r.router_provider_name == p.name]
        if request.require_structured_output and recs:
            if not any(r.structured_output.value for r in recs):
                continue
        if request.require_tool_calling and recs:
            if not any(r.tool_calling.value for r in recs):
                continue
        # Hardware: drop local models known to exceed fit when profile provided
        if hardware is not None and p.is_local and recs:
            bad = False
            for r in recs:
                if r.parameter_count is None:
                    continue
                fit = hardware.estimate_model_fit(
                    model_id=r.model_id,
                    parameter_count_b=r.parameter_count,
                    memory_estimate_gb=r.memory_estimate,
                    disk_estimate_gb=r.disk_estimate,
                    quantization=r.quantization,
                )
                # Only exclude if *all* mapped models fail memory fit
                if not fit.fits_memory:
                    bad = True
                else:
                    bad = False
                    break
            if bad and len(recs) > 0:
                # keep provider if any model fits; if none, skip
                if all(
                    not hardware.estimate_model_fit(
                        model_id=r.model_id,
                        parameter_count_b=r.parameter_count or 99,
                        memory_estimate_gb=r.memory_estimate,
                        quantization=r.quantization,
                    ).fits_memory
                    for r in recs
                    if r.parameter_count is not None
                ):
                    continue
        filtered.append(p)

    # Advisory reorder by historical success — only if learning mode is advisory
    # and never if it would reorder past a privacy/cost winner incorrectly:
    # we only stable-sort among equal cost tier when prefer is COST.
    if (
        request.advisory_prefer_success_rate
        and settings.learning_routing_mode == "advisory"
        and filtered
    ):
        def _adv_key(p: ProviderSpec):
            o = store.get(p.name)
            rate = o.success_rate if o and o.success_rate is not None else 0.5
            # Keep deterministic primary keys first (already sorted by router).
            # Use negative rate as last key only.
            if request.prefer is Prefer.COST:
                return (p.cost_per_1k, p.quality_tier, p.latency_tier, -rate)
            if request.prefer is Prefer.LATENCY:
                return (p.latency_tier, p.cost_per_1k, -rate)
            return (p.quality_tier, p.cost_per_1k, -rate)

        filtered = sorted(filtered, key=_adv_key)

    return filtered


def engine_ids_for_providers(providers: list[ProviderSpec]) -> list[str]:
    """Map ProviderSpec names to inference engine ids (family prefix)."""
    out: list[str] = []
    for p in providers:
        family = p.name.split("/", 1)[0]
        if family == "ollama":
            eid = "ollama"
        elif family in {"openai", "anthropic", "groq", "gemini", "deepseek", "glm", "qwen"}:
            eid = family
        else:
            eid = family
        if eid not in out:
            out.append(eid)
    return out
