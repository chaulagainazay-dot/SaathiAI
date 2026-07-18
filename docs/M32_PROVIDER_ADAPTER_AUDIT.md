# M32 — Provider-Adapter Audit (evidence-first intake)

Status: intake complete, implementation authorized (M32 only).
Starting HEAD: `206795f` on `milestone/m7-security-engine` (divergence 0/0).
Pre-existing runtime noise `docs/evidence/m27/` observed untracked and left untouched.

## 1. Scope of the audit

M32 builds **one bounded, governed provider-adapter pilot** and proves the full
governed path (intent → manifest/registry → connector certification → provider
config → account/credential readiness → policy → approval → ExecutionGateway →
connector runtime → provider adapter → normalized result → redaction → evidence
→ incident/health) **without bypassing any M27–M31 control**. Provider operates
in `OFF` or `SHADOW` only. No CANARY, no ACTIVE, no real credentials/accounts,
no writes, no financial/trading providers.

## 2. Existing provider-adapter / direct-transport code

| Path | Nature | Reuse in M32 |
|------|--------|--------------|
| `saathi/connectors/gov/adapters/http.py` | M27 governed HTTP adapter; **injectable `TransportFn`**, strips auth/cookie headers, `redact_payload`, bounded timeout + retry ceiling. | Pattern reference for bounded, injectable, redacted execution. The M32 provider adapter sits **above** this boundary (provider-neutral contract), never below it. |
| `saathi/connectors/gov/adapters/local_tool.py` | Allowlisted local commands, `shell=False`. | Confirms fail-closed allowlist pattern. |
| `saathi/connectors/gov/adapters/{mcp,browser}.py` | Governed MCP / browser adapters. | Out of scope; no new runtime. |
| `saathi/connectors/adapters/telegram.py` | **Legacy** connector using `httpx` directly. | Out of M32 scope; not a gov-runtime path. Flagged as pre-existing, not a provider-adapter bypass introduced by M32. |
| `saathi/server.py`, `health.py`, `pielts.py`, `autopost.py`, `analytics.py` | App-level `httpx`/`urllib` (health probes, LLM calls). | App plane, not connector-governed provider calls. Out of scope. |

No `saathi/connectors/providers/` package exists. No `tests/test_m32_*` exists.
M32 is a clean additive layer.

## 3. Reusable canonical systems (must reuse — do not recreate)

| Concern | Canonical source | M32 relationship |
|---------|------------------|------------------|
| Connector manifest / identity | `gov/models.py::ConnectorManifest`, `registry/builtins.py` | Provider identity **extends** manifest model; provider bound to a `connector_id`. |
| Connector registry / resolve | `gov/registry.py`, `registry/` | Reused; provider registry is a thin identity+alias map, not a second connector runtime. |
| Connector certification | `conformance/{fingerprint,eligibility,drift,store,models}.py` | Provider **verification** mirrors these patterns as an *additional* eligibility layer — never replaces M30. |
| Credential broker / account links | `saathi/credentials/*` (M31) | Reused where a provider needs credentials; pilot uses none. |
| Combined eligibility | `credentials/eligibility.py::combined_connector_eligibility` (reads M30 with `refresh_stale=False`) | M32 provider eligibility ANDs on top, also read-only. |
| Redaction | `gov/redaction.py::redact_payload` (+ mcp_governance) | Response/error/evidence redaction. |
| Side-effect classification | `gov/side_effects.py::SideEffectClass`, `PROHIBITED_OPERATIONS` | Provider side-effect ceiling = READ_ONLY/NONE; financial/trading fail closed. |
| Secret-leak detection | `credentials/leakscan.py` | Evidence guarded before every write. |
| Production certification | M25 runtime gate | Remains required, unchanged. |
| Bypass guard | `gov/bypass_guard.py` | Extended conceptually by a provider-bypass check that stays at 0. |

## 4. Timeout / retry / rate-limit / normalization / idempotency defaults found

- **Timeouts**: manifests carry `timeout_seconds` (10–30s); HTTP adapter enforces a single `timeout` on the injected transport. No connect/read split today.
- **Retry**: `max_retries` ceiling on manifest + adapter (`max_attempts = max_retries + 1`); no idempotency-aware classification.
- **Rate limits**: `rate_limit_per_minute` on manifest; server has ad-hoc `429` responses. No provider-side `Retry-After` parsing.
- **Normalization**: `ConnectorResult` is the canonical result; `redact_payload` strips forbidden keys. No provider-neutral request/response schema layer.
- **Idempotency**: `ConnectorRequest.idempotency_key` field exists; result carries `idempotency_state`. No request-fingerprint binding across provider/connector/account.

**Gap M32 fills**: a provider-neutral contract with connect+read+deadline
timeouts, deterministic retry taxonomy, `Retry-After`/rate-limit parsing with
clamping, request/response normalization schemas, and fingerprint-bound
idempotency — all above the existing adapter boundary.

## 5. Credential injection paths

M31 `injection.py` provides the narrow secret-injection boundary with mandatory
scrubbing. The M32 pilot is **credential-free** (`AuthMode.NONE`), so no secret
is injected; the contract still declares an `auth_profile` and `credential_lease`
slot so a future credentialed provider composes with M31 unchanged.

## 6. Evidence / redaction / health signals

- Evidence pattern: `conformance/evidence.py` + `credentials/evidence.py` use
  atomic writes + leak scan + repository-relative refs + schema version. M32
  reuses this exactly under `docs/evidence/m32/`.
- Health: connector health (`gov`), account/credential readiness (M31) are
  distinct. M32 adds a **separate** provider-health state machine.

## 7. Selected pilot provider

**Option A — local deterministic HTTP provider simulator** (`saathi.echo.v1`),
bound to connector `gov.http`. In-process, loopback-conceptual, never touches the
public internet. Chosen because repository evidence (injectable `TransportFn`,
deterministic sandbox harness in `conformance/sandbox.py`) strongly supports a
local deterministic provider, giving the strongest verification with zero live
dependency, zero credentials, zero accounts. See `M32_PROVIDER_SELECTION.md`.

Scenarios supported by the simulator: success, delayed, timeout, connection
failure, `429`+Retry-After, `500`, malformed JSON, oversized response, partial
success, duplicate request, idempotency replay, auth failure, authz failure,
scope failure, cancellation, shutdown-during-execution, forbidden sensitive
headers.

## 8. Explicit non-goals (deferred, not limitations-to-finish)

- No CANARY / ACTIVE provider rollout.
- No real OAuth, credential, or account link.
- No write / financial / trading / payment / social-write provider.
- No cloud inference; no Trading Guardian change.
- No new connector runtime, registry, broker, gateway, or certification authority.
- Optional public read-only verification (Capability 18) **not exercised**
  unless separately operator-authorized; deterministic milestone does not depend
  on it.

## 9. Bounded scope statement

M32 adds `saathi/connectors/providers/` (contract + governance + pilot adapter),
`saathi/connectors/testing/provider_simulator.py`, two test modules, evidence
under `docs/evidence/m32/`, and documentation. It mutates no M27–M31 runtime
semantics and no M30/M31 stores during eligibility reads.
