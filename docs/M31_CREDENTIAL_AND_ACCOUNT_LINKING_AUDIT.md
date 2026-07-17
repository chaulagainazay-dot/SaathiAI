# M31 — Credential and Account-Linking Audit

**Milestone:** M31  
**Branch:** `milestone/m7-security-engine`  
**Starting HEAD:** `3a9c629f227a6f6c10f5929d09ae46d00b78f60f`  
**Date:** 2026-07-17  

## Preflight

| Check | Result |
|-------|--------|
| Branch | `milestone/m7-security-engine` |
| HEAD | `3a9c629` (matches expected) |
| Remote divergence | `0/0` |
| Tracked worktree | clean |
| Untracked | `docs/evidence/m27/connector_events.jsonl` — prior M27 runtime events only |
| m27 noise classification | Generated `m27.connector_event.v1` JSONL; privacy_safe; no Bearer/password/api_key/client_secret/refresh_token |
| Action on m27 noise | **Leave untouched** (not deleted, not migrated) |
| production_certified | true |
| Connector/inference rollout | OFF |
| Connector bypasses | 0 |
| M30 conformance evidence | fresh (CERTIFIED_WITH_LIMITATIONS × 4) |
| Trading Guardian | UNCHANGED / UNENGAGED |

**Decision:** Proceed with M31.

---

## 1. Current credential reference paths

| Path | Role | Risk |
|------|------|------|
| `saathi/connectors/platform/credentials.py` | M15 CredentialRef + env/keychain resolve | Pre-gateway; resolve_secret returns values without lease |
| `saathi/connectors/platform/execution.py` | `_secret_getter` for platform adapters | Scoped resolve_for_account; not M27/M28 path |
| `saathi/connectors/accounts.py` | SQLite account + Fernet-encrypted secret blob | Legacy local store; raw secret in decrypt path |
| `saathi/connectors/adapters/telegram.py` | Reads `acct["secret"]["bot_token"]` | Legacy adapter; not gov path |
| `saathi/connectors/gov/auth.py` | Env name presence only | Safe; no values returned |
| `saathi/connectors/gov/redaction.py` | Strips secret-like keys | Reuse for evidence |
| `saathi/connectors/gov/gateway_bridge.py` | Blocks secret keys in ToolIntent | Good fail-closed pattern |
| `saathi/connectors/platform/enterprise/oauth.py` | M15.3 OAuth + PKCE state machine | Good prototype; not wired to gov runtime |
| `saathi/connectors/catalog.py` | Declares oauth/api_key auth types for SaaS names | Catalog only; no live secrets |

---

## 2. Direct environment access

* `gov.auth.resolve_auth` — presence of env names only (safe).
* `platform.credentials.resolve_secret` — returns `os.getenv` value (in-process; no lease).
* Config loaders elsewhere — out of M31 connector-auth scope unless they inject into connectors.

---

## 3. Secret-bearing configuration

* `.env` gitignored; never commit secrets.
* Platform encrypted_store / keychain backends contract-ready, not live-credential approved.
* No real OAuth client secrets in repo (by design).

---

## 4. Existing redaction utilities

* `saathi.connectors.gov.redaction.redact_payload`
* MCP redaction reuse
* M30 evidence secret pattern scrubbers

**M31:** Reuse; do not reimplement redaction.

---

## 5. Existing secure-storage abstractions

* Platform `SecretBackend` enum (env/keychain/encrypted/cloud)
* `accounts.py` Fernet encryption for local DB
* No canonical broker, lease, or injection boundary for gov runtime

---

## 6. Account identity models

* Platform store: connected accounts with credential refs (metadata)
* M29 manifests: `auth_mode`, `auth_env_names`, `secret_references` (names only)
* No account-link registry for OAuth lifecycle on gov path

---

## 7. OAuth prototypes

* `platform/enterprise/oauth.py` — full state machine + PKCE + scope expansion block
* Injectable exchange/refresh; environment-blocked without callbacks
* Not integrated with M28 ExecutionGateway or M30 certification

---

## 8. Refresh-token logic

* Present only as abstract callbacks in OAuthFlow.refresh
* No durable raw token store on OAuthFlow dataclass
* No governed refresh concurrency/lease

---

## 9. Duplicated / unsafe patterns

| Issue | Severity |
|-------|----------|
| Multiple secret resolve entry points without lease | High for future live path |
| Platform CredentialRef vs gov AuthMode parallel models | Medium |
| accounts.py can return decrypted secrets to caller | High if used outside tests |
| No quarantine state on platform CredStatus | Medium |
| OAuth state names differ from M31 suggested set | Low (normalize in M31) |

---

## 10. Connector-auth manifest fields (M29)

* `auth_mode`: none | env_var | local_secure | future_secret_manager
* `auth_env_names`, `secret_references` (names only)
* Built-ins all `AuthMode.NONE` — no live auth required today

---

## 11. Reusable infrastructure

* ExecutionGateway + GovernedConnectorRuntime
* M30 certification eligibility
* Side-effect + approval stores
* Atomic JSON writes (`runtime._atomic_write` pattern)
* Redaction, bypass guard, incidents (M26)
* Enterprise OAuth PKCE patterns (adapt, do not live-connect)

---

## 12. Bounded M31 scope

1. Canonical credential reference model (`saathi/credentials/`)
2. Credential broker + backends (test/in-memory/env-ref/unavailable; optional encrypted test)
3. Secret access leases
4. OAuth lifecycle + PKCE (provider-neutral; fake provider only)
5. Account-link registry
6. Scope governance + auth profiles
7. Narrow injection + eligibility hooks for gov runtime
8. Leak scan for lifecycle artifacts
9. Revocation / quarantine
10. CLI + tests + evidence

**Not in scope:** real OAuth, real accounts, live tokens, host CANARY/ACTIVE, Trading Guardian, M32.

---

## 13. Deferred live-provider work

* Real Gmail/Calendar/GitHub/Slack/etc. OAuth applications
* Operator-approved Keychain / production secret manager
* Live token refresh against providers
* Customer account UX
* Live-provider certification beyond M30 sandbox

---

## Scope decision

```text
AUDIT COMPLETE — IMPLEMENT M31 CREDENTIAL CONTROL PLANE
```

Canonical package: `saathi/credentials/`.  
Reuse M27–M30 governance. Do not replace connector runtime, registry, certification, or ExecutionGateway.  
Legacy platform credentials remain compatibility substrate; new gov path uses the broker.

---

## 14. Interruption recovery audit (resumed session)

The prior M31 session was interrupted. On resume, the untracked paths were treated
as **suspect partial work** and audited read-only before any mutation, staging, or
execution. No untracked path was deleted, reset, cleaned, stashed, or overwritten.

### 14.1 Secret-safety scan

No repo-native scanner (`gitleaks` / `detect-secrets` / `pre-commit`) is configured.
A bounded pattern scan was run over every untracked M31 path for:
`API_KEY ACCESS_TOKEN REFRESH_TOKEN CLIENT_SECRET PASSWORD Authorization Bearer
PRIVATE KEY BEGIN RSA BEGIN OPENSSH COOKIE SESSION oauth token secret`, plus
provider-token shapes (`eyJ…` JWT, `-----BEGIN`, `ya29.`, `xox[baprs]-`, `ghp_`,
`gho_`, `sk-…`, `AKIA…`) and long (`≥20`) base64/hex string literals.

| path | line | classification | redacted preview | verdict |
|------|------|----------------|------------------|---------|
| `saathi/credentials/models.py` | 122–127 | forbidden-secret-**name** list | `"access_token", "refresh_token", …` | placeholder (guard list, no values) |
| `saathi/credentials/models.py` | 14–23,59–67 | enum **names** | `API_KEY = "api_key"` | placeholder |
| `saathi/credentials/testing/sandbox_oauth.py` | 101–102 | synthetic token mint | `access="atk_"+uuid4; refresh="rtk_"+uuid4` | synthetic |
| `saathi/credentials/oauth.py` | 335–336,389 | in-process token fields | `session._access_token = str(tokens.get(...))` | synthetic (fake provider) |
| `saathi/credentials/broker.py` | long-literal hits | error-code / event / JSON-key strings | `"credential.lease_issued"` | not a secret |
| `docs/evidence/m27/connector_events.jsonl` | all | runtime event log | `schema=m27.connector_event.v1; privacy_safe=true` | no Bearer/password/token |

**Result: no real credential, key, JWT, cookie, or provider token found in any
untracked path.** All secret-shaped values are synthetic (`atk_`/`rtk_`/`ac_` +
uuid/sha256) minted by the deterministic fake provider, or field-**name** references
in guard lists. No `.env`, `*.key`, `*.pem`, `*.db`, `*.sqlite`, token cache, cookie
jar, or `__pycache__` exists under the untracked paths. **BLOCKED_BY_SECRET_RISK: none.**

### 14.2 Per-file classification

| path | classification | reason |
|------|----------------|--------|
| `docs/M31_CREDENTIAL_AND_ACCOUNT_LINKING_AUDIT.md` | **REUSE** | Coherent prior audit; extended with this recovery section + final report |
| `saathi/credentials/models.py` | **REUSE** | Metadata-only reference/lease/profile model; fail-closed on trading providers/scopes; no secret values |
| `saathi/credentials/lease.py` | **REUSE** | Bounded-TTL, single-use, replay/mutation-guarded, thread-safe lease store |
| `saathi/credentials/backends.py` | **REUSE** | Test/in-memory/env-ref/unavailable/encrypted-test backends; path-escape + symlink guards; no live backend |
| `saathi/credentials/broker.py` | **REPAIR** | Coherent control plane; removed 2 dead-code leftovers (L220 `or True`, L246 status tautology). No behavior change |
| `saathi/credentials/oauth.py` | **REUSE** | Provider-neutral PKCE lifecycle; state/code replay + scope-expansion/widening blocked; fake-provider only |
| `saathi/credentials/testing/sandbox_oauth.py` | **REUSE** | Deterministic in-process fake provider; synthetic tokens; no network |
| `docs/evidence/m27/connector_events.jsonl` | **PRE-EXISTING UNTRACKED NOISE (leave)** | Generated by gov runtime `_emit` (`runtime.py:195`, schema `m27.connector_event.v1`); not M31; no tracked `m27` evidence dir exists |

No file was classified `REMOVE_AS_GENERATED_JUNK`, `REPLACE_WITH_EXISTING_CANONICAL_COMPONENT`,
or `BLOCKED_BY_SECRET_RISK`. Coherence, import boundaries, and consistency with the
authorized M31 architecture were verified against M25–M30 and the M31 prompt.

### 14.3 `docs/evidence/m27/` disposition

`docs/evidence/m27/connector_events.jsonl` is runtime output of the M27 gov runtime
(`GovernedConnectorRuntime._emit`), not curated milestone evidence — the tracked tree
has evidence dirs for m25/m26/m28/m30 but **no m27**. It is neither tracked nor
gitignored. Per recovery policy it is **left untouched**: not deleted, not staged, not
migrated into M31. **No new `.gitignore` rule was added** — sibling evidence `.jsonl`
files (m26/m28) are deliberately tracked, so a broad ignore would risk hiding canonical
evidence, and no existing rule targets this exact file.

### 14.4 What the partial work did NOT include (built in this session)

The recovered code is the credential **data plane** only. Missing, authorized M31
deliverables built on resume: package `__init__` exports, scope-governance/auth-profile
module, synthetic secret-leak detector, account-link registry, narrow injection boundary,
M31 connector eligibility (composable with M30), evidence writer, CLI, test suite, and
evidence/documentation.

---

## 15. M31 final report

### 15.1 What shipped

| Module | Role |
|--------|------|
| `saathi/credentials/models.py` | Metadata-only reference/lease/auth-profile model; trading/financial guards |
| `saathi/credentials/backends.py` | Backend contract + in-memory / env-ref / unavailable / encrypted-test (no live backend) |
| `saathi/credentials/lease.py` | Bounded-TTL, single-use, replay/mutation-guarded lease store |
| `saathi/credentials/broker.py` | Credential control plane: create/lease/inject/rotate/quarantine/revoke/delete; unleased retrieval blocked |
| `saathi/credentials/scopes.py` | Auth-profile catalog + scope governance (no request/grant expansion; prohibited scopes fail closed) |
| `saathi/credentials/leakscan.py` | Synthetic secret-leak detector; guards evidence/event emission |
| `saathi/credentials/oauth.py` | Provider-neutral PKCE lifecycle; state/code replay + scope-expansion/widening blocked |
| `saathi/credentials/account_links.py` | Account-link registry: lifecycle, readiness, owner-scoping, revoke/quarantine cascade |
| `saathi/credentials/injection.py` | Narrow injection boundary; secrets scrubbed on block exit |
| `saathi/credentials/eligibility.py` | M31 credential eligibility; **read-only** composition with M30 certification |
| `saathi/credentials/evidence.py` | Leak-scanned, metadata-only evidence writer |
| `saathi/credentials/cli.py` + `__main__.py` | `status/readiness/profiles/list*/inspect*/demo/emit-evidence/verify` |
| `saathi/credentials/testing/sandbox_oauth.py` | Deterministic in-process fake OAuth provider (no network) |
| `tests/test_m31_credentials.py` | 43 tests across all modules + milestone invariants |

### 15.2 Recovery outcome

* Interrupted untracked M31 work **discovered** and audited read-only before any mutation.
* **Reused:** `models.py`, `lease.py`, `backends.py`, `oauth.py`, `testing/sandbox_oauth.py`, the audit doc.
* **Repaired:** `broker.py` (2 dead-code leftovers removed; no behavior change).
* **Replaced:** none. **Excluded:** `docs/evidence/m27/connector_events.jsonl` (runtime noise; left untouched, unstaged).
* **Secret scan:** no real credential/key/JWT/cookie/token in any untracked path; all secret-shaped values synthetic (fake provider). **No real credentials committed.**

### 15.3 Validation

| Suite | Result |
|-------|--------|
| `tests/test_m31_credentials.py` | **43 passed** |
| M27–M31 connector regression (`test_m27/28/29/30/31`) | **167 passed** |
| M25 production certification (`test_m25_cert_evidence`, `test_m25_live_provider_certification`) | **32 passed** |
| M31 suite tracked-tree side effects | none (fully hermetic: `persist=False` + isolated cert store) |
| `python -m saathi.credentials verify` | `invariants_ok=true, leak_clean=true` |
| `python -m saathi.credentials emit-evidence` | evidence written, leak-clean |

*Note:* running the existing M25/M28/M30 suites regenerates their own tracked evidence
and (via a manifest-less read) marked `gov.http` certification stale. Those were **test
side effects, not M31 changes** — all five affected tracked files were restored to HEAD
`3a9c629`, and M31 eligibility was hardened to consult M30 certification `refresh_stale=False`
(read-only) so composing eligibility can never mutate the M30 store.

### 15.4 Certification / rollout / guardrail state (at commit)

| Metric | Value |
|--------|-------|
| Platform production certification (`production_certified_probe`) | **true** |
| Connector certification freshness | `gov.http`, `gov.mcp`, `gov.browser`, `gov.local_tool` → **CERTIFIED_WITH_LIMITATIONS** (fresh, unchanged from HEAD) |
| Connector rollout mode | **OFF** |
| Production connector bypasses (`scan_connector_bypasses`) | **0** (6 pre-existing *allowlisted* informational findings; 100 files scanned) |
| Real credentials stored | **0** |
| Real OAuth flows completed | **0** |
| Real OAuth endpoints contacted | **0** |
| Live account links | **0** |
| Trading Guardian | **UNCHANGED / UNENGAGED** |

### 15.5 Scope boundaries honored

No real OAuth flow. No real credentials. No live accounts. No production deployment.
No connector rollout activation (mode stays OFF). No Trading Guardian changes. No
modification to the M27 connector runtime, M28 migration, M29 registry, M30 certification,
or the ExecutionGateway — M31 composes with them read-only. M32 not started.

**Starting HEAD:** `3a9c629`  
**Ending HEAD:** _recorded at commit time below._
