# M30 — Connector Conformance Audit

**Milestone:** M30  
**Branch:** `milestone/m7-security-engine`  
**Starting HEAD:** `9c4770fc004e9e9185cc5a0e20e137d3b67970e2`  
**Date:** 2026-07-17  

## Preflight

| Check | Result |
|-------|--------|
| Branch | `milestone/m7-security-engine` |
| HEAD | `9c4770f` (matches expected) |
| Remote divergence | `0/0` |
| Tracked worktree | clean (no modified/staged tracked files) |
| Untracked | `docs/evidence/m27/connector_events.jsonl` (runtime artifact only; not touched) |
| `production_certified` | `true` |
| Connector rollout | OFF (M29 default) |
| Inference rollout | OFF |
| Connector bypasses | 0 |
| Cloud fallback | disabled |
| Trading Guardian | UNCHANGED / UNENGAGED |

**Decision:** Continue. Untracked m27 event log is prior runtime residue, not active WIP.

---

## 1. Current adapter contracts

| Connector | Adapter | Contract summary |
|-----------|---------|------------------|
| `gov.http` | `HttpAdapter` | Injectable `transport`; methods allowlist; strips auth headers; retry/timeout; redacted result |
| `gov.mcp` | `McpAdapter` | Policy/inventory only via `mcp_governance`; no remote MCP tool execution |
| `gov.browser` | `BrowserAdapter` | Domain policy via `saathi.browser`; navigate is dry-run (no live browser) |
| `gov.local_tool` | `LocalToolAdapter` | Named op allowlist; `shell=False`; injectable `runner` |

Shared runtime contract (`GovernedConnectorRuntime.execute`):

```text
caller identity → side-effect class → registry resolve → trust/trading
→ rollout mode → lifecycle → canary → production cert (ACTIVE)
→ side-effect/approval → policy → auth → rate limit
→ adapter → redacted evidence
```

M29 manifests declare ceilings (ops, trust, domains, timeouts, retries, health/readiness).

---

## 2. Manifest vs runtime enforcement gaps

| Area | Manifest declares | Runtime enforces today | Gap for M30 |
|------|-------------------|------------------------|-------------|
| Identity | Static builtins | Registry resolve-only | None material |
| Operations | `supported_operations` | Policy + adapter deny | Behavioral proof incomplete |
| Domains | allow/deny | Policy HTTPS + allowlist | Needs conformance evidence |
| Trust | trust_level | PROHIBITED + floors | OK |
| Side effects | side_effect_classes | classify + evaluate | Manifest ceiling not fully verified vs adapter |
| Approvals | required_approvals | Method/side-effect based | Need binding/expiry/payload match tests |
| Rollout | rollout_compatible | OFF/SHADOW/CANARY/ACTIVE/DRAINING | ACTIVE lacks **connector** cert (only production) |
| Health/readiness | health_policy / readiness_policy | Lifecycle READY/DEGRADED | Distinct health vs readiness not fully probed |
| Dependencies | dependencies | Graph validation at register | Not exercised in execute path for missing deps |
| Fingerprint / drift | — | **Missing** | Primary M30 deliverable |
| Behavioral certification | — | **Missing** | Primary M30 deliverable |

---

## 3. Missing conformance checks (pre-M30)

- No canonical check catalog (MANIFEST…RESOURCE_SAFETY).
- No certification state machine (UNASSESSED…REVOKED).
- No certification fingerprint over manifest+adapter+policy surface.
- No credential-free sandbox harness package.
- ACTIVE does not require per-connector behavioral certification.
- No drift detection for certified connectors.
- No revocation path for connector certs.
- No `docs/evidence/m30/` packages.
- Readiness claims from import/lifecycle alone are not behaviorally proven for all failure modes.

---

## 4. Duplicated validation logic

- Domain HTTPS checks: `ConnectorPolicy` + potential adapter-level host use.
- Operation allowlists: manifest fields + policy + adapter internal allowlists (HTTP methods, local tools).
- Redaction: `gov.redaction` + `mcp_governance.redaction`.
- Approval: side_effects + runtime method set + gateway approval binding.

**M30 approach:** Reuse policy/runtime/adapters; do not fork validators. Conformance *observes* existing path outcomes.

---

## 5. Reusable test infrastructure

| Asset | Location | Reuse |
|-------|----------|-------|
| Fake HTTP transport | `tests/test_m27_*` `_transport_ok` / timeout | Promote to sandbox `FakeHttpTransport` |
| Injectable local runner | `LocalToolAdapter.runner` | `FakeLocalToolExecutor` |
| Browser dry-run | `BrowserAdapter` | `FakeBrowserGateway` wrapper |
| MCP policy path | `McpAdapter` | `FakeMcpServer` for tool inventory only |
| Atomic write | `runtime._atomic_write` | Reuse pattern for evidence |
| M26 incidents | `use_m26_incidents=False` in tests | TemporaryIncidentStore |
| Approval store | `runtime.approval_store` | TemporaryApprovalStore |
| Bypass guard | `gov/bypass_guard.py` | Keep; extend allowlist for conformance package |
| Deterministic clock | `clock=lambda: 1000.0` | `DeterministicClock` |

---

## 6. Fake / sandbox adapters today

- HTTP: transport injection (no live net in tests).
- Local tool: runner injection; real subprocess only for allowlisted ops.
- Browser: dry-run navigate; no Playwright live accounts.
- MCP: policy snapshot only; no external MCP servers.

---

## 7. Readiness claims not yet behaviorally proven

- Lifecycle `READY` after `validate()` does not prove OFF/SHADOW/approval/failure-injection behavior.
- MCP “healthy” is policy-module presence, not server tool conformance.
- Browser “healthy” is domain-policy presence, not session/lease/CAPTCHA path.
- ACTIVE eligibility uses production certification only — not connector behavioral cert.

---

## 8. Connector-specific limitations (in scope)

| Connector | Limitation |
|-----------|------------|
| `gov.http` | Certifies injectable/fake transport + loopback policy; not public internet |
| `gov.mcp` | Certifies policy inventory path; no live external MCP servers |
| `gov.browser` | Certifies governed dry-run / fake gateway; no real logins |
| `gov.local_tool` | Certifies allowlisted ops; not arbitrary OS tools |

---

## 9. Selected bounded scope

```text
gov.http
gov.mcp
gov.browser
gov.local_tool
```

Plus:

- Canonical conformance specification + certification state model
- Fingerprint + drift + revoke
- Sandbox harness (credential-free)
- Runtime eligibility: ACTIVE/CANARY require fresh connector certification
- Evidence under `docs/evidence/m30/`
- CLI: `python -m saathi.connectors.conformance …`
- Focused tests + integration with existing M25–M29 gates

---

## 10. Explicitly deferred

- Live SaaS (Gmail, Calendar, GitHub, Slack, Stripe, banks, brokers)
- Live OAuth / API keys / cookies
- Connector marketplace / remote plugin download
- Infrastructure drivers full migration
- Platform-wide HTTP scan outside connector-owned paths
- Real external browser automation accounts
- Trading Guardian engagement / financial execution connectors
- M31 and beyond
- Enabling CANARY/ACTIVE on the host (default remains OFF)

---

## 11. Scope decision

**Proceed with M30 implementation** as conformance + certification infrastructure for the four M29 built-ins, credential-free sandbox only, reusing M25–M29 systems without creating parallel runtimes/registries/gateways.

```text
AUDIT COMPLETE — IMPLEMENTATION AUTHORIZED BY M30 OPERATOR BRIEF
```
