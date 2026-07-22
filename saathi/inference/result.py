"""Structured inference result for M20.2 governed path."""
from __future__ import annotations

import hashlib
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from saathi.inference.request import InferenceErrorCategory


@dataclass
class StructuredInferenceResult:
    request_id: str
    mission_id: str = ""
    run_id: str = ""
    ok: bool = False
    selected_model: str = ""
    selected_provider: str = ""
    selected_engine: str = ""
    output_text: str = ""
    finish_reason: str = ""
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    latency_ms: float = 0.0
    engine_health: str = "unknown"
    classification: str = "local"  # local | cloud
    fallback_used: bool = False
    warnings: list[str] = field(default_factory=list)
    evidence_ref: str = ""
    result_fingerprint: str = ""
    error_category: Optional[str] = None
    error_message: str = ""
    router_chain: list[str] = field(default_factory=list)
    prompt_fingerprint: str = ""
    energy_supported: bool = False  # never fabricate
    energy_joules: Optional[float] = None
    timestamp: float = field(default_factory=time.time)

    def finalize_fingerprint(self) -> None:
        body = f"{self.request_id}|{self.selected_model}|{self.output_text[:500]}|{self.ok}"
        self.result_fingerprint = "sha256:" + hashlib.sha256(body.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        # never include secrets
        return d

    @classmethod
    def failure(
        cls,
        request_id: str,
        category: InferenceErrorCategory,
        message: str,
        *,
        mission_id: str = "",
        run_id: str = "",
        warnings: Optional[list[str]] = None,
        router_chain: Optional[list[str]] = None,
        prompt_fingerprint: str = "",
        latency_ms: float = 0.0,
    ) -> "StructuredInferenceResult":
        r = cls(
            request_id=request_id,
            mission_id=mission_id,
            run_id=run_id,
            ok=False,
            error_category=category.value,
            error_message=_sanitize_error(message),
            warnings=list(warnings or []),
            router_chain=list(router_chain or []),
            prompt_fingerprint=prompt_fingerprint,
            latency_ms=latency_ms,
            energy_supported=False,
            energy_joules=None,
        )
        r.finalize_fingerprint()
        return r


def _sanitize_error(msg: str, limit: int = 240) -> str:
    text = (msg or "").replace("\n", " ").strip()
    # strip obvious secrets
    low = text.lower()
    for token in ("authorization:", "bearer ", "api_key", "password"):
        if token in low:
            return "provider error (sanitized)"
    return text[:limit]
