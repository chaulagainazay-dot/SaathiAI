# NEPSE-COMPLETE-1 — closing the remaining data gaps

Status: in progress
Branch: `feature/nepse-completion`
Base: `d8d55bbd` (typed ShareSansar extractors)

## Why

Three defects are visible in the product today, and one blocker was recorded as
unsolvable. Research done before writing this plan showed the blocker is solvable
read-only after all.

| Gap | State before | Route found |
|---|---|---|
| 346 of 370 companies have no sector | only 24 known, from a curated list | `sectorwise-share-price`, `h3.heading-title` |
| 40+ brokers render as bare codes | 8 names hardcoded | `top-brokers`, 92 rows with names |
| No IPO pipeline | absent | `existing-issues`, `#myTableEip` |
| Dividends extracted but unused | route only, no surface | wire to a page |

## What was rejected, and why

- **`company-list` sector filter** — filtering needs a POST carrying a CSRF token.
  That is a write action. The browser surface was made read-only one commit ago
  and will not be widened for a convenience.
- **`stock-heat-map`** — canvas-rendered, no DOM table.
- **NEPSE's own portal** — permanently denied (`NO_PROTECTED_SCRAPING`).
- **The competitor's API** — free-riding on someone else's infrastructure.

## Design

### 1. Sector map — positional pairing, validated

The page renders, per sector, a heading then two blocks (top gainers, top losers):

```
h3.heading-title   → "Commercial Bank"
div.col-md-6       → Top Gainer table
div.col-md-6       → Top Loser table
```

Headings and blocks are separate node lists, so they can only be paired by ORDER.
Positional pairing is exactly the failure mode the header check exists to catch,
so it gets the same treatment:

- headings are filtered against a CANONICAL sector vocabulary (taken from the
  site's own sector dropdown), which drops sidebar headings such as
  "NEPSE Calendar" that are not sectors at all;
- the pairing is accepted only when `blocks === 2 × sectors`. Any other ratio
  means the layout moved, and the extractor returns nothing.

Coverage is PARTIAL by construction — the page lists only each sector's top
movers, about 186 of 370 symbols. That is not a defect to hide: every mapping it
yields is correct, and each carries the date it was observed, so a persisted map
accumulates as the movers rotate. The UI states coverage rather than implying the
whole market is classified.

### 2. Broker names

`top-brokers` carries all 92 broker numbers with names and real buy/sell totals.
Replaces the eight hardcoded names. A code still absent from the page renders as a
code — never a guessed name, because misattributing money flows to a real named
firm is the worst error available here.

### 3. IPO pipeline

`existing-issues` `#myTableEip`: symbol, company, units, price, open/close dates,
issue manager, status.

### 4. Surfaces

- Sector map feeds `/api/nepse/market`, replacing the 24-symbol curated map.
- Broker names feed `/api/nepse/floorsheet`.
- A new `/nepse/calendar` page shows announced dividends and the IPO pipeline.

## Invariants carried forward

- Deny-by-default browsing; ShareSansar only via `SAATHI_BROWSER_ALLOWED_DOMAINS`.
- Read-only actions only.
- Every extractor verifies the live header against the layout it was written for
  and returns zero rows on drift, naming the column that moved.
- Absent stays null, never 0.
- Scraped data is labelled `SCRAPED_PUBLIC_PAGE` / `RESEARCH_ONLY`, never mixed
  silently with the licensed archives.

## Verification

1. Unit tests per extractor, including a refusal test per failure mode
   (moved column, changed count, error page, bad pairing ratio).
2. Live run against the real site.
3. Cross-check sector assignments against known-correct examples.
4. Cross-check broker totals against the floorsheet count already verified to the
   rupee.
5. Full JS suite, lint, clean production build.

---

# NEPSE-COMPLETE-2 — web intelligence via wigolo

## What was wired

`wigolo` (github.com/KnockOutEZ/wigolo) is a local-first web search / fetch /
crawl / extract engine that runs as its own daemon. SaathiOS now calls it for
live web search: a `/nepse/research` surface, and optional web context appended
to chart narration.

## The licence boundary — the decisive constraint

**wigolo is AGPL-3.0.** That licence's network clause reaches software that is
combined with it and served to users. So the integration is deliberately
arm's-length:

- wigolo runs as a **separate process**, started independently, reached over its
  loopback HTTP API.
- **No wigolo source is imported, vendored, linked or copied into this repo.**
  `lib/web/wigolo.js` encodes the wire shape observed from a running daemon —
  the same way any HTTP client encodes the service it calls.
- Nothing in SaathiOS is derived from wigolo's code.

Vendoring it later would put SaathiOS's own licensing in question. That is the
single rule to keep.

## Security posture

- The daemon URL is **validated as loopback** before it is dialled. A config value
  that could name any host would turn the route into a request-forgery proxy —
  the same hole already closed in the governed browser.
- Only **read-only tools** are callable: search, fetch, extract, find_similar.
  `crawl`, `agent`, `watch`, `diff` and `research` schedule work, spend time or
  cost money, and are not reachable from this app.
- Every result is **fenced** through the existing injection filter before it can
  reach a screen or a prompt, and flagged results are shown as flagged.
- Web text is labelled `UNTRUSTED_WEB_CONTENT` and styled apart from SaathiOS's
  own figures. The prompt block states plainly that a snippet is **not a price**
  and **not an explanation of a price move** — a page mentioning a symbol is
  evidence the page exists, nothing more.
- Narration still passes through the numeric guard afterwards, so web text cannot
  smuggle a figure into an answer.

## Operational notes

- Start the daemon: `npx wigolo serve --port 3333`. SaathiOS does not start it.
- If it is not running the route says so and returns nothing — a search surface
  that silently degrades to zero results is indistinguishable from a web where
  nothing was written.
- `research` and `agent` want an LLM key; a local Ollama at :11434 was detected on
  this machine, so keyless synthesis is available if those are ever enabled.
- Core search is keyless. Observed engines in use: DuckDuckGo and Bing.
