"""Governed Moonshot Kimi transport.

This is a provider adapter only. Selection, retries, circuit state, cost
reservations, approvals, and audit remain owned by SaathiOS inference
governance and ModelRouter.
"""
from __future__ import annotations

import json
import os
from typing import Any, Callable, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from saathi.inference.adapters.openai_compat import OpenAICompatEngine
from saathi.inference.engine import CostEstimate, EngineCapabilities
from saathi.inference.errors import EngineError, EngineTimeoutError, EngineUnhealthyError

KIMI_OFFICIAL_BASE_URL = "https://api.moonshot.ai/v1"
KIMI_CODING_MODEL = "kimi-k2.7-code"
KIMI_CRITICAL_MODEL = "kimi-k3"

# Official Kimi API prices verified 2026-07-31, USD / 1M tokens.
KIMI_PRICING = {
    KIMI_CODING_MODEL: {"cache_hit_input": 0.19, "input": 0.95, "output": 4.00},
    KIMI_CRITICAL_MODEL: {"cache_hit_input": 0.30, "input": 3.00, "output": 15.00},
}


def validate_kimi_base_url(base_url: str) -> tuple[bool, str]:
    """Allow only Moonshot's official global HTTPS API origin."""
    try:
        parsed = urlparse((base_url or "").strip())
    except Exception:
        return False, "invalid_url"
    if parsed.scheme != "https":
        return False, "https_required"
    if parsed.username or parsed.password:
        return False, "userinfo_forbidden"
    if (parsed.hostname or "").lower() != "api.moonshot.ai":
        return False, "host_not_official"
    if parsed.port not in (None, 443):
        return False, "port_not_allowed"
    if parsed.path.rstrip("/") not in ("", "/v1"):
        return False, "path_not_v1"
    return True, "ok"


class KimiEngine(OpenAICompatEngine):
    """Kimi OpenAI-compatible adapter, disabled until governance selects it."""

    engine_id = "kimi"
    is_cloud = True
    governance_authority = "durable_governance_store"

    def __init__(
        self,
        base_url: Optional[str] = None,
        *,
        api_key: Optional[str] = None,
        default_model: Optional[str] = None,
        transport: Optional[Callable[..., Any]] = None,
    ) -> None:
        base = (base_url or os.getenv("KIMI_BASE_URL") or KIMI_OFFICIAL_BASE_URL).rstrip("/")
        ok, reason = validate_kimi_base_url(base)
        if not ok:
            raise EngineError(f"kimi base_url rejected: {reason}")
        key = api_key if api_key is not None else os.getenv("KIMI_API_KEY", "")
        super().__init__(
            base_url=base,
            api_key=key,
            default_model=default_model
            or os.getenv("KIMI_DEFAULT_MODEL")
            or KIMI_CODING_MODEL,
            engine_id=self.engine_id,
            is_cloud=True,
            transport=transport,
            production_context=True,
            skip_url_validation=True,
        )

    def _request(self, method: str, path: str, body: Optional[dict] = None, *, timeout: float = 30.0) -> Any:
        ok, reason = validate_kimi_base_url(self.base_url)
        if not ok:
            raise EngineError(f"kimi base_url rejected: {reason}")
        if not self.api_key:
            raise EngineError("kimi credential reference is not configured")
        bounded_timeout = min(max(float(timeout), 1.0), 120.0)
        url = f"{self.base_url}{path}"
        if self._transport is not None:
            return self._transport(method, url, body=body, timeout=bounded_timeout)
        payload = json.dumps(body).encode("utf-8") if body is not None else None
        request = Request(
            url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method=method,
        )
        try:
            with urlopen(request, timeout=bounded_timeout) as response:  # nosec B310 — exact official host
                raw = response.read()
                return json.loads(raw.decode("utf-8")) if raw else {}
        except HTTPError as exc:
            raise EngineError(f"kimi HTTP {exc.code}: {exc.reason}") from exc
        except URLError as exc:
            raise EngineUnhealthyError("kimi endpoint unreachable") from exc
        except TimeoutError as exc:
            raise EngineTimeoutError("kimi request timeout") from exc

    async def estimate_cost(
        self,
        *,
        model: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
    ) -> CostEstimate:
        price = KIMI_PRICING.get(model)
        if not price:
            return CostEstimate(known=False, notes="unverified Kimi model pricing")
        amount = (
            (max(0, int(prompt_tokens)) * price["input"])
            + (max(0, int(completion_tokens)) * price["output"])
        ) / 1_000_000
        return CostEstimate(
            currency="USD",
            amount=amount,
            per_1k_input=price["input"] / 1000,
            per_1k_output=price["output"] / 1000,
            known=True,
            notes="official Kimi API price; conservative cache-miss input rate",
        )

    async def capabilities(self) -> EngineCapabilities:
        return EngineCapabilities(
            streaming=True,
            tool_calling=True,
            structured_output=True,
            vision=True,
            audio=False,
            local=False,
            notes="Kimi remote API; governed cloud use only",
        )
