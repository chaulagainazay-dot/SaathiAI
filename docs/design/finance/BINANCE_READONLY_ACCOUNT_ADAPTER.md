# SaathiOS — Binance Read-Only Account Adapter (Gate A)

**From `64fb2b2b`; frozen contracts `FINANCIAL_BROWSER_SECURITY_CONTRACT` +
`PORTFOLIO_SNAPSHOT_CONTRACT` (64fb2b2b); workspace `a1136aa3`; Research `b771d761`; Fusion
`4d685383`.** First real financial-account provider — **read-only**. Gate A is
credential-independent (mock transports, no network, no secrets). **No credential was
requested or handled.**

## Two gates
- **GATE A (this milestone):** implementation + credential-independent certification. DONE.
- **GATE B (owner):** real read-only account connection — requires the owner to configure a
  Binance **read-only** API key via the SaathiOS secret store, independently. Owner
  credential is **not** configured → **STOP at Gate A** with
  `OWNER_BINANCE_READONLY_CREDENTIAL_REQUIRED`. The agent never asks for the key in chat.

## Reused architecture (Phase 0)
`CredentialRef` + `resolve_secret` (env/keychain secret references — values never stored);
`BinancePublicProvider` base (`api.binance.com/api/v3`); frozen `PortfolioSnapshot`/`Position`/
`UnifiedPortfolioView`; `finance/policy.py` (OWNER_PRIVATE_INPUT, redact); `finance/audit.py`;
`finance/session.py` kill-switch pattern. `crypto/binance.py` is **public market-data only**
(no account/trading) — confirmed; not extended with trading.

## Official contract used (Phase 1)
Stable Binance Spot endpoints (live-doc fetch was DNS-blocked in the build sandbox; real
field names re-verified at Gate B against the live API):
- `GET /api/v3/time` (public) — clock skew.
- `GET /api/v3/ticker/price` (public) — current price.
- `GET /api/v3/account` (SIGNED) — `balances[{asset,free,locked}]`, `canTrade/canWithdraw`.
- `GET /sapi/v1/account/apiRestrictions` (SIGNED) — `enableReading`, `enableWithdrawals`,
  `enableSpotAndMarginTrading`, `enableMargin`, `enableFutures`, `enableInternalTransfer`,
  `permitsUniversalTransfer`.
Signature HMAC-SHA256(query, secret); header `X-MBX-APIKEY`.

## Signed endpoint allowlist (Phases 26–28)
`SIGNED_READ_ALLOWLIST = {/api/v3/account, /sapi/v1/account/apiRestrictions}` — the **only**
endpoints that may ever be signed. `_signed_get` raises `EndpointBlocked` for anything else
(order/withdraw/transfer/margin/futures all `BINANCE_ENDPOINT_BLOCKED` — tested). There is
**no generic signed-request method**, no `place_order`/`withdraw`/`transfer`/`set_leverage`/
`enable_*`/`post`/`request`/`order` method on the adapter (tested). Module has **no POST/PUT/
DELETE** and no `.execute(`/`ExecutionGateway(` (tested). HTTP: GET-only.

## Permission model & assessment (Phases 2–3)
`assess_permissions` is **default-deny**: SAFE (`READ_ONLY_CONFIRMED`) only when
`enableReading` is true AND every trading/withdraw/margin/futures/transfer flag is false AND
account `canTrade`/`canWithdraw` are false; otherwise `UNSAFE_TRADING/WITHDRAW/MARGIN/FUTURES/
TRANSFER_PERMISSION`, `PERMISSION_UNKNOWN`, or `CREDENTIAL_INVALID`. A read is refused unless
`READ_ONLY_CONFIRMED` (→ `PERMISSION_UNSAFE`/`AUTH_FAILED`).

## Secret handling (Phases 4, 16, 46)
Secrets are env-backed `CredentialRef`s (`BINANCE_API_KEY`/`BINANCE_API_SECRET`), resolved
via `resolve_secret` only inside the signing scope, never stored on the instance, returned,
logged, screenshotted, or placed in snapshot/model/event/audit. `redact()` strips secret/
signature-looking strings. Agent sees only `BINANCE_READONLY_CONNECTED` /
`BINANCE_OWNER_ACTION_REQUIRED` / `BINANCE_PERMISSION_UNSAFE`.

## Portfolio mapping (Phases 8–17)
`build_snapshot` (only after `READ_ONLY_CONFIRMED`) → frozen `PortfolioSnapshot`
(`provider=BINANCE`, `account_type=CRYPTO`, `source_type=READ_ONLY_API_ACCOUNT_DATA`,
`data_class=READ_ONLY_ACCOUNT_OBSERVATION` — passed as a field value; frozen contract
**unmodified**). Zero balances filtered; locked preserved; stablecoins classified
(`STABLECOIN` set). Public price enrichment via `/ticker/price`; valuation in USDT;
stablecoins **not** assumed 1:1 (USDC priced via `USDCUSDT`); no path → `PRICE_UNAVAILABLE`
(retained, never fabricated). Cost basis / P·L are **not available** from balances →
`COST_BASIS_UNAVAILABLE` / `PNL_UNAVAILABLE` (never inferred). Dust (<1 USDT) flagged,
retained. `crypto_view` = total/allocation/stablecoin%/crypto%/locked%/largest, descriptive
only. `UnifiedPortfolioView` keeps USDT and NPR **separate** (no cross-currency sum without a
sourced FX rate).

## Consumers, cache, states, kill/disconnect (Phases 18–36)
`BinanceConnection`: one bounded cached snapshot (TTL 60 s) → many consumers (Financial
Browser / Central Command / chat / voice); typed `ConnectionState`
(NOT_CONNECTED/OWNER_ACTION_REQUIRED/READ_ONLY_CONNECTED/PERMISSION_UNSAFE/AUTH_FAILED/…).
Kill switch revokes agent capability + clears the ephemeral snapshot (secret **not** deleted).
Disconnect → NOT_CONNECTED. Clock-skew via public `/time`. Deterministic chat/voice reuse the
same view (P·L question answers `PNL_UNAVAILABLE`). Server: `/api/v1/finance/binance/
{status,portfolio,disconnect,kill,chat}` (auth-gated) + native `/finance/crypto` view (no
Buy/Sell/Swap/Deposit/Withdraw/Transfer controls). SPA mount re-asserted last.

## Gate A authority audit (Phase 38)
Binance trading/order/withdrawal/transfer/margin/futures calls = 0; broker = 0; orders = 0;
`ExecutionGateway.execute` = 0; Trading Guardian trade calls = 0; portfolio provider writes =
0. No execution path (test-enforced). No Chromium (REST only).

## Tests / regression / integrity
`tests/test_binance_readonly_v1.py` **20** (permission safe/unsafe/crosscheck, endpoint
allowlist, no-exec-methods, no-exec-source, snapshot mapping, balances/locked/stablecoin,
pricing/missing-quote, stablecoin-not-1:1, allocation, no-fabricated-P·L, unsafe-blocks-read,
currency separation, chat/voice, cache, kill/disconnect, clock-skew, audit-no-secrets,
owner-action-required) + finance 20 = 40; related regression **1333 passed / 0 failed**.
Frozen finance contracts (policy/session/portfolio) + `b771d761` + `4d685383` + workspace
`a1136aa3` = **0 diffs**.

## Limitations / external
Gate B (real account) not executed — owner credential not configured. Live Binance
field-name/doc verification was network-blocked in the sandbox (re-verify at Gate B). Cost
basis / P·L unavailable from balances (future: trade-history source, separately validated).
Valuation currently direct-USDT (else PRICE_UNAVAILABLE); multi-hop routing future.
`BINANCE_EXTERNAL_API_CONTRACT_DEPENDENCY` — SaathiOS does not control the Binance API.

## Verdict
Read-only Binance account adapter implemented and certified credential-independently:
default-deny permission assessment, signed-read allowlist, no execution path, deterministic
read-only PortfolioSnapshot + crypto view, secret non-exposure, kill/disconnect, zero trade
authority ⇒

**SAATHIOS_BINANCE_READONLY_ACCOUNT_ADAPTER_READY_FOR_OWNER_CONNECTION.** Not frozen (full
freeze requires Gate B). STOP before real account access —
`OWNER_BINANCE_READONLY_CREDENTIAL_REQUIRED`.

## Owner-side connection procedure (Gate B, owner performs — not via chat)
1. On Binance, create an API key with **only "Enable Reading"** (no spot/margin/futures
   trading, no withdrawals, no universal transfer); optionally IP-restrict.
2. Configure it in the SaathiOS secret store as `BINANCE_API_KEY` / `BINANCE_API_SECRET`
   (env or keychain reference) — **not** in any chat/terminal conversation.
3. SaathiOS verifies permissions (`READ_ONLY_CONFIRMED`) before any read; unsafe → refused
   (`BLOCKED_UNSAFE_BINANCE_API_PERMISSIONS`).

## Exact recommended next milestone
`M — BINANCE_READONLY_GATE_B_OWNER_VALIDATION` — after the owner configures a read-only key
via the secret store: verify permissions, one bounded real account read (balances redacted in
evidence), public-price enrichment, crypto UI + chat/voice, secret-exposure audit, then
certify `SAATHIOS_BINANCE_READONLY_PORTFOLIO_CERTIFIED` and freeze the adapter. No trading.

---

## Gate B attempt (2026-09-15) — BLOCKED at credential gate
Owner read-only credential is **not configured** (`BINANCE_API_KEY`/`BINANCE_API_SECRET`
absent) and the Binance API is **unreachable from the build sandbox** (`api.binance.com`
DNS-blocked, live probe → 000). Per Phase 3, Gate B **STOPS**:
`OWNER_BINANCE_READONLY_CREDENTIAL_REQUIRED`. No real account read performed; no credential
requested or printed.

**Credential-independent hardening delivered (Phase 2, pre-connection):** `assess_permissions`
now covers all known authority-bearing flags — withdrawals, internal/universal transfer,
futures, **portfolio-margin trading**, margin, **vanilla options**, **FIX API trade**, and
spot+margin trading — each mapped to a specific `UNSAFE_*_PERMISSION`; account `canTrade`/
`canWithdraw` cross-checked; read-only flags (`enableReading`, `enableFixReadOnly`,
`ipRestrict`) never block; and **any unrecognized truthy authority-looking permission →
`PERMISSION_UNKNOWN` (default-deny)** so a newly introduced Binance authority field cannot
silently pass. Core safety flags must be present or the verdict is `PERMISSION_UNKNOWN`.
This tightens safety before any real connection without touching the frozen contracts.

Gate B (permission verify → one bounded real read → enrichment → UI/chat/voice → secret
audit → certify + freeze) remains to be run in an environment where the owner has configured
a read-only key via the SaathiOS secret store and the Binance API is reachable.
