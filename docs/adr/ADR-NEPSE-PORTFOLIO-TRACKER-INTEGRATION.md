# ADR — NEPSE Portfolio Tracker Integration Audit

**Status:** AUDIT COMPLETE — integration recommended (bounded, read-only). No code wired.
**From SaathiOS HEAD `cb723b8a`.** Target: `https://nepseportfoliotracker.app/`.
Frozen: Research Surface `b771d761`, Fusion `4d685383`. Do NOT replace the official
NEPSE browser observation system (it stays the current-market authority).

## What the service is
A third-party NEPSE web/iOS/Android app (React SPA, SEO-prerendered, Express API behind
Cloudflare, Firebase auth). Features: portfolio tracking across accounts, holdings & P/L,
MeroShare WACC/cost-basis calculator, live prices, indices, heatmap, dividends, IPO
calendar, mergers, mutual funds, forex/gold, candlestick scanners, price alerts, company
pages, and an **advertised MCP** for AI clients.

## Structured access discovered (non-credentialed probes)
| Surface | Result |
|---|---|
| **MCP** `https://api.nepseportfoliotracker.app/mcp` (JSON-RPC 2.0, Express) | Real, **key-gated**. Unauth → `-32001 Unauthorized: Missing MCP API Key. Provide "Authorization: Bearer <mcp_key>" or "X-MCP-Key"`. `tools/list` refused without key → tools not machine-enumerable without a key. CORS `*`. |
| **REST** apex `/api/*` | Public, **unauthenticated GET works**: `today-prices`, `history/{symbol}?range=1D..5Y`, `search`, `announced-dividends`, `ipos`, `companies`, `market`, `news`, `mergers`, `mutual-funds`, `commodities`, `currency`, `holidays`, `promoter-lockins`, `updates`, `auth`. CORS `*`. Not a documented/guaranteed third-party contract (their app's own API). |
| `/api/docs` | 401 (private). |
| iframe embed | `x-frame-options: SAMEORIGIN` → **EMBED_BLOCKED**. |

### MCP capability (from public marketing — tools not enumerable without key)
"NEPSE MCP connects Claude, ChatGPT, and any MCP-compatible client to your **live portfolio
and NEPSE market data**": live portfolio value, **holdings & P/L on demand**, MeroShare WACC,
live market data. Auth = MCP API key issued from the app account (Bearer / `X-MCP-Key`).
"Learn More" → `/app/advanced-analysis` (in-app, behind account).

### REST data shapes (verified)
- `today-prices` → 100 records; per-record fields include full OHLC (`open/high/low/close_price`),
  `previous_close`, `change`, `percentage_change`, `total_traded_quantity`, `turnover`,
  `total_trades`, `average_traded_price`, `market_capitalization`, `fifty_two_week_high/low`,
  `last_traded_price`, `sector_name`, **`pe_ratio`, `pb_ratio`, `eps`, `dividend_yield`**,
  `logo_url`, `last_updated`, and **`source: REDIS_LIVE`**. business_date 2026-09-11.
- `history/{symbol}?range=` → daily OHLC candles (`business_date, open/high/low/close_price,
  total_traded_quantity`). Depth: NABIL 1M=18, 1Y=224, **5Y=1158**; 1D=119 (intraday).
- `announced-dividends`, `ipos`, `search` → structured JSON.

## Pricing (schema.org JSON-LD — authoritative)
- **Free** — NPR 0, all core portfolio features, no card.
- **Pro Monthly** — NPR 150 (3-day free trial; "≈ Rs.100/mo").
- **Pro Yearly** — NPR 1200.
- Scanners — Rs.200/mo standalone or bundled with Pro/Premium.
MCP ties to the account; portfolio-over-MCP effectively needs a Pro account + MCP key.

## Terms / access boundary (Phase 2)
- Privacy policy: standard (minimal data, cookies, Ezoic ads). A "Terms of Service" link
  exists but its body is SPA-gated — **UNKNOWN**; must be read by a human before any
  production/commercial programmatic use. No explicit public-API license was found.
- Classification per method:
  - **MCP** → `SUPPORTED_MCP` (their intended AI-client integration; key-gated).
  - Public `/api/*` GET → `SUPPORTED_PUBLIC_WEB` (works, CORS `*`) but **best-effort /
    UNKNOWN as a stable third-party contract** (undocumented, may change).
  - iframe embed → `UNSUPPORTED` (X-Frame-Options blocks it).
  - Anything auth/rate-limit/token-bypass or credential copying → `UNSUPPORTED_AUTOMATION`
    (prohibited; not attempted).

## Source authority (Phase 5) & reconciliation (Phase 6/14)
Classify tracker data **`THIRD_PARTY_STRUCTURED_MARKET_DATA`**, `source_authority =
NEPSE_PORTFOLIO_TRACKER`. **NOT `OFFICIAL_NEPSE`.** Official browser observation retains
higher authority for current market state; tracker adds history + fundamentals + dividends
+ (via MCP) portfolio.

**Cross-source comparison (tracker last candle 2026-09-11 vs official NEPSE observation):**
| Symbol | Tracker close / vol | Official close / vol | Verdict |
|---|---|---|---|
| NABIL | 552.00 / 37,182 | 552.00 / 37,182 | **CONFIRMED** |
| API | 334.70 / 229,569 | 334.70 / 229,569 | **CONFIRMED** |
| AKPL | 255.00 / 127,972 | 255.00 / 127,972 | **CONFIRMED** |
| HDL | 1192.00 / 28,552 | 1192.00 / 28,552 | **CONFIRMED** |
Exact agreement (OHLC too). Tracker is high-fidelity but still reconciled, never
auto-overwriting official; on divergence → `SOURCE_DISAGREEMENT`, official wins for current
LTP, tracker flagged for richer history/context.

## Historical data (Phase 7)
5Y daily OHLC available. **Do NOT promote to canonical MD-1**: only `business_date` (no
explicit tz / retrieval `available_at`), no visible split/dividend adjustment or
corporate-action metadata, no point-in-time semantics, `today-prices` capped at 100/page.
Usable as `THIRD_PARTY_HISTORICAL_SERIES` for charts/operational context, not for
regulated backtests.

## Chart data contract (Phase 10 — design)
```python
@dataclass(frozen=True)
class MarketPoint:
    timestamp: float; open: Decimal; high: Decimal; low: Decimal
    close: Decimal; volume: Decimal
@dataclass(frozen=True)
class MarketSeries:
    symbol: str; instrument_id: str; timeframe: str      # 1D/1W/1M/3M/6M/1Y/5Y
    start: float; end: float
    source: str                                          # "NEPSE_PORTFOLIO_TRACKER"
    source_authority: str                                # THIRD_PARTY_STRUCTURED_MARKET_DATA
    retrieved_at: float; points: tuple[MarketPoint, ...]
    # derived indicators (descriptive analytics only, reproducible): sma/ema/rsi/macd/atr/bollinger
```
SaathiOS draws its own charts from `MarketSeries` (Central Command chart surface) — it does
**not** depend on the tracker's TradingView widget or screenshots. Indicators are
descriptive only. **No trading signals in scope.**

## Minimal adapter (design only — not wired)
```python
class NEPSEPortfolioTrackerAdapter:            # READ-ONLY, execution_authority = False
    def market_history(symbol, range) -> MarketSeries          # public REST /api/history
    def fundamentals(symbol) -> dict                           # today-prices pe/pb/eps/div_yield
    def dividends(symbol=None) -> list                         # /api/announced-dividends
    def ipos() -> list                                         # /api/ipos
    def portfolio() -> PortfolioReadModel                      # MCP + owner key (Pro) — DEFER
```
Reuses existing `normalize_symbol`/`instrument_id_for`, portfolio-context contracts,
market-source-health, reconciliation. No parallel architecture. No portfolio mutation.

## SaathiOS fit (Phases 4, 9, 11, 30–33)
- **Central Command**: NEPSE Market workspace (Overview/Chart/Portfolio/Sectors/Research/
  Catalysts) with source badges (Official NEPSE vs NEPSE Portfolio Tracker) + freshness.
- **Chat/Voice**: answer history/fundamentals/dividends questions with source tag; current
  LTP still from official observation.
- **Catalyst/Research**: dividends + fundamentals enrich CURRENT context (never historical
  reaction; Fusion untouched).
- **Trading Guardian**: read-only context only. `execution_authority = false`.

## Resource impact (Phase 15)
Prefer MCP/REST — **no second Chromium**. Do NOT run official-NEPSE + tracker + Browser-Use
Chromiums together on M2/8 GB. Playwright **not needed** for the tracker (structured access
exists). Embed blocked anyway.

## Authority audit (Phase 16/19)
execution_authority = false; broker = 0; orders = 0; ExecutionGateway.execute = 0; Trading
Guardian trade = 0; portfolio writes = 0; withdrawals = 0; leverage = 0. Read-only.

## Classification matrix (Phase 17)
| Capability | Decision |
|---|---|
| MCP (read-only) | **INTEGRATE** (primary supported path; owner Pro key required) |
| Market quotes (current) | **COMBINE** — official authority + tracker reconcile |
| Historical OHLC (5Y daily) | **ADAPT** as THIRD_PARTY_HISTORICAL_SERIES (not canonical) |
| Portfolio holdings / P&L / WACC | **INTEGRATE (DEFER wiring)** — MCP + owner Pro key; closes Fusion portfolio_context gap |
| Dividends | **INTEGRATE** (public REST) |
| Fundamentals (pe/pb/eps/div-yield) | **ADAPT** (public REST, third-party) |
| Technical indicators | **ADAPT** — compute descriptive-only from MarketSeries in SaathiOS |
| Advanced charts | **COMBINE** — draw own charts from MarketSeries |
| Scanners | **DEFER** (paid; signal-adjacent) |
| Alerts | **DEFER** |
| Browser embed (iframe) | **REJECT** (X-Frame-Options SAMEORIGIN) |
| Playwright extraction | **REJECT** (structured access exists; avoid 2nd Chromium) |
| Their AI assistant | **DEFER** (SaathiOS keeps its own) |
| Their TradingView charts | **REJECT** (draw own from data) |

## Security risks
Third-party dependency (availability/schema drift); undocumented public API may change or
be restricted; ToS body unread (UNKNOWN — read before commercial use); portfolio MCP key is
a secret (owner-issued, store in secret manager, never in code/logs, never entered by the
agent). CORS `*` is theirs, not a license.

## Recommended architecture
1. **Now (no creds):** read-only market adapter over public `/api/history` +
   `/api/announced-dividends` + fundamentals → `MarketSeries` → reconcile vs official
   (CONFIRMED/SOURCE_DISAGREEMENT, official wins current) → SaathiOS-drawn charts. Tagged
   `THIRD_PARTY_STRUCTURED_MARKET_DATA`. No canonical MD-1 promotion.
2. **Deferred (owner action):** owner subscribes Pro, issues an MCP key, provides it to
   SaathiOS secret store → wire the read-only **portfolio** MCP tools (holdings/P&L/WACC)
   to close the Fusion `portfolio_context` gap. Never mutate; execution_authority=false.
3. Keep the official NEPSE browser as current-market authority; tracker = enrichment.

## Recommendation
**Proceed to a bounded implementation** of step 1 (public read-only market/history/dividends
adapter + MarketSeries + reconciliation + chart), because the data is verified-accurate,
structured, and needs no credentials or second browser. **Defer** step 2 (portfolio MCP)
until the owner provides a Pro MCP key, and read the Terms of Service first.

## Exact next bounded milestone
`M — TRACKER_MARKET_HISTORY_READMODEL` — implement the read-only public-REST market/history/
dividends/fundamentals adapter → `MarketSeries` (+ reproducible descriptive indicators) →
source reconciliation vs official NEPSE → SaathiOS chart surface in Central Command; tagged
THIRD_PARTY, zero authority, no canonical MD-1 writes, no trading signals; portfolio-MCP
wiring deferred pending an owner-supplied Pro MCP key + ToS review.
