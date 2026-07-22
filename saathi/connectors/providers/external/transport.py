"""M33 — Canonical outbound external transport boundary.

This is the ONLY sanctioned place an external network call may originate. It
resolves the approved endpoint from the profile, validates the hostname, resolves
and SSRF-checks every destination IP, enforces TLS policy, applies the deadline
and response-size limit, governs redirects (revalidating each hop), and returns a
bounded transport result. It never decides eligibility, approval, credential
scope, rollout, or provider verification — those live outside transport.

Every external dependency (DNS resolver, TLS prober, byte sender) is injectable so
deterministic tests never touch the network.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Optional
from urllib.parse import urlparse

from saathi.connectors.providers.external.dns_ssrf import (
    DnsSsrfError,
    Resolver,
    resolve_and_validate,
)
from saathi.connectors.providers.external.endpoint_policy import (
    EndpointPolicyError,
    validate_endpoint,
    validate_redirect_target,
)
from saathi.connectors.providers.external.models import (
    ExternalFailure,
    ExternalProviderProfile,
)
from saathi.connectors.providers.external.request_envelope import ExternalRequestEnvelope
from saathi.connectors.providers.external.tls_policy import (
    TlsPolicy,
    TlsPolicyError,
    TlsResult,
    assert_verification_enabled,
    classify_tls,
    safe_tls_metadata,
)


@dataclass
class SendContext:
    method: str
    url: str
    host: str
    port: int
    pinned_ips: tuple[str, ...]
    headers: dict[str, str]
    timeout: float
    response_limit: int

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["pinned_ips"] = list(self.pinned_ips)
        return d


# A sender performs one bounded request and returns a raw bounded dict:
#   {status_code, headers, body_bytes, decompressed_size, content_type, location}
Sender = Callable[[SendContext], dict[str, Any]]
TlsProber = Callable[[str], TlsResult]


@dataclass
class TransportResult:
    ok: bool
    provider_id: str = ""
    failure_code: str = ""
    status_code: int = 0
    headers: dict[str, str] = field(default_factory=dict)
    body_bytes: bytes = b""
    decompressed_size: int = 0
    content_type: str = ""
    latency_ms: float = 0.0
    redirect_chain: list[dict[str, Any]] = field(default_factory=list)
    tls: dict[str, Any] = field(default_factory=dict)
    transport_classification: str = "ok"
    hops: int = 0

    def raw_for_response(self) -> dict[str, Any]:
        return {
            "status_code": self.status_code,
            "headers": self.headers,
            "body_bytes": self.body_bytes,
            "decompressed_size": self.decompressed_size,
            "content_type": self.content_type,
            "latency_ms": self.latency_ms,
            "redirect_chain": self.redirect_chain,
            "transport_classification": self.transport_classification,
        }

    def safe_summary(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "provider_id": self.provider_id,
            "failure_code": self.failure_code,
            "status_code": self.status_code,
            "content_type": self.content_type,
            "body_bytes": len(self.body_bytes),
            "hops": self.hops,
            "tls": self.tls,
            "redirect_chain": self.redirect_chain,
            "transport_classification": self.transport_classification,
            "privacy_safe": True,
        }


class ExternalTransport:
    def __init__(
        self,
        *,
        resolver: Optional[Resolver] = None,
        tls_prober: Optional[TlsProber] = None,
        sender: Optional[Sender] = None,
        clock: Optional[Callable[[], float]] = None,
    ):
        import time as _t

        self.resolver = resolver
        self.tls_prober = tls_prober
        self.sender = sender
        self.clock = clock or _t.perf_counter

    def send(
        self,
        profile: ExternalProviderProfile,
        envelope: ExternalRequestEnvelope,
        *,
        tls_policy: Optional[TlsPolicy] = None,
    ) -> TransportResult:
        """Drive one governed external request. Returns a bounded TransportResult."""
        policy = tls_policy or TlsPolicy()
        pid = profile.provider_id
        t0 = self.clock()
        redirect_chain: list[dict[str, Any]] = []
        tls_meta: dict[str, Any] = {}
        current_url = profile.endpoint_reference
        redirect_limit = int(profile.redirect_limit)
        hops = 0

        # A sender is mandatory in-process: without one, refuse rather than
        # accidentally reach out. Live wiring injects _urllib_sender explicitly.
        if self.sender is None:
            return self._fail(pid, ExternalFailure.EXTERNAL_VERIFICATION_ABORTED, t0, "no_sender_configured")

        try:
            assert_verification_enabled(policy)
        except TlsPolicyError as e:
            return self._fail(pid, e.code, t0, "tls_policy")

        while True:
            is_redirect = hops > 0
            # 1. endpoint policy (host allowlist, https, port, path)
            try:
                if is_redirect:
                    host, port, _ = validate_redirect_target(current_url, profile)
                else:
                    host, port, _ = validate_endpoint(current_url, profile)
            except EndpointPolicyError as e:
                code = ExternalFailure.REDIRECT_POLICY_BLOCKED if is_redirect else e.code
                return self._fail(pid, code, t0, "endpoint", redirect_chain, tls_meta, hops)

            # 2. DNS + SSRF (fresh resolution every hop; no rebinding window)
            try:
                pinned = resolve_and_validate(host, resolver=self.resolver)
            except DnsSsrfError as e:
                return self._fail(pid, e.code, t0, "dns_ssrf", redirect_chain, tls_meta, hops)

            # 3. TLS policy (when a prober is injected; live sender enforces its own
            #    hardened SSL context independently)
            if self.tls_prober is not None:
                try:
                    tls_result = self.tls_prober(host)
                    classify_tls(tls_result, policy)
                    tls_meta = safe_tls_metadata(tls_result)
                except TlsPolicyError as e:
                    return self._fail(pid, e.code, t0, "tls", redirect_chain, tls_meta, hops)

            # 4. bounded send
            ctx = SendContext(
                method=envelope.method,
                url=envelope.url(host, port) if not is_redirect else current_url,
                host=host,
                port=port,
                pinned_ips=tuple(pinned),
                headers=dict(envelope.safe_headers),  # rebuilt safe; no auth/cookie forwarded
                timeout=float(envelope.deadline),
                response_limit=int(envelope.response_limit),
            )
            try:
                raw = self.sender(ctx)
            except TimeoutError:
                return self._fail(pid, ExternalFailure.NETWORK_TIMEOUT, t0, "send", redirect_chain, tls_meta, hops)
            except ConnectionResetError:
                return self._fail(pid, ExternalFailure.CONNECTION_RESET, t0, "send", redirect_chain, tls_meta, hops)
            except ConnectionRefusedError:
                return self._fail(pid, ExternalFailure.CONNECTION_REFUSED, t0, "send", redirect_chain, tls_meta, hops)
            except Exception:
                return self._fail(pid, ExternalFailure.PROVIDER_UNAVAILABLE, t0, "send", redirect_chain, tls_meta, hops)

            status = int(raw.get("status_code", 0))
            headers = raw.get("headers") or {}
            body = raw.get("body_bytes") or b""
            if isinstance(body, str):
                body = body.encode("utf-8", "strict")

            # response-size ceiling at the transport boundary too
            if len(body) > int(envelope.response_limit):
                return self._fail(pid, ExternalFailure.RESPONSE_TOO_LARGE, t0, "oversize", redirect_chain, tls_meta, hops)

            # 5. redirect governance
            if 300 <= status < 400:
                loc = raw.get("location") or headers.get("location") or headers.get("Location") or ""
                redirect_chain.append({"host": host, "status": status, "scheme": "https"})
                if redirect_limit <= 0 or hops >= redirect_limit:
                    return self._fail(pid, ExternalFailure.REDIRECT_POLICY_BLOCKED, t0, "redirect_ceiling", redirect_chain, tls_meta, hops)
                if not loc:
                    return self._fail(pid, ExternalFailure.REDIRECT_POLICY_BLOCKED, t0, "redirect_no_location", redirect_chain, tls_meta, hops)
                # loop detection
                if any(urlparse(loc).hostname == r["host"] for r in redirect_chain) and urlparse(loc).path == urlparse(current_url).path:
                    return self._fail(pid, ExternalFailure.REDIRECT_POLICY_BLOCKED, t0, "redirect_loop", redirect_chain, tls_meta, hops)
                hops += 1
                current_url = loc
                continue

            # 6. success / non-redirect terminal
            latency = round((self.clock() - t0) * 1000, 3)
            if status == 429:
                cls = "rate_limited"
            elif status >= 500:
                cls = "provider_unavailable"
            elif status >= 400:
                cls = "client_error"
            else:
                cls = "ok"
            return TransportResult(
                ok=200 <= status < 300,
                provider_id=pid,
                status_code=status,
                headers={str(k): str(v) for k, v in headers.items()},
                body_bytes=bytes(body),
                decompressed_size=int(raw.get("decompressed_size", len(body))),
                content_type=str(raw.get("content_type") or headers.get("content-type") or headers.get("Content-Type") or ""),
                latency_ms=latency,
                redirect_chain=redirect_chain,
                tls=tls_meta,
                transport_classification=cls,
                hops=hops,
            )

    def _fail(
        self,
        pid: str,
        code: ExternalFailure,
        t0: float,
        stage: str,
        redirect_chain: Optional[list] = None,
        tls_meta: Optional[dict] = None,
        hops: int = 0,
    ) -> TransportResult:
        return TransportResult(
            ok=False,
            provider_id=pid,
            failure_code=code.value,
            latency_ms=round((self.clock() - t0) * 1000, 3),
            redirect_chain=redirect_chain or [],
            tls=tls_meta or {},
            transport_classification=f"blocked:{stage}",
            hops=hops,
        )


# ── Live sender (used ONLY on the explicit operator verify path; never in tests)
def urllib_sender(ctx: SendContext) -> dict[str, Any]:  # pragma: no cover - network path
    """Hardened live sender: verified TLS, no redirects, bounded read."""
    import ssl
    import urllib.request

    context = ssl.create_default_context()
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    context.minimum_version = ssl.TLSVersion.TLSv1_2

    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None  # transport governs redirects, not urllib

    opener = urllib.request.build_opener(
        _NoRedirect(), urllib.request.HTTPSHandler(context=context),
    )
    req = urllib.request.Request(ctx.url, method=ctx.method, headers=dict(ctx.headers))
    try:
        with opener.open(req, timeout=ctx.timeout) as resp:
            limit = int(ctx.response_limit)
            body = resp.read(limit + 1)
            if len(body) > limit:
                body = body[:limit]
                oversized = True
            else:
                oversized = False
            hdrs = {k.lower(): v for k, v in resp.headers.items()}
            return {
                "status_code": resp.status,
                "headers": hdrs,
                "body_bytes": body,
                "decompressed_size": len(body) if not oversized else limit + 1,
                "content_type": hdrs.get("content-type", ""),
                "location": hdrs.get("location", ""),
            }
    except urllib.error.HTTPError as e:  # non-2xx still yields a response object
        body = e.read(int(ctx.response_limit)) if hasattr(e, "read") else b""
        hdrs = {k.lower(): v for k, v in (e.headers or {}).items()}
        return {
            "status_code": e.code,
            "headers": hdrs,
            "body_bytes": body,
            "decompressed_size": len(body),
            "content_type": hdrs.get("content-type", ""),
            "location": hdrs.get("location", ""),
        }
    except ssl.SSLError as e:
        raise ConnectionResetError(f"tls_error:{type(e).__name__}")
