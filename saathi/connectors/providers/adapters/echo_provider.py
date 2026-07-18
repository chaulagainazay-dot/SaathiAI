"""M32 — Echo provider adapter (the bounded, governed pilot).

Local deterministic pilot bound to connector ``gov.http`` and provider identity
``saathi.echo.v1``. READ_ONLY only. It performs ONE provider attempt per call:
transport-level failures propagate as exceptions (the runtime classifies and
decides retries); HTTP-status conditions are normalized into a
``ProviderAdapterResult`` carrying a canonical error code + retry category.

The adapter never determines authority, activates rollout, fetches credentials,
or mutates certification/verification.
"""
from __future__ import annotations

import time
from typing import Any, Optional

from saathi.connectors.providers.config import ProviderConfig
from saathi.connectors.providers.contract import ProviderAdapter
from saathi.connectors.providers.errors import (
    ProviderError,
    classify_exception,
    classify_status,
    retry_category_for,
    safe_error_message,
)
from saathi.connectors.providers.models import (
    ProviderAdapterResult,
    ProviderErrorCode,
    ProviderExecutionContext,
    ProviderHealthState,
    ProviderIdentity,
    ProviderSideEffectClass,
    ProviderStatus,
    RetryCategory,
)
from saathi.connectors.providers.normalization import (
    normalize_headers,
    normalize_request,
    normalize_response,
)
from saathi.connectors.providers.ratelimit import parse_rate_limit, safe_rate_limit_evidence
from saathi.connectors.testing.provider_simulator import ProviderSimulator


class EchoProviderAdapter(ProviderAdapter):
    adapter_version = "1.0.0"

    def __init__(
        self,
        *,
        simulator: Optional[ProviderSimulator] = None,
        identity: Optional[ProviderIdentity] = None,
    ):
        self.simulator = simulator or ProviderSimulator()
        self.identity = identity or ProviderIdentity(
            provider_id="saathi.echo.v1",
            connector_id="gov.http",
            transport="local_simulator",
            base_endpoint_class="inprocess",
            environment="test",
            capabilities=("echo", "read_item", "list_items", "health"),
            side_effect_class=ProviderSideEffectClass.READ_ONLY.value,
        )
        self._config: Optional[ProviderConfig] = None

    # ── contract ─────────────────────────────────────────────────────────────
    def prepare(self, config: ProviderConfig) -> None:
        self._config = config

    def validate_request(self, ctx: ProviderExecutionContext) -> None:
        caps = set(self.identity.capabilities)
        if ctx.operation not in caps:
            raise ProviderError(ProviderErrorCode.INVALID_REQUEST, f"unsupported_operation:{ctx.operation}")
        allowed_ops = self._config.allowed_operations if self._config else tuple(self.identity.capabilities)
        req_limit = self._config.request_size_limit if self._config else 64 * 1024
        # normalize_request raises on any injection/oversize
        normalize_request(
            ctx.payload, operation=ctx.operation,
            allowed_operations=tuple(allowed_ops), request_size_limit=req_limit,
        )

    def execute(self, ctx: ProviderExecutionContext) -> ProviderAdapterResult:
        t0 = time.perf_counter()
        resp_limit = self._config.response_size_limit if self._config else 256 * 1024
        max_retry_after = self._config.rate_limit_policy.max_retry_after_seconds if self._config else 10.0
        scenario = str((ctx.safe_metadata or {}).get("scenario") or "success")

        raw = self.simulator.execute(scenario, {
            "request_id": ctx.request_id,
            "idempotency_key": ctx.idempotency_key,
            "payload": ctx.payload,
            "operation": ctx.operation,
        })
        status_code = int(raw.get("status_code", 0))
        headers = normalize_headers(raw.get("headers"))
        rl = parse_rate_limit(raw.get("headers"), now=t0, max_retry_after=max_retry_after)

        latency = round((time.perf_counter() - t0) * 1000, 3)
        base_kwargs: dict[str, Any] = {
            "provider_id": self.identity.provider_id,
            "operation": ctx.operation,
            "provider_request_id_safe": str(headers.get("x-request-id", ""))[:64],
            "rate_limit": safe_rate_limit_evidence(rl),
            "latency_ms": latency,
            "side_effect_class": self.identity.side_effect_class,
            "mode": ctx.mode,
            "authoritative": False,
        }

        if 200 <= status_code < 300:
            normalized = self.normalize_response(raw)  # raises on malformed/oversized
            partial = status_code == 206 or bool(normalized.get("partial"))
            return ProviderAdapterResult(
                status=ProviderStatus.PARTIAL.value if partial else ProviderStatus.SUCCESS.value,
                normalized_data=normalized,
                safe_metadata={"status_code": status_code, "headers": headers},
                retryability=RetryCategory.NO_RETRY.value,
                limitations=["partial_success"] if partial else [],
                error_code=ProviderErrorCode.PARTIAL_SUCCESS.value if partial else "",
                **base_kwargs,
            )

        # non-2xx → canonical error result
        code = classify_status(status_code)
        cat = retry_category_for(code)
        status = ProviderStatus.RATE_LIMITED.value if code == ProviderErrorCode.RATE_LIMITED else ProviderStatus.ERROR.value
        return ProviderAdapterResult(
            status=status,
            normalized_data={},
            safe_metadata={"status_code": status_code, "headers": headers},
            retryability=cat.value,
            error_code=code.value,
            safe_message=safe_error_message(code, str(raw.get("body"))[:80]),
            **base_kwargs,
        )

    def normalize_response(self, raw: Any) -> dict[str, Any]:
        resp_limit = self._config.response_size_limit if self._config else 256 * 1024
        body = raw.get("body") if isinstance(raw, dict) else raw
        return normalize_response(body, response_size_limit=resp_limit)

    def classify_error(self, exc: BaseException) -> str:
        return classify_exception(exc).value

    def health(self) -> str:
        try:
            _ = self.simulator.version
            return ProviderHealthState.HEALTHY.value
        except Exception:
            return ProviderHealthState.UNAVAILABLE.value

    def capabilities(self) -> tuple[str, ...]:
        return tuple(self.identity.capabilities)

    def close(self) -> None:
        return None
