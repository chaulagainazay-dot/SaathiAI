# SaathiOS Private Alpha — Release Process

Private alpha, invite only, local first. A "release" here means **a SHA a tester is asked to run**.
It does not mean deployment, publication, or any public availability.

---

## 1. Versioning

`0.1.0-alpha.N` — increment `N` per release candidate.

The `0.1.0` prefix is deliberate and must not advance to `1.0.0`, and the `-alpha` suffix must not
be dropped, while any of the following hold: production is not authorized, provider and broker
connectivity are disabled, or real-user validation is incomplete. **The version must never imply
production stability.**

## 2. One candidate at a time

Exactly one release candidate is live for testers at any moment. Two concurrent candidates make
feedback unattributable — a tester report against an unknown build is close to worthless.

## 3. Gate checklist

A candidate may go to testers only when every line passes:

- [ ] approved SHA recorded, full 40 characters
- [ ] no open P0 defect
- [ ] no open P1 defect
- [ ] full backend suite passes
- [ ] full frontend suite passes
- [ ] lint passes
- [ ] production build succeeds
- [ ] browser certification passes
- [ ] loopback-only binding verified for every SaathiOS listener
- [ ] hard authorities verified false (`production_authorized`, `permits_live_execution`, trading execution)
- [ ] no public registration path exists
- [ ] no provider or broker connection configured
- [ ] secret scan clean
- [ ] migration review completed, or "no migrations" recorded
- [ ] rollback point identified (the previous good SHA)
- [ ] changelog updated
- [ ] known issues updated
- [ ] owner approval recorded

Any unchecked line blocks the candidate. There is no partial release.

## 4. Rollback

The rollback point is the previous SHA that passed this checklist in full.

Rollback is: stop the frontend, `git checkout <previous good SHA>`, `npm ci` if dependencies moved,
`npm run build`, restart, verify `/platform` renders and the health endpoint answers.

**Always rebuild and restart together.** A rebuild under a running `next start` leaves it serving a
stale in-memory manifest and the app breaks with a `ChunkLoadError` while still reporting HTTP 200
(defect PA-D-002). This has now bitten twice.

Database rollback is **not** covered by a git checkout. If a candidate ran a migration, the
rollback plan must state how to reverse it, or the candidate must not ship.

## 5. Tester notice

On each release, tell testers: the version, the SHA, what changed, what to re-test, what is known
broken, and what is deliberately unavailable.

Never describe a private-alpha release as "stable", "ready", "live" or "connected".

## 6. Prohibited at every release

No public deployment. No DNS change. No push without explicit owner authorization. No merge of
PR #12, #13 or #14 without explicit owner authorization. No enabling of registration, OAuth,
provider login, broker credentials, order controls or live execution. No weakening of
authentication, session expiry, RBAC, workspace isolation or approval controls to make a release
pass its gate.

If a gate fails, fix the product. Never lower the gate.
