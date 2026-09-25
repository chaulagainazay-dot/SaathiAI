# SaathiOS — Browser Use Isolated Agentic Acquisition (Evaluation)

**Builds on `b9d2cbaf`.** Evaluates `browser-use` **0.13.10** as an OPTIONAL escalation
driver behind the FROZEN `BrowserResearchProvider` contract. The contract, tiers,
freshness, provenance, reconciliation, and bridges were **not** changed. browser-use
adapts to SaathiOS, never the reverse.

## Verdict: `BROWSER_USE_DEFER`
Architecturally integrated (isolated, contained, contract-conformant, safe) but **not
adopted**: with the locally available models it provides **no benefit** and is **200–400×
slower and ~15× heavier** than the existing HTTP tier, and offers no edge over the
Playwright tier for JS pages. It would require a capable **multimodal** model (API key +
cost) to be useful — which the single-owner, 8 GB, local-first, no-key constraint does not
currently support. The driver is built and certified so a future capable model can plug in
**without redesign**.

## Isolation (Phase 2)
- browser-use installed in an **isolated venv** (`scratchpad/bu_venv`), **never** the main
  SaathiOS venv (verified: `pip show browser-use` empty in main venv; importing
  `saathi.browser_research.browseruse_adapter` leaves `browser_use` absent from
  `sys.modules`).
- Boundary: `SaathiOS → BrowserUseSubprocessAdapter → isolated python → _browseruse_runner.py → JSON → BrowserResearchProvider`.
- Main-process files import **zero** browser-use symbols (test-enforced).

## Dependency audit (Phase 3)
- Version **0.13.10**, Python 3.12, **110 packages**, **336 MB** venv.
- Bundles native `ollama` client (**no API key required**), plus `openai/anthropic/groq/google-genai` clients, `posthog` telemetry, own CDP harness (`cdp-use`, `browser-harness`).
- Telemetry disabled for the eval (`ANONYMIZED_TELEMETRY=false`, `BROWSER_USE_TELEMETRY=false`).

## Subprocess protocol & capability boundary (Phases 4–6)
- Input: public-research JSON (url, task, allowed_domains, model, bounds). Output: one JSON payload.
- Subprocess env is **secret-stripped** (no `*KEY/*TOKEN/*SECRET/*PASSWORD/ANTHROPIC/OPENAI/…`); receives no gateway, Trading Guardian, broker, DB handle, credential, or market_data write.
- Read-only task contract forbids login/credentials/submit/buy-sell-trade-withdraw/download/captcha.
- Domain governance reused twice: pre-flight `check_domain` (allowlist/SSRF/private-IP/metadata/scheme) **and** post-run re-validation of every visited URL → off-policy navigation = `BROWSER_USE_DOMAIN_BLOCKED`. browser-use's own `allowed_domains` set as defense-in-depth.

## Failure containment (Phases 14–15)
Typed degraded results, no SaathiOS crash: `BROWSER_USE_TIMEOUT`, `BROWSER_USE_CRASH`,
`BROWSER_USE_RESOURCE_LIMIT`, `BROWSER_USE_MODEL_UNAVAILABLE`, `BROWSER_USE_INVALID_RESULT`,
`BROWSER_USE_DOMAIN_BLOCKED`. Timeout kills the whole process group (`start_new_session` +
`killpg`). browser-use's own Chromium reset/cleanup observed working in live runs.

## Live evidence (Phases 9–10, model = local Ollama)
| Mission | Driver | Result | Runtime | Peak RSS | Facts |
|---|---|---|---|---|---|
| A simple official (sebon.gov.np) | **HTTP tier** | ✅ 47 real Tier-1 facts | **1.4 s** | **62 MB** | 47 |
| A simple official (sebon.gov.np) | browser-use `qwen3:4b` | ❌ **hallucinated** unrelated "ArXiv papers" task | ~120 s | ~600 MB | 0 |
| A simple official (sebon.gov.np) | browser-use `qwen3:8b` | ❌ empty, stuck at `about:blank` | **316 s** | **965 MB** | 0 |
| B JS-heavy (nepalstock.com) | HTTP tier | ⚠️ empty SPA shell (37 chars) | 0.8 s | 48 MB | 0 |
| B JS-heavy (nepalstock.com) | Playwright tier | existing certified escalation for JS render | — | — | — |
| B JS-heavy (nepalstock.com) | browser-use | no edge over Playwright; needs multimodal model | — | — | — |

Root causes: browser-use is **vision-first** (sends screenshots to the LLM — local Ollama
models are non-multimodal, raising `model does not support multimodal requests`); small
local models hallucinate/ignore the task; 8B is far too slow per step on 8 GB.

## Performance matrix (Phase 21)
| | HTTP | PLAYWRIGHT | BROWSER_USE (local) |
|---|---|---|---|
| Success (simple official) | ✅ high | ✅ high | ❌ fails/hallucinates |
| Extraction precision | heuristic (noisy) | heuristic (noisy) | unusable w/ local models |
| Runtime | ~1.4 s | seconds | 120–316 s |
| Peak RAM | ~62 MB | low-moderate | ~600–965 MB |
| CPU | low | moderate | high (LLM+Chromium) |
| LLM cost | none | none | high if capable multimodal model used |
| Complexity | low | low | high (venv+subprocess+model) |
| Multi-step ability | none | scripted | native (but unreliable locally) |
| Cleanup reliability | ✅ | ✅ | ✅ (observed) |

## Authority audit (Phase 16)
`ExecutionGateway.execute` = 0, Trading-Guardian trade fns = 0, broker adapters = 0,
canonical market_data writes = 0, payment/withdrawal = 0, credential entry = 0. The
browser-use path never receives objects capable of those actions (adapter/runner import
none — test-enforced). Provenance stays `BROWSER_DERIVED` / `WEB_INTELLIGENCE`; optional
`driver=BROWSER_USE` metadata only.

## Evidence & reconciliation integration (Phases 17–18)
browser-use output → `BrowserUseResearchProvider.fetch` → `FetchedPage` → the SAME
`nepse.extract_facts` → tiering/freshness/reconciliation → evidence & confidence bridges.
No direct writes to `saathi/evidence`.

## Files (additive only)
`saathi/browser_research/_browseruse_runner.py` (isolated-venv entrypoint — never imported
by main process), `saathi/browser_research/browseruse_adapter.py`,
`tests/test_browseruse_adapter_v1.py` (18 tests), this doc. **Zero frozen files changed.**

## Tests
`tests/test_browseruse_adapter_v1.py` **18 passing** (+22 v1 = 40): isolated launch,
no-main-import, request/result serialization, timeout, crash, malformed, model-unavailable,
resource bounds, cleanup, domain/SSRF/localhost block, off-policy navigation block, prompt
injection as content, read-only-task contract, secret-stripped env, no gateway/TG/market_data
imports, provenance, evidence normalization.

## Limitations
1. Useful browser-use requires a **multimodal** model — unavailable locally (no key, 8 GB).
2. Local small models hallucinate; 8B is prohibitively slow (~5 min/mission).
3. Missions C/D (multi-step/crypto) not benchmarked live — blocked by the same model gap.
4. Playwright-tier deep JS extraction on nepalstock not separately re-benchmarked.

## Recommended next milestone (do NOT auto-start)
`M — BROWSER_RESEARCH_EXTRACTION_PRECISION_V2`: per-source DOM/selector extraction +
Playwright-tier deep extraction for JS pages (nepalstock) + Nepali BS→AD date conversion —
the actual precision gaps. Re-evaluate browser-use only if/when a capable multimodal model
is available (`BROWSER_USE` driver already wired for drop-in).

**Verdict: SAATHIOS_BROWSER_USE_ISOLATED_AGENTIC_ACQUISITION_EVALUATED — classification BROWSER_USE_DEFER.**
