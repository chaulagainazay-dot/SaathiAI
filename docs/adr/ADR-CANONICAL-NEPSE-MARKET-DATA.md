# ADR — Canonical NEPSE Market-Data Source Authority

**Milestone:** M — CANONICAL_NEPSE_MARKET_DATA_FEED (from `4d685383`, Research Surface frozen `b771d761`).
**Status:** **CANONICAL_NEPSE_MARKET_DATA_SOURCE_BLOCKED** — no automated source can currently be
classified `OFFICIAL_STRUCTURED` / `OFFICIAL_DOWNLOAD` / `LICENSED_STRUCTURED` without defeating an
anti-bot control or promoting browser-derived data. Per the milestone STOP condition, the canonical
ingester was **not** built. No code changed; baselines untouched.

## Phase 0 — existing MD-1 components (reuse targets, no duplication)
- `saathi/platform/market_data/`: MD-1 contract, `MarketDataStore` (`md_bars`/`md_quotes`/`md_instruments`), `MDBar`/`MDQuote`, `provider.py` (abstract `MarketDataProvider` + **fixture provider only**), `fixtures.py` (synthetic/defect-injection bars), `quality.py`, `identity.py`.
- `saathi/platform/nepse/historical.py`: `HistoricalBar` (four timestamps: `session_date`, `as_of`, `available_at`, `received_at`; OHLC + timezone validation), `PointInTimeDataset.visible_at(replay_time)` — the look-ahead-safe primitive.
- `saathi/platform/nepse/{instruments.py (symbol master: normalize_symbol/instrument_id_for), calendar.py (NEPSE trading weekdays/holidays), importers/ (owner-file CSV parser, transaction-oriented)}`.
- Any canonical bar ingester must write **through** `MarketDataStore`/`HistoricalBar` with `available_at`, reuse `instruments.normalize_symbol`, and reuse `calendar.py`. **No new bar schema / store / symbol registry / provider interface.**

## Source discovery (probed directly, no browser token)
| Candidate | Owner | Format | Auth | Direct result | Classification | Canonical-eligible? |
|---|---|---|---|---|---|---|
| `nepalstock.com /api/nots/securityDailyTradeStat`, `/nepse-index`, `/graph/index` | NEPSE (official) | JSON | rotating in-browser token | **401 "UNAUTHORIZED ACCESS"** | `UNSTABLE_PRIVATE_ENDPOINT` (AUTH_REQUIRED via anti-bot) | **No** — needs token replay (forbidden) or in-browser capture (browser-derived, forbidden as canonical) |
| `nepalstock.com /api/nots/market/export/today-price`, `/marketwatch` | NEPSE (official) | CSV/JSON export | token + params | **400 Bad Request** | `UNSTABLE_PRIVATE_ENDPOINT` | **No** (same gate) |
| `nepalstock.com` in-browser JSON (M-NEPSE_DEEP_EXTRACTION_V3 capture) | NEPSE | JSON via Playwright | site's own token | 200 in-browser only | `BROWSER_DERIVED` | **No** — explicitly non-canonical (WEB_INTELLIGENCE) |
| `nepsealpha.com`, `sharesansar.com` APIs | third-party | JSON/HTML | varies | not official | `PUBLIC_STRUCTURED_UNOFFICIAL` | **No** — not official; terms/licensing unclear |
| SEBON / NRB | regulators | HTML/PDF | none | notices only | `HTML_ONLY` | **No** — no price bars |
| **Owner-supplied official NEPSE export** (owner downloads Today's-Price / historical CSV/XLS from their own authenticated browser and provides the file) | NEPSE (official artifact) | CSV/XLS | owner does it manually | not present yet | **`OFFICIAL_DOWNLOAD`** | **Yes** — official artifact, no token-defeat, no HTML scraping. **Not yet available (owner-interactive).** |
| Licensed market-data vendor feed | vendor | API | key | none configured | `LICENSED_STRUCTURED` (absent) | Yes if procured |

## Phase 1 — canonical bar authority contract (for when a source lands)
1. Only the approved structured-source ingester may write `md_bars`; nothing else.
2. Research / browser / document / Agent-Reach / Browser-Use evidence can **never** override or write bar values.
3. Every bar carries provenance (source identity + authority) + `available_at`.
4. `available_at` = earliest instant SaathiOS could legitimately know the completed EOD bar (publication/retrieval boundary, **not** `trading_date 00:00`); conservative + labelled if publication time unknown.
5. Corrected/revised source values are version-safe/auditable (revision detection, no silent overwrite).
6. Failed acquisition never fabricates bars.
7. Conflicting structured values → typed reconciliation state, never silent pick.
8. Source degradation never falls back to browser/HTML prices.

## Decision
The only **automated** official source (nepalstock.com JSON) is anti-bot-token-gated; using it as
canonical would require defeating that control (prohibited) or the browser-capture path (browser-derived,
prohibited as canonical). No official public download works unauthenticated; no licensed feed is
configured. Therefore the automated canonical source is **BLOCKED**. The catalyst market-reaction path
correctly remains `MARKET_DATA_UNAVAILABLE` — no fabrication, no browser prices as canonical.

## Recommended next options (best → acceptable)
1. **`M — OWNER_NEPSE_EOD_IMPORT`** (smallest safe path): a canonical EOD-bar ingester over an
   **owner-supplied official NEPSE export** (`OFFICIAL_DOWNLOAD`): owner manually downloads the
   official Today's-Price/historical CSV from their authenticated browser; SaathiOS parses → validates
   (OHLC/volume) → `normalize_symbol` → assigns provenance=`NEPSE_OFFICIAL_EXPORT` + conservative
   `available_at` → persists via `MarketDataStore`/`HistoricalBar`, idempotent + revision-audited. No
   network, no token, no scraping. Then run the Catalyst market-reaction + look-ahead gates on real bars.
2. **Licensed structured vendor feed** (`LICENSED_STRUCTURED`) if the owner procures one (API key via
   existing secret mechanism).
3. **Do NOT** promote nepalstock browser-capture, Agent-Reach, or third-party pages to canonical.

## Invariants (unchanged this milestone)
No code written. `ExecutionGateway.execute` = 0, TG trade = 0, broker = 0, portfolio writes = 0,
canonical **and** non-canonical market_data writes = 0. Research Surface frozen `b771d761` and Fusion
baseline `4d685383` structurally unchanged. Agent-Reach ADAPT; Browser Use DEFER.

**Verdict: CANONICAL_NEPSE_MARKET_DATA_SOURCE_BLOCKED.** Market Intelligence Fusion remains
`SAATHIOS_MARKET_INTELLIGENCE_FUSION_CERTIFIED_WITH_LIMITATIONS` (unchanged; not upgradable without real canonical bars).
