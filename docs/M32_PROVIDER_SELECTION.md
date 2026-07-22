# M32 — Provider Selection (documented before implementation)

## Decision

**Category: Option A — local deterministic HTTP provider simulator.**

Selected provider identity: **`saathi.echo.v1`** (adapter `EchoProviderAdapter`),
bound to canonical connector **`gov.http`**.

## Why Option A

The task's preferred order is A → B → C, and Option A is chosen unless repository
evidence strongly supports another. Repository evidence *supports* A:

- `gov/adapters/http.py` already uses an **injectable `TransportFn`**, proving the
  codebase's chosen validation strategy is deterministic in-process transports.
- `conformance/sandbox.py` ships `FakeHttpTransport` + `DeterministicClock` —
  deterministic simulation is the established M27–M30 verification idiom.
- A local simulator gives full control over success, timeout, `429`, `500`,
  malformed, oversized, partial, duplicate, auth/authz/scope failure,
  cancellation, and shutdown — the exact matrix M32 must verify.

Options B (credential-free public read-only API) and C (official provider
sandbox) were **rejected for the deterministic milestone**:

- B introduces external-uptime dependence and terms/robots risk; not needed for
  correctness and would make tests flaky. It remains available as optional
  Capability-18 verification only under separate operator authorization.
- C requires disposable sandbox credentials and secret handling outside Git;
  unnecessary for a read-only pilot and raises the secret-management surface.

## Safety properties

| Property | Value |
|----------|-------|
| Network access | none (in-process; never contacts public internet) |
| Credentials | none (`AuthMode.NONE`, no secret injected) |
| Accounts | none (no account link created) |
| Side-effect ceiling | `READ_ONLY` / `NONE` |
| Data classification | `PUBLIC` / `INTERNAL` only |
| Rollout | `OFF` default; `SHADOW` maximum |
| Verification ceiling | `SIMULATION_VERIFIED` (SHADOW over the simulator is still local → not live) |
| Trading Guardian | UNCHANGED / UNENGAGED |

## Rejected provider categories (hard fail-closed)

Gmail, Calendar, Slack, Facebook, Instagram, YouTube publish, LinkedIn publish,
banking, payments, exchange/brokerage, production GitHub mutation, real browser
login, social posting, trading, withdrawal, financial transfers. Any provider id
matching `trade|order|broker|exchange|wallet|withdraw|transfer|payment|bank|
financial|leverage|margin|futures|crypto execution` resolves to
`PROHIBITED / BLOCKED / OUT_OF_SCOPE` and cannot be selected or pass eligibility
(regression-tested).

## Public network usage in M32

**None.** No credentials or accounts were used. The optional public read-only
check was not exercised.
