# SaathiOS — Market Intelligence Fusion & Catalyst Engine (v1)

**Above the frozen Research Surface (`b771d761`).** A bounded, deterministic, read-only,
point-in-time-safe layer that fuses ResearchEvents + canonical market data + read-only
portfolio/risk context into `CatalystEvent`s. **A catalyst is an observed market/company
event WITH context — never a trade signal, recommendation, price target, expected return, or
position instruction.** Zero trade authority. Agent-Reach ADAPT (unchanged). Browser Use DEFER.

## Phase 0 — architecture inventory (audit before build)
- **Canonical market data:** `saathi/platform/market_data/` (MD-1 contract, `md_bars/md_quotes`, `HistoricalBar`/`PointInTimeDataset.visible_at` = look-ahead-safe primitive, `available_at` authority) — **schema/machinery excellent, but the provider is fixture-only; there is NO live canonical NEPSE market-data feed** (bars in `*_research.db` are synthetic/defect-injection fixtures). → market-reaction runs when a real reader is supplied; live NEPSE = `MARKET_DATA_UNAVAILABLE`.
- **Research events/evidence/reconciliation/freshness/tiers:** frozen `saathi/browser_research/*` — **CONSUMED read-only** via `build_from_evidence` / `ResearchEvent` (no duplicate taxonomy, no second store).
- **Portfolio:** no server-side NEPSE holdings (frontend localStorage; `portfolio.py` is a USD/crypto compute engine) → `PORTFOLIO_CONTEXT_UNAVAILABLE` unless read-only holdings are injected.
- **Trading Guardian risk:** `tg/portfolio_risk/*` is optimiser/committee-coupled → **not invoked**; a safe read-only concentration projection is computed from injected holdings instead (Phase 7).
- Reused: evidence store, research contract, freshness/tiers, MD-1 point-in-time semantics. **No new stores/scheduler/taxonomy/symbol-registry/confidence system created.**

## New components (additive, `saathi/market_intelligence/`)
- `catalyst.py` — `CatalystEvent` + `MarketContext`/`PortfolioContext`/`RiskContext` (+ typed status enums), reuses frozen `ResearchEventType` (Phase 4, no duplicate taxonomy), `compute_priority` (operator-attention/risk relevance, HIGH/MEDIUM/LOW + reasons), `FORBIDDEN_TRADE_TOKENS`.
- `market_reaction.py` — `compute_market_reaction` (point-in-time, **look-ahead-safe**: `price_after` = first bar available STRICTLY after publication; a bar available at/before publication can never be "after"), injectable canonical bar reader, typed degraded.
- `fusion.py` — `fuse` (ResearchEvent → CatalystEvent), `build_snapshot`/`build_from_store`, `MarketIntelligenceSnapshot`, `central_command_projection`, `chat_answer`, `voice_answer`.

## Authority model
- **Canonical structured market data owns numeric prices** (never overridden by browser/research evidence). Research/official docs confirm events. This matches the existing MD-1 principle.
- Catalyst market-reaction is **descriptive `MARKET_REACTION`** (price_before/after, %change, volume_ratio) — explicitly **not** expected return / forecast / signal strength.
- Priority is **operator attention / portfolio-risk relevance**, not investment attractiveness; every priority carries `priority_reasons`.

## Point-in-time / look-ahead (Phase 2) — tested
`price_before` = last bar with `available_at ≤ publication_ts`; `price_after` = first bar with
`available_at > publication_ts` (strict). Missing before/after → `INSUFFICIENT_HISTORY`; no
reader/data → `MARKET_DATA_UNAVAILABLE`; no ts → `TIMESTAMP_UNRESOLVED`; no symbol →
`SYMBOL_UNRESOLVED`. Tests assert a pre-publication bar is never used as the reaction "after".

## Live NEPSE validation (Phase 20) — real events, honest degradation
`build_from_store(default_store())` over the **real** frozen evidence: **13 catalysts** from real
ResearchEvents (UMRH/MBL dividends, PMHPL suspension, SBL delisting, …), **0 untraceable**
(every catalyst → evidence_refs), priority MEDIUM 8 / LOW 5 (TIER_1 + recent + high-attention;
none HIGH — no portfolio relevance / market reaction to elevate). **market_context =
MARKET_DATA_UNAVAILABLE, portfolio_context = PORTFOLIO_CONTEXT_UNAVAILABLE** (no live feed / no
holdings — reported honestly, **no scraped prices masqueraded as canonical**). **Fusion latency
0.002 s, peak RSS 31.6 MB.**

## Authority invariants (verified)
`ExecutionGateway.execute` = 0, Trading-Guardian trade = 0, broker = 0, portfolio writes = 0,
market_data writes = 0, orders/payments/withdrawals = 0. `catalyst/market_reaction/fusion`
import none of gateway/TG/broker/portfolio_construction/portfolio_risk/market_data.store
(test-enforced). No trade-authority tokens (buy/sell/long/short/execute/target price/position
size/order/entry/exit/stop) appear in any catalyst output/priority/chat/voice (test-enforced).

## Frozen baseline integrity (Phase 22)
`git diff b771d761` on `research_surface.py`, `browser_research/*`, `components/research/*`,
`app/research/*`, and `server.py` → **0 modifications**. Everything is additive.

## Tests
`tests/test_market_intelligence_v1.py` **15**: mapping, point-in-time reaction, look-ahead
prevention, after-close publication, missing history, degraded states, portfolio relevance/
unavailable, read-only risk projection, priority + reasons, contradiction preserved, evidence
traceability, no-trade-language negative, no-authority-imports, snapshot + projections,
MARKET_DATA_UNAVAILABLE snapshot.

## Limitations (why CERTIFIED_WITH_LIMITATIONS)
1. **No live canonical NEPSE market-data feed** → market-reaction is `MARKET_DATA_UNAVAILABLE`
   for real events (reaction logic proven with fixture bars; activates when a real reader lands).
2. **No server-side NEPSE holdings** → portfolio/risk context `UNAVAILABLE` unless injected.
3. Central Command / chat / voice delivered as **backend projections** (functions), not wired
   into a live UI/route this milestone (Research UI stays frozen; new surface deferred).
4. NEPSE trading-calendar/session precision not modeled (windowing uses `available_at`; session
   boundaries best-effort) — deeper calendar integration deferred.

## Verdict
Deterministic, point-in-time-safe, evidence-traceable catalyst fusion engine implemented and
live-validated on real ResearchEvents, with market-reaction/portfolio/risk **honestly degraded**
pending real feeds, zero trade authority, frozen baseline untouched. Canonical market-data
context is absent, so per the milestone rule full certification is not awarded:

**SAATHIOS_MARKET_INTELLIGENCE_FUSION_CERTIFIED_WITH_LIMITATIONS.**

## Exact recommended next milestone
`M — CANONICAL_NEPSE_MARKET_DATA_FEED`: a governed, point-in-time historical/EOD NEPSE bar
ingester populating `md_bars` (MD-1 `available_at`) so the catalyst market-reaction path
activates on real data — **structured feed only, no browser-derived prices as canonical**. Then
re-run market-reaction gates to upgrade to full certification. Browser Use stays DEFER.
