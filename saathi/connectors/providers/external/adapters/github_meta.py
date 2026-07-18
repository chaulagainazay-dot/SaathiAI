"""M33 — GitHub Meta external provider adapter (read-only pilot).

Conforms to the M32 ``ProviderAdapter`` contract so it composes with the existing
governed runtime, eligibility, verification, health, and quarantine layers. Its
``execute`` drives the canonical external transport boundary, builds a read-only
request envelope, normalizes and schema-checks the response, and maps every
outcome into a provider-neutral ``ProviderAdapterResult``. It never determines
authority, activates rollout, fetches credentials, or mutates certification.

The transport (DNS resolver / TLS prober / byte sender) is injected, so offline
deterministic tests never touch the network.
"""
from __future__ import annotations

from typing import Any, Optional

from saathi.connectors.providers.config import ProviderConfig
from saathi.connectors.providers.contract import ProviderAdapter
from saathi.connectors.providers.errors import classify_exception, classify_status, retry_category_for
from saathi.connectors.providers.external.models import (
    ExternalFailure,
    ExternalProviderProfile,
)
from saathi.connectors.providers.external.profiles import GITHUB_META, GITHUB_META_SCHEMA
from saathi.connectors.providers.external.request_envelope import (
    RequestEnvelopeError,
    build_request_envelope,
)
from saathi.connectors.providers.external.response_envelope import (
    ResponseEnvelopeError,
    build_response_envelope,
)
from saathi.connectors.providers.external.schema import SchemaContract, validate_schema
from saathi.connectors.providers.external.tls_policy import TlsPolicy
from saathi.connectors.providers.external.transport import ExternalTransport
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
from saathi.connectors.providers.ratelimit import parse_rate_limit, safe_rate_limit_evidence
from saathi.credentials.leakscan import is_clean

# External failure → (ProviderErrorCode, RetryCategory, ProviderStatus)
_FAILURE_MAP: dict[str, tuple[ProviderErrorCode, RetryCategory, str]] = {
    ExternalFailure.DNS_RESOLUTION_FAILED.value: (ProviderErrorCode.CONNECTION_FAILED, RetryCategory.SAFE_RETRY, ProviderStatus.ERROR.value),
    ExternalFailure.DNS_POLICY_BLOCKED.value: (ProviderErrorCode.POLICY_BLOCKED, RetryCategory.POLICY_BLOCKED, ProviderStatus.DENIED.value),
    ExternalFailure.SSRF_POLICY_BLOCKED.value: (ProviderErrorCode.POLICY_BLOCKED, RetryCategory.POLICY_BLOCKED, ProviderStatus.DENIED.value),
    ExternalFailure.ENDPOINT_POLICY_BLOCKED.value: (ProviderErrorCode.POLICY_BLOCKED, RetryCategory.POLICY_BLOCKED, ProviderStatus.DENIED.value),
    ExternalFailure.TLS_CERTIFICATE_FAILED.value: (ProviderErrorCode.POLICY_BLOCKED, RetryCategory.NO_RETRY, ProviderStatus.DENIED.value),
    ExternalFailure.TLS_HOSTNAME_FAILED.value: (ProviderErrorCode.POLICY_BLOCKED, RetryCategory.NO_RETRY, ProviderStatus.DENIED.value),
    ExternalFailure.TLS_POLICY_BLOCKED.value: (ProviderErrorCode.POLICY_BLOCKED, RetryCategory.NO_RETRY, ProviderStatus.DENIED.value),
    ExternalFailure.REDIRECT_POLICY_BLOCKED.value: (ProviderErrorCode.POLICY_BLOCKED, RetryCategory.NO_RETRY, ProviderStatus.DENIED.value),
    ExternalFailure.PROXY_POLICY_BLOCKED.value: (ProviderErrorCode.POLICY_BLOCKED, RetryCategory.NO_RETRY, ProviderStatus.DENIED.value),
    ExternalFailure.NETWORK_TIMEOUT.value: (ProviderErrorCode.TIMEOUT, RetryCategory.SAFE_RETRY, ProviderStatus.TIMEOUT.value),
    ExternalFailure.CONNECTION_REFUSED.value: (ProviderErrorCode.CONNECTION_FAILED, RetryCategory.SAFE_RETRY, ProviderStatus.ERROR.value),
    ExternalFailure.CONNECTION_RESET.value: (ProviderErrorCode.CONNECTION_FAILED, RetryCategory.SAFE_RETRY, ProviderStatus.ERROR.value),
    ExternalFailure.RESPONSE_TOO_LARGE.value: (ProviderErrorCode.MALFORMED_RESPONSE, RetryCategory.NO_RETRY, ProviderStatus.ERROR.value),
    ExternalFailure.DECOMPRESSION_LIMIT_EXCEEDED.value: (ProviderErrorCode.MALFORMED_RESPONSE, RetryCategory.NO_RETRY, ProviderStatus.ERROR.value),
    ExternalFailure.UNSUPPORTED_CONTENT_TYPE.value: (ProviderErrorCode.MALFORMED_RESPONSE, RetryCategory.NO_RETRY, ProviderStatus.ERROR.value),
    ExternalFailure.MALFORMED_ENCODING.value: (ProviderErrorCode.MALFORMED_RESPONSE, RetryCategory.NO_RETRY, ProviderStatus.ERROR.value),
    ExternalFailure.SCHEMA_INCOMPATIBLE.value: (ProviderErrorCode.MALFORMED_RESPONSE, RetryCategory.NO_RETRY, ProviderStatus.ERROR.value),
    ExternalFailure.PROVIDER_RATE_LIMITED.value: (ProviderErrorCode.RATE_LIMITED, RetryCategory.RATE_LIMITED, ProviderStatus.RATE_LIMITED.value),
    ExternalFailure.PROVIDER_UNAVAILABLE.value: (ProviderErrorCode.PROVIDER_UNAVAILABLE, RetryCategory.PROVIDER_UNAVAILABLE, ProviderStatus.ERROR.value),
    ExternalFailure.REQUEST_CONTRACT_VIOLATION.value: (ProviderErrorCode.INVALID_REQUEST, RetryCategory.NO_RETRY, ProviderStatus.ERROR.value),
    ExternalFailure.EXTERNAL_VERIFICATION_ABORTED.value: (ProviderErrorCode.POLICY_BLOCKED, RetryCategory.POLICY_BLOCKED, ProviderStatus.DENIED.value),
}


def _identity_for(profile: ExternalProviderProfile) -> ProviderIdentity:
    return ProviderIdentity(
        provider_id=profile.provider_id,
        provider_version="1.0.0",
        adapter_version=profile.adapter_version,
        connector_id=profile.connector_id,
        transport="http",
        base_endpoint_class=profile.endpoint_class,
        environment=profile.environment,
        auth_profile=profile.auth_profile,
        capabilities=tuple(profile.operation_set),
        side_effect_class=profile.side_effect_class,
        rate_limit_profile=profile.rate_limit_profile,
        data_classification=profile.data_classification,
        display_name=profile.provider_display_name,
    )


class GithubMetaAdapter(ProviderAdapter):
    adapter_version = "1.0.0"

    def __init__(
        self,
        *,
        profile: Optional[ExternalProviderProfile] = None,
        schema: Optional[SchemaContract] = None,
        transport: Optional[ExternalTransport] = None,
        tls_policy: Optional[TlsPolicy] = None,
        identity: Optional[ProviderIdentity] = None,
    ):
        self.profile = profile or GITHUB_META
        self.schema = schema or GITHUB_META_SCHEMA
        self.transport = transport  # injected; None disables live execution (offline-safe)
        self.tls_policy = tls_policy or TlsPolicy()
        self.identity = identity or _identity_for(self.profile)
        self._config: Optional[ProviderConfig] = None

    # ── contract ─────────────────────────────────────────────────────────────
    def prepare(self, config: ProviderConfig) -> None:
        self._config = config

    def validate_request(self, ctx: ProviderExecutionContext) -> None:
        if ctx.operation not in self.profile.operation_set:
            raise RequestEnvelopeError(ExternalFailure.REQUEST_CONTRACT_VIOLATION, f"unsupported_operation:{ctx.operation}")
        # build to validate injection/method/path/query — raises on any violation
        build_request_envelope(
            self.profile,
            request_id=ctx.request_id or "validate",
            idempotency_key=ctx.idempotency_key,
            query=(ctx.payload or {}).get("query") if isinstance(ctx.payload, dict) else None,
        )

    def execute(self, ctx: ProviderExecutionContext) -> ProviderAdapterResult:
        base = {
            "provider_id": self.profile.provider_id,
            "operation": ctx.operation,
            "side_effect_class": self.profile.side_effect_class,
            "mode": ctx.mode,
            "authoritative": False,
        }
        if self.transport is None:
            return self._err(ExternalFailure.EXTERNAL_VERIFICATION_ABORTED.value, base, ["no_transport_offline_safe"])

        try:
            envelope = build_request_envelope(
                self.profile, request_id=ctx.request_id or "exec",
                idempotency_key=ctx.idempotency_key,
                query=(ctx.payload or {}).get("query") if isinstance(ctx.payload, dict) else None,
            )
        except RequestEnvelopeError as e:
            return self._err(e.code.value, base)

        tr = self.transport.send(self.profile, envelope, tls_policy=self.tls_policy)
        rl = parse_rate_limit(tr.headers)
        base["rate_limit"] = safe_rate_limit_evidence(rl)
        base["latency_ms"] = tr.latency_ms

        # transport-level policy/network failure
        if tr.failure_code:
            code, cat, status = _FAILURE_MAP.get(
                tr.failure_code,
                (ProviderErrorCode.UNKNOWN_PROVIDER_ERROR, RetryCategory.NO_RETRY, ProviderStatus.ERROR.value),
            )
            r = self._err(tr.failure_code, base)
            r.error_code = code.value
            r.retryability = cat.value
            r.status = status
            r.safe_metadata = {"transport": tr.safe_summary()}
            return r

        # HTTP-status handling
        if tr.ok:
            try:
                resp = build_response_envelope(
                    tr.raw_for_response(), response_limit=int(self.profile.response_limit_bytes),
                    method=envelope.method,
                )
            except ResponseEnvelopeError as e:
                r = self._err(e.code.value, base)
                m = _FAILURE_MAP.get(e.code.value)
                if m:
                    r.error_code, cat, r.status = m[0].value, m[1], m[2]
                    r.retryability = cat.value
                return r

            # Schema is validated against the parsed body (field names/types only —
            # public flags such as verifiable_password_authentication are not
            # dropped by the secret-key stripper here).
            schema_res = validate_schema(resp.raw_parsed, self.schema)
            if not schema_res.compatible:
                r = self._err(ExternalFailure.SCHEMA_INCOMPATIBLE.value, base, [f"schema:{schema_res.overall}"])
                r.error_code = ProviderErrorCode.MALFORMED_RESPONSE.value
                r.retryability = RetryCategory.NO_RETRY.value
                r.safe_metadata = {"schema_result": schema_res.to_dict()}
                return r

            # normalized_data: project the parsed body onto the DECLARED schema
            # fields only (whitelist). This keeps public declared flags while
            # dropping any unexpected/injected keys (e.g. stack traces). A final
            # leak check falls back to the secret-stripped copy just in case.
            declared = {f.name for f in self.schema.fields}
            projected = {k: v for k, v in resp.raw_parsed.items() if k in declared}
            normalized = projected if is_clean(projected) else resp.normalized_data

            return ProviderAdapterResult(
                status=ProviderStatus.SUCCESS.value,
                normalized_data=normalized,
                provider_request_id_safe=resp.provider_request_id_safe,
                retryability=RetryCategory.NO_RETRY.value,
                limitations=["external_read_only", "single_endpoint_only", "non_production"],
                safe_metadata={
                    "status_code": resp.status_code,
                    "content_type": resp.content_type,
                    "schema_result": schema_res.to_dict(),
                    "tls": tr.tls,
                    "redirect_chain": resp.redirect_chain_safe,
                    "transport_classification": resp.transport_classification,
                },
                **base,
            )

        # non-2xx, non-policy (e.g. 429/5xx/4xx)
        status_code = tr.status_code or 0
        code = classify_status(status_code) if status_code else ProviderErrorCode.PROVIDER_UNAVAILABLE
        cat = retry_category_for(code)
        status = ProviderStatus.RATE_LIMITED.value if code == ProviderErrorCode.RATE_LIMITED else ProviderStatus.ERROR.value
        r = self._err(f"http_{status_code}", base)
        r.error_code = code.value
        r.retryability = cat.value
        r.status = status
        r.safe_metadata = {"status_code": status_code, "transport": tr.safe_summary()}
        return r

    def normalize_response(self, raw: Any) -> dict[str, Any]:
        resp = build_response_envelope(
            raw if isinstance(raw, dict) else {"body_bytes": raw, "status_code": 200, "content_type": "application/json"},
            response_limit=int(self.profile.response_limit_bytes),
        )
        return resp.normalized_data

    def classify_error(self, exc: BaseException) -> str:
        code = getattr(exc, "code", None)
        if isinstance(code, ExternalFailure):
            m = _FAILURE_MAP.get(code.value)
            if m:
                return m[0].value
        return classify_exception(exc).value

    def health(self) -> str:
        # local probe only — bound config + profile present; no network
        return ProviderHealthState.HEALTHY.value if self.profile else ProviderHealthState.UNAVAILABLE.value

    def capabilities(self) -> tuple[str, ...]:
        return tuple(self.profile.operation_set)

    def close(self) -> None:
        return None

    # ── helpers ──────────────────────────────────────────────────────────────
    def _err(self, safe_message: str, base: dict[str, Any], limitations: Optional[list[str]] = None) -> ProviderAdapterResult:
        return ProviderAdapterResult(
            status=ProviderStatus.ERROR.value,
            normalized_data={},
            error_code=ProviderErrorCode.INTERNAL_ADAPTER_ERROR.value,
            safe_message=safe_message[:160],
            retryability=RetryCategory.NO_RETRY.value,
            limitations=list(limitations or []),
            **base,
        )
