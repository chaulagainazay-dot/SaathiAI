"""Canonical SaathiOS model catalogue with capability provenance.

Does not hard-code unverified claims: each capability field carries provenance.
ModelRouter remains authoritative for selection; this is metadata only.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Optional

from saathi.inference.errors import CatalogueError


class CapabilityProvenance(str, Enum):
    DECLARED = "declared"    # vendor/docs claim
    DETECTED = "detected"    # runtime probe
    TESTED = "tested"        # benchmark / eval
    INFERRED = "inferred"    # heuristic


class PrivacyClass(str, Enum):
    LOCAL = "local"
    CLOUD = "cloud"
    HYBRID = "hybrid"


class Availability(str, Enum):
    UNKNOWN = "unknown"
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    STALE = "stale"


@dataclass(frozen=True)
class ProvenancedBool:
    value: bool
    provenance: CapabilityProvenance = CapabilityProvenance.DECLARED
    source: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "provenance": self.provenance.value,
            "source": self.source,
        }


def _pb(value: bool, prov: CapabilityProvenance = CapabilityProvenance.DECLARED, source: str = "") -> ProvenancedBool:
    return ProvenancedBool(value=value, provenance=prov, source=source)


@dataclass
class ModelRecord:
    provider: str
    model_id: str
    display_name: str
    parameter_count: Optional[float] = None  # billions
    quantization: str = "unknown"
    context_window: Optional[int] = None
    runtime: str = ""
    local_or_cloud: str = "local"  # local | cloud
    memory_estimate: Optional[float] = None  # GB
    disk_estimate: Optional[float] = None  # GB
    tool_calling: ProvenancedBool = field(default_factory=lambda: _pb(False, CapabilityProvenance.INFERRED))
    structured_output: ProvenancedBool = field(default_factory=lambda: _pb(False, CapabilityProvenance.INFERRED))
    vision: ProvenancedBool = field(default_factory=lambda: _pb(False, CapabilityProvenance.INFERRED))
    audio: ProvenancedBool = field(default_factory=lambda: _pb(False, CapabilityProvenance.INFERRED))
    streaming: ProvenancedBool = field(default_factory=lambda: _pb(True, CapabilityProvenance.DECLARED, "openai-compat-default"))
    estimated_latency_class: str = "unknown"  # low|medium|high|unknown
    estimated_cost: Optional[float] = None  # relative per 1k; None unknown
    privacy_class: PrivacyClass = PrivacyClass.LOCAL
    availability: Availability = Availability.UNKNOWN
    health_status: str = "unknown"
    last_verified_at: Optional[float] = None
    source: str = "saathi_builtin"
    notes: str = ""
    router_provider_name: str = ""  # maps to ModelRouter ProviderSpec.name when known

    def key(self) -> str:
        return f"{self.provider}/{self.model_id}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model_id": self.model_id,
            "display_name": self.display_name,
            "parameter_count": self.parameter_count,
            "quantization": self.quantization,
            "context_window": self.context_window,
            "runtime": self.runtime,
            "local_or_cloud": self.local_or_cloud,
            "memory_estimate": self.memory_estimate,
            "disk_estimate": self.disk_estimate,
            "tool_calling": self.tool_calling.to_dict(),
            "structured_output": self.structured_output.to_dict(),
            "vision": self.vision.to_dict(),
            "audio": self.audio.to_dict(),
            "streaming": self.streaming.to_dict(),
            "estimated_latency_class": self.estimated_latency_class,
            "estimated_cost": self.estimated_cost,
            "privacy_class": self.privacy_class.value,
            "availability": self.availability.value,
            "health_status": self.health_status,
            "last_verified_at": self.last_verified_at,
            "source": self.source,
            "notes": self.notes,
            "router_provider_name": self.router_provider_name,
        }

    def validate(self) -> None:
        if not self.provider or not self.model_id:
            raise CatalogueError("provider and model_id are required")
        if self.local_or_cloud not in {"local", "cloud"}:
            raise CatalogueError(f"invalid local_or_cloud: {self.local_or_cloud}")
        if self.parameter_count is not None and self.parameter_count < 0:
            raise CatalogueError("parameter_count must be >= 0")
        if self.context_window is not None and self.context_window <= 0:
            raise CatalogueError("context_window must be positive")
        if self.memory_estimate is not None and self.memory_estimate < 0:
            raise CatalogueError("memory_estimate must be >= 0")


class ModelCatalogue:
    """In-memory catalogue with provenance-aware records."""

    def __init__(self, records: Optional[list[ModelRecord]] = None, *, stale_after_seconds: float = 86400.0):
        self._records: dict[str, ModelRecord] = {}
        self.stale_after_seconds = stale_after_seconds
        for r in records or []:
            self.upsert(r)

    def upsert(self, record: ModelRecord) -> None:
        record.validate()
        self._records[record.key()] = record

    def get(self, provider: str, model_id: str) -> Optional[ModelRecord]:
        return self._records.get(f"{provider}/{model_id}")

    def get_by_key(self, key: str) -> Optional[ModelRecord]:
        return self._records.get(key)

    def list_records(self) -> list[ModelRecord]:
        return list(self._records.values())

    def mark_health(
        self,
        provider: str,
        model_id: str,
        *,
        health_status: str,
        availability: Availability,
        verified_at: Optional[float] = None,
    ) -> Optional[ModelRecord]:
        rec = self.get(provider, model_id)
        if rec is None:
            return None
        updated = replace(
            rec,
            health_status=health_status,
            availability=availability,
            last_verified_at=verified_at if verified_at is not None else time.time(),
        )
        self.upsert(updated)
        return updated

    def refresh_stale(self, *, now: Optional[float] = None) -> list[ModelRecord]:
        """Mark records with old verification as STALE; return them."""
        now = now if now is not None else time.time()
        stale: list[ModelRecord] = []
        for key, rec in list(self._records.items()):
            if rec.last_verified_at is None:
                continue
            if now - rec.last_verified_at > self.stale_after_seconds:
                updated = replace(rec, availability=Availability.STALE, health_status="stale")
                self._records[key] = updated
                stale.append(updated)
        return stale

    def supports(
        self,
        provider: str,
        model_id: str,
        capability: str,
        *,
        require_tested: bool = False,
    ) -> bool:
        rec = self.get(provider, model_id)
        if rec is None:
            return False
        attr = getattr(rec, capability, None)
        if not isinstance(attr, ProvenancedBool):
            raise CatalogueError(f"unsupported capability field: {capability}")
        if require_tested and attr.provenance != CapabilityProvenance.TESTED:
            return False
        return bool(attr.value)


def _builtin_records() -> list[ModelRecord]:
    """Small built-in set aligned with SaathiOS DEFAULT_PROVIDERS + local defaults.

    Provenance is declared/inferred only — not claimed as tested.
    """
    return [
        ModelRecord(
            provider="ollama",
            model_id="qwen2.5:3b",
            display_name="Qwen2.5 3B (Ollama)",
            parameter_count=3.0,
            quantization="q4",
            context_window=32768,
            runtime="ollama",
            local_or_cloud="local",
            memory_estimate=2.2,
            disk_estimate=2.0,
            tool_calling=_pb(True, CapabilityProvenance.DECLARED, "ollama/qwen2.5 docs"),
            structured_output=_pb(True, CapabilityProvenance.INFERRED, "json-mode common"),
            streaming=_pb(True, CapabilityProvenance.DECLARED, "ollama stream API"),
            estimated_latency_class="medium",
            estimated_cost=0.0,
            privacy_class=PrivacyClass.LOCAL,
            source="saathi_builtin",
            router_provider_name="ollama/local",
            notes="Default local model for M2 8 GB class devices",
        ),
        ModelRecord(
            provider="ollama",
            model_id="tinyllama-1.1b",
            display_name="TinyLlama 1.1B",
            parameter_count=1.1,
            quantization="q4",
            context_window=2048,
            runtime="ollama",
            local_or_cloud="local",
            memory_estimate=1.0,
            disk_estimate=0.7,
            tool_calling=_pb(False, CapabilityProvenance.INFERRED, "small model"),
            structured_output=_pb(False, CapabilityProvenance.INFERRED, "unreliable"),
            streaming=_pb(True, CapabilityProvenance.DECLARED, "ollama stream API"),
            estimated_latency_class="low",
            estimated_cost=0.0,
            privacy_class=PrivacyClass.LOCAL,
            source="saathi_builtin",
            router_provider_name="ollama/local",
        ),
        ModelRecord(
            provider="ollama",
            model_id="llama3.1:8b",
            display_name="Llama 3.1 8B",
            parameter_count=8.0,
            quantization="q4",
            context_window=128000,
            runtime="ollama",
            local_or_cloud="local",
            memory_estimate=5.5,
            disk_estimate=4.7,
            tool_calling=_pb(True, CapabilityProvenance.DECLARED, "meta/ollama"),
            structured_output=_pb(True, CapabilityProvenance.INFERRED, "common"),
            streaming=_pb(True, CapabilityProvenance.DECLARED, "ollama"),
            estimated_latency_class="high",
            estimated_cost=0.0,
            privacy_class=PrivacyClass.LOCAL,
            source="saathi_builtin",
            router_provider_name="ollama/local",
            notes="Likely memory pressure on 8 GB unified memory",
        ),
        ModelRecord(
            provider="gemini",
            model_id="gemini-3.5-flash",
            display_name="Gemini 3.5 Flash",
            parameter_count=None,
            quantization="n/a",
            context_window=1000000,
            runtime="cloud",
            local_or_cloud="cloud",
            tool_calling=_pb(True, CapabilityProvenance.DECLARED, "google docs"),
            structured_output=_pb(True, CapabilityProvenance.DECLARED, "google docs"),
            vision=_pb(True, CapabilityProvenance.DECLARED, "google docs"),
            streaming=_pb(True, CapabilityProvenance.DECLARED, "google docs"),
            estimated_latency_class="low",
            estimated_cost=0.0,
            privacy_class=PrivacyClass.CLOUD,
            source="saathi_builtin",
            router_provider_name="gemini/3.5-flash",
        ),
        ModelRecord(
            provider="groq",
            model_id="llama-3.3-70b-versatile",
            display_name="Llama 3.3 70B (Groq)",
            parameter_count=70.0,
            quantization="n/a",
            context_window=128000,
            runtime="cloud",
            local_or_cloud="cloud",
            tool_calling=_pb(True, CapabilityProvenance.DECLARED, "groq docs"),
            structured_output=_pb(True, CapabilityProvenance.INFERRED, "json mode"),
            streaming=_pb(True, CapabilityProvenance.DECLARED, "groq"),
            estimated_latency_class="low",
            estimated_cost=0.0,
            privacy_class=PrivacyClass.CLOUD,
            source="saathi_builtin",
            router_provider_name="groq/llama-3.3-70b",
        ),
        ModelRecord(
            provider="anthropic",
            model_id="claude-sonnet",
            display_name="Claude Sonnet",
            parameter_count=None,
            quantization="n/a",
            context_window=200000,
            runtime="cloud",
            local_or_cloud="cloud",
            tool_calling=_pb(True, CapabilityProvenance.DECLARED, "anthropic docs"),
            structured_output=_pb(True, CapabilityProvenance.DECLARED, "anthropic docs"),
            vision=_pb(True, CapabilityProvenance.DECLARED, "anthropic docs"),
            streaming=_pb(True, CapabilityProvenance.DECLARED, "anthropic"),
            estimated_latency_class="medium",
            estimated_cost=6.0,
            privacy_class=PrivacyClass.CLOUD,
            source="saathi_builtin",
            router_provider_name="anthropic/claude",
        ),
        ModelRecord(
            provider="openai",
            model_id="gpt-4o",
            display_name="GPT-4o",
            parameter_count=None,
            quantization="n/a",
            context_window=128000,
            runtime="cloud",
            local_or_cloud="cloud",
            tool_calling=_pb(True, CapabilityProvenance.DECLARED, "openai docs"),
            structured_output=_pb(True, CapabilityProvenance.DECLARED, "openai docs"),
            vision=_pb(True, CapabilityProvenance.DECLARED, "openai docs"),
            streaming=_pb(True, CapabilityProvenance.DECLARED, "openai"),
            estimated_latency_class="medium",
            estimated_cost=5.0,
            privacy_class=PrivacyClass.CLOUD,
            source="saathi_builtin",
            router_provider_name="openai/gpt-4o",
        ),
    ]


_DEFAULT: Optional[ModelCatalogue] = None


def get_default_catalogue() -> ModelCatalogue:
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = ModelCatalogue(_builtin_records())
    return _DEFAULT


def reset_default_catalogue() -> None:
    """Test helper."""
    global _DEFAULT
    _DEFAULT = None
