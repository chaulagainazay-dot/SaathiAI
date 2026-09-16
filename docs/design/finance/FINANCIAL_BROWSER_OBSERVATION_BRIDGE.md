# SaathiOS — Financial Browser Runtime Observation Bridge

**From `6f15db37`.** Solves the structural blocker `BLOCKED_OWNER_BROWSER_RUNTIME_NOT_SHARED`:
`FinancialBrowserRuntimeManager` is an in-process singleton, so the owner's headed Playwright
context lives only in the SaathiOS backend process that created it; any second process (a
validation tool, the Claude build sandbox) gets a fresh empty singleton and cannot reach the
owner's `Page`/`BrowserContext`. This milestone adds a **narrow authenticated loopback bridge**
that lets a local consumer request *normalized observations* from the browser-owning process —
never browser control.

## Canonical process topology (Phase 0)
One FastAPI app (`saathi/server.py`, title "SaathiAI"), backend `127.0.0.1:8765`
(`SAATHI_HOST`/`PORT`), launched by launchd `com.ajay.saathiai` → `scripts/start_baadar.sh`.
`:3100` is the Next.js frontend proxy, not the backend. **FastAPI and
`FinancialBrowserRuntimeManager` share the same process** (module-level `_MANAGER` singleton),
so the bridge lives INSIDE that backend process — no new daemon, event bus, or browser
process. Earlier validation saw `:8765`/`:3100` = no listener simply because that backend was
not running in / reachable from the build sandbox.

## Bridge = normalized observations, not browser control (critical principle)
```
Owner → OwnerFinancialBrowser → Playwright Page → FinancialBrowserRuntimeManager
      → FinancialPageObserver → redaction/allowlist → PortfolioSnapshot
      → authenticated loopback observation API → local consumers / validation
```
The observer executes INSIDE the browser-owning process; only the typed/redacted result crosses
the boundary. Playwright objects, raw DOM/HTML, cookies, tokens, screenshots **never** cross.

## Narrow service (`observation_bridge.py`)
`FinancialBrowserObservationService` (process singleton) exposes only:
`status(provider)`, `observe_portfolio(provider)`, `observe_account_summary(provider)`,
`observe_structure(provider)` (owner-authorized, sanitized), `evidence(provider)`
(privacy-minimized). **No** page/context/browser/click/type/navigate/submit/evaluate/download/
screenshot/dom/html/cookies attribute exists (test-enforced).

## Gating (Phases 4, 14, 15, 16, 21, 22)
Every observation verifies, in order: provider resolves; runtime exists & not closed
(`FINANCIAL_BROWSER_RUNTIME_NOT_FOUND`); provider matches the addressed runtime else
`PROVIDER_RUNTIME_MISMATCH`; owner authenticated else `OWNER_FINANCIAL_LOGIN_REQUIRED` /
`OWNER_REAUTHENTICATION_REQUIRED`; session not expired (TTL); Saathi Read ON else
`SAATHI_READ_DISABLED`; live page present else `OWNER_FINANCIAL_PORTFOLIO_PAGE_REQUIRED`;
current hostname within provider policy domain else `PROVIDER_DOMAIN_OUT_OF_SCOPE`; not a
sensitive surface (login/otp/withdraw/order/transfer/settings/…) else
`SENSITIVE_PAGE_OBSERVATION_BLOCKED`. Structure inspection additionally requires explicit
`authorize_structure_inspection` (owner) else `STRUCTURE_INSPECTION_NOT_AUTHORIZED`.

## Authenticated loopback (Phase 3) + routes (Phase 24)
Routes reuse the existing SaathiOS auth (global `_auth` middleware over `/api/*` + per-route
`_is_authed`/`_is_local`); no second auth system. Bound to `127.0.0.1` only. Unauthenticated →
401.
- `GET  /api/v1/finance/browser/runtimes` (now auth-gated)
- `POST /api/v1/finance/browser/{open,mark-authenticated,saathi-read,close}` (now auth-gated)
- `GET  /api/v1/finance/browser/portfolio` (now auth-gated)
- `GET  /api/v1/finance/browser/{provider}/status`
- `POST /api/v1/finance/browser/{provider}/observe-portfolio`
- `POST /api/v1/finance/browser/{provider}/observe-structure`  (owner-authorized, sanitized)
- `GET  /api/v1/finance/browser/{provider}/evidence`  (validation projection)

## Response contract (Phases 6, 7)
Typed envelope: provider, runtime_id, runtime_state, authentication_state, saathi_read_state,
observation_state, observed_at, freshness, available, state, holding_count, and either the
authorized `view` (PortfolioSnapshot projection — UI/chat/voice) or the privacy-minimized
`evidence` projection (holding_count, resolved/unresolved symbol counts, available field
**names**, source classification, schema_state — **no owner quantities/values**). The frozen
`PortfolioSnapshot` contract is unchanged.

## Sanitized structure observation (Phases 9, 10, 27)
`FinancialPageStructureObserver.observe_structure` returns shape only: table/grid presence, row
count, column count, allowlist-classified + redacted header labels, candidate row/field
selectors, allowed/private field **names**, `selectors_verified`. It never returns owner cell
values, names, account ids, textContent, innerHTML, raw DOM, cookies, or tokens
(test-asserted: 0 owner values in output).

## Concurrency / cache / invalidation (Phases 18, 19, 21, 22)
Per-provider single-flight lock collapses concurrent consumers to one DOM traversal; a bounded
5 s cache serves UI/chat/voice/validation. Any gate failure, kill switch (`disable_saathi_read`),
`close`, or session expiry invalidates the cache (gates are re-checked before every cache hit;
`close` also explicitly invalidates).

## Certification proof (Phases 29, 30)
`tests/test_finance_observation_bridge_v1.py` (20 tests): a REAL backend subprocess
(`tests/_bridge_boot.py`) owns a seeded runtime + live page; the pytest process (second
process, authenticated via `SAATHI_TOKEN`) obtains the **same runtime_id**, receives a
**normalized observation** (holding_count + view) with **no raw DOM/HTML/cookie/token/
screenshot** in the payload, confirms there is **no generic DOM/browser-control endpoint**
(guessed `/dom`, `/html`, `/evaluate`, `/click`, `/page` → 404), gets the evidence projection
without owner values, and confirms `close` from the second process invalidates observation. A
separate test drives a REAL headless Chromium page (file://) through the actual
`ReadOnlyPageReader` + structure observer, proving the real-browser read path is read-only and
leaks 0 owner values. No credentials, no trading.

## Resource (Phase 31)
Bridge adds **no new Chromium** (imports no Playwright, launches nothing). Measured:
status ≈ 0.004 ms, cached observe ≈ 0.007 ms, fresh observe ≈ 95 ms (dominated by one-time
Official-NEPSE enrichment init, not the bridge).

## Security / authority (Phases 32, 33)
Across the bridge: raw DOM / HTML / cookies / tokens / passwords / OTP / screenshots /
Playwright objects / generic browser-control RPC = **0**. TMS BUY/SELL/MODIFY/CANCEL/TRANSFER/
WITHDRAW = 0; Binance trading/orders/withdrawal = 0; bridge clicks/typing/navigation/
submissions = 0; `ExecutionGateway.execute` = 0; Trading Guardian trade calls = 0; portfolio
mutations = 0. Browser-guard `scan_repository().ok` = True (bridge/observer import no raw
Playwright; the headed runtime remains the only allowlisted driver).

## Frozen baselines (Phase 35)
`64fb2b2b` (security contract + PortfolioSnapshot), `a1136aa3` (workspace), `b771d761`
(research), `4d685383` (fusion), `97fce540` (Binance API adapter), `6f15db37` (TMS read
pipeline) — all 0 diffs. Provisional TMS selectors **unchanged**; observer changes are pure
additions (`current_url`, `header_labels`, structure observer) that reference existing selectors
without modifying them.

## Verdict
A local authenticated SaathiOS consumer can safely request normalized observations from the
process that owns the Financial Browser — proven across a real process boundary with zero
browser control and zero private-channel leakage ⇒
**SAATHIOS_FINANCIAL_BROWSER_RUNTIME_OBSERVATION_BRIDGE_CERTIFIED.**
This does NOT certify TMS or Binance browser portfolio reads, and does not freeze external DOM.

## Exact next milestone (do NOT start now)
Resume `M — TMS_BROWSER_PORTFOLIO_READ`: owner starts canonical SaathiOS → Finance → Browser →
selects TMS → logs in manually → opens Holdings → enables Saathi Read; then the validation
process uses this certified bridge (`observe-structure` → evidence-backed selector replacement →
one `observe-portfolio` read → PortfolioSnapshot → Official-NEPSE enrichment → UI/chat/voice →
TMS observer certification).
