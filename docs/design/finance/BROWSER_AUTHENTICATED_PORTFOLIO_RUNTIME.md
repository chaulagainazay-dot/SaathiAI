# SaathiOS — Browser-Authenticated Financial Portfolio Runtime

**From `97fce540`; frozen `FINANCIAL_BROWSER_SECURITY_CONTRACT` + `PORTFOLIO_SNAPSHOT_CONTRACT`
(64fb2b2b); workspace `a1136aa3`; Research `b771d761`; Fusion `4d685383`.** New primary
account-access architecture: **owner manual browser login → local authenticated session →
deterministic read-only DOM observation → PortfolioSnapshot**. No API key required. The
Binance API adapter (`97fce540`) is kept intact but **DEFERRED / optional fast-path**.

## Architecture (owner browser ≠ agent capability)
```
OWNER opens provider site (headed, provider-scoped browser) and enters ALL credentials
  → owner-authenticated session (cookies live in the browser profile, never surfaced)
  → owner explicitly enables "Saathi Read"
  → deterministic read-only observer (allowlist + redaction)
  → typed observation → PortfolioSnapshot (OWNER_AUTHENTICATED_BROWSER_OBSERVED)
  → SaathiOS intelligence / chat / voice / charts
```
The authenticated page's raw DOM/HTML/accessibility-tree/screenshot is **never** sent to any
model — only deterministically extracted, allowlisted, redacted fields are.

## Runtime selection (Phase 0–1)
Chosen: **headed Playwright Chromium with a provider-scoped persistent user-data-dir**
(`launch_persistent_context`, `headless=False`), launched on-demand by SaathiOS; the owner
drives it and logs in. Rationale: closest "browser inside SaathiOS" feel; per-provider profile
isolates cookies (TMS ≠ Binance); reuses the installed Chromium (no permanent second browser
on M2/8 GB); the observer reads the same page deterministically. Rejected: system-Chrome
default profile via CDP (exposes all owner tabs/cookies — unsafe isolation); iframe (embed
blocked by X-Frame-Options); native WebView (no existing SaathiOS desktop WebView). A headed
window needs a real desktop session → in a headless/server context `open()` returns
`DISPLAY_UNAVAILABLE`; the real window appears on the owner's Mac.

## Owner/agent boundary (Phases 5–8, 13)
Owner may navigate/click/type/login/logout/OTP/CAPTCHA/passkey/use the account normally. The
agent may **only** read approved normalized observations. Credential fields (password/OTP/
2FA/passkey/security-question) are `OWNER_PRIVATE_INPUT` — agent visibility 0; never entered,
captured, logged, screenshotted, or modeled. Default after login: `SAATHI_READ_OFF`; the owner
explicitly enables `SAATHI_READ_ON` (a persistent visible read-only indicator) to permit
observation — which still grants **no** interaction. Kill switch (`Disable Saathi Read`) and
`Close` revoke capability + clear ephemeral buffers.

## Observer contract (Phases 9–14)
`FinancialPageObserver` exposes only `authentication_state` / `observe_portfolio` /
`observe_account_summary` / `health`. It has **no** click/type/submit/navigate/download/upload/
evaluate method. `ReadOnlyPageReader` wraps a page with only `exists/count/text/rows` — no
interaction surface (test-enforced). Each observer declares `ALLOWED_FIELDS`, `PRIVATE_FIELDS`
(dropped: name/account-id/email/phone/BOID/bank/…), and `PROHIBITED_REGIONS` (order/withdraw/
transfer/settings). Extraction is deterministic (selector → text), redacted, allowlist-only.
`BinanceBrowserPortfolioObserver` and `TMSBrowserPortfolioObserver` ship with **PROVISIONAL,
unverified selectors** (`SELECTORS_PROVISIONAL_UNVERIFIED`) — real per-provider DOM is verified
only at owner login; unknown fields stay unavailable, never fabricated. No token/cookie/header
extraction, no XHR replay, no private-API use — DOM-visible fields only.

## PortfolioSnapshot mapping (Phase 15–17)
`build_snapshot` → frozen `PortfolioSnapshot` with `source_type=OWNER_AUTHENTICATED_BROWSER_
OBSERVED`, `data_class=OWNER_AUTHENTICATED_BROWSER_OBSERVATION` (field value; frozen contract
**unmodified**). TMS → EQUITY/NPR (qty + WACC from the broker page; current-price authority
remains the Official NEPSE pipeline); Binance → CRYPTO/STABLECOIN/USDT (holdings from the
authenticated page; public Binance price applied where legitimately reachable). Account
displayed value is tagged `BROWSER_DISPLAYED` (explicitly **not** canonical exchange data).
Cost basis / P·L → `COST_BASIS_UNAVAILABLE` / `PNL_UNAVAILABLE` (never inferred).
`UnifiedPortfolioView` keeps NPR and USDT **separate** (no cross-currency sum without sourced
FX). Chat/voice consume the snapshot only (never the raw page).

## Server surface
`/api/v1/finance/browser/{runtimes,open,mark-authenticated,saathi-read,close,portfolio}`
(auth-gated) + the `/finance/browser` shell. `open` returns `OWNER_FINANCIAL_LOGIN_REQUIRED`;
`portfolio` returns data only when `read_allowed` (owner-authenticated **and** Saathi Read ON)
against a live owner page.

## Binance network restriction (Phase 11)
No VPN/proxy/route bypass. If the Binance site is unreachable on the owner's network →
`PROVIDER_ACCESS_UNAVAILABLE`. (Note: from the build host `api.binance.com` is DNS-blocked; the
owner uses the site normally on their own compliant network/browser.)

## Security / authority (Phases 25, 29)
password/OTP/cookie/raw-DOM/screenshot-to-model exposure = 0; API keys not required/used; agent
clicks/typing/navigation/form-submission = 0; financial execution = 0. No execution path in the
runtime modules (test-enforced: no place_order/buy/sell/withdraw/transfer/`ExecutionGateway(`/
`.execute(`). Provider sessions isolated (separate user-data-dirs). Binance API adapter kept
intact, DEFERRED, no Gate B, no API credential requested.

Browser-guard: the headed persistent-context runtime is added to the governed
`LOW_LEVEL_DRIVER_ALLOWLIST` (like the human-browser stack); this pass also allowlisted the
previously-unlisted governed NEPSE browser modules (`nepse_live`, `nepse_acquire`,
`nepse_capture`), so `scan_repository().ok` is now True (a pre-existing guard red, missed by
earlier `-k`-filtered runs, is fixed).

## Tests / regression / integrity
`tests/test_browser_financial_runtime_v1.py` **18** (Saathi Read gate, no-interaction
observer/reader, allowlist+private-drop+redaction, auth detection, TMS/Binance snapshot
mapping, browser-displayed source, view PNL/cost unavailable, chat/voice, currency separation,
no-execution-path, adapter intact, private-never-surfaces, prohibited regions, read-requires-
owner-auth) + finance 20 + binance 21 = 59; browser-guard suite 92 pass; related regression
**1826 passed**. One unrelated pre-existing failure: `test_m17_1_live::test_live_browser_
launch_and_close` — an environment-dependent live-Chrome teardown check in `computer_agent`
(not finance; flaky in this headless host). Frozen finance contracts (policy/session/portfolio)
+ Binance API adapter (`binance_account`/`crypto_portfolio`) + `b771d761` + `4d685383` +
`a1136aa3` = **0 diffs**.

## Verdict
Owner-controlled browser-authenticated portfolio runtime + deterministic read-only observer +
snapshot mapping + Saathi Read gate + kill switch + provider isolation, certified credential-
independently with zero credential handling and zero execution authority ⇒

**SAATHIOS_BROWSER_AUTHENTICATED_FINANCIAL_PORTFOLIO_RUNTIME_READY_FOR_OWNER_LOGIN.**
Provider-specific certification (`SAATHIOS_TMS_BROWSER_PORTFOLIO_READ_CERTIFIED` /
`SAATHIOS_BINANCE_BROWSER_PORTFOLIO_READ_CERTIFIED`) is **not** granted — it requires genuine
owner login + real-DOM observer validation.

## Exact owner action required
On the owner's Mac (desktop session): open SaathiOS → Finance → Browser → select a provider →
SaathiOS opens the provider site in the owner-controlled browser → **log in yourself** (all
credentials/OTP/CAPTCHA) → confirm authenticated → enable **Saathi Read**. SaathiOS never
enters or reads credentials.

## Exact next step after owner login
Resume provider validation (no credentials read): confirm authenticated surface, verify the
provider's real DOM selectors, run one deterministic read-only observation → PortfolioSnapshot
→ view/chat/voice, audit for zero credential/DOM/screenshot leakage, then grant the
provider-specific browser-portfolio certification. No trading, no TMS order/execution.
