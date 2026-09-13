# SaathiOS — Agent-Reach Evaluation

**From `94227487`.** Evaluated `github.com/Panniantong/Agent-Reach` as an OPTIONAL bounded
web-research acquisition adapter behind the existing research architecture. **Not** a
market-data authority. Browser Use stays DEFER.

## Verdict: `AGENT_REACH_ADAPT`
The useful, working piece (Jina Reader webpage extraction + web search) is adopted as a
**bounded optional fallback acquisition tier** behind the frozen `BrowserResearchProvider`
contract, feeding the existing extractor/evidence/snapshot pipeline. The full `agent-reach`
CLI is **not** installed (not required); most of its other channels are non-functional here.
Canonical NEPSE data stays with the certified governed pipeline.

## Already wired? (Phases 1-2) — PARTIALLY
- `agent-reach` CLI: **MISSING** (not on PATH / npm / pip).
- `saathi/tools/internet_reach.py` (docstring "via Agent-Reach backends") IS present and wired into `saathi/tools/registry.py` as **chat/agent tools** (`read_webpage`, `web_search`, `youtube_*`, `github_repo`, `rss_feed`, `reach_doctor`) — but **NOT** into the `browser_research` evidence/snapshot pipeline.
- Backend availability: **Jina Reader works** (`curl r.jina.ai/<url>`, no key/install — live SEBON markdown returned); `mcporter` ✅, `gh` ✅; **yt-dlp MISSING, feedparser MISSING, agent-reach CLI MISSING**.
- Classification: **partially integrated (chat tools only); CLI absent; ~half the channels non-functional.**

## Root cause of earlier "missing NEPSE real data" (Phase 6) — NOT Agent-Reach
Traced end-to-end: the certified governed pipeline (Playwright `OFFICIAL_ENDPOINT` capture)
already produces real NEPSE data. Earlier the live UI showed nothing because (a) the running
backend was **stale** (pre-deploy) and (b) the evidence store was **empty** until a mission
ran. Both were addressed this session (backend redeployed by owner; 14 real evidence rows
populated → 13 Tier-1 events). **Agent-Reach neither caused nor fixes this.** Canonical NEPSE
data comes from the governed pipeline, not Agent-Reach.

## Adapter (additive, `saathi/browser_research/agent_reach.py`)
- `AgentReachProvider(BrowserResearchProvider)`: `fetch(url)` via the existing `internet_reach.read_webpage` (Jina; injectable), bounded `max_pages`/`max_runtime`, **domain/SSRF policy on the real target** (explicit allowlist → strict; none → public web open but private-IP/metadata/`file:`/`data:`/scheme blocked), read-only, cleanup. `search(query)` via `web_search` (Exa/mcporter → DDG fallback); snippets are context, never confirmed facts.
- `agent_reach_records(page)` → `ExtractedRecord` tagged `ExtractionMethod.JINA_READER`, markdown-link-stripped + `noise.is_noise`-filtered, BS/AD dates, symbol resolution — flows into the existing `records_to_facts` → evidence → snapshot. New methods `JINA_READER`, `AGENT_REACH_SEARCH`.
- `agent_reach_available()` diagnostic. **No evidence writes inside the adapter**; no CLI dependency.

## Live validation (Phase 20/29)
- Jina via adapter on `sebon.gov.np` + `nrb.org.np`: succeeded, clean markdown; after noise filtering, real records (e.g. "Annual Report Submission Status of Listed Companies 2081/82", "Stock Broker and Dealer Quarterly Reporting status 2082/83"). Web search: status ok via `exa/mcporter`.
- **Peak RSS 32.7 MB, ~16 s** for 2 pages + a search. Cleanup OK.
- Extraction precision is **moderate** (markdown/nav/chatbot residue) — a fallback-tier quality, below the governed `OFFICIAL_ENDPOINT` JSON path.

## Current-pipeline comparison (Phase 21)
| | Governed pipeline (current) | Agent-Reach / Jina |
|---|---|---|
| NEPSE structured data | ✅ 13 Tier-1 events (JSON, symbols/dates/docs) | ✗ not canonical; generic markdown only |
| Arbitrary public page / issuer / news | limited (HTTP text / SPA shell) | ✅ clean markdown of any public URL |
| Web search | none | ✅ (Exa/mcporter → DDG) |
| Install footprint | 0 (uses installed Playwright) | 0 for Jina (curl); full CLI not installed |
| Precision | high (official JSON) | moderate (markdown noise) |
| Peak RAM | ~38–64 MB | ~33 MB |
| Dependencies | none new | none new (Jina=curl); CLI/yt-dlp/feedparser absent |

## Fallback order (Phase 23)
1. canonical structured API/exchange feed → 2. official HTTP endpoint → 3. governed
Playwright/XHR (`OFFICIAL_ENDPOINT`) → **4. Agent-Reach Jina/search adapter** → 5. reputable
secondary web. Agent-Reach is **never** first choice for structured market data. It is provided
but **not wired as a default** in `nepse_v3` (optional; caller opts in).

## Authority / security (Phases 17-18)
`agent_reach.py` imports no gateway/Trading-Guardian/broker/portfolio/market_data (test).
`ExecutionGateway.execute`=0, TG trade=0, broker=0, portfolio writes=0, market_data writes=0.
Webpage content is DATA: prompt-injection detected (`detect_prompt_injection`) and recorded,
never executed; injection lines never become corporate actions (tested). Facts are always
`WEB_INTELLIGENCE`/`BROWSER_DERIVED`; canonical market value never overwritten (reconciliation
unchanged, tested). No browser cookies stored; no authenticated session reuse.

## Tests
`tests/test_agent_reach_v1.py` **16** (147 across research suite): detection, adapter success,
timeout, cleanup, domain+SSRF block, malformed output, search normalization, web-read
normalization + tier preservation, evidence integration, reconciliation, prompt-injection-as-
data, WEB_INTELLIGENCE-only, no-authority-imports, no-model, degraded path, usable-as-provider.

## Limitations
1. `agent-reach` CLI not installed; **yt-dlp / feedparser channels non-functional**; `reach_doctor` unusable (CLI absent).
2. Jina extraction precision moderate (markdown/nav/chatbot residue) — fallback quality, not official-JSON quality.
3. Exa search depends on `mcporter` + provider key/config (present binary; key not verified).
4. Adapter provided but intentionally **not wired as a default** acquisition path.

## Browser Use
Unchanged: **BROWSER_USE_DEFER** (not invoked, not re-evaluated).

## Verdict
**SAATHIOS_AGENT_REACH_EVALUATED → AGENT_REACH_ADAPT** — bounded Jina/search adapter built,
tested, and live-proven as an optional fallback web-research tier behind the existing contract;
full CLI not adopted; canonical NEPSE unaffected.

## Next milestone (do NOT auto-start)
Resume `M — RESEARCH_SURFACE_OWNER_E2E_CLOSURE` (owner in-pane login was pending) to finish the
authed browser E2E and freeze the research surface. Optionally, later: wire the Agent-Reach
adapter as an explicit tier-4 fallback for non-NEPSE/issuer/news research. Browser-use DEFER.
