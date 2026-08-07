# DOCUMENTATION_TRUTH_AUDIT

**Rule:** Historical evidence files are **immutable**. This audit classifies claims; it does not rewrite certifications.

| Claim area | Doc signal | Code/tests | Git ancestry | Classification |
| --- | --- | --- | --- | --- |
| master is product tip | implied by default GitHub base | False — tip is 331 commits ahead | master behind harness tip | **STALE** (as product baseline) |
| BUILD_STATUS “current milestone M5” | BUILD_STATUS.md last updated 2026-07-03 | Far superseded | pre-UI-foundation era relative to tip | **STALE** |
| AUTONOMOUS_ROADMAP FM-I6.2 LIVE denied | tip roadmap entry | memory gate code + evidence | on recommended tip | **VERIFIED** |
| Private alpha launch readiness certified_with_limitations | LOOP_STATE m336–m343 | suite claims in LOOP_STATE; not re-run fully here | contained | **VERIFIED_WITH_LIMITATIONS** (not re-executed this audit) |
| Live trading unauthorized | LOOP_STATE + TG cert fields | flags/code denials | contained | **VERIFIED** |
| Provider connectivity disabled | LOOP_STATE / provider contracts | mock connectivity packages | contained | **VERIFIED** |
| ExecutionGateway sole authority | M49 / FM docs | gateway + harness bridge | contained | **VERIFIED_WITH_LIMITATIONS** (residual subprocess tools) |
| AgentHarness production ready | some narrative risk | FM-I explicitly non-production | tip | **CONTRADICTED** if claimed production; docs mostly careful |
| Local model role-qualified | M369–M376 | qualification apparatus | contained | **VERIFIED_WITH_LIMITATIONS** (not production; FM-I6 model pin not role-qualified) |
| Full duplex voice | none honest | interruption docs say no | contained | N/A — **DESIGN_ONLY** not claimed |
| Voice settings surface exists | VOICE inventory | `settings/voice` page | private-alpha | **VERIFIED** |
| Owner audible voice review complete | checklist template | not re-run | — | **UNVERIFIED** (this audit) |
| Twenty integration productized | PR #15 draft | evaluation branch only | OUT of baseline | **DESIGN_ONLY / UNPUBLISHED** relative to baseline |
| M17 concurrency fixed on all tips | PR #17 merged to m344-remote | fix commits | **missing from harness tip** | **CONTRADICTED** if claimed on recommended tip |
| Paper portfolio / sim OMS | TG docs + PORTFOLIO_ACCOUNTING | PaperPortfolioEngine, OrderSimulator | contained | **VERIFIED** (paper-only) |
| Institutional fund ledger | roadmap aspirations | not full multi-book fund admin | — | **DESIGN_ONLY / MISSING** |
| CAPABILITY_MATURITY_MATRIX rows | matrix | mixed ages | — | **VERIFIED_WITH_LIMITATIONS** / many **STALE** rows need per-row reval |
| FM-C1 freeze / contradiction register | architecture docs | present on tip | contained | **VERIFIED** as documentation freeze, not runtime proof |
| Clean-clone private alpha | CLEAN_CLONE_CERT | evidence present | contained | **VERIFIED_WITH_LIMITATIONS** (historical run) |
| PR #21 size = true feature surface | GitHub additions 430k | mostly base=master artifact | head contains full chain | **CONTRADICTED** as “FM-I6-only size” |

## Documentation systems of record (preferred)

1. `docs/AUTONOMOUS_ROADMAP.md` on recommended tip (recent FM entries)  
2. `docs/architecture/*` FM-C1 freeze set  
3. `docs/e2e-functional-audit/*` for voice/UI recovery  
4. `docs/trading/*` + LOOP_STATE heritage for TG  
5. **This audit directory** for integration truth  

Do not treat `BUILD_STATUS.md` as current without rewrite in a future docs mission.
