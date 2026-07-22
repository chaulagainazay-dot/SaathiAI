# M34 — Live External Verification Plan

**Milestone:** M34 — Bounded Live Read-Only External Verification & Canary Readiness
**Branch:** `milestone/m7-security-engine`
**Builds on:** M33 (`ff319be`) — one official, credential-free, read-only external provider
**Provider / endpoint / operation (unchanged from M33):** `github_meta` — `GET https://api.github.com/meta` — `get_meta`
**Surface:** `saathi/connectors/providers/external/m34.py`
**Command version:** `m34.live_external_verify.v1`

---

## 1. Purpose

M33 delivered the offline, fixture-backed external provider adapter and proved every
governance control (DNS/SSRF, TLS, endpoint policy, request/response envelopes, schema,
leak scan) offline. **No live external call was ever made in M33.**

M34 adds a **bounded, operator-triggered, read-only live-verification harness** on top of
the M33 adapter. It is designed to be run once, by an operator, to confirm the provider
behaves on the real network exactly as the offline fixtures modeled — and to produce a
**reliability qualification** and **canary-readiness assessment** — **without activating any
rollout, without writes, without credentials, and without an account link.**

## 2. Scope (hard boundaries)

| Dimension | M34 value |
|-----------|-----------|
| Providers | exactly one — `github_meta` (M33-approved) |
| Endpoints | exactly one — `https://api.github.com/meta` |
| Operations | exactly one — `get_meta` (read-only `GET`) |
| Credentials | none — anonymous public metadata |
| Account link / OAuth | none |
| Writes | none — write methods blocked by profile + defence-in-depth |
| Live-call budget | **3**, retries included (hard max 5, minimum 1) |
| Rollout | connector / provider / inference all remain **OFF** |
| Canary / active providers | **0 / 0** |
| Trading Guardian | **UNCHANGED / UNENGAGED** |

Anything outside this table is explicitly **out of scope for M34** and recorded as an
unsupported scope in evidence (`writes`, `other_endpoints`, `authenticated_operations`,
`account_linked_operations`).

## 3. Pre-live gates (all must pass before any on-network call)

1. **Offline test gates** — the three focused M34 suites are green:
   - `tests/test_m34_live_external_security.py`
   - `tests/test_m34_live_external_runtime.py`
   - `tests/test_m34_reliability_and_readiness.py`
2. **Authorization** — all four operator acknowledgements present:
   `--ack-read-only --ack-network --ack-non-production --ack-call-budget`.
3. **Provider identity** — resolves to `github_meta` / `get_meta`; no fallback substitution.
4. **Not quarantined** — provider quarantine store reports clean.
5. **Read-only ceiling** — profile method is `GET`; write methods fail closed.
6. **Env opt-in** — `SAATHI_M34_LIVE_VERIFY_ENABLED=1` (never set in CI or the test suite).
7. **Budget bounds** — approved budget within `[1, 5]`; default `3`.

If any gate fails, the harness returns `aborted`/`blocked`, `live_call: false`,
`verification_state: UNVERIFIED`, and never touches the network.

## 4. Bounded live-call procedure (operator-only)

```
SAATHI_M34_LIVE_VERIFY_ENABLED=1 \
  python -m saathi.connectors.providers external-verify github_meta \
  --ack-read-only --ack-network --ack-non-production --ack-call-budget
```

- Each call runs through the full M32 runtime → M33 external adapter → hardened transport
  (DNS/SSRF revalidation, TLS verification, redirect limit 0, response-size ceiling 256 KiB).
- A **transient** failure (`NETWORK_TIMEOUT`, `CONNECTION_RESET`, …) may be retried **only if
  budget remains**; the retry **consumes budget**. A **security** or **schema** failure is
  terminal and never retried. Total on-network calls therefore never exceed the approved
  budget of 3.
- Every call is reduced to bounded, leak-scanned evidence: latency bucket, size bucket,
  schema-compatibility class, normalized-result fingerprint, rate-limit visibility. **No raw
  body and no raw headers are ever persisted.**

## 5. Qualification & readiness logic

- **Repeatability:** `STABLE_EXACT` / `EXPECTED_DYNAMIC_VARIATION` / `UNEXPECTED_VARIATION` /
  `NON_COMPARABLE` (dynamic fields such as timestamps are ignored).
- **Reliability:** requires ≥2 successful, schema-compatible calls →
  `QUALIFIED_WITH_LIMITATIONS`. Any security failure → `NOT_QUALIFIED_SECURITY_FAILURE`;
  schema failure → `NOT_QUALIFIED_SCHEMA_FAILURE`; only transient → `…TRANSIENT_FAILURE`.
- **Canary readiness (assessment only):** `CANARY_READY_WITH_LIMITATIONS` only when
  reliability qualified, external state fresh, provider healthy, not quarantined, leak scan
  clean, zero direct-network bypasses, zero external writes, and rollout OFF. **The
  assessment never activates a canary — it only reports readiness.**

## 6. Verification states

- Max state reachable in M34: `EXTERNAL_READ_ONLY_VERIFIED_WITH_LIMITATIONS`.
- On failure: `EXTERNAL_VERIFICATION_FAILED`.
- On any unmet precondition: `UNVERIFIED` (no state change persisted).

## 7. Pre-live evidence (this session)

The harness was exercised **offline against the committed sanitized `github_meta` fixture**
(fixture-backed simulation — no network) to validate the full path and produce the evidence
set under `docs/evidence/m34/`. The genuine on-network live call remains **operator-only and
NOT EXERCISED** in this session (`docs/evidence/m34/live_external_call_result.json`,
`on_network_live_call: false`, `call_count_on_network: 0`).

- **M34 fingerprint:** `5b29b329b8933865059a62e6f03a867ffada27f965bb438d8131728e236a800e`
- **Evidence generator:** `scripts/m34_generate_evidence.py` (deterministic, offline, leak-scanned)
