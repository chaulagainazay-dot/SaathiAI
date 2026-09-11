# SaathiOS Private Alpha — Changelog

Private alpha, invite only, local first. Versions never imply production stability.

---

## 0.1.0-alpha.2 — unreleased (candidate)

**Branch:** `improve/saathios-private-alpha-product-excellence`
**Base:** `6b55013`
**Status:** NOT RELEASED — real-user validation has not run.

### Fixed
- **Expired sessions no longer dead-end the platform** (`6b55013`, defect `PA-D-001`, P1).
  An idle-expired session (idle TTL 3600 s) previously showed a raw `SESSION_INVALID` error and
  kept the dead token, so the sign-in form — which renders only when no token is held — never
  appeared. Recovery from an authenticated `SESSION_INVALID`, `MEMBERSHIP_REVOKED` or `401` now
  clears the token through the canonical helper, blanks every authenticated field, and restores
  the sign-in surface with a plain-language notice.
  Deliberately narrow: `403`, `5xx`, offline and malformed responses never clear the token, so a
  transient outage cannot silently sign the owner out. An unauthenticated `401` remains an ordinary
  failed sign-in.

### Added
- 11 regression tests in `lib/platform-ops.test.js` covering expiry, `MEMBERSHIP_REVOKED`,
  authenticated `401`, the non-clearing cases (`403`/`500`/offline/malformed), private-data
  clearance, loop safety, and re-login after recovery.
- Private-alpha quality evidence corpus under `docs/private-alpha-quality/`: product inventory,
  user validation plan, real-user test scripts, feedback schema and log, accessibility audit,
  performance baseline, retention policy, defect log, release process, known issues.

### Changed
- `logout()` now shares one clear helper with expiry recovery, and additionally blanks `config`,
  `echo` and `selectedModule`, which it previously left behind.

### Security
- No control was weakened. No authentication, session expiry, RBAC, workspace isolation or
  approval control was modified. Backend untouched — frontend only.
- Hard authorities re-verified false: `PRODUCTION_NOT_AUTHORIZED`,
  `TRADING_GUARDIAN_UNENGAGED_ADVISORY_ONLY`, `CONNECTOR_MUTATIONS_DRY_RUN_ONLY`,
  `AUTHORITY_FAIL_CLOSED`, `permits_live_execution = False`.
- Every SaathiOS listener verified loopback-only. Secret scan clean.

### Known issues
See `PRIVATE_ALPHA_KNOWN_ISSUES.md`. No open P0 or P1; seven open P2/P3.

### Not done
No retention tooling was implemented and no data was deleted. No performance optimisation was
performed — every measured value sits far inside its budget, and speculative rewrites were declined.

---

## 0.1.0-alpha.1 — prior state

**SHA:** `c2f198c` (branch `fix/saathios-full-e2e-functional-recovery`, PR #14 draft)

Full application E2E recovery; passwordless-login bypass closure; duplicate mission conflict
handling; approval-scope validation repair; voice and microphone route cleanup; loopback-only
frontend binding; `/unlock` hydration repair; full browser route coverage; clean-clone verification.

State reached: `PRIVATE_ALPHA_READY_FOR_OWNER_OPERATION_OFFLINE_INVITE_ONLY`.
