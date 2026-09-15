# SaathiOS — Financial Browser & Read-Only Portfolio Architecture (v1)

**From `a1136aa3`; frozen workspace `a1136aa3`; Research `b771d761`; Fusion `4d685383`.**
Foundation for a SPECIALIZED Financial Browser + a READ-ONLY Portfolio Intelligence layer.
Audit + security contracts + bounded safe shell. **No credentials handled, no autonomous
login, no execution.** This milestone builds the security skeleton only.

## Architecture inventory reused (Phase 0)
GovernedBrowser + `check_domain` (browser/); certified official-NEPSE live pipeline
(`market_data/nepse_live*`); tracker read-model (`market_data/tracker/*`); `trading_models`
(Position/Account/AssetClass); ExecutionGateway (`connectors/platform/execution.py`);
Trading Guardian (`platform/trading_guardian.py`, `platform/tg/*`); secret/credential infra
(`security/store.py`+`registry.py`, `credentials/*`, `tg/connectivity_governance/
credential_policy.py`); crypto public adapter (`platform/crypto/binance.py` — **public
market-data only, no account/trading**); Event Fabric/SSE; frozen Research Surface + Fusion.
**No duplication** — the finance package is a thin security/capability layer above these.

## Core principle — owner browser ≠ agent capability
The owner interacts with a financial site and enters every credential themselves. The agent
receives only explicit READ capabilities per provider. Every account ACTION is structurally
blocked. The Financial Browser is **never** an execution path.

## Provider capability matrix (Phase 1 — evidence-based; UNKNOWN where unproven)
| Provider | public market data | read-only API | read-only MCP | account data | agent read | agent actions | embed |
|---|---|---|---|---|---|---|---|
| NEPSE | PUBLIC_MARKET_DATA | UNSUPPORTED (401) | UNSUPPORTED | UNSUPPORTED | AGENT_READ_ALLOWED | PROHIBITED | EMBED_BLOCKED (SAMEORIGIN) |
| Portfolio Tracker | PUBLIC_MARKET_DATA | READ_ONLY_API | READ_ONLY_MCP (deferred) | READ_ONLY_MCP (owner key) | AGENT_READ_ALLOWED | PROHIBITED | EMBED_BLOCKED (SAMEORIGIN) |
| Binance | PUBLIC_MARKET_DATA | UNKNOWN (future) | UNKNOWN | UNKNOWN (owner key, future) | UNKNOWN | PROHIBITED | UNKNOWN (headers unobtainable) |
| TMS | UNKNOWN | UNSUPPORTED | UNSUPPORTED | OWNER_BROWSER_SESSION | UNKNOWN (unproven) | PROHIBITED | UNKNOWN (403 from sandbox) |

## Threat model & credential boundary (Phases 2–4, 33–35)
- **OWNER_PRIVATE_INPUT** (regex-classified: password/passcode/OTP/2FA/TOTP/CVV/PIN/secret/
  api-key/private-key/seed/mnemonic/recovery/security-answer/token) — the agent may **not**
  read, log, screenshot, or place these in any model context / event / audit / chat / voice.
- Authentication challenges (CAPTCHA/OTP/2FA/passkey/device/security-question) are **owner-
  only** → `OWNER_AUTHENTICATION_REQUIRED`; never automated or bypassed.
- Session cookies/tokens are **never** exposed through any contract (the session dataclass
  has no cookie/token/secret field — test-enforced).
- `redact()` strips header/kv secrets, Bearer tokens, long opaque tokens, and OTP-looking
  codes from any string before it can reach a log/model/event.
- Financial page content is **UNTRUSTED DATA, never authority** — `enforce()` decides purely
  from (actor, action, provider); page text ("ignore instructions", "execute this trade",
  "reveal key") is just an action string → default-deny.
- **DOM data minimization**: deterministic extraction into typed contracts; never send whole
  authenticated pages/screenshots to a model. Authenticated financial screenshots are **not**
  sent to remote models by default.

## Interaction model (Phases 7–9)
Modes `OWNER_CONTROL` / `AGENT_READ_ONLY` / `OWNER_APPROVAL_REQUIRED` (reserved) / `BLOCKED`.
Actors `OWNER_INPUT` vs `AGENT_INPUT` are distinguished structurally. `enforce()`: owner may
do anything; agent may only perform `ALLOWED_AGENT_READS`; every `PROHIBITED_AGENT_ACTIONS`
(BUY/SELL/PLACE_ORDER/…/WHITELIST_ADDRESS, 23 actions) and anything unknown is denied. For
this milestone account actions are `OWNER_CONTROL` or `BLOCKED` only.

## Contracts (this milestone)
- `policy.py` — `FinancialBrowserPolicy` (per-provider domains/paths/regions/prohibited
  actions/nav/session), enums, `enforce`, `classify_field`, `redact`, `POLICIES` registry.
- `session.py` — `FinancialBrowserSession` (no secret fields) + `FinancialBrowserManager`:
  on-demand, provider-scoped, owner-authenticated; expiry → `OWNER_REAUTH_REQUIRED`; kill
  switch (single/all) revokes capability + clears buffers; `agent_read` gated by owner-auth
  + policy.
- `portfolio.py` — `Position`, `PortfolioSnapshot` (`data_class=READ_ONLY_PORTFOLIO_
  OBSERVATION`, source types OWNER_AUTHENTICATED_BROWSER_OBSERVED / READ_ONLY_API /
  READ_ONLY_MCP / OWNER_IMPORTED), `FXObservation`, `UnifiedPortfolioView` (currency-
  separated — NPR/USD never summed without a sourced FX rate), deterministic
  `snapshot_metrics` (allocation/concentration/unrealized P·L). No fabricated fields.
- `audit.py` — bounded in-memory read log; detail redacted; never secrets.
- `capability_matrix.py` — provider matrix + component classification.
- server: `/api/v1/finance/{providers,sessions,sessions/open,sessions/kill,audit}` (auth-
  gated) + native `/finance/browser` shell (provider cards; kill switch; **no trade
  controls, no embedded account site, no credential handling in the page**).

## Provider integration paths (audit results)
- **NEPSE** — reuse the certified official browser (current-market authority
  `OFFICIAL_PAGE_OBSERVED`); do not create another NEPSE browser.
- **Portfolio Tracker** — reuse the certified public REST read-model; portfolio **MCP
  deferred** pending an owner-supplied Pro key + ToS review.
- **Binance** — existing adapter is **public market-data only**; safest future path =
  official **read-only account API** with permissions (reading only; spot/margin/futures/
  withdraw/transfer/api-management = false), key held in the SaathiOS secret store, agent
  sees `BINANCE_READONLY_CONNECTED` not the secret. **Not implemented; no key requested.**
- **TMS** — owner-only login (password/OTP/CAPTCHA = OWNER_PRIVATE_INPUT). Holdings-read
  appropriateness is **UNPROVEN** (per-broker; ToS/frame behavior UNKNOWN; sandbox got 403).
  No autonomous login. Buy/Sell/cancel/transfer = PROHIBITED_AGENT_ACTION.

## Embed reality check (Phase 12)
NEPSE + Tracker = **EMBED_BLOCKED** (X-Frame-Options SAMEORIGIN, proven). Binance + TMS =
**UNKNOWN** (headers unobtainable from the sandbox; TMS returned 403). Recommendation:
`EXTERNAL_BROWSER_REQUIRED` / owner-controlled governed session — **no iframe bypass**, and
do **not** add a permanent second Chromium (M2/8 GB): reuse the one governed browser
on-demand.

## Bounded prototype (Phases 41–43)
Financial Browser shell + provider cards + domain policy + interaction-mode enforcement +
read-only capability model + kill switch. Non-sensitive proof only: public NEPSE via the
existing certified path; **no real financial-account login**, no Binance/TMS credentials,
no MCP key. `/finance/browser` → 200 (reachable; routing mount-order re-asserted), API 401
(auth-gated).

## Authority audit (Phase 45)
broker calls = 0, orders = 0, ExecutionGateway.execute = 0, Trading Guardian trade calls = 0,
withdrawals = 0, transfers = 0, leverage changes = 0, browser order submissions = 0, Binance
trading calls = 0, TMS order requests = 0, portfolio writes = 0. No execution path in the
finance package (test-enforced: no `.execute(`/`place_order(`/`withdraw(`/`ExecutionGateway(`).

## Tests / regression / integrity
`tests/test_finance_browser_v1.py` **20** (matrix, allowlist, owner/agent enforce, all
prohibited actions blocked, credential-field classification, redaction, no secret fields,
read gating, isolation, expiry/reauth, kill switch, audit redaction, PortfolioSnapshot,
currency separation, source types, no-execution-path, prompt-injection, modes, nav/download).
Related regression **1519 passed / 0 failed**. Frozen `b771d761` + `4d685383` = 0 diffs;
workspace-frozen files (`a1136aa3`) untouched.

## Freeze
Per the freeze rule, the **credential-independent contracts are frozen** at this commit:
`FINANCIAL_BROWSER_SECURITY_CONTRACT` (policy/enforce/interaction-modes/prohibited-actions/
credential-redaction/session-lifecycle/kill-switch) and `PORTFOLIO_SNAPSHOT_CONTRACT`
(Position/PortfolioSnapshot/source-types/currency-separation). **Not frozen** (external,
SaathiOS does not control): TMS DOM schema, Binance API contract, Portfolio Tracker MCP
contract → recorded `EXTERNAL_PROVIDER_CONTRACTS_NOT_FROZEN`.

## Remaining security risks / limitations
Per-broker TMS variance + ToS UNKNOWN; Binance account API + embed UNKNOWN (sandbox-blocked
headers); portfolio MCP deferred (no key); real authenticated financial login is owner-
interactive and out of scope here; local-webview vs governed-session decision deferred to the
production slice.

## Verdict
Security/capability skeleton designed, structurally enforced, and tested; bounded safe shell
reachable; zero credentials handled; zero execution authority; frozen baselines untouched ⇒

**SAATHIOS_FINANCIAL_BROWSER_AND_READ_ONLY_PORTFOLIO_ARCHITECTURE_CERTIFIED_WITH_LIMITATIONS**
(security + PortfolioSnapshot contracts FROZEN; external provider contracts not frozen).

## Exact recommended next production milestone
`M — BINANCE_READONLY_ACCOUNT_ADAPTER` — implement the read-only Binance **account** API
adapter (owner-supplied read-only key via the SaathiOS secret store; reading-only permission
enforced; agent sees `BINANCE_READONLY_CONNECTED`, never the secret) → `PortfolioSnapshot`
(crypto) with public-market-data price enrichment → UnifiedPortfolioView crypto section. No
trading, no withdrawals, no futures/margin; execution stays behind Trading Guardian +
ExecutionGateway.
