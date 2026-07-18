# M33 — External Provider Candidate Audit

**Milestone:** M33 — Official Sandbox / Read-Only External Provider Pilot
**Scope:** integrate exactly one real external provider, read-only, non-production.
**Maximum verification state:** `EXTERNAL_READ_ONLY_VERIFIED_WITH_LIMITATIONS`
**Rollout:** connector/provider/inference rollout remain **OFF**. Trading Guardian **UNCHANGED / UNENGAGED**.

This audit is produced **before** implementation, per the M33 evidence-first intake requirement.

---

## 1. Selection policy applied

Priority order from the M33 brief:

- **Option A** — official credential-free read-only API *(preferred)*
- **Option B** — official sandbox with disposable test credentials
- **Option C** — official developer test account

A provider is admissible only if it is official, documented, HTTPS, read-only (no writes / no side effects), credential-free (or disposable-sandbox), bounded in response size, rate-limited politely, and free of personal / financial / trading / social-publishing / email / calendar data.

Prohibited by hard rule (fail closed): trading, order, broker, exchange, wallet,
withdraw, transfer, payment, bank, financial, leverage, margin, futures, crypto
execution; Gmail, Google Calendar/Drive personal content, Slack, Facebook,
Instagram, LinkedIn, TikTok, YouTube publishing, WhatsApp; banking / payment /
crypto / brokerage / wallet / trading APIs; **production GitHub mutation**;
production cloud administration; health / government-identity systems;
browser-login automation.

---

## 2. Candidates considered

| # | Candidate | Owner | Auth | Method | Side effect | Data class | Verdict |
|---|-----------|-------|------|--------|-------------|-----------|---------|
| 1 | `https://api.github.com/meta` | GitHub, Inc. | none | GET | READ_ONLY | PUBLIC (infra metadata) | **SELECTED** |
| 2 | `https://www.cloudflare.com/cdn-cgi/trace` | Cloudflare, Inc. | none | GET | READ_ONLY | PUBLIC + **caller egress IP** | rejected — echoes requester IP (borderline personal/telemetry); text schema harder to validate |
| 3 | `https://api.ipify.org?format=json` | ipify (community) | none | GET | READ_ONLY | **caller egress IP** | rejected — sole purpose is returning caller IP (personal-ish); non-official owner |
| 4 | `https://worldtimeapi.org/api/timezone/Etc/UTC` | community | none | GET | READ_ONLY | PUBLIC | rejected — recurrent uptime outages; unclear ownership/terms |
| 5 | `https://restcountries.com/v3.1/alpha/us` | community-maintained | none | GET | READ_ONLY | PUBLIC | rejected — large response; community ownership; weaker terms |
| 6 | `https://date.nager.at/api/v3/PublicHolidays/2026/US` | Nager.Date | none | GET | READ_ONLY | PUBLIC | rejected — third-party, uptime limitation, weaker SLA/terms |
| 7 | `https://httpbin.org/get` | community | none | GET | READ_ONLY | echoes request | rejected — not an authoritative official owner; echoes request headers |
| 8 | `https://www.githubstatus.com/api/v2/status.json` | GitHub (Statuspage) | none | GET | READ_ONLY | PUBLIC | strong runner-up — official status JSON; kept as documented alternative |

---

## 3. Selected provider — `github_meta`

- **provider_id:** `github_meta`
- **display name:** GitHub Meta (public infrastructure metadata)
- **owner:** GitHub, Inc.
- **official documentation:** https://docs.github.com/en/rest/meta/meta#get-github-meta-information
- **endpoint:** `https://api.github.com/meta`
- **method / operation:** `GET` / `get_meta` (single read-only operation)
- **auth:** none (unauthenticated). Unauthenticated rate limit is 60 requests/hour — far above the M33 budget of 1–3 calls.
- **side-effect class:** `READ_ONLY` (zero writes, zero account interaction)
- **data classification:** `PUBLIC` (published infrastructure metadata: IP ranges, versions, capability flags)
- **schema:** stable documented JSON object — booleans (`verifiable_password_authentication`), string (`ssh_key_fingerprints` object), and arrays of CIDR strings (`hooks`, `web`, `api`, `git`, `packages`, `pages`, `importer`, `actions`, `dependabot`), plus `domains` and `ssh_keys`.
- **rate-limit behavior:** exposes `x-ratelimit-limit`, `x-ratelimit-remaining`, `x-ratelimit-reset`; `429` carries `retry-after`. Ideal for exercising real rate-limit parsing.
- **response size:** small (single-digit KB → tens of KB). Bounded well under the 256 KiB ceiling.
- **uptime dependency:** GitHub API is highly available but remains an external dependency (limitation, not a repository test dependency — offline tests use fixtures).
- **privacy:** no personal data, no caller identifier echoed, no cookies, no auth.

### Why selected

1. **Official, named owner** with first-party documentation and published terms — satisfies the "official + clear terms" criteria that community APIs (candidates 3–7) fail.
2. **Genuinely credential-free and read-only.** No API key, no account, no OAuth, no writes. The unauthenticated endpoint is documented as public.
3. **Non-mutating.** The `production GitHub mutation` prohibition concerns write operations against GitHub accounts/repos. `GET /meta` performs **zero** writes, touches **no** account, and returns only published infrastructure metadata. No account is connected; no credential is used. The prohibition is preserved.
4. **Rich, stable, documented schema** — enables real schema-compatibility verification and drift classification.
5. **Real rate-limit headers** — enables genuine rate-limit-awareness verification instead of a header-less guess.
6. **Small bounded JSON** — safe for response-size ceilings and fixture capture.

### Explicit limitations (recorded, not hidden)

- One provider, one endpoint, one read-only operation (`get_meta`) only.
- Success here proves external read-only compatibility for **this** endpoint only — it does **not** generalize to other GitHub operations, does **not** authorize writes, and does **not** imply CANARY/ACTIVE eligibility.
- Provider uptime, terms, and schema are external and may change.
- No account link, no credential, no OAuth.

---

## 4. Terms / privacy / acceptable-use assessment

- GitHub REST API is public and documented; unauthenticated access to `/meta` is expected and rate-limited (60/hr).
- No scraping, no browser automation, no user-generated side effects, no login.
- M33 uses **1** live call by default (max 3 with explicit justification) — deep within acceptable-use.
- No personal data is requested, stored, or committed. Fixtures are sanitized (see `docs/M33_FIXTURE_POLICY.md`).

**terms_review_status:** `REVIEWED_ACCEPTABLE`

---

## 5. Rejected candidates — reasons summary

- **Caller-IP echoers (Cloudflare trace, ipify):** return the requester's egress IP — borderline personal/telemetry; avoided on privacy-conservatism.
- **Community/third-party reference APIs (restcountries, worldtimeapi, nager.date, httpbin):** non-authoritative ownership, weaker/unclear terms, or uptime limitations that conflict with "stable public endpoint" and "clear terms."
- **Anything financial / trading / social / email / calendar:** rejected by hard rule; regression tests assert these can never be selected.

---

## 6. Operator approval requirements

- Live verification is **operator-triggered only** (`external-verify <id> --ack-read-only --ack-network`) and excluded from the standard test suite.
- Rollout stays OFF regardless of verification outcome.
- No production authority, no write authority, no account link is granted by M33.
