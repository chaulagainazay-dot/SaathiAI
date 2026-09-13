# SaathiOS — Research Surface UI Wiring

**Builds on `119f8c4a`.** Wires the certified research intelligence projection into real
product surfaces: read-only backend API, a Central Command research tile, and chat/voice.
Backend intelligence stays authoritative — the frontend only presents. Browser Use = DEFER.

## Existing-surface audit (Phase 1)
- Backend routes are thin `@app.get/post` handlers delegating to a module (e.g. `ceo_home`). Chat = `POST /api/v1/agent/chat` → `_safe_respond`; voice = `POST /api/v1/voice/command` → `_safe_respond`. Auth is middleware (`_auth`); non-whitelisted routes require a session. Same-origin proxy already routes `:3100 /api/* → loopback :8765`.
- Frontend: Next.js `app/*` + `components/*`; components fetch via `lib/api.afetch` (credentials-include, `API_BASE=""` same-origin). Existing `app/nepse/*` surface. → **INTEGRATE** (new `/research` route + tile); **REUSE** afetch/auth/proxy.

## Backend (additive)
- `saathi/research_surface.py` — read-only BFF: `intelligence()`, `events()`, `event_detail(id)`, `brief()`, `health()`, `maybe_answer_chat()`, `maybe_answer_voice()`. Projects `build_from_evidence` (30s cache so a UI render never triggers collection). No re-implementation of authority/clustering.
- `server.py` — 5 routes: `GET /api/v1/research/{intelligence,events,events/{id},brief,health}` (thin delegates, not whitelisted → session-gated). Chat/voice wired by one hook inside `_safe_respond`: research queries answer from the snapshot (evidence-backed, deterministic) before the LLM path; non-research text falls through unchanged.

## Frontend (additive)
- `components/research/ResearchIntelligence.jsx` + `app/research/page.jsx` + `research.css`. Renders overview, source health (text labels, never color-only), events by `research_priority`, click-through event detail (evidence/document/contradiction), with LOADING / EMPTY / DEGRADED / ERROR states. Same-origin afetch; **no Buy/Sell/order/trade-score controls or wording**. Responsive (≤480px single-column, no horizontal overflow); accessible (aria labels, `aria-busy`, semantic buttons, `:focus-visible`).

## API response rule / read-only authority
Responses carry already-normalized backend output (`read_only:true`); the frontend computes no
authority. Every route is READ-ONLY — no trade/order/portfolio/market_data/approval/broker path.

## Refresh / SSE decision (Phase 28)
Collection and presentation are separate: the tile reads the projected snapshot; a 30s BFF
cache prevents rebuild storms. **Polling the read endpoint on demand is used for v1** (documented
decision) — no new SSE/WebSocket added; adapting the existing event stream (`research.snapshot.updated`)
is deferred.

## Live proof (in-process HTTP, no DB writes)
- App imports; **5 research routes registered**; BFF imports.
- `GET` all 5 research routes → **401** (auth enforced — not whitelisted; Phase 27 satisfied).
- `POST /api/v1/agent/chat` "what changed in nepse today?" → **200**, deterministic reply from the snapshot (real evidence store empty → "No research evidence available…", **no LLM, no fabrication**).
- Populated behavior (events/detail/brief/health/contradiction/citations/token-gated/portfolio-relevance) proven by 15 in-process BFF tests against a seeded temp store.

## pypdf dependency (Phase 24, re-confirmed)
Single `requirements.txt` spec; previously undeclared/optional; now correctly owned; no conflict.

## Tests
- Backend: `tests/test_research_surface_v1.py` **15** (snapshot/events/detail/not-found/brief/health/token-gated/unsupported/deterministic-chat/voice/no-model/contradiction/citations/portfolio-relevance/not-whitelisted/no-authority-imports).
- Frontend: `components/research/research-tile.test.js` **6** (same-origin fetch, product states, no trade wording, evidence+health+token-gated surfaced, a11y+responsive, page renders).
- Suite total **149 backend + 6 frontend** green.

## Authority invariants (verified)
`ExecutionGateway.execute` = 0, Trading-Guardian trade = 0, broker = 0, portfolio writes = 0,
market_data writes = 0, orders = 0. `research_surface.py` imports none of them (test). Routes
read-only; UI has no execution controls.

## Limitations (why CERTIFIED_WITH_LIMITATIONS)
1. **Live browser E2E not executed**: rendering the tile in the running app needs the new code deployed to `:3100`/`:8765` (backend restart — owner-gated, avoid `kickstart -k` race) + an authenticated login. Routes/BFF/tile are proven in-process + unit-tested, but a real logged-in browser render, live same-origin network capture, and 390×844 visual pass were not run this session.
2. **Live voice audio not exercised** (physical mic / TTS round-trip) — the voice route uses the same `_safe_respond` research hook (wired + covered deterministically), but a spoken turn was not validated.
3. Portfolio relevance is read-only via injected holdings; routes do not yet pass live holdings (no portfolio-API read wired).
4. Optional LLM chat/voice synthesis hook exists but deterministic replies are authoritative; not exercised with a live model.

## Verdict
Read-only research API + Central Command tile + chat/voice wiring are implemented, unit-tested,
and proven live in-process (routes register, auth enforced, deterministic evidence-backed chat),
with zero authority expansion — but a full logged-in browser E2E + live voice were not run
(owner deploy + interactive), so:

**SAATHIOS_RESEARCH_SURFACE_UI_WIRING_CERTIFIED_WITH_LIMITATIONS.**

## Next milestone (do NOT auto-start)
`M — RESEARCH_SURFACE_LIVE_E2E`: owner deploys the build to `:3100`/`:8765`, logs in, and runs
the browser + voice E2E gates (real render, same-origin capture, 390×844, spoken brief), then
close to full certification. Browser-use stays DEFER.
