"""M21.1 — Canonical caller policy registry for governed inference.

Does not replace ModelRouter or caller_rollout modes. Defines what each
caller is *allowed* to request under the M21.1 contract. Unknown callers
fail closed on governed paths.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional

from saathi.inference.caller_rollout import (
    CALLER_CHEAP_ASK,
    CALLER_PROSE_CLEAN,
    PROMOTION_FORBIDDEN,
    SELECTED_CALLERS,
)


class CallerCertification(str, Enum):
    CERTIFIED_OPT_IN = "certified_opt_in"  # M20.3 selected
    PILOT = "pilot"
    LEGACY = "legacy"
    TEST = "test"
    FORBIDDEN = "forbidden"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class CallerPolicy:
    caller_id: str
    description: str
    product_area: str
    certification: CallerCertification
    enabled: bool = True
    local_only: bool = True
    cloud_allowed: bool = False
    cloud_fallback_allowed: bool = False
    tools_allowed: bool = False
    streaming_allowed: bool = False
    structured_output_allowed: bool = False
    allowed_capabilities: frozenset[str] = field(
        default_factory=lambda: frozenset({"screening", "standard", "fast", "private"})
    )
    max_input_chars: int = 6000
    max_output_tokens: int = 512
    timeout_seconds: float = 45.0
    max_retries: int = 0
    max_concurrency: int = 1
    privacy_default: str = "internal"
    retention_policy: str = "metadata_only"
    request_cost_ceiling: float = 0.0  # 0 = local free / no cloud spend
    log_prompt: bool = False
    log_output: bool = False
    legacy: bool = False
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["certification"] = self.certification.value
        d["allowed_capabilities"] = sorted(self.allowed_capabilities)
        return d


# Canonical registry — extend, do not duplicate.
_CALLER_POLICIES: dict[str, CallerPolicy] = {
    CALLER_CHEAP_ASK: CallerPolicy(
        caller_id=CALLER_CHEAP_ASK,
        description="Routine screening / cheap tasks (M20.3 opt-in)",
        product_area="tools",
        certification=CallerCertification.CERTIFIED_OPT_IN,
        local_only=True,
        cloud_allowed=False,
        cloud_fallback_allowed=False,
        max_input_chars=6000,
        max_output_tokens=512,
        timeout_seconds=45.0,
        allowed_capabilities=frozenset({"screening", "fast", "standard", "private"}),
        notes="Default rollout legacy; governed via compat adapter",
    ),
    CALLER_PROSE_CLEAN: CallerPolicy(
        caller_id=CALLER_PROSE_CLEAN,
        description="Prose cleanup (M20.3 opt-in)",
        product_area="tools",
        certification=CallerCertification.CERTIFIED_OPT_IN,
        local_only=True,
        cloud_allowed=False,
        cloud_fallback_allowed=False,
        max_input_chars=8000,
        max_output_tokens=1024,
        timeout_seconds=60.0,
        allowed_capabilities=frozenset({"standard", "private", "screening"}),
        notes="Default rollout legacy",
    ),
    "execution_gateway": CallerPolicy(
        caller_id="execution_gateway",
        description="ToolIntent → ModelGateway → governed path",
        product_area="execution",
        certification=CallerCertification.PILOT,
        max_input_chars=16000,
        max_output_tokens=1024,
        timeout_seconds=60.0,
        notes="Governed via gateway when flags on",
    ),
    "m20_certification": CallerPolicy(
        caller_id="m20_certification",
        description="M20.6 live/injected certification suite",
        product_area="inference_cert",
        certification=CallerCertification.PILOT,
        max_input_chars=4000,
        max_output_tokens=256,
        timeout_seconds=30.0,
        allowed_capabilities=frozenset({"screening", "standard", "private", "fast"}),
    ),
    "m20_6_certification": CallerPolicy(
        caller_id="m20_6_certification",
        description="M20.6 certification suite (explicit id)",
        product_area="inference_cert",
        certification=CallerCertification.PILOT,
        max_input_chars=4000,
        max_output_tokens=256,
        timeout_seconds=30.0,
        allowed_capabilities=frozenset({"screening", "standard", "private", "fast"}),
    ),
    "test_m21": CallerPolicy(
        caller_id="test_m21",
        description="Deterministic unit tests",
        product_area="test",
        certification=CallerCertification.TEST,
        max_input_chars=2000,
        max_output_tokens=128,
        timeout_seconds=15.0,
    ),
    "test_m20": CallerPolicy(
        caller_id="test_m20",
        description="M20 deterministic tests",
        product_area="test",
        certification=CallerCertification.TEST,
        max_input_chars=8000,
        max_output_tokens=512,
        timeout_seconds=30.0,
    ),
    "test_m21_0": CallerPolicy(
        caller_id="test_m21_0",
        description="M21.0 kill-switch tests",
        product_area="test",
        certification=CallerCertification.TEST,
        max_input_chars=2000,
        max_output_tokens=128,
        timeout_seconds=15.0,
    ),
    # Transitional unlabeled caller — TEST-only under M21.2.
    # Production / staging posture must fail closed (see contract + provider_decision).
    "unknown": CallerPolicy(
        caller_id="unknown",
        description="Transitional unlabeled caller — test environments only",
        product_area="test",
        certification=CallerCertification.TEST,
        max_input_chars=16000,
        max_output_tokens=1024,
        timeout_seconds=60.0,
        allowed_capabilities=frozenset(
            {"screening", "standard", "fast", "private", "reasoning", "long", "multimodal"}
        ),
        notes=(
            "M21.2: restricted to pytest/test; denied when SAATHI_PRODUCTION_POSTURE=1 "
            "or SAATHI_ENV=production|staging. Expiry: remove in M21.3"
        ),
    ),
    "chat_engine": CallerPolicy(
        caller_id="chat_engine",
        description="Chat default residual path (legacy llm.generate)",
        product_area="chat",
        certification=CallerCertification.LEGACY,
        local_only=False,  # historical cloud-ok via router
        cloud_allowed=True,  # legacy only — not governed path
        cloud_fallback_allowed=True,
        max_input_chars=32000,
        max_output_tokens=2048,
        timeout_seconds=120.0,
        legacy=True,
        notes="LEGACY_ALLOWED_TEMPORARILY until chat migration (target M21.x/M23)",
    ),
    "legacy_llm_generate": CallerPolicy(
        caller_id="legacy_llm_generate",
        description="saathi.llm.generate default execution path",
        product_area="llm",
        certification=CallerCertification.LEGACY,
        local_only=False,
        cloud_allowed=True,
        cloud_fallback_allowed=True,
        max_input_chars=32000,
        max_output_tokens=4096,
        timeout_seconds=120.0,
        legacy=True,
        notes="Canonical legacy execution; ModelRouter still selects",
    ),
    "fake_engine": CallerPolicy(
        caller_id="fake_engine",
        description="Fake/deterministic engine tests",
        product_area="test",
        certification=CallerCertification.TEST,
        max_input_chars=4000,
        max_output_tokens=256,
        timeout_seconds=10.0,
    ),
}

# Forbidden aliases never register as enabled governed callers
for _fid in PROMOTION_FORBIDDEN:
    _CALLER_POLICIES.setdefault(
        _fid,
        CallerPolicy(
            caller_id=_fid,
            description=f"Promotion-forbidden surface ({_fid})",
            product_area="security",
            certification=CallerCertification.FORBIDDEN,
            enabled=False,
            local_only=True,
            cloud_allowed=False,
            notes="Must never be auto-promoted to governed inference",
        ),
    )


def get_caller_policy(caller_id: str) -> Optional[CallerPolicy]:
    cid = (caller_id or "").strip()
    if not cid:
        return None
    return _CALLER_POLICIES.get(cid)


def require_caller_policy(caller_id: str) -> CallerPolicy:
    pol = get_caller_policy(caller_id)
    if pol is None:
        return CallerPolicy(
            caller_id=caller_id or "unknown",
            description="Unknown caller",
            product_area="unknown",
            certification=CallerCertification.UNKNOWN,
            enabled=False,
            notes="Fail closed on governed paths",
        )
    return pol


def is_known_caller(caller_id: str) -> bool:
    return (caller_id or "").strip() in _CALLER_POLICIES


def is_governed_callable(caller_id: str) -> bool:
    """True if caller may use governed InferenceRequest path."""
    pol = get_caller_policy(caller_id)
    if pol is None or not pol.enabled:
        return False
    if pol.certification is CallerCertification.FORBIDDEN:
        return False
    if pol.certification is CallerCertification.UNKNOWN:
        return False
    # Legacy callers are not auto-governed
    if pol.legacy and pol.certification is CallerCertification.LEGACY:
        return False
    return True


def caller_policy_snapshot() -> dict[str, Any]:
    return {
        "schema": "m21.1.caller_policy.v1",
        "milestone": "M21.1",
        "selected_m20_3": sorted(SELECTED_CALLERS),
        "callers": {k: v.to_dict() for k, v in sorted(_CALLER_POLICIES.items())},
        "count": len(_CALLER_POLICIES),
    }


def list_caller_ids() -> list[str]:
    return sorted(_CALLER_POLICIES.keys())
