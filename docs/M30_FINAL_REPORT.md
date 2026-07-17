# M30 Final Report — Connector Conformance, Sandbox Validation, and Certification

## 1. Executive result

```text
M30 COMPLETE WITH LIMITATIONS
```

## 2. Baseline and tip

| Item | Value |
|------|-------|
| Starting HEAD | `9c4770fc004e9e9185cc5a0e20e137d3b67970e2` |
| Ending HEAD | *(set after final commit)* |
| Branch | `milestone/m7-security-engine` |
| Worktree at start | clean tracked (untracked m27 runtime evidence left untouched) |
| Remote divergence at start | `0/0` |

## 3. Repository evidence

### Audit findings

* M29 manifests declare ceilings; runtime enforces most policy paths.
* ACTIVE required production certification only — **not** per-connector behavioral cert (gap closed by M30).
* Reusable fakes: injectable HTTP transport, local runner, browser dry-run, MCP policy path.
* No prior certification fingerprint/drift/revoke package.

### Selected scope

```text
gov.http | gov.mcp | gov.browser | gov.local_tool
```

### Deferred

Live SaaS/OAuth; infrastructure drivers; platform-wide HTTP scan; real browser logins; host CANARY/ACTIVE enablement; M31.

## 4. Conformance architecture

```text
registry
→ conformance specification
→ sandbox harness
→ check results
→ fingerprint
→ certification decision
→ runtime eligibility
```

**Package:** `saathi/connectors/conformance/`

## 5. Certification state model

UNASSESSED → ASSESSING (lease) → CERTIFIED | CERTIFIED_WITH_LIMITATIONS | FAILED | ENVIRONMENT_BLOCKED  
CERTIFIED* → STALE (fingerprint drift)  
* → REVOKED (explicit; evidence preserved)

## 6. Fingerprint and drift

* Inputs: manifest ceilings + adapter/runtime/policy/trust/conformance surface hashes + spec version.
* Docs excluded (false-positive control).
* Drift marks CERTIFIED* → STALE; verify reports freshness invariant.

## 7. Built-in connector results

| Connector | State | Limitations | Readiness implication | Evidence |
|-----------|-------|-------------|----------------------|----------|
| gov.http | CERTIFIED_WITH_LIMITATIONS | fake transport; no public internet | Not live SaaS ready | `docs/evidence/m30/connectors/gov.http/` |
| gov.mcp | CERTIFIED_WITH_LIMITATIONS | policy inventory only; no external MCP | Not live MCP ready | `docs/evidence/m30/connectors/gov.mcp/` |
| gov.browser | CERTIFIED_WITH_LIMITATIONS | dry-run; no live login | Not live automation ready | `docs/evidence/m30/connectors/gov.browser/` |
| gov.local_tool | CERTIFIED_WITH_LIMITATIONS | allowlist only | Not arbitrary OS tools | `docs/evidence/m30/connectors/gov.local_tool/` |

Fingerprints recorded in each `fingerprint.json` and `docs/evidence/m30/certification_registry.json`.

## 8. Sandbox safety

| Property | Result |
|----------|--------|
| External network | none (fake transport) |
| Live credentials | 0 |
| Temp isolation | yes |
| Filesystem bounds | temp dirs |
| Subprocess | allowlisted / fake runner; no shell=True |
| Cleanup | harness `close()` |

## 9. Failure injection

Timeout, connection failure, rate limit, missing/expired/mismatched approval, idempotency conflict, oversized payload, undeclared ops, domain/HTTPS deny, financial/trading deny, OFF/SHADOW no side effect — all fail closed without false success.

## 10. Runtime integration

* **OFF** — no adapter execution (default).
* **SHADOW** — governance; no external side effect.
* **CANARY** — deterministic; requires connector certification.
* **ACTIVE** — production cert + connector cert + READY + policy + approval.
* **DRAINING** — blocks new work.

## 11. Security

Secret redaction; approval enforcement; trust/PROHIBITED; side-effect floors; direct-access bypass guard = 0; prohibited/trading connectors not executable-certified.

## 12. Files changed (primary)

| Path | Purpose |
|------|---------|
| `saathi/connectors/conformance/*` | Spec, sandbox, assessor, fingerprint, store, drift, eligibility, CLI |
| `saathi/connectors/gov/runtime.py` | ACTIVE/CANARY connector certification gate |
| `saathi/connectors/gov/adapters/http.py` | Local health/validate without URL |
| `saathi/connectors/gov/adapters/local_tool.py` | health/validate allowlist |
| `saathi/connectors/gov/bypass_guard.py` | Allowlist conformance package |
| `tests/test_m30_connector_conformance.py` | Focused tests |
| `tests/test_m27/28/29_*.py` | Fixture auto_fixture cert store |
| `docs/M30_*` | Documentation |
| `docs/evidence/m30/**` | Certification evidence |
| `docs/AUTONOMOUS_*`, `TECHNICAL_DEBT.md`, `Brain.md`, `Business.md` | Program state |

## 13. Tests and validation

| Check | Result |
|-------|--------|
| Focused M30 | 38 passed |
| M25–M30 focused (M26–M30 set) | 174 passed |
| Full suite | **3287 passed, 1 skipped, 0 failed** |
| Conformance verify | ok |
| Drift | fresh_certified all four; ok |
| Connector bypass | 0 |
| Direct provider bypass | 0 (release_check) |
| Residual exceptions | 0 |
| Cloud fallback default | false |
| Runtime gate | ok, production_certified=true |
| Release check | ok |
| Trading Guardian | UNCHANGED / UNENGAGED |

## 14. Certification relationship

```text
platform production certification  ≠  connector behavioral certification
connector health                   ≠  connector readiness
connector rollout                  ≠  execution authorization
```

All layers may apply; none alone is sufficient for live ACTIVE production use.

## 15. Invariants

```text
production_certified = true
production blockers = []
connector certification states = CERTIFIED_WITH_LIMITATIONS × 4 builtins
connector evidence freshness = true
connector rollout = OFF
inference rollout = OFF
connector bypasses = 0
connector conformance bypasses = 0
direct provider bypasses = 0
process-local production authorities = 0
residual inference exceptions = 0
cloud fallback = disabled
live credentials used = 0
live external accounts connected = 0
Trading Guardian = UNCHANGED / UNENGAGED
```

## 16. Commits and push

*(filled after push)*

## 17. Limitations and technical debt

* Sandbox certification does not equal live-provider certification.
* Live OAuth remains deferred.
* Infrastructure drivers outside built-in scope remain deferred.
* Platform-wide HTTP scanning outside connector-owned paths remains future work.
* Browser validation uses deterministic/governed dry-run, not real external websites/accounts.
* Host connector rollout remains OFF by design.

## 18. Exact next action

```text
READY FOR OPERATOR AUTHORIZATION TO START M31
```

Do not auto-start M31.
