# M36 — Final Report

## 1. Executive result

> **M36 IMPLEMENTATION COMPLETE — REAL SANDBOX SESSION NOT EXERCISED**

M36 delivers a complete operator-controlled real-sandbox verification path as a
composition of M31–M35 credential/session governance and M33/M34 canonical
transport. All focused offline tests pass. Deterministic offline evidence is
generated under `docs/evidence/m36/`. No disposable sandbox credential was
available in an approved secret source, so **no real secret was retrieved and
no live external network call was made**.

**Blocker for live exercise:** no operator-supplied disposable sandbox secret
reference (OS Keychain / approved env / encrypted store) with completed runtime
acknowledgements.

---

## 2. Baseline and tip

| Item | Value |
|------|-------|
| Starting HEAD | `233faa578a1b33fe2ede5f69f16c0801d8db4b3d` (M35 tip) |
| Ending HEAD | `f97155b4ae1bd50cc330795d4a35c501bd2434b5` |
| Branch | `milestone/m7-security-engine` |
| Preflight remote divergence | `0 0` |
| Worktree noise (preserved, unstaged) | `docs/evidence/m25/*`, `docs/evidence/m27/connector_events.jsonl`, `docs/evidence/m28/deprecation_events.jsonl` |
| `docs/evidence/m27/` | **untouched** (not staged, not modified by M36) |

---

## 3. Architecture reused

| Layer | Components |
|-------|------------|
| M31 | `CredentialBroker`, `SecretBackend`, broker leases, `leakscan`, models |
| M32 | `write_evidence`, quarantine patterns |
| M33 | `github_meta` profile, `ExternalTransport`, DNS/SSRF, TLS, endpoint policy, envelopes |
| M34 | Call budget ≤ 3, latency/size buckets, live env-flag pattern |
| M35 | `SecretHandle`, sandbox account registry, scope classes, ceilings, session leases, fingerprints |

No parallel credential broker, secret store, lease system, account registry,
approval system, session system, transport, adapter, audit ledger, or
certification system was created.

---

## 4. Provider and operation

| Field | Value |
|-------|--------|
| Provider | `github_meta` |
| Identity endpoint | `GET https://api.github.com/user` (`get_authenticated_user`) |
| Operation endpoint | `GET https://api.github.com/meta` (`get_meta`) |
| Host allowlist | `api.github.com` |
| Authentication required for identity | **Yes** |
| Authentication required for `/meta` | **No** (public) |
| Auth injection | Sender wrapper only; never on envelope; never in evidence |

Identity operation is a same-provider binding via `dataclasses.replace` on the
approved profile (hostname/TLS/redirect ceilings preserved). No second provider.

---

## 5. Sandbox identity

| Field | Offline status |
|-------|----------------|
| Classification | `DISPOSABLE_SANDBOX` (synthetic qualification path) |
| Safe alias | `synthetic-sandbox` / operator alias |
| Environment | `SANDBOX` |
| Production data | Declared absent |
| Real account verified | **NOT EXERCISED** |
| Revocation plan | Manual GitHub PAT delete + local lease revoke |

---

## 6. Credential

| Field | Offline status |
|-------|----------------|
| Type | `api_key` (synthetic) |
| Secret source | `IN_MEMORY_TEST` offline; Keychain preferred for live |
| Fingerprint | Domain-separated HMAC (see evidence) |
| Real secret loaded | **0** |
| Observed scopes | Fixture `read:user` offline only |

---

## 7. Authorization and lease

| Field | Policy |
|-------|--------|
| Acknowledgements | All 8 required |
| Call budget | max 3 |
| Lease | issued → consume use → **revoked** on complete |
| Authorization | one-use, expires, not reusable for M37 |
| Actual live calls | **0** |

---

## 8. Transport security

Canonical path: `ExternalTransport` + injectable sender.
HTTPS-only, hostname allowlist, DNS/SSRF, TLS, redirect limit 0, timeout,
response-size ceiling, content-type checks, header redaction, call-budget
accounting. Authorization header never logged or evidenced.

---

## 9. Session result

| Field | Offline fixture simulation |
|-------|----------------------------|
| Transitions | AUTHORIZED → … → COMPLETED → SECRET_CLOSED → LEASE_CONSUMED |
| Account match | Yes (synthetic subject id fingerprint) |
| Scope | Observed `read:user` → VERIFIED_READ_ONLY / extra-read handling |
| Reliability | `SINGLE_SUCCESS` (not production reliability) |
| Live network | **NOT EXERCISED** |

---

## 10. Cleanup

| Item | Status |
|------|--------|
| Secret handle | Closed on success and failure paths |
| Local lease | Revoked on session complete |
| External credential revocation | N/A (no real credential) |
| Cleanup attestation | Policy documented; SILENT_ACTIVE forbidden |

---

## 11. Certification

```
m36_certification (offline path) = REAL_SANDBOX_SESSION_VERIFIED (fixture) / AUTHORIZATION_READY (no live)
real sandbox session = NOT_EXERCISED

production authorization = NOT GRANTED
rollout authorization = NOT GRANTED
CANARY authorization = NOT GRANTED
ACTIVE authorization = NOT GRANTED
write authority = NOT GRANTED
```

---

## 12. Evidence and leaks

Offline evidence under `docs/evidence/m36/` (20 files). Leak scan clean on
generator output. No raw secrets, personal identities, Authorization headers,
or raw response bodies in evidence. Paths repository-relative.

---

## 13. Network accounting

```
identity calls (live) = 0
operation calls (live) = 0
retries = 0
redirect calls = 0
total live calls = 0
writes = 0
financial calls = 0
trading calls = 0
```

Offline fixture simulation consumes 2 budget units (identity + meta) with no network.

---

## 14. Tests

| Suite | Result |
|-------|--------|
| Focused M36 | **137 passed** |
| M31–M36 combined regressions | **794 passed** |
| Full suite | **4080 passed, 1 skipped, 1 failed** (pre-commit dirty-tree readiness: `test_readiness_clean_repo` reports `unsafe` while `saathi/credentials/*` is uncommitted — expected; re-check after commit) |
| Critical path M31–M36 | green |
| Warnings | pre-existing DeprecationWarnings (datetime.utcnow, tar.extractall, llm facade) — not introduced by M36 |

---

## 15. Files changed

| Path | Purpose |
|------|---------|
| `saathi/credentials/m36.py` | M36 coordinator |
| `saathi/credentials/cli.py` | M36 CLI commands |
| `scripts/m36_generate_evidence.py` | Offline evidence generator |
| `tests/test_m36_*.py` | Focused offline tests (4 files) |
| `docs/M36_*.md` | Audit, ops, certification, final report |
| `docs/evidence/m36/*` | Deterministic offline evidence |
| `Brain.md` / `Business.md` | Platform notes |
| `docs/AUTONOMOUS_ROADMAP.md` / `AUTONOMOUS_LOOP_STATE.json` | Milestone tracking |
| `.saathi-agent-state/HANDOFF.md` | Handoff |

---

## 16. Test-side-effect handling

Known pre-existing noise left **unstaged**:

- `docs/evidence/m25/*` timestamp noise
- `docs/evidence/m27/connector_events.jsonl`
- `docs/evidence/m28/deprecation_events.jsonl`

`docs/evidence/m27/` was not modified by M36 implementation.

---

## 17. Security invariants

```
production_certified = true (unchanged)
M31–M35 governance = preserved
connector/provider/inference rollout = OFF
CANARY = 0, ACTIVE = 0
production credentials/accounts/OAuth = 0
real sandbox credentials used = 0
external network calls = 0
external writes = 0
financial/trading calls = 0
raw secrets committed = 0
Trading Guardian = UNCHANGED / UNENGAGED
M37 = NOT STARTED
```

---

## 18. Commits and push

| Item | Value |
|------|-------|
| Commit | `4e825f37ff06913132943b17e0dba67629e6b3f8` — `feat(m36): operator-controlled real sandbox session governance` |
| Ending HEAD | `f97155b4ae1bd50cc330795d4a35c501bd2434b5` |
| Push target | `origin/milestone/m7-security-engine` |
| Pre-push readiness re-check | `test_readiness_clean_repo` **passed** after commit |
| Known unstaged noise | m25/m27/m28 evidence only |

---

## 19. Limitations

- One provider only (`github_meta`)
- One account only (when live)
- One operation set only (identity + meta)
- Maximum three calls
- No sustained reliability test
- Provider scope visibility depends on GitHub OAuth scope headers
- Manual external revocation
- No OAuth
- No production credential/account
- No writes
- No rollout / CANARY / ACTIVE
- No Trading Guardian engagement
- **Real session not exercised in this run**

---

## 20. Exact next action

```
READY FOR OPERATOR AUTHORIZATION TO START M37
```

(Real sandbox live verification remains optional operator follow-up under M36
gates if a disposable credential is later supplied; it is not required to begin
M37 review if the operator accepts the offline completion state.)

Alternatively, if the operator requires a live session before M37:

```
M36 REMAINS OPEN — no disposable sandbox secret reference available
```

**This run concludes with implementation-complete offline readiness and
explicit non-exercise of the live path.** Operator may authorize M37 after
accepting that limitation, or supply a disposable Keychain reference to complete
live verification first.
