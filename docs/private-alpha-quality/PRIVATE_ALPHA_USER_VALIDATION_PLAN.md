# SaathiOS Private Alpha — Real User Validation Plan

**Build under test:** `6b55013` (`improve/saathios-private-alpha-product-excellence`)
**Status:** prepared, not yet executed
**Maximum testers:** 5. Do not expand without owner review.

SaathiOS is private alpha, invite only, local first, offline first, loopback only. It is not a
production system, it holds no real financial authority, and it connects to no broker or provider.

---

## 1. Cohorts

| Cohort | Count | Role | Purpose |
|---|---|---|---|
| A | 1 | Owner | Full administrative journey, approvals, diagnostics, recovery, release review |
| B | 1–2 | Operator | Project and mission creation, approval requests, execution, cancellation, evidence |
| C | 1 | Viewer | Read-only access, route clarity, permission-denied behaviour, dashboard usability |

Existing accounts: `owner@e2e.local`, `operator@e2e.local`, `viewer@e2e.local` — all active and
password-protected. Testers use aliases (`T-OWNER-1`, `T-OP-1`, `T-VIEW-1`) in all records.

## 2. Invite process

1. Owner issues an invitation through the existing invitations mechanism (16 records already exist).
2. Owner shares the loopback URL and the tester guide **in person or over a trusted channel**.
3. Owner sets the tester's initial password directly. **Never send a password over chat or email.**
4. Tester confirms they have read the consent and privacy section below.
5. No self-registration exists and none may be enabled.

Access is local only. A tester must be at the machine, or on a trusted operator-controlled session.
Do not expose port 3000 to a network to accommodate a remote tester.

## 3. Test tasks and duration

Each tester runs the scripts in `REAL_USER_TEST_SCRIPTS.md`.

| Script | Cohort | Expected duration |
|---|---|---|
| A — First-time user | A, B, C | 15–20 min |
| B — Operator mission flow | B | 20–30 min |
| C — Owner approval flow | A | 15–20 min |
| D — Voice and assistant | A, B | 15–20 min |
| E — Failure and recovery | A | 15–20 min |

Total per tester: 30–60 minutes. Run one script per sitting; fatigue produces false usability signal.

## 4. Privacy instructions

**Use synthetic data only.** Name projects and missions `Test Project 1`, `Alpha Mission A`, and so on.

Never enter, and never capture in a screenshot:

- real passwords, tokens, API keys or recovery codes
- real financial account numbers or broker credentials
- real customer, patient or client personal data
- government identifiers
- anything you would not want stored in a git repository

Voice recordings are **not** collected. If you test voice, only your written impression is recorded.

Before attaching a screenshot, confirm no credential or real personal data is visible.

## 5. Consent language

> I understand SaathiOS is an unreleased private alpha running locally on this machine.
> I agree to use only synthetic test data. I understand my written feedback and any screenshots
> I approve will be stored in the project repository under an alias. I understand no audio of my
> voice is recorded. I may stop at any time, and I may ask for any of my feedback to be removed.

Record consent as a yes/no plus a date against the tester alias. Do not store a signature.

## 6. Issue reporting

Report through the owner, who records entries in `PRIVATE_ALPHA_FEEDBACK_LOG.json` against the
schema. For each issue, state in your own words:

- what you were trying to do
- what you expected
- what actually happened
- whether it happened again when you retried

Do not self-classify severity — triage does that. "This confused me" is a valid and valuable report.
**Confusion is a product defect, not user error.**

## 7. Prohibited activities

Testers must not:

- attempt to enable provider login, OAuth, or broker connectivity
- enter real financial credentials or connect a financial account
- attempt to enable live trading or order execution
- expose the service to a network or change the loopback binding
- attempt to bypass authentication, RBAC or workspace isolation
- share credentials with anyone, including other testers
- deploy, push or publish anything

Security probing is not part of this programme. Report anything that *looks* wrong instead.

## 8. Support contact

Owner: Ajay Chaulagain. If SaathiOS becomes unusable mid-session, stop and report — do not attempt
repair. A stuck session is itself a finding worth recording.

## 9. Exit criteria

The validation programme is complete when all of the following hold:

- [ ] 1 owner session completed
- [ ] 1 operator session completed
- [ ] 1 viewer session completed
- [ ] at least 3 complete scripted journeys finished end to end
- [ ] every P0 and P1 issue resolved and re-verified, or the release explicitly blocked
- [ ] owner has reviewed all unresolved P2 and P3 items
- [ ] no issue is closed as cosmetic without written evidence

Until then the programme status is `REAL_USER_VALIDATION_PENDING`.

## 10. Known constraint at time of writing

Automation prepared this plan but could not execute any part of it. All platform accounts are
password-protected, and automation must neither enter the owner's password nor bootstrap a new
account. Every authenticated journey below therefore remains unexercised by anyone.
