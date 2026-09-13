# SaathiOS — Research Surface Live E2E (closure attempt)

**From `71013cf1`.** Validation-only milestone: close the live gates for the research surface.
No architecture change, no code change this run. Browser Use = DEFER.

## What was proven LIVE this session (software-verifiable, no owner password)
- **Runtime topology (Phase 1):** `:3100` canonical frontend listener (node PID 50394); **no `:3000` listener**; `:8765` loopback backend (Python PID 50645). Same-origin proxy healthy: `GET :3100/api/v1/auth/session` → **200** (proxied to backend).
- **Same-origin routing for the new prefix (Phase 8, partial):** `GET :3100/api/v1/research/health` → **401**, proxied to the backend and rejected by `_auth` — proving the `/api/v1/research` prefix reaches the backend through the same-origin proxy and auth is enforced (no browser call to `:8765`).
- **Live real evidence populated (Phase 5):** ran ONE bounded real NEPSE deep collection (acquisition `OFFICIAL_ENDPOINT`, no Browser Use, no token-gated bypass) → wrote **14 real evidence rows** (0→14) into the live `~/.saathi/evidence.db` via the normal path. Collection 10.5 s.
- **Real snapshot + surface projection (Phases 6/7 data-layer):** `research_surface.intelligence()` over the **real** store → state OK, **13 events**, all `TIER_1_OFFICIAL`, confidence 0.9, **0 untraceable events**; first event DIVIDEND [UMRH] priority 0.713 with 1 evidence ref; brief `what_changed`=5; projection latency **0.001 s** (collection separate). Real data, no fixtures.
- **No-model (Phase 19):** the entire surface path is deterministic; the above ran with no LLM.
- **Regression (Phase 33):** research surface + intelligence + browser-research v1/v2 + NEPSE deep v3 + document ingestion + **auth recovery (20)** = **151 backend tests pass**; frontend research tile + single-origin + cookie-auth + canonical-port = **17 pass**.
- **Authority (Phase 32):** no code changed; research modules import no gateway/TG/broker/portfolio/market_data (import-audited); routes read-only; 0 execution controls.

## Deployment status (why the browser gates can't be closed by me)
The **running backend (PID 50645) started Sep 12 13:02**, ~19 h before the research-route
commits (Sep 13 08:26). So the live `:8765` build **does not contain** `/api/v1/research/*`
(the 401 is `_auth` rejecting before routing — a bogus path 401s identically). Closing the
authed browser gates requires **two owner-interactive actions I must not perform**:
1. **Deploy** the new build to the owner's live `:3100`/`:8765` (a service restart of
   `com.saathi.local` — disruptive to the owner's running session, and subject to the known
   `kickstart -k` backend-kill race). I do not restart the owner's live services unprompted.
2. **Owner login** in the real browser — requires the owner's password, which I must never
   know, print, create, or bypass. The authed same-origin capture, authed render, authed
   chat/voice, and viewport visual gates all sit behind this login.

Both are correct security/operational boundaries, not defects.

## Gate status
| Gate | Result |
|---|---|
| Canonical :3100 / no :3000 / loopback :8765 | **PASS (live)** |
| Same-origin proxy forwards `/api/v1/research` + auth enforced | **PASS (live, unauthenticated)** |
| Real evidence populated via normal path | **PASS (live, 14 rows)** |
| Real snapshot event count / traceability | **PASS (live, 13 events, 0 untraceable)** |
| Surface projection (intelligence/events/detail/brief/health) on real store | **PASS (live data-layer)** |
| No-model operation | **PASS** |
| Regression suites | **PASS (151 + 17)** |
| Authority audit (0 writes/execute) | **PASS** |
| Owner browser login | **BLOCKED_OWNER_INTERACTIVE** (password) |
| Authed same-origin network capture | **BLOCKED_OWNER_INTERACTIVE** (login + deploy) |
| Authed Central Command render / event detail / citations | **BLOCKED_OWNER_INTERACTIVE** (login + deploy) |
| Live chat/voice through authed browser | **BLOCKED_OWNER_INTERACTIVE** (login + deploy) |
| Desktop + 390×844 authed visual | **BLOCKED_OWNER_INTERACTIVE** (login + deploy) |
| Physical spoken voice | **PHYSICAL_VOICE_ENVIRONMENT_BLOCKED** |
| Live portfolio relevance | **LIVE_PORTFOLIO_RELEVANCE_NOT_WIRED** (by design) |
| Optional model summary | **OPTIONAL_MODEL_SUMMARY_UNEXERCISED** (deterministic authoritative) |

## Owner steps to finish full certification
1. Deploy the new build (canonical local restart) — e.g. `python scripts/reset_owner_password.py` is unrelated; restart via the established `com.saathi.local`/`start_local.sh` path, being mindful of the `kickstart -k` race (may need a manual backend start).
2. Log in at `http://localhost:3100`.
3. Open `/research`, verify overview/events/detail/citations/source-health/brief render from the live snapshot (14 rows already present).
4. Ask in chat: "What changed in NEPSE today?" then a present symbol (e.g. "Show UMRH disclosures").
5. Voice: "What happened in NEPSE today?"
6. DevTools network: confirm all research calls hit `:3100`, none hit `:8765`; check 390×844.

## Verdict
Backend, data-layer, same-origin routing, real-evidence population, no-model operation,
regression, and authority are proven live; the authenticated **browser** E2E (login-gated) and
the new-build **deploy** are owner-interactive and were not performed. Therefore:

**SAATHIOS_RESEARCH_SURFACE_UI_WIRING_CERTIFIED_WITH_LIMITATIONS** (unchanged; not upgraded to
full CERTIFIED — authed browser E2E outstanding, owner-interactive). **Not frozen.**

## Next milestone
`M — RESEARCH_SURFACE_OWNER_E2E_CLOSURE`: owner deploys + logs in; re-run the browser/voice/
viewport gates to upgrade to full CERTIFIED and freeze. Browser-use stays DEFER.
