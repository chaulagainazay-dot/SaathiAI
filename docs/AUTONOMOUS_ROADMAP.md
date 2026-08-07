# SaathiOS Autonomous Roadmap

## FM-I6.1 — LocalModelHarness Closeout (2026-08-07)

| Field | Value |
| --- | --- |
| Mode | **Hardening / publication closeout** — no new features |
| Baseline | FM-I6 @ `228f6efbc94402fc2a4129cb038b34d5ec7f8f51` |
| Branch | `implementation/fm-i6-bounded-local-model-harness` |
| Report | `docs/agent-runtime/FM_I6_1_CLOSEOUT.md` |
| Evidence | `docs/evidence/fm_i6_1/` |
| Runtime boundary | **TRUE_WILDCARD_EXPOSURE** (`*:11434` LAN/global open) — operator guide only |
| Live inference | **SKIPPED** (binding + memory free%) |
| Mock regression | 184 passed, 1 skipped |
| Terminal verdict | `FM_I6_1_CLOSEOUT_CERTIFIED_WITH_LIMITATIONS` |
| FM-I7 ready | **No** |
| Production certified | **False** |
| Next | FM-I7 only after separate owner authorization + preferably operator loopback rebind |

## FM-I6 — Bounded LocalModelHarness Implementation (2026-08-07)

| Field | Value |
| --- | --- |
| Mode | **Internal non-production** — LocalModelHarness plumbing + mock transport |
| Baseline | FM-I5 @ `8a45aa947944540e87a106616a2d42142543a5ca` |
| Branch | `implementation/fm-i6-bounded-local-model-harness` |
| Report | `docs/agent-runtime/FM_I6_LOCAL_MODEL_HARNESS_IMPLEMENTATION.md` |
| Package | `saathi.agent_runtime.harness.local_model*` |
| Runtime | Ollama user-managed loopback; mock transport CI-authoritative |
| Model pin | `qwen2.5:1.5b` (not role-qualified) |
| Live tests | Gated — binding unsafe and/or memory pressure on certifying host |
| Terminal verdict | `FM_I6_LOCAL_MODEL_HARNESS_CERTIFIED_WITH_LIMITATIONS` |
| Production certified | **False** |
| Next | **FM-I7 only after separate owner authorization** — do not auto-start |

## FM-I5 — LocalModelHarness Design and Security (2026-08-07)

| Field | Value |
| --- | --- |
| Mode | **Design-only** — architecture + security ADR; no implementation |
| Baseline | FM-I4 @ `498bf2f75dfe765368a125bfe68c1a3e8e1a985f` |
| Branch | `docs/fm-i5-local-model-harness-design` |
| ADR | `docs/adr/ADR-LOCAL-MODEL-HARNESS.md` |
| Report | `docs/agent-runtime/FM_I5_LOCAL_MODEL_HARNESS_DESIGN.md` |
| Runtime selection | `OLLAMA_SELECTED` (0.32.5 user-managed) |
| Model pin | `qwen2.5:1.5b` (digest pinned; synthetic proof only; not M376 role-qualified) |
| Process ownership | `USER_MANAGED_RUNTIME` |
| Network | loopback `http://127.0.0.1:11434` only; cloud fallback prohibited |
| Terminal verdict | `FM_I5_LOCAL_MODEL_HARNESS_DESIGN_APPROVED_WITH_LIMITATIONS` |
| Production certified | **False** |
| Forbidden | LocalModelHarness code, ollama pull/run/start/stop, inference, providers, credentials, FM-I6 without new auth |
| Next | **FM-I6 only after separate owner authorization** — do not auto-start |

## FM-I4 — Harness Resource Governance (2026-08-07)

| Field | Value |
| --- | --- |
| Mode | **Internal non-production** — in-process admission, queue, fairness, limits |
| Baseline | FM-I3 @ `4ebcd71c9489823bd7c53a44822d0bb572abf012` |
| Branch | `implementation/fm-i4-resource-governance` |
| Report | `docs/agent-runtime/FM_I4_RESOURCE_GOVERNANCE.md` |
| Governor | `HarnessSessionGovernor` (not a general scheduler) |
| Production certified | **False** |
| Next | **FM-I5 only after separate owner authorization** |

## FM-I3 — Durable Harness Session State (2026-08-07)

| Field | Value |
| --- | --- |
| Mode | **Internal non-production** — isolated SQLite session/event durability |
| Baseline | FM-I2 @ `dd09ca033dd335694975b42102d11b0375a4e53e` |
| Branch | `implementation/fm-i3-durable-harness-state` |
| Report | `docs/agent-runtime/FM_I3_DURABLE_HARNESS_STATE.md` |
| Store | `HarnessDurableStore` (injected; no process singleton) |
| Replay | Inspection only (`can_execute=False`) |
| Recovery | Fail-closed; no auto tool/model resume |
| Production certified | **False** |
| Next | **FM-I4 only after separate owner authorization** |

## FM-I2 — Real ExecutionGateway Integration (2026-08-07)

| Field | Value |
| --- | --- |
| Mode | **Internal non-production** — real EG contract via isolated local no-op/echo only |
| Baseline | FM-I1.5 @ `43df48b79065ceec1f37fd9dacca1d09579b6b67` |
| Branch | `implementation/fm-i2-execution-gateway-integration` |
| Report | `docs/agent-runtime/FM_I2_EXECUTIONGATEWAY_INTEGRATION.md` |
| Adapter | `RealExecutionGatewayAdapter` → `ExecutionGateway.submit` |
| GatewayTestDouble | Retained for isolated unit tests |
| Production certified | **False** |
| Next | **FM-I3 only after separate owner authorization** |

## FM-I1.5 — Harness Stress Certification (2026-08-07)

| Field | Value |
| --- | --- |
| Mode | **Internal non-production** — stress, fuzz, concurrency, replay; no real adapter |
| Baseline | FM-I1 @ `bf957f8fd7c942bcc139a30dfcb596c9d6b44fec` |
| Branch | `implementation/fm-i1.5-harness-stress-certification` |
| Report | `docs/agent-runtime/FM_I1_5_HARNESS_STRESS_CERTIFICATION.md` |
| Tests | `tests/test_fm_i1_5_harness_stress.py` + FM-I1 suite |
| Production certified | **False** |
| Next | **FM-I2 only after separate owner authorization** |

## FM-I1 — Fake AgentHarness Proof (2026-08-07)

| Field | Value |
| --- | --- |
| Verdict | See terminal certification on branch `implementation/fm-i1-fake-agent-harness` |
| Mode | **Internal non-production proof** — contract types + FakeInMemoryHarness + HarnessSessionController |
| Authorized base | `docs/fm-c2-agent-session-harness-relationship` @ `97dc6bfab840834f3430df347f526835d94f34cd` |
| Package | `saathi.agent_runtime.harness` |
| Tests | `tests/test_fm_i1_agent_harness.py` |
| FZ-01 | **Partially unfrozen** for FM-I1 scope only |
| FZ-02 / FZ-07 | **Fully retained** |
| Production certified | **False** |
| Forbidden | Providers, commercial CLIs, Ollama, credentials, network/shell/browser, AgentSessionAdapter edits, EG replacement |
| Next | **FM-I2 only after separate owner authorization** — do not auto-start |

**AgentHarness is an internal platform multi-turn driver proof. Not production-activated.**

## FM-C2 — AgentSessionAdapter ↔ AgentHarness Relationship (2026-08-06)

| Field | Value |
| --- | --- |
| Verdict | `AGENT_SESSION_HARNESS_RELATIONSHIP_APPROVED_WITH_LIMITATIONS` |
| Mode | **Design-only** — no production code, no adapter changes, no FakeInMemoryHarness |
| Baseline SHA | `f79726d5746ecd485210dee6af12a3ed33a9f01e` |
| ADR | `docs/adr/ADR-AGENT-SESSION-ADAPTER-HARNESS-RELATIONSHIP.md` |
| Design | `docs/architecture/FM_C2_AGENT_SESSION_ADAPTER_HARNESS_RECONCILIATION.md` |
| Decision | **Alternative F** — controller composition + plane separation |
| Platform multi-turn contract | **AgentHarness** (FM-I1 internal fake proof landed; still not production) |
| Engineering process sessions | **AgentSessionAdapter** (active; eng-scoped only; **unchanged by FM-I1**) |
| Wrap/implement each other? | **No in v1** |
| ToolIntent construction | Controllers only — never either driver |
| CX-05 | **Closed** (relationship) |
| FZ-01 | **Partially unfrozen** for FM-I1 only (2026-08-07) |
| FZ-02 | **Retained** |
| Commercial CLIs | **Blocked** (FZ-07) |
| Next | **FM-I1 complete on implementation branch** — do not start FM-I2 without owner authorization |

**Do not modify AgentSessionAdapter or integrate commercial CLIs from this ADR alone.**

## FM-C1 — Architecture Documentation Freeze and Contradiction Repair (2026-08-06)

| Field | Value |
| --- | --- |
| Verdict | `ARCHITECTURE_DOCUMENTATION_BASELINE_FROZEN_WITH_LIMITATIONS` |
| Mode | **Documentation only** — no production code, adapters, renames, providers, credentials, CI |
| Starting SHA | `e9581f43848cf90283c7c4e1c0dbfbad65a4a531` |
| Authority index | `docs/architecture/ARCHITECTURE_AUTHORITY_INDEX.md` |
| Terminology | `docs/architecture/CANONICAL_TERMINOLOGY.md` |
| Freeze register | `docs/architecture/ARCHITECTURE_FREEZE_REGISTER.md` |
| Contradiction register | `docs/architecture/FM_C1_CONTRADICTION_REGISTER.md` |
| Baseline report | `docs/architecture/FM_C1_DOCUMENTATION_BASELINE_REPORT.md` |
| Key repair | ADR-EXECUTIONGATEWAY → **ACCEPTED_IMPLEMENTED** (was stale “awaiting implementation”) |
| AgentHarness | Remains **unimplemented** and **frozen** (FZ-01) |
| FakeInMemoryHarness | **Unauthorized** |
| Policy floors / skill promotion | **Deferred** (FZ-16 / FZ-17); not renumbered as active milestones |
| Commercial CLIs | **Blocked** (FZ-07) |
| Next | **Completed:** FM-C2 design relationship. Implementation remains **FM-I1** gated. |

**Documentation baseline frozen. Implementation still separately gated.**

## M386–M393 — Architecture Consolidation and Overlap Review (2026-08-06)

| Field | Value |
| --- | --- |
| Verdict | `SAATHIOS_ARCHITECTURE_READY_WITH_CONSOLIDATION_REQUIRED` |
| Mode | **Analysis + design only** — no production code, adapters, migrations, providers, or CI |
| Inspected SHA | `e9581f43848cf90283c7c4e1c0dbfbad65a4a531` |
| ADR | `docs/adr/ADR-SAATHIOS-ARCHITECTURE-CONSOLIDATION.md` |
| Full review | `docs/architecture/M386_M393_ARCHITECTURE_CONSOLIDATION_REVIEW.md` |
| Composite readiness | ≈ 68 / 100 (see scorecard in review) |
| ExecutionGateway | Remains **sole** external-action authority |
| AgentHarness | Design retained **conditionally**; **not** to implement until engineering `AgentSessionAdapter` relationship ADR (FM-C2) |
| Renumbering | Prior QM ADR “M386 policy floors / M387 skill promotion” **deferred** (not cancelled); M386–M393 reclaimed for consolidation |
| Forbidden | AgentHarness types; FakeInMemoryHarness; policy floors; skill promotion; commercial CLIs; EG/TG/RBAC weaken; QM import |
| Next | **Completed follow-on:** FM-C1 documentation baseline. Then **FM-C2** design-only only. |

**Do not auto-start AgentHarness implementation, policy floors, skill promotion, or commercial CLI adapters.**

## M385 — AgentHarness Interface Design (2026-08-06)

| Field | Value |
| --- | --- |
| Verdict | `AGENT_HARNESS_DESIGN_APPROVED_WITH_LIMITATIONS` |
| Mode | **Design-only** — no adapters, no runtime code, no providers |
| ADR | `docs/adr/ADR-AGENT-HARNESS-INTERFACE.md` |
| Design | `docs/agent-runtime/M385_AGENT_HARNESS_INTERFACE_DESIGN.md` |
| Placement | Under `agent_runtime` via controller; tools only via ExecutionGateway |
| First future adapter order | FakeInMemoryHarness → LocalModelHarness (read-only) → bounded coding |
| Forbidden | QM import; gateway bypass; TG change; commercial CLI adapters without cert |
| Next | M386–M393 + **FM-C1 complete**. Implementation still blocked; next design = **FM-C2** only |

**AgentHarness is an internal driver contract, not an authority layer. Design-only; not implemented.**

## M377–M384 — QM Multi-Agent Runtime Architecture Gap Analysis (2026-08-06)

| Field | Value |
| --- | --- |
| Verdict | `ADAPT_SELECTED_PATTERNS` |
| Mode | **Analysis-only** — no production code, no deploy, no QM import |
| QM tip audited | `0f0e0adccce2` (github.com/yc-software/qm, MIT) |
| ADR | `docs/adr/ADR-QM-MULTI-AGENT-RUNTIME.md` |
| Evidence | `docs/agent-runtime/M377_M384_QM_MULTI_AGENT_RUNTIME_GAP_ANALYSIS.md` |
| Scores | Architecture 42 · Security 38 · Governance 31 (0–100) |
| Forbidden | Replace ExecutionGateway / Approval / Governance / RBAC / Trading Guardian |
| Follow-on | M385 design complete; M386–M393 architecture consolidation complete (docs); policy floors / skill promotion still deferred |

**QM is a conceptual reference only. No runtime alignment. No plugin integration. No QM source copied.**

## M296–M303 — Institutional Portfolio & Risk Intelligence (2026-07-30)

| Field | Value |
| --- | --- |
| Verdict | `INSTITUTIONAL_PORTFOLIO_RISK_INTELLIGENCE_CERTIFIED_WITH_LIMITATIONS` |
| Max state | `INSTITUTIONAL_PORTFOLIO_RISK_INTELLIGENCE_ONLY` |
| Package | `saathi/platform/tg/portfolio_risk/` |
| Branch | `milestone/m296-m303-portfolio-risk-intelligence` |
| UI | `/trading/portfolio-risk` |
| Browser | `cert:m303` |
| Broker / live / orders | **Not authorized** |
| Next | M304–M311 read-only market observation after review |

Evidence: `docs/trading/M296_M303_PORTFOLIO_RISK_INTELLIGENCE.md`, `docs/trading/m296_m303_evidence/`.

## M280–M287 — Autonomous Research Orchestrator (2026-07-30)

| Field | Value |
| --- | --- |
| Verdict | `AUTONOMOUS_RESEARCH_ORCHESTRATOR_CERTIFIED_WITH_LIMITATIONS` |
| Max state | `AUTONOMOUS_RESEARCH_ORCHESTRATION_ONLY` |
| Package | `saathi/platform/tg/research_orchestrator/` |
| Branch | `milestone/m280-m287-autonomous-research-orchestrator` |
| UI | `/trading/research-orchestrator` |
| Browser | `cert:m287` |
| Live / broker / orders | **Not authorized** |
| Next | M288–M295 paper simulation only after review |

Evidence: `docs/trading/M280_M287_AUTONOMOUS_RESEARCH_ORCHESTRATOR.md`, `docs/trading/m280_m287_evidence/`.

## M272–M279 — Multi-Strategy Research Lab & Adaptive Portfolio Intelligence (2026-07-30)

| Field | Value |
| --- | --- |
| Verdict | `MULTI_STRATEGY_RESEARCH_LAB_AND_ADAPTIVE_PORTFOLIO_INTELLIGENCE_CERTIFIED_WITH_LIMITATIONS` |
| Max state | `RESEARCH_PORTFOLIO_AND_PAPER_CANDIDATE_EVALUATION_ONLY` |
| Package | `saathi/platform/tg/research_lab/` |
| Branch | `milestone/m272-m279-multi-strategy-research-lab` |
| UI | `/trading/research-lab` |
| Browser | `cert:m279` |
| Preserved OOS | AAPL + BTCUSDT `tf_dual_ma` remain `OUT_OF_SAMPLE_FAILED` |
| Paper candidate | Human review required; does **not** authorize execution |
| Live / broker / canary / orders | **Not authorized** |
| Next | Completed by M280–M287 orchestrator |

Evidence: `docs/trading/M272_M279_MULTI_STRATEGY_RESEARCH_LAB.md`, `docs/trading/m272_m279_evidence/`.

## M264–M271 — Intelligence Recovery, Clean-Clone Repro & Historical Data (2026-07-30)

| Field | Value |
| --- | --- |
| Verdict | `INTELLIGENCE_BASELINE_RECOVERED_AND_HISTORICAL_DATA_QUALIFIED_WITH_LIMITATIONS` |
| Defect fixed | M248–M255 was untracked; now committed |
| Clean clone | Backend 37 / FE 10 / build / cert:m255 / cert:m263 passed |
| Historical status | `BOUNDED_REAL_HISTORICAL_DATA_VALIDATED_WITH_LIMITATIONS` |
| Branch | `milestone/m264-m271-intelligence-recovery-historical-data` |
| UI | `/trading/intelligence` + `/trading/research-data` |
| Browser | `cert:m255`, `cert:m263`, `cert:m271` |
| Live / broker / canary / orders | **Not authorized** |
| Next | Completed by M272–M279 research lab |

**M248–M255 IS NOW PRESENT IN COMMITTED GIT HISTORY.**
**M248–M263 PASSES FROM A CLEAN CLONE USING COMMITTED SOURCE ONLY.**

Evidence: `docs/trading/M264_M271_INTELLIGENCE_RECOVERY_AND_HISTORICAL_DATA.md`, `docs/trading/m264_m271_evidence/`.

## M256–M263 — Market Data Foundation, Dataset Governance & Signal Validation (2026-07-30)

| Field | Value |
| --- | --- |
| Verdict | `RESEARCH_GRADE_MARKET_DATA_AND_SIGNAL_VALIDATION_CERTIFIED_WITH_LIMITATIONS` |
| Max state | `RESEARCH_DATA_AND_SIGNAL_VALIDATION_READY` |
| Package | `saathi/platform/tg/market_data/` |
| Branch | `milestone/m256-m263-market-data-signal-validation` |
| UI | `/trading/research-data` |
| CLI | `md-*` / `paper-gov md-*` |
| API | `/api/v1/platform/tg/research-data/*` |
| Tests | Focused 23; II+MD 37; FE unit 10; browser WITH_LIMITATIONS |
| Synthetic label | `SYNTHETIC_TEST_DATA` when fixtures used |
| Historical completeness | `REAL_HISTORICAL_DATA_VALIDATION_INCOMPLETE` on fixture-only cert |
| Connectivity / credentials / canary / orders | **Not authorized** |
| Live trading | **Not authorized** |
| Next | M264 only after human review; do not auto-start |

**THE SYSTEM REMAINS RESEARCH, PAPER AND SANDBOX ONLY.**

**NO REAL BROKER CONNECTION. NO CREDENTIALS. NO CANARY ACTIVATION. NO ORDER EXECUTION. NO GUARANTEED PROFITABILITY.**

Evidence: `docs/trading/M256_M263_MARKET_DATA_AND_SIGNAL_VALIDATION.md`, `docs/trading/m256_m263_evidence/`.

## M248–M255 — Institutional Investment Intelligence & Portfolio Brain (2026-07-30)

| Field | Value |
| --- | --- |
| Verdict | `INSTITUTIONAL_INVESTMENT_INTELLIGENCE_CERTIFIED_WITH_LIMITATIONS` |
| Max state | `PAPER_INTELLIGENCE_ENGINE_READY` |
| Package | `saathi/platform/tg/intelligence/` |
| UI | `/trading/intelligence` |
| Limitation addressed by M256–M263 | Ungoverned synthetic bars when no historical dataset |

Evidence: `docs/trading/M248_M255_INSTITUTIONAL_INVESTMENT_INTELLIGENCE.md`, `docs/trading/m248_m255_evidence/`.

## M240–M247 — Provider Selection, Read-Only Canary Design & Human Authorization Package (2026-07-30)

| Field | Value |
| --- | --- |
| Verdict | `PROVIDER_CANARY_PLANNING_CERTIFIED_WITH_LIMITATIONS` |
| Max state | `READ_ONLY_CANARY_PACKAGE_READY_FOR_OWNER_REVIEW` |
| Preferred provider | **Alpaca** (recommendation only; eligibility unconfirmed) |
| Fallback provider | **Kraken** |
| Package | `saathi/platform/tg/provider_canary_planning/` |
| Branch | `milestone/m240-m247-provider-canary-planning` |
| UI | `/trading/provider-canary-planning` |
| CLI | `paper-gov pcp-*` |
| API | `/api/v1/platform/tg/provider-canary-planning/*` |
| Tests | Focused 23; M216–M247 regression 79; FE unit 15; browser WITH_LIMITATIONS |
| Connectivity / credentials / canary | **Not authorized** |
| Live trading | **Not authorized** |
| Owner sign-off | **Not claimed by automation** |
| Next | M248 only after human owner review; do not auto-start |

**THE SYSTEM REMAINS PAPER, SANDBOX AND PLANNING ONLY.**

**NO REAL BROKER CONNECTION. NO CREDENTIALS. NO CANARY ACTIVATION. PREFERRED PROVIDER IS A RECOMMENDATION ONLY.**

Evidence: `docs/trading/M240_M247_PROVIDER_CANARY_PLANNING.md`, `docs/trading/m240_m247_evidence/`.

## M208–M215 — Extended Paper Campaign Validation & Operational Graduation (2026-07-30)

| Field | Value |
| --- | --- |
| Verdict | `OPERATIONAL_GRADUATION_CERTIFIED_WITH_LIMITATIONS` |
| Scope | Multi-campaign ops, health monitoring, graduation, intelligence, analytics, simulation, evidence, dashboard |
| Package | `saathi/platform/tg/paper_activation/ops/` over durable paper gov |
| Branch | `milestone/m208-m215-ops-graduation` |
| Tests | Focused 15; TG M166–M215 115; full backend 5568/1 skipped; frontend 240; build pass |
| Browser | `OPS_GRADUATION_BROWSER_CERT_PASSED_WITH_LIMITATIONS` |
| Live / production | Not authorized |
| Auto live promotion | Forbidden |

**THE SYSTEM REMAINS PAPER ONLY. LIVE TRADING IS NOT AUTHORIZED. NO STRATEGY IS AUTOMATICALLY PROMOTED TO LIVE EXECUTION.**

**OPERATIONAL GRADUATION DOES NOT GRANT BROKER OR REAL-MONEY AUTHORITY.**

Evidence: `docs/trading/M208_M215_OPERATIONAL_GRADUATION.md`, `docs/trading/m208_m215_evidence/`.

## M200–M207 — Durable Paper Ledger & Long-Horizon Ops (2026-07-29)

| Field | Value |
| --- | --- |
| Verdict | `DURABLE_PAPER_OPERATIONS_CERTIFIED_WITH_LIMITATIONS` |
| Storage | SQLite WAL multi-process paper_gov.db |
| Event ledger | Append-only pg_events |
| Campaigns | Long-horizon paper campaigns (never live-eligible) |
| Live / production | Not authorized |

Evidence: `docs/trading/M200_M207_DURABLE_PAPER_OPERATIONS.md`, `docs/trading/m200_m207_evidence/`.

## M192–M199 — Paper Activation Governance (2026-07-29)

| Field | Value |
| --- | --- |
| Verdict | `PAPER_ACTIVATION_GOVERNANCE_CERTIFIED_WITH_LIMITATIONS` |
| Activation | Owner-approved PAPER_ELIGIBLE → PAPER_ACTIVE only |
| Portfolio | Multi-portfolio cash simulator; risk halt; kill switch |
| Orders | Market/limit/stop/IOC/FOK; fees/slippage; no exchange |
| Browser | PAPER_ACTIVATION_BROWSER_CERT_PASSED |
| Live / production | Not authorized |

Evidence: `docs/trading/M192_M199_PAPER_ACTIVATION.md`, `docs/trading/m192_m199_evidence/`.

## M184–M191 — Historical Market Data & Strategy Qualification (2026-07-29)

| Field | Value |
| --- | --- |
| Verdict | `TRADING_GUARDIAN_HISTORICAL_RESEARCH_CERTIFIED_WITH_LIMITATIONS` |
| Historical adapters | Local CSV/Parquet, Binance public (file-first), NEPSE local, Yahoo local |
| Quality / CA | Strict gates; raw preserved; quarantine non-promotable |
| Research | Multi-period + regime matrix + WF + stress + Monte Carlo |
| Qualification | 26-gate PAPER_ELIGIBLE; fixture never promotes |
| Browser | M191 historical browser cert (automated; owner sign-off not claimed) |
| Live / production | Not authorized |

Evidence: `docs/trading/M184_M191_HISTORICAL_RESEARCH.md`, `docs/trading/m184_m191_evidence/`.

## M176–M183 — Trading Guardian Paper Validation (2026-07-29)

| Field | Value |
| --- | --- |
| Verdict | `TRADING_GUARDIAN_PAPER_VALIDATION_CERTIFIED_WITH_LIMITATIONS` |
| Data contract | AUTHORITATIVE_RESULT_REQUIRES_NON_FIXTURE_DATA; fail-closed incomplete |
| Walk-forward | Expanding/rolling/anchored; final test untouched |
| Stress lab | Costs, regimes, data quality, parameter sensitivity |
| Portfolio | Correlation/sector/heat; UNRECONCILED_BLOCKED |
| Recovery | 16/16 scenarios |
| Browser | TRADING_GUARDIAN_BROWSER_CERT_PASSED (automated; owner sign-off not claimed) |
| Backend | 5499 passed, 1 skipped |
| Frontend | 218 passed |
| Live / production | Not authorized |

Evidence: `docs/trading/M176_M183_PAPER_VALIDATION.md`, `docs/trading/m176_m183_evidence/`.

## M166–M175 — Trading Guardian Research & Paper Foundation (2026-07-29)

| Field | Value |
| --- | --- |
| Verdict | `TRADING_GUARDIAN_RESEARCH_AND_PAPER_FOUNDATION_READY_WITH_LIMITATIONS` |
| Package | `saathi/platform/tg/` composition over M62 paper stack |
| Strategies | Kotegawa-inspired MR, trend, momentum RS, no-trade control |
| Authority | ADVISORY default; paper only; no live mode |
| Gates | Policy + risk + kill switch + Approval Center + ExecutionGateway |
| UI | /trading + regime/proposals/backtests/comparison/journal/policy |
| CLI | `python -m saathi.platform.tg.cli` |
| Tests | M166–M175 focused 28; M62 regression subset green |
| Live / production | Not authorized |

Evidence: `docs/trading/M166_M175_TRADING_GUARDIAN_FOUNDATION.md`, `docs/trading/m166_m175_evidence/`.

## M80–M86 — Live Conversational Intelligence (2026-07-28)

| Field | Value |
| --- | --- |
| Verdict | `LIVE_CONVERSATIONAL_INTELLIGENCE_COMPLETE_WITH_LIMITATIONS` |
| Service | Central `ConversationService` under `saathi/platform/conversation/` |
| Provider | Local Ollama `qwen2.5:1.5b` (NDJSON stream); unavailable fail-closed |
| Voice | Voice Runtime calls ConversationService; templates removed from default path |
| Context | Multi-turn SessionMemory; second turn retains prior context |
| Interrupt | Cancels generation + speech; late chunks rejected |
| Intent | Propose/block only; ExecutionGateway remains sole executor |
| STT | Browser path certified for partial/final contract |
| Browser media | Playwright synthetic getUserMedia PASS |
| Tests | M80 11; M79 17; M74 15; M72 cert subset; frontend voice 11 |
| Production | Not authorized |

Evidence: `docs/autonomous/milestones/M80_M86_LIVE_CONVERSATIONAL_INTELLIGENCE.md`,
`docs/evidence/m86/`, `docs/evidence/m85/`.

## M79 — Real-Time Voice Runtime (2026-07-28)

| Field | Value |
| --- | --- |
| Milestone | `M79_COMPLETE_WITH_LIMITATIONS` |
| Verdict | `REALTIME_VOICE_RUNTIME_COMPLETE_WITH_LIMITATIONS` |
| Runtime | Centralized VoiceSessionManager + input/VAD/STT/conversation/SpeechRuntime/playback |
| Speech | Reuses certified SpeechService; incremental segment speak; exclusive playback |
| STT | browser (streaming partials), whisper_compatible (if installed), macos_speech (helper), unavailable |
| UI | Unified-shell Live Voice dock: mic, indicators, transcript, interrupt, history |
| RBAC | `voice.listen`, `voice.transcribe`, `voice.session.read` (+ existing speak) |
| Regression | M79 backend 17; M74 15; frontend voice 10 |
| Browser | Code-complete explicit-mic path; automation getUserMedia not fully certified |
| Production | Not authorized; no push/merge/deploy/model download/cloning |
| Next | Optional ChatEngine binding and human mic certification |

Evidence: `docs/autonomous/milestones/M79_REALTIME_VOICE_RUNTIME.md` and
`docs/evidence/m79/`.

## M77 — Voice Output Foundation Certification (2026-07-28)

| Field | Value |
| --- | --- |
| Milestone | `M77_COMPLETE_WITH_LIMITATIONS` |
| Verdict | `VOICE_FOUNDATION_COMPLETE_WITH_LIMITATIONS` |
| Speech | Authenticated provider-neutral service can synthesize local English through the macOS system provider |
| Providers | macOS runtime-verified; Unavailable truthful; VoxCPM adapter implemented but disabled/not installed/not configured/not runtime-verified |
| Lifecycle | Persisted queue, bounded workers, heavy concurrency 1, cancel, timeout, cleanup, restart reconciliation, evidence/audit |
| UI | Shared shell Speak/Play/Stop, provider/fallback state, profile/rate controls, no autoplay; IELTS feedback-only Yeti read-aloud |
| Regression | Voice backend 15; full backend 5,272 passed/1 skipped; frontend 189; ESLint/build pass |
| Browser | Dedicated M77 production journey FAIL after 14 hard + 1 accessibility gates; M64 regression PASS (21 hard/12 state/6 responsive/3 accessibility); no browser certification claim |
| Security | 19 changed production files secret-clean; Python dependencies consistent; production npm audit zero; cloning disabled |
| Resources | M2/8 GiB; cold 4.539s, warm 1.663s, ~48.3MB max RSS, cancel 46.04ms; no VoxCPM/model download |
| Languages | English backend/native provider only; browser playback not certified; Nepali unsupported-not-verified |
| Production | Not authorized; no push, merge, PR, deploy, public listener, paid call, or production mutation |
| Next | Diagnose/re-certify the browser client transition before any VoxCPM download or voice expansion |

Evidence: `docs/autonomous/milestones/M77_VOICE_CERTIFICATION.md` and
`docs/evidence/m77/`. This milestone does not authorize production use.

## M72 — Autonomous Mission Runtime Final Certification (2026-07-28)

| Field | Value |
| --- | --- |
| Milestone | M72_COMPLETE |
| Verdict | `MISSION_RUNTIME_COMPLETE` |
| Certification | Server-authored, authenticated, tenant-scoped, immutable, snapshot-hashed, and atomic with the `CERTIFIED` transition |
| Required gates | Complete DAG; no blockers; PASS test/browser and mission evidence; independent approved review; current matching checkpoint; valid commit/rollback SHAs |
| Persistence | Certificate and runtime terminal state survive restart; duplicate or stale certification fails closed |
| Dashboard | Final verdict, certifier, summary, evidence count, snapshot hash, and limitations render from backend state after reload |
| Regression | 3 new; 18 M69–M72; 138 related; full backend 5,257 passed/1 skipped; frontend 183 |
| Browser | Production PASS: 33 hard, 3 responsive, 2 accessibility; zero page/console/hydration errors |
| Security | 16 changed production files secret-clean; Python packages consistent; production npm audit zero vulnerabilities |
| Limits | Single-host/local; internal deterministic attestation; exhaustive AT and production activation deferred |
| Next | Await a separately authorized platform/application mission |

Evidence: `docs/autonomous/M72_MISSION_RUNTIME_CERTIFICATION.md` and
`docs/platform/m72_evidence/`. No push, merge, deployment, or production change.

## M71 — Authenticated Mission Runtime API and Dashboard (2026-07-28)

| Field | Value |
| --- | --- |
| Milestone | M71_COMPLETE |
| API | Authenticated plan/run/control/recovery/approval/evidence/review/checkpoint plus dashboard/detail reads |
| Scope | Existing platform context, RBAC, tenant/project visibility, audit, and approval authority |
| Dashboard | Backend-driven Mission Control cards/detail with health, progress, phase/task/agent, DAG, evidence, blockers, ETA, budgets, and checkpoints |
| Browser authority | Read-only; no direct run, gateway, or automatic approval control |
| Certification | 3 new + 135 related backend tests; 183 frontend; lint/build pass; production browser PASS (21 hard, 2 responsive, 2 accessibility); secret scan clean |
| Next | M72 final certification, full regression/security review, and authoritative capability documentation |

Evidence: `docs/autonomous/M71_MISSION_RUNTIME_DASHBOARD.md` and
`docs/platform/m71_evidence/`. No push, merge, deployment, or production change.

## M70 — Mission Decisions, Agents, Dispatch, and Recovery (2026-07-28)

| Field | Value |
| --- | --- |
| Milestone | M70_COMPLETE |
| Agents | 8 bounded orchestration roles; no identity, permission, connector, or executor authority |
| Scheduling | Priority + dependency readiness; safe bounded parallel batch; finite cycles and no-progress stops |
| Dispatch | PlatformAgentRuntime only; ExecutionGateway remains sole registered-tool executor |
| Decisions | Continue/wait/review/approval/stop/complete; predicted resource gates |
| Recovery | Same-execution approval resume; confirmed-failure retry; no replay after uncertain recorded dispatch |
| Control | Pause, resume, cancellation intent/confirmation, checkpoints |
| Certification | 8 new + 132 related backend tests; 180 frontend; retained M64 browser PASS; production secret scan clean |
| Next | M71 authenticated API and unified-shell Mission Dashboard |

Evidence: `docs/autonomous/M70_MISSION_RUNTIME_ORCHESTRATION.md`. No push, merge,
deployment, or production change.

## M69 — Autonomous Mission Runtime Foundation (2026-07-28)

| Field | Value |
| --- | --- |
| Milestone | M69_COMPLETE |
| Scope | Durable Mission → Goal → Phase → Milestone → Task → Subtask hierarchy, DAG, lifecycle, budgets, evidence/review gates, checkpoints, dashboard read model |
| Authority | Existing platform `missions`, identity/context, RBAC, project/workspace scope, audit, and PlatformStore |
| Execution | No new execution path; M70 must use PlatformAgentRuntime → ExecutionGateway only |
| Persistence | Additive single-host SQLite runtime/nodes/dependencies/evidence/decisions/checkpoints/reviews/certifications |
| Certification | 4 focused + 124 related backend tests; 180 frontend tests; retained M64 browser PASS; production-code secret scan clean |
| Safety | Bounded plans/resources/retries; nested secret fields rejected; no production or trading authority |
| Next | M70 bounded decision/retry/recovery and governed role-agent dispatch |

Evidence: `docs/autonomous/M69_MISSION_RUNTIME_FOUNDATION.md`. No push, merge,
deployment, or production change.

## M61 — Backend Workflow Persistence & Safe Mutation APIs (2026-07-26)

| Field | Value |
| --- | --- |
| Milestone | M61_COMPLETE_WITH_LIMITATIONS |
| Scope | Server-authoritative persistence for plans, notifications, saved views, templates, attention mutations, drafts, and search; optimistic concurrency + audit |
| Backend | CHANGED — models.py (5 permissions), store.py (_migrate_m61 + CRUD, 6 tables), workflow_service.py (new), api.py (20 endpoints) |
| Frontend | Adapters only (lib/workflow-api.js); M60 pages rewired, no UX redesign |
| Capability | plan/notifications/saved-views/templates/attention/search now SERVER_PERSISTED/AUTHORIZED/AUDITED |
| Certification | 11 backend tests; 53 existing platform tests pass; M61 cert proves fresh-browser persistence; FE 130 unit + lint + build green |
| Safety | Execution authority unchanged; approvals server-owned; tenant isolation; localhost-only; production not authorized |
| Deferred (M62) | Distributed persistence, event streaming, multi-node coordination |

Evidence: `docs/platform/M61_*.md`, `docs/platform/m61_evidence/`. No push/merge/deploy.

## M60 — Guided Operator Workflows & Safe Action Orchestration (2026-07-26)

| Field | Value |
| --- | --- |
| Milestone | M60_COMPLETE_WITH_LIMITATIONS |
| Scope | Guided operator journeys: onboarding, mission create/plan, agent selection, approval prep, execution readiness, action queue, notifications, evidence, saved views, search, templates, role-aware actions |
| Backend | Unchanged (no Python files touched) |
| New | `lib/operator.js` (+tests), `lib/local-store.js`, `components/spatial/GuidedWorkflow.jsx`, 13 routes under `app/platform/`, `scripts/m60_browser_cert.mjs` |
| LIVE APIs | mission/project/approval create, governed execution (POST /missions,/projects,/approvals,/execute) |
| Bounded | plan DRAFT_ONLY, notifications DERIVED, saved-views/templates LOCAL_ONLY, search authorized-loaded-records, attention ack/resolve BLOCKED |
| Certification | Production browser cert PASS (25 hard gates); dev regression PASS; axe 0 critical; M59 cert re-run PASS |
| Tests | 130/130 frontend unit (18 new); lint clean; build clean |
| Safety | All M57-M59 boundaries retained; approvals server-owned; no browser-direct execution; production not authorized |
| Deferred (M61) | Backend mutation APIs: plan/notification/saved-view/template persistence, attention resolution, server search |

Evidence: `docs/platform/M60_*.md`, `docs/platform/m60_evidence/`. No push/merge/deploy.

## M59 — Spatial Workspaces, Command Interface & UI Certification (2026-07-26)

| Field | Value |
| --- | --- |
| Milestone | M59_COMPLETE_WITH_LIMITATIONS |
| Scope | Four standalone spatial workspaces (Mission Control, Agent Constellation, Approval Authority Center, Runtime Attention Center) + command palette + context drawer + shared shell |
| Backend | Unchanged (no Python files touched) |
| New | `lib/workspace.js` (+tests), `lib/platform-client.js`, `components/spatial/{SpatialWorkspaceShell,SpatialCommandPalette,SpatialContextDrawer,RequireSession,primitives}`, 8 routes under `app/platform/`, `scripts/m59_browser_cert.mjs` |
| Certification | Production-build browser cert PASS (21 hard gates); dev regression PASS; axe 0 critical (10 serious pre-existing); responsive 390px PASS; reduced-motion PASS |
| Tests | 112/112 frontend unit (18 new); lint clean; build clean |
| Safety | All M57/M58 boundaries retained; approvals server-authorized; production not authorized; connectors dry-run; financial/trading disabled; localhost-only |
| Deferred (M60) | Governed mission/approval creation; operator-safe retry/cancel; evidence-export workflow; notifications; saved views; onboarding; chrome-a11y pass |

Evidence: `docs/platform/M59_*.md`, `docs/platform/m59_evidence/`. No push/merge/deploy.

## M58 — Glass Frame Interface & Central AI Command Center (2026-07-26)

| Field | Value |
| --- | --- |
| Milestone | M58_COMPLETE_WITH_LIMITATIONS |
| Scope | UI/UX transformation of `/platform` + `/platform/ops` into a spatial Glass Frame AI OS |
| Backend | Unchanged (no Python files touched) |
| New | `lib/spatial.js` (+tests), `components/spatial/*`, `scripts/m58_browser_cert.mjs` |
| Certification | M58_BROWSER_CERTIFIED (13 gates); M54/M55/M56/M57 re-run CERTIFIED |
| Tests | 94/94 frontend unit; lint clean; build clean |
| Safety | PlatformAgentRuntime canonical; ExecutionGateway sole tool authority; connectors DRY_RUN_ONLY; financial/trading disabled; multi-host disabled; production not authorized |
| Deferred (M59) | Standalone Mission Control / Agents / Approval / Attention spatial screens; spatial command palette; prod-build cert; axe-core + CWV budget |

Evidence: `docs/platform/M58_*.md`, `docs/platform/m58_evidence/`. No push/merge/deploy.

## M57 — Localhost Daily-Use Hardening, Process Control & Launcher (2026-07-25)

| Item | State |
|---|---|
| Launcher | bin/saathi-local: start/stop/restart/status/open/logs/doctor (~/.local/bin symlink) |
| Ownership | PID-file + command-signature; reuse healthy, stop only own; fail-closed on unrelated |
| Heartbeat | single-host beat on 30s BFF task; node-local healthy while running, stale after stop |
| Cold-load UI | loading state + bounded retry/backoff; transient vs fatal distinguished |
| macOS shortcut | PREPARED (scripts/macos/saathi-open.sh → saathi-local open); operator assigns ⌥⌘B |
| Login startup | LaunchAgent com.saathi.local-launcher prepared, DISABLED by default |
| Local readiness | saathi.platform.local_readiness; wired into doctor + release gate |
| Browser certification | see docs/platform/m57_evidence/ |
| Binding | localhost-only (127.0.0.1 / localhost); never 0.0.0.0; no tunnels |
| Runtime/Gateway | PlatformAgentRuntime canonical; ExecutionGateway sole authority |
| Connectors DRY_RUN_ONLY · Financial/Trading/Multi-host | DISABLED |
| Milestone | M57_COMPLETE_WITH_LIMITATIONS (local) |
| Production | NOT_AUTHORIZED |

Evidence: `docs/platform/M57_*.md`. Localhost-only daily-use hardening; no
deployment, no production, no multi-host.


## M56 — Distributed Runtime Foundation (Single-Host Compatible) (2026-07-25)

| Item | State |
|---|---|
| Abstractions | RuntimeNode/Cluster, WorkerLease/ExecutionLease, RuntimeHeartbeat, DistributedClock |
| Worker registry | register/heartbeat/drain/pause/resume/retire (RUNTIME_OPERATE) |
| Lease coordination | acquire/renew/verify/transfer/recover; single-owner, fail-closed |
| Scheduler | advisory single-host plan (FIFO/priority, round-robin); pause/resume |
| Topology / node health / metrics | read-only, tenant-scoped, no secrets |
| Recovery certification | 7 scenarios (worker/lease/heartbeat/scheduler/drain/retire/reassign) |
| Operator console | /platform/ops cluster/topology/node-health/scheduler/recovery cards |
| Browser certification | see docs/platform/m56_evidence/ |
| Persistence | config-backed (m56_*); NO schema migration; backwards compatible |
| Runtime/Gateway | PlatformAgentRuntime canonical; ExecutionGateway sole authority |
| Connectors DRY_RUN_ONLY · Financial/Trading | DISABLED |
| Trading Guardian | UNENGAGED_ADVISORY_ONLY |
| Milestone | M56_COMPLETE_WITH_LIMITATIONS (local) |
| Production | NOT_AUTHORIZED |

Evidence: `docs/platform/M56_*.md`. Single-host only; multi-host foundation
prepared, not enabled. No deployment, no production authorization.


## M55 — Platform Release Candidate & Operational Excellence (2026-07-25)

| Item | State |
|---|---|
| Release validator | 20 checks PASS/WARNING/FAIL/UNKNOWN + score; advisory only |
| Release gate CLI | `python -m saathi.platform.release_check`; READY_WITH_LIMITATIONS |
| Health service | uptime/memory/queue/sessions/tenant counts/latency; tenant-safe |
| Metrics service | executions/approvals/exports/attention/recovery/errors; no PII |
| Backup validation | manifest+checksum+integrity+restore SIMULATION (non-destructive) |
| Recovery certification | restart/dispatch/binding scenarios; no dup/escalation/replay |
| Operator console | read-only `/platform/ops` dashboard |
| Browser certification | `M55_BROWSER_CERTIFIED` (local, isolated DB) |
| Runtime/Gateway | PlatformAgentRuntime canonical; ExecutionGateway sole authority |
| Connectors DRY_RUN_ONLY · Financial/Trading | DISABLED |
| Trading Guardian | UNENGAGED_ADVISORY_ONLY |
| Milestone | M55_COMPLETE_WITH_LIMITATIONS (local) |
| Production | NOT_AUTHORIZED |

Evidence: `docs/platform/M55_*.md`, browser evidence in
`docs/platform/m55_evidence/`. Advisory release readiness only — no deployment,
no production authorization.


## M54 — Private-Alpha Operational Readiness and Browser Certification (2026-07-25)

| Item | State |
|---|---|
| Diagnostics | tenant-scoped bounded health + private-alpha safety labels |
| Evidence export | JSON/CSV, allowlist + forbidden-key scrub, deterministic hash, audit |
| Retention | dry-run purge preview, holds, owner/admin-gated (never deletes) |
| Recovery drills | restart/approval/dispatch/cancellation/binding races (single-host) |
| Operator UI | `/platform` readiness panel: diagnostics, export, dry-run retention |
| Browser certification | local managed BFF+UI+Chromium; isolated DB; evidence JSON |
| CORS | `X-Platform-Token` allowed; scoped `SAATHI_CORS_ORIGINS` for split-origin |
| Runtime/Gateway | PlatformAgentRuntime canonical; ExecutionGateway sole authority |
| Connectors | DRY_RUN_ONLY · Financial/Trading | DISABLED |
| Trading Guardian | UNENGAGED_ADVISORY_ONLY |
| Milestone | M54_COMPLETE_WITH_LIMITATIONS (local) |
| Production | NOT_AUTHORIZED |

Evidence: `docs/platform/M54_*.md`, browser evidence in
`docs/platform/m54_evidence/`. Deployment, distributed telemetry, real retention
purge, and production authorization are not claimed.


## M53 — Platform Runtime Operations and Binding Administration (2026-07-24)

| Item | State |
|---|---|
| Bindings | multiple durable tenant-scoped identities; ACTIVE/SUSPENDED/REVOKED |
| Binding policy | tool/capability scope + role/owner authority ceilings |
| Runtime operations | list, inspect, timeline, attention, bounded metrics |
| Reconciliation | permissioned/idempotent; uncertain dispatch never replayed |
| Runtime/Gateway | PlatformAgentRuntime canonical; ExecutionGateway authority unchanged |
| UI | bounded private-alpha `/platform` operator views |
| Connectors | DRY_RUN_ONLY |
| Trading Guardian | UNENGAGED_ADVISORY_ONLY |
| Milestone | M53_REMOTE_CERTIFIED_WITH_LIMITATIONS |
| Draft PR | #11 (base M52) — draft, not merged |
| CI | reliability PR-head run 30108250805 success (critical-regressions + full-suite) |
| Production | NOT_AUTHORIZED |

Evidence: `docs/platform/M53_*.md`, remote evidence in
`docs/platform/M53_REMOTE_VERIFICATION.md`. Draft PR #11 pushed and CI-certified;
not merged. Browser certification, deployment, and production authorization are
not claimed.


## M52 — Platform Agent Runtime Consolidation (2026-07-23)

| Item | State |
|---|---|
| Platform runtime | `PlatformAgentRuntime` canonical |
| Gateway | ExecutionGateway retained as sole registered-tool authority |
| Context | token/session/membership/tenant/binding enforced |
| Lifecycle | durable explicit transitions + terminal immutability |
| Recovery | no automatic replay after recorded dispatch |
| Legacy AgentExecutor | direct dispatch removed; platform binding required |
| Remote delivery | draft PR #10; base M51; head M52 |
| CI | reliability run 30056416160 GREEN |
| Connectors | DRY_RUN_ONLY |
| Trading Guardian | UNENGAGED_ADVISORY_ONLY |
| Milestone | M52_COMPLETE_WITH_LIMITATIONS |
| Remote certification | M52_REMOTE_CERTIFIED_WITH_LIMITATIONS |
| Production | NOT_AUTHORIZED |

Evidence: `docs/platform/M52_*.md`. Local and CI validation are recorded.
Browser certification and deployment are not claimed.



## M51 — Private Alpha Productization (2026-07-23)

| Item | State |
|---|---|
| Auth | LOCAL_PASSWORD (scrypt) + fixtures |
| Sessions | hardened (rotate, idle, absolute) |
| Invitations | LOCAL_PRIVATE_ALPHA_INVITE |
| Membership admin | ACTIVE |
| Workspace context | ACTIVE + token rotate on switch |
| Agent binding | PlatformAgentBinding |
| Milestone | M51_COMPLETE_WITH_LIMITATIONS |
| Production | NOT_AUTHORIZED |

Evidence: `docs/platform/M51_*.md`. Superseded in runtime scope by M52.


## M50 — Platform Integration, Identity Foundation, Private Alpha Readiness (2026-07-23)

| Item | State |
|---|---|
| Identity / sessions | ACTIVE (platform store) |
| RBAC | viewer · operator · owner · admin · system |
| Organizations / workspaces | ACTIVE |
| Projects / mission links | ACTIVE |
| Approval Center | ACTIVE (pending→decided→consumed) |
| Platform API | `/api/v1/platform/*` |
| UI | `/platform` foundation console |
| Runtime | Reuses M49 ExecutionGateway only |
| Connectors | DRY_RUN_ONLY |
| Trading Guardian | ADVISORY_ONLY |
| Milestone | M50_COMPLETE_WITH_LIMITATIONS |
| Production | NOT_AUTHORIZED |

Evidence: `docs/platform/M50_*.md`. **M51 not started.**

## M49.4 — Tool Runtime Closure Review and Merge Readiness (2026-07-23)

| Item | State |
|---|---|
| Program | M49 tool-runtime closure + certification |
| Core question | YES_WITH_LIMITATIONS (safe to integrate with residual bounds) |
| Gateway | TOOL_GATEWAY_ENFORCED |
| Legacy | LEGACY_RUNTIME_BOUNDED (59 retained; not eliminated) |
| Shell | FREEFORM_SHELL_BLOCKED (`project_run` always blocked) |
| Connectors | DRY_RUN_ONLY; generic execution ABSENT |
| Idempotency | SINGLE_HOST_SAFE / MULTI_HOST_UNSAFE |
| Merge readiness | MERGE_READY_WITH_LIMITATIONS (no merges performed) |
| Production | PRODUCTION_NOT_AUTHORIZED |
| Trading Guardian | UNENGAGED_ADVISORY_ONLY |
| Milestone | M49_4_COMPLETE_WITH_LIMITATIONS |

Evidence: `docs/tool-runtime/M49_4_*.md`. **M50 not started.**

## M49.3 — Legacy Runtime Elimination, Gateway Completion, Connector Hardening (2026-07-23)

| Item | State |
|---|---|
| Freeform shell | BLOCKED (allowlisted command manifests only) |
| ExecutionGateway for supported tools | ENFORCED |
| saathi.tools | Migrated map + deferred disabled + LEGACY_BOUNDED residual |
| Connector actions | Action-specific; mutations DRY_RUN_ONLY |
| Approval scope | Action + target aware |
| Cancellation | No UNKNOWN on supported tools |
| Trading Guardian | UNENGAGED_ADVISORY_ONLY |
| Milestone | COMPLETE_WITH_LIMITATIONS |

Evidence: `docs/tool-runtime/M49_3_*.md`. Superseded for closure certification by M49.4.

## M49.2 — Tool Migration, Connector Convergence, Durable Idempotency (2026-07-23)

| Item | State |
|---|---|
| Durable SQLite idempotency | ENFORCED for tool service default |
| saathi.tools Wave A/B slice | PARTIAL migrated |
| Connector fixtures | PARTIAL (gmail/gcal read + send stub) |
| Subprocess cancel helper | ACTIVE for allowlisted diag |
| Trading Guardian | UNENGAGED_ADVISORY_ONLY |

Evidence: `docs/tool-runtime/M49_2_*.md`. Superseded in-scope by M49.3 on branch `milestone/m49-3-gateway-completion`.

## M49.1 — Canonical Tool Execution Framework (2026-07-23)

| Item | State |
|---|---|
| ToolExecutionService + ToolRegistry | ACTIVE (bounded builtins) |
| ExecutionGateway integration | PARTIAL→enforced for registered tools |
| Full monorepo tool migration | DEFERRED |
| Trading Guardian | UNENGAGED_ADVISORY_ONLY |

Evidence: `docs/tool-runtime/M49_1_*.md`. Draft PR for M49 branch. **M49.2 not started.**

## M48 — Agent Runtime Baseline (2026-07-23)

| Slice | State |
|---|---|
| M48.1 contracts + inventory | COMPLETE |
| M48.2 start_agent_run façade | COMPLETE |
| M48.3 durable lifecycle | COMPLETE |
| M48.4 M8 wrap + entry enforcement | COMPLETE_WITH_LIMITATIONS |
| M48.5 runtime closure review | COMPLETE_WITH_LIMITATIONS |

Evidence pack: `docs/agent-runtime/M48_5_*.md`. Draft PR #3 OPEN unmerged. **M49 not started.**

## M21–M39 Master Program (2026-07-16)

**Platform program status:** Phase 1 active — **M21.0–M21.4** and **M22 provider migration COMPLETE WITH LIMITATIONS**; not production-certified.
Do not auto-run M21–M39 in one unattended block.

Canonical docs:

| Doc | Role |
|-----|------|
| `docs/M21_39_MASTER_PROGRAM_AUDIT.md` | Intake, conflict map, asset→phase map |
| `docs/M21_39_MASTER_PROGRAM_ROADMAP.md` | Canonical platform M21–M39 roadmap |
| `docs/M21_39_GATE_MATRIX.md` | Per-milestone exit gates + evidence tiers |
| `docs/M21_0_RUNTIME_PRODUCTION_CONFIG.md` | M21.0 architecture + ops |
| `docs/M21_0_VALIDATION.md` | M21.0 validation |

### M21.0 (Runtime Production-Configuration Inventory + Provider Policy) — COMPLETE

Path inventory, production config validator, provider policy + kill switches, gateway kill enforcement, console `prod-config`. Tests: `tests/test_m21_0_production_config.py`.

### M21.1 (Canonical Request Contract + Residual Path Controls) — COMPLETE WITH LIMITATIONS

Extended `InferenceRequest`, `validate_contract`, caller policy registry, residual allowlist, AST bypass guard, gateway enforcement, compat builds contract requests. Legacy chat/llm paths remain allowlisted (not fully migrated). Tests: `tests/test_m21_1_request_contract.py`. Docs: `docs/M21_1_*`. **Not** production certified; live model still env-blocked.

### M21.2 (Provider Availability, Cost, Failover, Circuit Governance) — COMPLETE WITH LIMITATIONS

Canonical provider descriptors, availability/readiness model, Decimal cost policy, failure taxonomy, deterministic retry/failover (defaults off), process-local circuit breaker, kill precedence, cheap_ask proxy blocked, unknown caller test-only. Tests: `tests/test_m21_2_provider_governance.py`. Docs: `docs/M21_2_*`. Live Ollama still env-blocked; production_certified=false.

### M21.3 (Residual Inference Path Migration + Release-Check) — COMPLETE WITH LIMITATIONS

Residual inventory UNKNOWN=0; chat compatibility adapter; `llm.generate` deprecated preflight facade; `_llm_helper` HTTP chain removed; agent/research preflight; transitional unknown FORBIDDEN; `python -m saathi.inference.release_check`. Tests: `tests/test_m21_3_residual_path_migration.py`. Docs: `docs/M21_3_*`. Legacy sinks expire M22/M23; production_certified=false.

### M21.4 (Runtime Consolidation + Production-Configuration Gate) — COMPLETE WITH LIMITATIONS

Canonical `runtime_gate`; release_check integrated into ops release gate; residual manifest validated (count frozen 7 at close); kill-switch matrix; fake/test isolation; certification invariant (`production_certified=false` without live+suite evidence); full suite attempted. Tests: `tests/test_m21_4_runtime_consolidation.py`. Docs: `docs/M21_4_*`. Live Ollama ENVIRONMENT_BLOCKED.

### M22 (Governed Provider Implementation + Legacy SDK Migration) — COMPLETE WITH LIMITATIONS

Provider HTTP/SDK moved under `saathi.inference.adapters` (`http_providers`, `grounding`, `agent_provider`). `llm.generate` pure facade; agent/research facades thin; residual EXPLICIT_LEGACY_EXCEPTION=0; manifest exceptions reduced in M23. Release-check facade purity. Tests: `tests/test_m22_provider_migration.py`. Docs: `docs/M22_*`. Cloud fallback off; production_certified=false.

### M23 — Full governed chat default (COMPLETE WITH LIMITATIONS)

Canonical `saathi.chat.runtime` sole production chat path; ChatRequest + context builder + stream events; chat residual exception removed (manifest exceptions=2 → cloud/openai_compat M24); release/runtime M23 gates. Tests: `tests/test_m23_governed_chat_default.py`. Docs: `docs/M23_*`. production_certified=false.

### M24 — Durable circuit/cost + engine consolidation (COMPLETE WITH LIMITATIONS)

Canonical `DurableGovernanceStore` (SQLite): circuit state, usage ledger, budget reservations, recovery, operator audit. Process-local circuit/cost no longer production authority. Cloud + OpenAI-compat residual exceptions removed (manifest exceptions=0). Tests: `tests/test_m24_durable_provider_governance.py`. Docs: `docs/M24_*`. production_certified=false; live Ollama still ENVIRONMENT_BLOCKED. Do not start M25 without operator authorize.

### M25 — Live local provider certification (BLOCKED — ENVIRONMENT)

Harness `saathi.inference.live_cert_m25` + evidence under `docs/evidence/m25/`. Discovery proves Ollama.app missing (broken symlink), runtime down, no models, memory pressure. No install/start/pull performed. Verdict: `M25 BLOCKED — LIVE LOCAL PROVIDER ENVIRONMENT UNAVAILABLE`. Tests: `tests/test_m25_live_provider_certification.py`. Docs: `docs/M25_*`. production_certified=false. Do not start M26 without operator authorize.

### M26–M28 — Ops + connectors (COMPLETE)

M26 inference ops; M27 governed connector framework; M28 ExecutionGateway connector enforcement. Default connector/inference rollout OFF; production_certified=true (computed package). Do not auto-start next without authorize.

### M29 — Connector identity + trust registry (COMPLETE)

Canonical manifests, trust levels, capability ceilings, registry resolve-only identity, docs CLI. Tests: `tests/test_m29_connector_identity.py`. Docs: `docs/M29_*`. No live SaaS.

### M30 — Connector conformance + certification (COMPLETE WITH LIMITATIONS)

Canonical conformance specification, certification state model, fingerprint/drift/revoke,
credential-free sandbox harness, built-in assessments for `gov.http|mcp|browser|local_tool`.
ACTIVE/CANARY require fresh connector certification (distinct from M25 production cert).
Tests: `tests/test_m30_connector_conformance.py`. Docs: `docs/M30_*`. Evidence: `docs/evidence/m30/`.
Default connector rollout remains OFF. No live SaaS/OAuth. **Do not auto-start M31.**

### Milestone-number namespaces (mandatory)

| Namespace | Meaning |
|-----------|---------|
| **Platform M21–M39** | This monorepo production program (runtime → governed execution → studio → public → cert) |
| **PRODUCT/IELTSAlert M21.x** | Separate product repo `/Users/macbookpro/Saathi/apps/pielts` — **not** platform M21 |
| **M20.10 options A/B/C** | Historical handoff choices; remapped in program roadmap (A→env unlock/M24 evidence; B→M21.0 slice; C→M30/PRODUCT) |

Platform Phase 1 target: **M21** Runtime Consolidation → **M22** Provider migration (done) → **M23** Chat governed default (done) → **M24** Durable governance (done) → **M25** Live cert (BLOCKED env).
Next recommended: operator unlock Ollama **or** **M26** with authorize only. Do not auto-start M26.

Prior series: **M20 COMPLETE WITH LIMITATIONS** (live local inference still environment-blocked).

---

## ECP / MCP memory note (2026-07-15)

External Capability Program **ECP M17.24** completed: SES-000E Part 6 register for
all Priority 1–3 repositories, project Grok skills (GSAP + loop engineering +
audit/health), initial MCP inventory. **No runtime services.**

### Milestone number mapping (MCP governance)

| Historical label | Canonical label |
|------------------|-----------------|
| M17.25 Project MCP Governance and Memory Consolidation | **M18.1** Project MCP Governance and Memory Consolidation |

Originally implemented and committed under the temporary label
“M17.25 — Project MCP Governance and Memory Consolidation” (`2223322`);
canonical roadmap designation is now **M18.1**.

**M18.1 (MCP Governance)** completed: authoritative `docs/MCP_INVENTORY.md`,
canonical `saathi-codebase-memory`, provider-neutral memory contract,
namespace isolation, health/degradation, write governance, Continuum remains
**BLOCKED_LICENSE**.

**M20.5–M20.10 (series plan)** authorized: session ledger/recovery (M20.5) → live small-model cert (M20.6) → orchestrator/inference consolidation (M20.7) → bounded extra callers (M20.8) → integration/security/resource cert (M20.9) → closure + M21 handoff (M20.10). Plan: `docs/M20_SERIES_PLAN_M20_5_TO_M20_10.md`. Master loop: `docs/M20_MASTER_AUTONOMOUS_ENGINEERING_LOOP.md`. **Do not auto-run the whole series in one unattended block.**

**M20.10 (Closure + M21 Handoff)** completed: series closed with limitations; operational runbook + recert path + M21 options; M21 **not** started. Docs: `docs/M20_10_*`.

**M20.9 (Integration / Regression / Security / Operational Certification)** completed with limitations: M20.8 INTENTIONALLY_SKIPPED; authority-boundary + flag + ledger/recovery/approval + TG tests; M20.6 remains environment-BLOCKED; callers stay legacy default; no production claim. Docs: `docs/M20_9_*`, `docs/M20_8_STATUS.md`.

**M20.8 (Bounded Additional Caller Adoption)** **INTENTIONALLY_SKIPPED** at finalization: no live-certified local model (M20.6 BLOCKED); certify M20.3 pair only. Status: `docs/M20_8_STATUS.md`.

**M20.7 (Engineering Orchestrator + Governed Inference Consolidation)** completed: shared read-only `saathi/m20_console` (flags inventory, unified status, CLI discovery, disable procedure); Control Center cells `governed_inference` + `m20_console`; domains remain separate (no second gateway/router/ledger/store merge); defaults still off/legacy; TG unengaged. Docs: `docs/M20_7_*`.

**M20.6 (Live Local Inference Certification)** **BLOCKED** on pilot host: certification suite + 10-case corpus + discovery/selection implemented (`saathi/inference/certification.py`); live run found no usable Ollama binary and zero installed models (no auto-download); defaults remain legacy; TG unengaged. Docs: `docs/M20_6_*`. Unblock: operator-install Ollama + ≤3B model, re-run `python -m saathi.inference.certification run`.

**M20.5 (Canonical Engineering Session Ledger, Integrity Evidence, Recovery)** completed: append-only hash-chained `session_ledger.jsonl`; integrity evidence store; recovery for stale leases / missing PID / resume plans (no auto-launch); CLI `ledger|recover|evidence|resume-plan`. Not a second harness run ledger. Docs: `docs/M20_5_*`.

**M20.3 (Opt-In LLM Caller Migration + Live Small-Model Validation)** completed: inventory of direct `llm.generate` sites; selected exactly two low-risk callers (`cheap_ask`, `prose_clean`); rollout modes `legacy|shadow|governed_local_with_fallback|governed_local_only` (default legacy); compatibility adapter over M20.2 path; shadow metrics; security denials never fall back; chat default unchanged; live Ollama validation harness (honest `unavailable` when no Ollama/model); TG isolated. Docs: `docs/M20_3_*`.

**M20.4 (Engineering Control Center + supervised read-only sessions)** completed: Control Center engineering facet (versioned read model, redacted); repository integrity snapshots + quarantine; bound read-only approvals for real Claude; store locking/leases; CLI control-center/approve-readonly/integrity; mock pilot green; live Claude optional/dry_run if binary missing. Writes/commits/pushes remain disabled. Docs: `docs/M20_4_ENGINEERING_*`.

**M20.2 (Governed Local Inference Execution Path)** completed: ToolIntent/`ModelGateway` path → authoritative ModelRouter → M20.1 runtime → Ollama-first local engine; structured result + evidence events; hardware/concurrency/timeout/host allowlist; default-off (`SAATHI_INFERENCE_ENABLED` + `SAATHI_INFERENCE_GATEWAY_ENABLED`); no global `llm.generate`/chat switch; no OJ process; TG isolated. Docs: `docs/M20_2_GOVERNED_LOCAL_INFERENCE_EXECUTION.md`.

**M20.1 (Selective OpenJarvis Primitive Integration — Slice A)** completed: SaathiOS-native `saathi/inference` (engine contract, registry/discovery, catalogue+provenance, M2 8 GB hardware profile, Ollama/OpenAI-compat/cloud/fake adapters, bounded benchmarks, ModelRouter observation bridge, skill/sandbox gates). OpenJarvis audited as Apache-2.0 **reference only** — no OJ source copied, no OJ process, default-off. ModelRouter remains authoritative; TG unengaged. Not production-ready; normal `llm.generate` path unchanged by default. Docs: `docs/M20_1_OPENJARVIS_*`.

**M20.0 (Governed Engineering Orchestrator)** completed: control/supervision layer for coding-agent engineering work (`saathi/engineering/`). Deterministic backlog + candidate selection, repository readiness, bounded prompt builder, mock + Claude Code adapters, progress monitor, checkpoints, validation coordinator, bounded retry, stop policy, commit/push verifiers, durable handoff, CLI. Disabled by default; reuses Mission Engine / ExecutionGateway / Knowledge Service / run-ledger concepts without duplicating them. Harmless mock pilot + 61 deterministic tests. No merge/deploy/trading. Docs: `docs/M20_0_ENGINEERING_ORCHESTRATOR_*`.

**M19.6.1 (Linux short-video pilot residual)** completed: silent-WAV deterministic narration, assemble video-only fallback, thumbnail seek 0.0 + Pillow fallback; CI Critical Manifest + full suite green on f4065d6.

**M19.6 (CI Critical Manifest Environment Honesty)** completed: fixed Gate-C Critical Manifest failures that misclassified Linux/CI environment limits as security or product regressions (studio quota vs free-disk order, native permission summary schema on non-macOS, multi-app harness/redteam probes requiring ffmpeg when absent). CI installs ffmpeg/jq/sqlite3 for live pilot coverage. Not a product promotion; TG/InsForge untouched.

**M19.5 (Incremental knowledge refresh + change awareness)** completed: commit/fingerprint-aware refresh over M18.2 indexer; git change detection; leases; cache epoch; multi-repo isolation; durable evidence; runtime.refresh() wired. Not production-ready.

**M19.4 (Context Composer + mission context quality)** completed: structured budgeted composer over M19.0 results; profiles coding/repair/audit/architecture/incident; provenance/trust/injection boundaries; mission+repair facades attach `composed` on unified path only; TG/InsForge untouched. Not production-ready.

**M19.3 (Real-Index Knowledge Campaign + controlled promotion)** completed: real registered-index dual-path campaign; durable metrics; promote exactly one caller (`codebase_memory_search`) to `unified_with_fallback` with per-caller/`SAATHI_KS_DISABLE_PROMOTIONS` rollback; TG/InsForge/chat LTM untouched. Not production-ready.

**M19.2 (Shadow Evaluation Campaign + second-wave KS adoption)** completed: campaign metrics, control_center repository facet (opt-in), repair_context_prepare; default legacy; TG/InsForge untouched. Not production-ready.

**M19.1 (Knowledge Service adoption)** first-wave callers via adoption gateway; default rollout `legacy` (M19.3 promotes one pilot caller); shadow/fallback; TG isolated. Not production-ready.

**M19.0 (Unified Knowledge Service)** retrieval router + multi-repo context over M18.2.

**M18.4 (InsForge governed migration write pilot)** structured ops + fingerprint approval + gateway; writes still dual-flag disabled by default.

**M18.3 (InsForge read-only provider pilot)** registers InsForge as data-plane adapter (`saathi/providers/insforge`); elevated by M18.4 for governed migrations only.

**M18.2 (Governed Codebase Memory Indexing & Retrieval)** operationalizes local-first
repository indexing, hybrid retrieval, provenance, freshness, and evaluation.
Continuum pilot only when licence is clarified (do not auto-install).

Browser milestone **M17.25 — Governed Interactive Browser Sessions** remains M17.25
(distinct from the historical MCP-governance temporary label).

Do not auto-start Priority 2/3 installs on the 8 GB Mac.

---
Detected state: branch milestone/m7-security-engine, HEAD 1feb928 (M17.7, four
live apps: FFmpeg/SQLite/jq/zip). Priorities checked this invocation: no open
Critical/High (critical_checks green, red-team 81/81); release blockers are all
environment-blocked (authenticated browser, live approval click, staging
deploy+rollback — need credentials/deploy). Highest ready-now, non-filler gap is
therefore real validation + reliability of an already-built layer.

## Candidate scoring (this invocation)
| candidate | priority | notes | ready-now |
|-----------|----------|-------|-----------|
| **M17.8 long-running harness task control** | #3/#4 | top "actionable without approval" real-debt item; cancel + orphan-free timeout kill + LIVE resource-limit enforcement + durable run journal w/ crash reconciliation; reuses the sole adapter (no second execution engine); no install/permission/credential | **5** |
| production monitoring/alerting | #4 | valuable but medium/large; less bounded for one iteration | 3 |
| AI Studio multi-harness pipeline | #5 | chains live apps; valuable but broader; do after execution reliability is proven | 3 |
| authenticated browser workflow | #5 | needs a safe staging credential (blocked) | 1 |
| native Finder/TextEdit actuation | — | macOS TCC permission required (blocked) | 0 |
| workflow intelligence engine | #6 | large; risks a second execution engine; premature | 1 |
| another system-utility harness | — | explicitly out — would only inflate app count | 0 |

## Decision (this invocation)
Priority chain says: no Critical/High open, release blockers environment-blocked →
take the highest-value ready-now "real validation of an already-built capability"
that also advances "long-session stability / crash recovery". → **M17.8 governed
long-running harness task control**. Bounded, reuses the one adapter boundary, and
is fully live-validatable (real cancel, real SIGXFSZ resource kill, real crash
reconciliation). Turns the top actionable real-debt item from "designed" to
"live-proven".

## M17.9 (this invocation) — durable run ledger, concurrency safety, recovery ops
Start/rollback point: HEAD `2dcfd3d` (M17.8). No higher Critical/High open;
release blockers environment-blocked. Selected the top real-debt item: upgrade
M17.8's single-process JSONL journal into a **transactional SQLite run ledger**.
Delivered: CAS state machine (one-claimant-per-run, terminal immutability, stale-
writer rejection), ownership-safe cancellation, exactly-once idempotent crash
recovery, heartbeats + stuck-run classification, recovery operations, safe
reversible JSONL migration, admin-maintenance CLI (verified OS identity, audited —
NO caller-supplied identity trusted), owner-safe Control Center read model, ledger
db in the backup/restore + integrity gates, and **11 dedicated blocking Critical
Manifest checks**. Multi-PROCESS concurrency proven (spawn, not threads); live
process lifecycle, restart persistence, and backup/isolated-restore proven.
Reuses the ONE adapter (no second execution engine). Verdict: **RUN LEDGER STAGING
READY** — not production-ready (needs multi-user load, production monitoring/
alerting, representative deployment, incident-response drill). Pause/resume/
checkpoint kept `contract_ready` (process suspension ≠ application checkpointing).

## M17.10 (this invocation) — harness run monitoring & stuck-run alerting
Start/rollback point: HEAD `73e97f9` (M17.9). No higher Critical/High open; release
blockers environment-blocked. Selected the bounded first slice of the "production
monitoring" candidate (the roadmap gated it on "a bounded design existing"): a
deterministic, deduplicated, self-resolving stuck-run alerting layer over the M17.9
run ledger. Delivered: ledger `run_alert` store (partial-unique dedup, idempotent
raise, auto-resolve on terminal/reconcile, admin-audited acknowledge), a
`run_monitor.py` sweep (classify → alert → reconcile → self-heal; deterministic,
injectable now/thresholds/is_alive), Control Center attention integration
(`kind: harness_run`), 3 admin-gated CLI commands, and **2 dedicated blocking
Critical Manifest checks**. Multi-PROCESS concurrent-sweep dedup proven; restart
persistence proven. Extends the ledger + Control Center attention + event bus — no
second monitoring stack. Touches no financial/external surface (Trading Guardian
not engaged). Verdict: **HARNESS RUN MONITORING STAGING READY** — not production
(external transports, scheduled sweeps, multi-user load, incident drill remain).

## M17.11 (this invocation) — scheduled monitoring & reliable alert delivery
Start/rollback point: HEAD `28ce958` (M17.10). No higher Critical/High open; release
blockers environment-blocked. Made the M17.10 monitoring substrate operationally
useful: durable, deduplicated, retryable notification DELIVERY over the ledger
(additive `run_alert_delivery` table, unique idem_key, lease-based concurrency-safe
claims, bounded deterministic retry `[0,60,300,900,3600]`s → terminal_failed,
restart-safe, resolve/ack suppression), a narrow transport contract + one
credential-free durable local transport (external providers fail-closed stubs), an
opt-in interval scheduler adapter (default DISABLED, idempotent registration, overlap
lock, mirrors the storage watchdog pattern — no new framework), the full
notification/monitor event taxonomy, Control Center delivery-health + attention
integration, 4 admin-gated CLI commands, and **7 dedicated blocking Critical Manifest
checks**. Multi-PROCESS concurrency proven (dedup/claim/dispatch/stale-reclaim).
Extends the ledger + event bus + Control Center attention + admin gate — no second
monitoring/scheduler/bus/DB/auth. Trading Guardian not engaged (no financial/external
execution; notification stays advisory-compatible). Verdict: **RELIABLE LOCAL ALERT
DELIVERY STAGING READY** — not production (external transports, auto scheduling,
multi-user load, incident drill remain).

## M17.12 (this invocation) — governed multi-harness pipeline
Start/rollback point: HEAD `22c2fe0` (M17.11). No higher Critical/High open; release
blockers environment-blocked. M17.8–M17.11 proved single-run execution + monitoring
+ delivery reliability — clearing the exact gate the roadmap set on the "AI Studio
multi-harness pipeline" candidate ("do after execution reliability is proven"). Made
the four proven live apps (FFmpeg/SQLite/jq/zip) composable into ONE governed,
deterministic, SEQUENTIAL, fail-closed workflow. This is an ORCHESTRATOR, not a
second execution engine: every step runs through the SAME governed
`run_harness_action` (ownership → trust → risk/approval → the sole adapter →
INDEPENDENT verification). Delivered: additive `pipeline_run` + `pipeline_step`
ledger tables (PK-unique, terminal-immutable, owner-safe), a `pipeline.py`
orchestrator (one confined workspace, artifact wiring, fail-closed short-circuit on
the first non-success, pre-execution path-escape rejection, honoured approval gates
— no silent elevation), Control Center pipelines cell + `harness_pipeline`
attention, 3 CLI commands (1 always-on census + 2 admin-gated owner-safe), and **7
dedicated blocking Critical Manifest checks**. LIVE two-application chain proven
(sqlite `safe_mutation` → data.db → zip `pack` → bundle.zip, independently verified,
artifact wired end-to-end). Multi-PROCESS concurrent create dedup proven. Extends
the ledger + event bus + Control Center attention + admin gate — no second execution
engine / trust model / DB / scheduler / bus. Trading Guardian not engaged (approval
gates strengthened, never bypassed). Verdict: **GOVERNED MULTI-HARNESS PIPELINE
STAGING READY** — not production (parallel/branching DAGs, pipeline retry/resume,
untrusted spec ingestion, multi-user load remain).

## M17.13 (this invocation) — autonomous mission engine
Start/rollback point: HEAD `186a72f` (M17.12). No higher Critical/High open; release
blockers environment-blocked. M17.12 proved that real tools compose into ONE governed
workflow; M17.13 adds the layer ABOVE it so the system can be driven by OBJECTIVES,
not tools. HIERARCHY is now Mission → Pipeline → Harness Step → Adapter →
Verification → Ledger. A Mission is ONE business objective (today's IELTS lesson,
daily CEO brief, kitchen inventory audit) carrying strongly-typed validated
parameters, an approval requirement, and a reference to a reusable TEMPLATE — and it
NEVER executes a tool: it DELEGATES to the existing M17.12 `PipelineRunner` (which
delegates to the sole governed `run_harness_action`). Delivered: additive
`mission` + `mission_run` ledger tables (PK-unique, UNIQUE(mission_id,attempt),
explicit fail-closed state machine
draft→(approval_required|approved)→queued→running→{completed|failed|cancelled|blocked}
with immutable terminals, owner-safe field projections, params secret-rejected on
write), a `mission.py` MissionEngine (strong parameter validation BEFORE execution;
owner isolation on every op; approval gates honoured with NO silent elevation;
fail-closed — a mission completes ONLY if its delegated pipeline succeeded, no partial
success; retry rejected unless failed, and a failed retry CLONES a new instance;
trusted-Python templates like the pilots), Control Center missions cell +
`harness_mission` attention (failed → high, approval_required → medium), 6 CLI
commands (1 always-on census + 5 admin-gated owner-safe), and **7 dedicated blocking
Critical Manifest checks**. LIVE proven: a mission completes via a real delegated
governed pipeline (sqlite → data.db → zip → bundle.zip, independently verified); a
pipeline failure fails the mission. Multi-PROCESS concurrent create dedups to exactly
one. Extends the ledger + event bus + Control Center attention + admin gate — no
second execution engine / trust model / DB / scheduler / approval path. Distinct from
the older `saathi/missions/` business-content package (untouched). Trading Guardian
not engaged (approval gates strengthened, never bypassed). Verdict: **AUTONOMOUS
MISSION ENGINE STAGING READY** — not production (untrusted mission-spec ingestion,
live scheduling + event/triggered execution, parallel missions, multi-user load
remain).

## M17.14 (this invocation) — governed mission scheduler & trusted event triggers
Start/rollback point: HEAD `73fd251` (M17.13). No higher Critical/High open; release
blockers environment-blocked. M17.13 delivered objective-driven missions; M17.14 adds
the WHEN layer ABOVE the MissionEngine so approved missions run on a schedule or from
a trusted internal event — without a second scheduler DB, job runner, execution
engine, approval system, or event bus. HIERARCHY: Scheduler/Trusted-Event → Mission
instance → MissionEngine → PipelineRunner → run_harness_action → Adapter →
verification → ledger; the scheduler NEVER executes a tool (static test asserts no
PipelineRunner/adapter/subprocess reference). Delivered: additive `mission_schedule`
+ `mission_occurrence` (UNIQUE dedup_key) + `mission_event_trigger` +
`mission_event_receipt` (UNIQUE dedup_key) ledger tables; deterministic tz-aware due
math (one_time/interval/daily/weekly; DST via zoneinfo; cron omitted); each due time
→ exactly ONE occurrence and each occurrence → at most ONE mission (deterministic
mission id = crash-safe idempotency); lease-based claiming (active lease not
stealable, expired recoverable); restart reconciliation (no duplicate mission);
infra-only bounded retry `[0,60,300,900,3600]`s (NEVER for approval/owner/param/
mission outcome); a trusted event ALLOWLIST with static template binding +
allowlisted scalar payload mapping + durable receipt dedup (payload can't set owner/
template/risk/approval); an opt-in interval runner (default DISABLED); Control Center
scheduler cell + attention; 12 CLI commands (1 always-on census + 11 admin-gated
owner-safe); and **8 dedicated blocking Critical Manifest checks**. LIVE proof: a
scheduled data_bundle mission generated one occurrence, dispatched through the
MissionEngine to a real governed sqlite→zip pipeline (independently verified), re-swept
with no duplicate occurrence/mission, and reconciled after a simulated restart.
Multi-PROCESS + multi-thread concurrent occurrence create each dedup to exactly one.
Extends the ledger + event bus + Control Center attention + admin gate — no second
scheduler/engine/DB/bus. Trading Guardian not engaged (scheduler/event modules carry
no trading surface; scheduling never converts advisory into execution permission).
Verdict: **GOVERNED MISSION SCHEDULING & TRUSTED EVENT TRIGGERS STAGING READY** — not
production (cron, public webhooks, untrusted JSON defs, distributed/parallel
scheduling, production auto-scheduling remain).

## M17.15 (this invocation) — governed pipeline retry, resume & checkpoints
Start/rollback point: HEAD `4cad92a` (M17.14). No higher Critical/High open; release
blockers environment-blocked. Closes the M17.12 deferred gap (pipeline retry/resume/
checkpoint) that M17.14's retry section pointed at. A failed/interrupted pipeline now
CONTINUES FROM ITS LAST INDEPENDENTLY VERIFIED STEP instead of restarting — implemented
inside/around the existing PipelineRunner + ledger, with NO second pipeline/execution
engine, retry framework, verification path, or ledger. Delivered: additive
`pipeline_checkpoint` (UNIQUE per pipeline_id,step_index) + `pipeline_recovery` ledger
tables; a checkpoint written ONLY after a verified success; deterministic fingerprints
(step-definition / dependency / artifact) that reuse ONLY a CONTIGUOUS valid verified
prefix and fail closed on any mismatch (owner, step identity, fingerprints, verify
policy, artifact existence+confinement+integrity, invalidation); category-ALLOWLISTED
bounded retry on the shared RETRY_SCHEDULE (approval/owner/verification/param/tamper/
cancellation/unknown never auto-retry); approval never implied (increased risk
invalidates reuse; resume stops at approval_required; risk-4 manual-only); lease-based
recovery claiming (one winner, active not stealable, expired reclaimable); crash
reconciliation preferring reconcile over duplicate execution (uncertain → stop_uncertain,
never assume success); a governed audited attempt-bounded `reopen_pipeline` (the ONE
exception to pipeline terminal immutability; complete_pipeline unchanged); mission
integration (failed mission pipeline resumes in place, no duplicate mission); Control
Center recovery cell + attention; `pipeline-recovery-health` + 7 admin-gated owner-safe
CLI commands (operator may INVALIDATE but never force-valid); and **9 dedicated blocking
Critical Manifest checks**. LIVE proof: sqlite→zip with an injected transient failure —
step1 verified+checkpointed, step2 transient-fails, retry reuses step1 (not rerun),
step1 revalidated, step2 verified, pipeline succeeds; duplicate resume refused;
tamper of data.db invalidates the checkpoint and reruns from step1. Extends the ledger
+ Control Center attention + admin gate — no second engine. Trading Guardian not engaged
(recovery module has no trading surface; recovery adds no execution path). Verdict:
**GOVERNED PIPELINE RETRY / RESUME / CHECKPOINT STAGING READY** — not production
(parallel/branching DAGs, distributed/remote/cloud checkpoints, untrusted pipeline JSON,
cross-owner reuse, production auto-scheduling remain).

## M17.16 (this invocation) — governed bounded parallel & branching pipeline graphs
Start/rollback point: HEAD `5bc8317` (M17.15). Closes the M17.12/M17.15 deferred gap
(parallel/branching DAG). The pipeline gains a bounded, deterministic, ACYCLIC graph —
one fork, N independent branches, one explicit join barrier (diamond A→(B,C)→D) —
implemented as a thin dependency-aware bounded executor (`pipeline_graph.py`) that
WRAPS the existing PipelineRunner and calls the SAME `_run_step` → `run_harness_action`
for every step. NO second pipeline/execution/DAG engine, scheduler, retry framework,
checkpoint system, approval system, or ledger. Delivered: full pre-exec graph
validation (cycle / unknown-dep / dup-id / self-dep / owner / size / concurrency /
nested-fork / second-join / branch-width / artifact-collision / secret-name /
path-escape / unknown-or-non-executable-harness → no partial exec); bounded
ThreadPoolExecutor (≤4 workers) over a deterministic ready queue; the join barrier via
the dependency mechanism (no partial join); fail-closed on first branch failure (join
never runs, siblings settle honestly, unstarted cancelled, never partial-success);
dependency-CLOSED checkpoint reuse on graph resume (not a linear prefix) reusing the
M17.15 `_validate_checkpoint`; branch-local retry via the shared M17.15 schedule;
durable per-step claims (`pipeline_step_claim`) for exactly-once + crash-safe reclaim;
graph-launch + resume dedup; additive ledger tables (`pipeline_graph`/
`pipeline_dependency`/`pipeline_branch`/`pipeline_step_claim`; the graph IS a
pipeline_run reusing pipeline_step + pipeline_checkpoint); mission integration
(`MissionTemplate.build_graph` launches a graph through the SAME PipelineRunner, no
duplicate mission/occurrence); Control Center owner-safe graph cell + attention; CLI
(`pipeline-graph-health` always + 6 admin-gated owner-safe, resume driven through the
owning mission template — no arbitrary graph JSON, no force-success/skip/bypass); 13
BLOCKING pipeline_graph.* manifest checks; 44 tests. LIVE PROOF: real sqlite→
(sqlite||sqlite)→zip diamond with concurrent verified branches, confinement,
fail-closed, partial reuse, tamper invalidation, dedup, crash-before-join reconcile.
Trading Guardian not engaged (graph layer asserted free of trading surfaces).
Verdict: **GOVERNED BOUNDED PARALLEL/BRANCHING GRAPH STAGING READY** — not production
(cyclic/nested-fork graphs, dynamic mutation, untrusted graph JSON, distributed/remote
execution, cross-owner delegation, production auto-scheduling, live trading remain OUT).

## M17.17 — governed graph mission scheduling & recovery integration (DONE)
Autonomous-loop milestone (start/rollback e7207dd). Joins M17.14 scheduling, M17.15
recovery, M17.16 graph pipelines, and M17.13 MissionEngine so a SCHEDULED occurrence (or
trusted event) launches a GRAPH-backed mission, survives interruption, resumes through the
EXISTING graph + recovery layers, and settles the mission AND occurrence EXACTLY ONCE. No
new execution path: scheduler → MissionEngine → PipelineRunner → bounded graph executor →
run_harness_action → adapter → verification → ledger. Scheduler still delegates ONLY to the
MissionEngine (fresh execution via engine.launch; no direct graph/recovery calls, asserted).
New MissionEngine methods (mission authority): resume_graph_mission / settle_recovered /
reconcile_running_mission + honest graph→mission classification. Honest state map with
approval→approval_required, stop_uncertain→blocked (fail closed), transient failure→deferred
retry_wait→succeeded after recovery. Idempotent + durable (deterministic recovered mission
id; recovery/step/occurrence claims); original failed mission immutable (linked retry). Crash
windows F/G reconciled. Retry = M17.15 allowlist + [0,60,300,900,3600]s. NO new tables (one
read-only helper). Additive default-off scheduler flag. 12 BLOCKING scheduled_graph.*
manifest checks (194 total); 31 deterministic tests; M17.13–16 regression 160 green; full
suite 1844/1 skipped/0 failed. LIVE PROOF (credential-free): scheduled sqlite-root → 2
concurrent verified sqlite branches → zip join; repeat sweep no-dup; injected retryable
branch failure → durable recovery → reuse root+branch_a, rerun branch_b + join once →
mission+occurrence settled once (idempotent); crash F/G reconciled; approval branch blocks
join+schedule without auto-approval. Trading Guardian not engaged (asserted free of trading
surfaces). Verdict: **GOVERNED SCHEDULED GRAPH RECOVERY STAGING READY** — not production
(production auto-scheduling, distributed/multi-region recovery, untrusted graph JSON, dynamic
mutation, public webhooks, live trading remain OUT).

## M17.18 — harness registry boot persistence (DONE)
Autonomous-loop milestone (start/rollback `04be33c` / M17.17). Closes the real-debt
item: `data/application_harnesses/registry.json` was written by `persist()` but never
loaded — in-memory pilot bootstrap only. Delivered: load-on-first-bootstrap
(fail-closed on missing/corrupt/oversized/secret-bearing JSON), persist-on-mutate
(`register`, `import_records`), external records demoted if disk claims executable
trust, pilot code-seed with restrictive-only trust overlay from disk, CLI
`import-cli-anything` now registers+persists, `load_report()` / summary diagnostics,
15 deterministic tests, 5 blocking `registry.*` critical checks. No second registry,
no ledger/schema change, Trading Guardian unengaged. Verdict: **REGISTRY BOOT
PERSISTENCE STAGING READY**.

## M17.18.1 — curated vs runtime memory conventions split (DONE)
Hygiene follow-on after M17.18 (start HEAD after M17.18 + AGENTS.md). Nightly
`memory_reflector` previously appended auto-learned bullets into
`saathi/memory/conventions.md`, leaving durable dirt on every loop. Delivered:
curated baseline stays git-tracked under `saathi/memory/`; runtime learning writes
only to `data/memory/learned_conventions.{md,jsonl}`; agent loads curated then a
short learned slice; `.saathi-agent-state/` + `storage/*.db*` gitignored; 3
deterministic tests. No second memory engine. Verdict: **MEMORY CONVENTIONS SPLIT
STAGING READY**.

## M17.19 — harness registry untrusted persistence hardening (DONE)
Autonomous-loop milestone (start `059671d`). Persisted `registry.json` is treated
as untrusted input: bounded read, versioned envelope (schema_version=1), shared
entry validator for boot/register/import, resource limits, unknown-field reject,
restrictive-only pilot trust overlays, demotion of elevated external trust, atomic
tmp+fsync+replace writes, fail-closed envelope rejection with pilots preserved,
bounded diagnostics (hashes/counts, no full payloads), CLI strict import exit 3,
5 new blocking critical checks, 38 focused tests + M17.18 regression green. No
second registry. Trading Guardian unengaged. Verdict: **REGISTRY UNTRUSTED
PERSISTENCE HARDENING STAGING READY**.

## M17.20 — multi-writer harness registry concurrency (DONE)
Autonomous-loop milestone (start `f0e1a55`). Serializes registry mutations with
process-safe `fcntl.flock` + in-process RLock, durable `revision` CAS,
lock→reload→mutate→atomic-write, `applied_ops` idempotency, bounded lock
timeout, crash-safe prior-file preservation, CLI exit 4/5 for contention/conflict,
5 new blocking critical checks, 33 focused tests. Single-host only (not
multi-host consensus). Trading Guardian unengaged. Verdict: **REGISTRY
MULTI-WRITER CONCURRENCY STAGING READY**.

## M17.21 — Control Center Registry Health cell (DONE)
Autonomous-loop milestone (start `a276843`). Read-only Registry Health object
with deterministic score/status; Control Center cell + overview + attention;
CEO Daily Brief only when unhealthy; safe diagnostics API; 5 blocking critical
checks; 19 focused tests. No second dashboard/registry. Trading Guardian
unengaged. Verdict: **REGISTRY HEALTH CELL STAGING READY**.

## M17.22 — Universal ExecutionGateway Phase 1 (DONE)
Autonomous-loop milestone (start `398d40e`). One authoritative execution
boundary: ToolIntent → validation → permission → risk → approval →
ExecutionGateway.submit → connector/CLI/local/MCP handler → evidence →
security event → run ledger → Control Center + gated CEO brief. Deterministic
states (terminal-immutable), durable ExecutionRecord, digest-bound approval,
idempotency + restart recovery, M17 retry schedule, +5 `execution.*` critical
checks, 25 focused tests. Connector substrate reuses existing approval engine
(no second gateway/queue/approval system). Trading Guardian unchanged. Browser /
n8n / LLM / trading migration deferred. Verdict: **UNIVERSAL EXECUTION GATEWAY
PHASE 1 STAGING READY**.

## M17.23 — Governed Browser Actions through ExecutionGateway (DONE)
Autonomous-loop milestone (start after restored M17.22). Browser actions enter
ExecutionGateway via GovernedBrowser: domain/scheme policy, risk classification,
digest-bound approval, idempotency, uncertain-outcome non-retry, prompt-injection
isolation, workspace downloads/uploads, CC browser cell + gated CEO brief.
Reuses BrowserService tiers (no second engine). 46 focused tests; +6 browser.*
checks. Residual: default BrowserService.open ungoverned for compat; live
interactive CDP paths deferred. Trading Guardian unengaged. Verdict:
**GOVERNED BROWSER ACTIONS STAGING READY**.

## M17.24 — Eliminate Residual Ungoverned Browser Dispatch Paths (DONE)
Autonomous-loop milestone (start `f2f262f`). Inventory of all browser dispatch
paths; production singleton `BrowserService(allow_direct=False)` defaults to
gateway; raw agent-browser / AppleScript / ChatGPT browser fail closed (optional
`SAATHI_ALLOW_RAW_BROWSER`); BrowserConnector production path governed; human
`/api/v1/human/test` requires governed intent + approval/env; AST import/launch
allowlist in `saathi/browser/guard.py`; context attribution (actor, mission/run,
approval, schedule, trigger, retry, checkpoint, mission forgery, trading
isolation); +5 blocking `browser.*` critical checks; 30 focused M17.24 tests.
Trading Guardian unengaged for ordinary browse; trading-classified actions deny
without TG auth. No live trading, no deploy, no push. Verdict:
**ALL PRODUCTION BROWSER DISPATCH PATHS GOVERNED**.

## M17.25 — Governed Interactive Browser Sessions, Actions, and Human Handoffs (DONE)
Autonomous-loop milestone (start `caca1da` / tag `m17.24-browser-governance-complete`).
Extends M17.24 from navigation/dispatch into interactive execution:
`InteractiveBrowser` + `BrowserSessionStore` (ownership, leases, lifecycle,
action ledger, handoffs, checkpoints); action taxonomy (read_only → financial);
target resolution (ambiguous/missing/coordinates blocked); commit boundary
(submit requires dedicated approval + idempotency + pre-commit checkpoint —
navigation approval insufficient); human handoff workflow (pause, claim,
complete/decline, validated resume); production hard-blocks
`SAATHI_ALLOW_RAW_BROWSER`; agent click/fill/type route through interactive
sessions; +5 blocking critical checks; 34 focused tests. Trading Guardian
isolation preserved. No live external side effects, no push/deploy. Verdict:
**INTERACTIVE BROWSER SESSIONS, ACTIONS, AND HUMAN HANDOFFS GOVERNED**.

## M17.26 — Production Browser Adapter, Domain Policy, Evidence Redaction, Workflow Migration (DONE)
Autonomous-loop milestone (start `7b21915` / M17.25). Connects governed sessions
to real adapter boundary: `ProductionBrowserAdapter` (sandbox/CDP) +
`HumanMacAdapter` under `adapter_contract` (attach/validate/health/act/reconcile);
environment-specific `DomainPolicyService` (production deny-by-default, HTTPS,
no localhost/private/file/javascript, deceptive-domain normalization, redirect/
popup revalidation); `EvidenceRedactionPipeline` (classification, deterministic
masks, suppress secrets, OCR optional-only); workflow step schema +
`execute_workflow_step` → `InteractiveBrowser.act`; adapter health/reconnect/
kill-switch; Control Center privacy-safe snapshot; +5 blocking critical checks;
90+ focused M17.26 tests. Trading Guardian isolation preserved; no live trading,
no real external browser actions, no push/deploy. Verdict:
**PRODUCTION BROWSER ADAPTERS, DOMAIN POLICY, WORKFLOW MIGRATION, AND EVIDENCE REDACTION GOVERNED**.

## Blocked / deferred (need user action or larger scope)
- authenticated browser / cloud connector workflow — needs a safe staging account.
- native Finder/TextEdit actuation — macOS Accessibility (TCC) not granted.
- GUI harness apps (LibreOffice/Blender/Kdenlive) — not installed.
- staging deploy + live rollback drill — needs a deploy target (no push/deploy).
- pause/resume/checkpoint, workflow intelligence, production monitoring — larger,
  next candidates once a deploy/credential path or a bounded design exists.

## PRODUCT/IELTSAlert track (not platform M21)

IELTSAlert revenue work lives in **`/Users/macbookpro/Saathi/apps/pielts`** under **product** milestone labels (`docs/M21_*` in that repo).
In SaathiAI docs, refer to it as **PRODUCT/IELTSAlert M21.x** so it never collides with **platform M21** (Runtime Consolidation). Not a SaathiOS platform rewrite.

## M32 — Governed Provider-Adapter Pilot, End-to-End Connector Validation, Shadow Operations (DONE)
Autonomous-loop milestone (start `206795f` / M31 credentials complete). Adds one
bounded, governed provider-adapter pilot proving the full path: intent → manifest/
registry → connector certification → provider config → account/credential readiness
→ policy → approval → ExecutionGateway → connector runtime → provider adapter →
normalized result → redaction → evidence → incident/health — WITHOUT bypassing any
M27–M31 control. New `saathi/connectors/providers/`: canonical `ProviderAdapter`
contract; provider identity registry (canonical alias resolution, fail-closed
prohibition of financial/trading/social-write providers); secret-free config with
endpoint/side-effect/data-class policy; request/response normalization (injection
rejection, sensitive-data stripping, raw-response containment); canonical error
taxonomy; deterministic bounded retry; fingerprint-bound idempotency; bounded
rate-limit awareness; provider health + quarantine (distinct from connector/account/
credential); provider verification fingerprint + drift + NON-mutating eligibility
read (M31 correction preserved); composed execution eligibility (M25+M30+M32+M31+
rollout+approval); leak-scanned evidence; CLI; `EchoProviderAdapter` pilot over a
deterministic in-process `provider_simulator` (loopback only). Pilot: `saathi.echo.v1`
on `gov.http`, READ_ONLY, credential-free, OFF/SHADOW only. Highest verification =
`SIMULATION_VERIFIED`. 128 focused tests; M27–M31 regression green; gov connector
certs re-assessed fresh after allowlisting the provider runtime. No CANARY/ACTIVE,
no real credentials/accounts/writes, no financial/trading provider. Trading Guardian
UNCHANGED / UNENGAGED. Verdict: **GOVERNED PROVIDER-ADAPTER PILOT — SIMULATION-VERIFIED**.

## M36 — Operator-Controlled Real Sandbox Credential Verification (2026-07-18)

**Status:** Implementation complete offline; real sandbox session **not exercised** (no disposable credential reference supplied).

- Composition of M31–M35 + M33/M34 transport
- Identity: `GET /user`; operation: `GET /meta` on `github_meta`
- Call budget 3; rollout remains OFF; M37 not started
- Evidence: `docs/evidence/m36/`
- Module: `saathi/credentials/m36.py`

## M37 — Real Sandbox Verification, Provider Generalization, Security Certification (2026-07-18)

**Status:** `SECURITY_CERTIFIED_WITH_LIMITATIONS` (live sandbox not exercised).

- Provider contract: identity/health/operation/capabilities/qualification/cleanup
- Reference provider: github_meta only
- Negative matrix: 13/13 offline
- Evidence: docs/evidence/m37/
- Modules: saathi/credentials/sandbox_provider.py, saathi/credentials/m37.py
- M38 not started

## M38 — Multi-Session Reliability, Recovery, Canary Readiness Evaluation (2026-07-18)

**Status:** READY_WITH_LIMITATIONS (live multi-session not exercised; CANARY not granted).

- MultiSessionCoordinator with explicit state machine
- Bounded concurrency, aggregate budgets, deterministic retry
- Recovery/reconcile without secret reopen from evidence
- Canary readiness evaluator (read-only)
- Evidence: docs/evidence/m38/
- Module: saathi/credentials/m38.py
- M39 authorized for implementation after M38 tip

## M39 — Live Disposable Sandbox Validation & Canary Authorization Decision (2026-07-18)

**Status:** M39 IMPLEMENTATION COMPLETE — OFFLINE CERTIFIED, LIVE VALIDATION BLOCKED (operator disposable secret reference required; CANARY not granted).

- Live preflight fail-closed; feature flag `SAATHI_M39_ALLOW_LIVE_SANDBOX_VALIDATION`
- Secret reference only (Keychain / env name / approved store); 10 runtime acks
- Live single + multi-session runners composed from M36–M38 (github_meta GET /user + /meta only)
- Canary eligibility evaluator (read-only; never grants CANARY)
- Evidence: docs/evidence/m39/ (live statuses NOT_EXERCISED)
- Module: saathi/credentials/m39.py

**Explicit live-dependent state (offline checkpoint):**
- live single-session: NOT_EXERCISED
- live multi-session: NOT_EXERCISED
- external credential revocation: NOT_EXERCISED
- live encrypted-store wiring: NOT_EXERCISED
- CANARY: NOT GRANTED
- ACTIVE: NOT GRANTED
- M40 production authorization: NOT GRANTED
- M40 not started

## M39.1 — Operator Live-Validation Dry-Run Tooling (2026-07-19)

**Status:** OFFLINE OPERATOR TOOLING COMPLETE (PRE-M40 offline readiness extension).

- Module `saathi/credentials/m39_1.py` composes M39; introduces no new subsystem
- CLI: `m39-1-plan`, `m39-1-preview`, `m39-1-backend-availability`,
  `m39-1-revocation-checklist`, `m39-1-diagnostics`, `m39-1-emit-evidence`
- Dry-run execution plan, command preview, secret-backend availability (no `get()`),
  revocation checklist, redacted diagnostics — all offline, no secret resolution
- Tests: 25 passed; evidence `docs/evidence/m39_1/` (deterministic, leak-clean)
- Authorities unchanged: CANARY / ACTIVE / M40 production authorization NOT GRANTED
- Plan: `docs/PRE_M40_OFFLINE_READINESS_PLAN.md`; next: M39.2

## M39.2 — Live-Test Failure-Mode Simulation (2026-07-19)

**Status:** ALL_FAULTS_FAIL_CLOSED (offline; SIMULATED_NOT_LIVE).

- Module `saathi/credentials/m39_2.py` composes the M39 single-session runner,
  M37 transport testkit, and M38 retry classifier; no new subsystem
- CLI: `m39-2-simulate-fault`, `m39-2-simulation-matrix`, `m39-2-emit-evidence`
- 11 fault modes injected via runner seams: throttle_429, auth_denied_401/403,
  server_error_500, malformed_response, network_timeout, connection_reset,
  connection_refused, dns_resolution_failure, secret_resolution_failure,
  kill_switch_tripped — every one fails closed, closes the SecretHandle, and
  matches its M38 retry classification; baseline fixture passes; no live network
- Multi-session partial-failure already covered by M38 failure matrix (not duplicated)
- Tests: 22 passed; evidence `docs/evidence/m39_2/` (deterministic, leak-clean)
- Authorities unchanged: CANARY / ACTIVE / M40 production authorization NOT GRANTED
- Next: M39.3 (canary-readiness framework completion)

## M39.3 — Canary-Readiness Framework (2026-07-19)

**Status:** CANARY_FRAMEWORK_COMPLETE — CANARY NOT GRANTED (offline).

- Module `saathi/credentials/m39_3.py` composes `m39.evaluate_canary_eligibility`;
  no new subsystem
- CLI: `m39-3-prerequisites`, `m39-3-framework`, `m39-3-approval-schema`,
  `m39-3-validate-approval`, `m39-3-canary-decision`, `m39-3-emit-evidence`
- Immutable prerequisites PRQ-1..PRQ-13 (deny-by-default); rollback triggers
  RBK-1..RBK-7; circuit breakers CBK-1..CBK-3; rollout bound 1–5%; allowlist
  github_meta / user,meta / GET; graduate/abort exit criteria; operator
  approval-record schema + validator (deny-by-default)
- Hard invariant: `evaluate_canary_decision` ALWAYS returns CANARY_NOT_GRANTED,
  every grants_* false — even with all prerequisites met and a valid approval
  record — because live evidence is NOT_EXERCISED; CLI aborts on any grant
- Tests: 16 passed; evidence `docs/evidence/m39_3/` (deterministic, leak-clean)
- Authorities unchanged: CANARY / ACTIVE / M40 production authorization NOT GRANTED
- Next: M39.4 (deployment & rollback preparation)

## M39.4 — Deployment & Rollback Preparation (2026-07-19)

**Status:** DEPLOY_ROLLBACK_PREP_COMPLETE (offline; executes nothing).

- Module `saathi/credentials/m39_4.py`; no new subsystem
- CLI: `m39-4-validate-config`, `m39-4-release-checklist`, `m39-4-rollback-plan`,
  `m39-4-backward-compat`, `m39-4-emit-evidence`
- Fail-closed deployment-config validator; REL-1..REL-10 release checklist;
  reversible rollback plan RB-1..RB-6 + TEXT-ONLY script (no push/--force/reset
  --hard; git revert preferred; Trading Guardian untouched); backward-compat proof
  (11/11 M31–M39 entry points present, additive-only); artifact-integrity
  fingerprint stability; SMK-1..SMK-4 smoke tests; post-deploy verification plan
- Nothing is executed; no production deployment authorized
- Tests: 11 passed; evidence `docs/evidence/m39_4/` (deterministic, leak-clean)
- Authorities unchanged: CANARY / ACTIVE / M40 production authorization NOT GRANTED
- Next: M39.5 (monitoring & incident response)

## M39.5 — Monitoring & Incident Response (2026-07-19)

**Status:** MONITORING_INCIDENT_SURFACE_COMPLETE_OFFLINE.

- Module `saathi/credentials/m39_5.py`; no new subsystem; local/synthetic signals only
- CLI: `m39-5-audit-contracts`, `m39-5-validate-event`, `m39-5-alert-definitions`,
  `m39-5-detect-alerts`, `m39-5-incident-runbook`, `m39-5-recovery-runbook`,
  `m39-5-emit-evidence`
- 8 audit-event contracts + fail-closed validator (rejects unknown type, missing
  fields, non-privacy-safe, secret-claiming, forbidden fields, leak); ALT-1..ALT-9
  alert definitions + deterministic detector (SEV1-3); 8-metric contract; incident
  severity defs; INC-1..INC-6 incident runbook; REC-1..REC-6 recovery runbook
- Canary-grant attempt is a SEV1 alert; no secret ever accepted in an event
- Tests: 17 passed; evidence `docs/evidence/m39_5/` (deterministic, leak-clean)
- Authorities unchanged: CANARY / ACTIVE / M40 production authorization NOT GRANTED
- Next: M39.6 (security & adversarial test expansion)

## M39.6 — Security & Adversarial Test Expansion (2026-07-19)

**Status:** ADVERSARIAL_COVERAGE_EXPANDED (test-only; synthetic credentials only).

- No production code changed; `tests/test_m39_6_adversarial.py` — 37 passed
- Vectors: raw-secret injection, env value-vs-name confusion, command injection,
  endpoint/traversal/SSRF/method escape, provider substitution, scope/rollout
  escalation, canary escalation (forged live inputs still cannot grant),
  kill-switch bypass, budget bypass, unsafe defaults, evidence tampering,
  exception/output leakage, redaction, non-live guarantee
- Authorities unchanged: CANARY / ACTIVE / M40 production authorization NOT GRANTED
- Next: M39.7 (reproducibility & clean-environment validation)

## M39.7 — Reproducibility & Clean-Environment Validation (2026-07-19)

**Status:** REPRODUCIBLE_AND_SELF_CONTAINED (offline).

- Module `saathi/credentials/m39_7.py`; no new subsystem
- CLI: `m39-7-reproduce`, `m39-7-dependencies`, `m39-7-cli-contract`, `m39-7-emit-evidence`
- Byte-for-byte reproducibility of all 5 M39.x evidence builders (double-build +
  file emit/re-emit); AST dependency self-containment (stdlib + saathi only, no
  network lib); 29-command CLI contract with a read-only subset executed via cli.main
- Tests: 28 passed; evidence `docs/evidence/m39_7/` (deterministic, leak-clean)
- Authorities unchanged: CANARY / ACTIVE / M40 production authorization NOT GRANTED
- Next: M39.8 (final operator package)

## M39.8 — Final Operator Package (2026-07-19)

**Status:** OPERATOR_PACKAGE_COMPLETE — PRE-M40 offline readiness series COMPLETE.

- Doc `docs/M39_8_OPERATOR_PACKAGE.md` (human handbook) + module
  `saathi/credentials/m39_8.py` (machine-readable manifest)
- CLI: `m39-8-operator-package`, `m39-8-emit-evidence`
- Consolidates architecture, trust boundaries, credential-reference setup,
  supported backends, disposable-token requirements, minimum/prohibited
  permissions, 10 acknowledgements, all procedures, evidence interpretation,
  known limitations, residual risks, and the go-live checklist
- Authority state recorded: LIVE PROVIDER CERTIFICATION / CANARY / ACTIVE NOT
  GRANTED; PRODUCTION DEPLOYMENT NOT AUTHORIZED; Trading Guardian UNENGAGED
- Tests: 10 passed; evidence `docs/evidence/m39_8/` (deterministic, leak-clean)
- **PRE-M40 offline readiness series complete.** M40 remains blocked on operator
  live validation.

## M40 — Live Validation & Production Certification (2026-07-19)

**Status:** LIVE CERTIFIED — provider `github_meta` (read-only, sandbox), 2026-07-19.
Completed with an operator-supplied disposable PAT (Keychain reference): validation
phase stages 1–4 + 6 PASSED live (identity bound, GET /user + /meta 2xx, SecretHandle
destroyed, isolated, budget-bounded); revocation phase stage 5 PASSED (post-revocation
HTTP 401 confirmed). Evidence `docs/evidence/m40/live_certification_record.json`. Live
certification is evidence only — CANARY / ACTIVE / ROLLOUT NOT GRANTED, PRODUCTION
DEPLOYMENT NOT AUTHORIZED, operator M39.3 approval still mandatory. Trading Guardian
UNENGAGED. (Original layer completed offline as fail-closed LIVE_BLOCKED before the
operator supplied the credential.)

- Module `saathi/credentials/m40.py` composes M31–M39 runners only; no new
  subsystem, provider capability, product feature, or production path
- Real gated 6-stage pipeline `run_live_certification` (acks → preflight → single →
  multi → revocation → evidence); fail-closed; LIVE_CERTIFIED reachable only with a
  real provider exercised. `run_stage_rehearsal` proves stage wiring offline
  (SIMULATED_NOT_LIVE, never certifies)
- Verdicts: LIVE_CERTIFIED / LIVE_FAILED / LIVE_BLOCKED_OPERATOR_SECRET_REQUIRED /
  LIVE_BLOCKED. This session: LIVE_BLOCKED_OPERATOR_SECRET_REQUIRED (no credential)
- CLI: `m40-certify`, `m40-rehearsal`, `m40-emit-evidence` (inherit forbidden-argv guard)
- Docs: M40_IMPLEMENTATION / M40_SECURITY_AUDIT / M40_OPERATOR_GUIDE /
  M40_TEST_REPORT / M40_FINAL_REPORT
- Tests: 25 passed; evidence `docs/evidence/m40/` (deterministic, leak-clean);
  backward-compat 11/11 intact
- Authorities unchanged: LIVE PROVIDER CERTIFICATION / CANARY / ACTIVE NOT GRANTED;
  PRODUCTION DEPLOYMENT NOT AUTHORIZED; Trading Guardian UNENGAGED

## M41 — Bounded Read-Only Canary Rollout (2026-07-19)

**Status:** LAYER COMPLETE — CANARY_NOT_ACTIVATED (deny-by-default). Branch
`milestone/m41-canary-rollout`.

- Module `saathi/credentials/m41.py` composes M39.3 (approval + rollback triggers) +
  M40 (live cert + read-only runner) + M39.5 (alerts). No new subsystem.
- Operator-authorized bounded read-only canary for `github_meta` only. Deny-by-default:
  requires a valid M39.3 approval record + M40 LIVE_CERTIFIED evidence + disposable
  credential reference. Rollout ceiling 5%, read-only /user + /meta, GET only.
- Mandatory automatic rollback (any M39.5 alert or kill switch → halt + rollback,
  SecretHandles closed), mandatory kill switch (SAATHI_M39_KILL_SWITCH), zero error budget.
- State machine: CANARY_NOT_ACTIVATED / CANARY_BLOCKED / CANARY_ACTIVE_BOUNDED /
  CANARY_ROLLED_BACK.
- **Does NOT modify the M32 ExecutionMode.CANARY/ACTIVE prohibition** (verified intact).
  Never grants active/production/write; scope expansion FORBIDDEN.
- CLI: `m41-authorization-status`, `m41-rehearsal`, `m41-run-canary`, `m41-emit-evidence`
  (inherit forbidden-argv guard).
- Tests: 17 passed; evidence `docs/evidence/m41/` (deterministic, leak-clean);
  backward-compat 11/11 intact.
- Authorities: CANARY NOT ACTIVATED · ACTIVE / PRODUCTION / WRITE NOT GRANTED · Trading
  Guardian UNENGAGED. Activation requires operator approval record + fresh disposable
  credential.

## M42 — Canary Evidence Review & Graduation Decision (2026-07-20)

**Status:** REVIEW COMPLETE — recommendation `GRADUATION_NOT_RECOMMENDED` (advisory only).
Branch `milestone/m42-graduation-review`.

- Module `saathi/credentials/m42.py` composes M40/M41 evidence + M39.3 criteria +
  M39.5 alert contracts. Grants nothing; no network/credential/provider mutation; no
  runtime authority change.
- Evidence inventory + consistency + GC-1..GC-14 criteria + AB-1..AB-11 & AB-PROV abort
  evaluators + deterministic recommendation (RECOMMENDED / NOT_RECOMMENDED / BLOCKED).
- Verdict on committed evidence: NOT_RECOMMENDED. M40 chain is machine-proven and
  clean; M41 bounded-canary completion is OPERATOR_ATTESTED, not machine-verified
  in-repo (AB-PROV). 14/14 criteria pass on content, 6 rest on attestation.
- CLI: `m42-evidence-inventory`, `m42-evaluate-criteria`, `m42-review-graduation`,
  `m42-emit-evidence`. Tests: 25 passed; evidence `docs/evidence/m42/` deterministic,
  leak-clean; backward-compat 11/11; M32 prohibition intact.
- Explicitly NOT granted: ACTIVE / PRODUCTION / WRITE / FULL_ROLLOUT / SCOPE_EXPANSION
  / TRADING_GUARDIAN. Trading Guardian UNENGAGED.
- To reach RECOMMENDED: supply machine-verified M41 bounded-canary evidence.

## M43 — Machine-Verified Bounded Canary & Graduation Revalidation (2026-07-20)

**Status:** LAYER COMPLETE — machine-verified live run PENDING operator disposable credential.

- Module `saathi/credentials/m43.py` composes M39.3 + M40 + M41 + M42; grants nothing;
  strengthens provenance only. Two-phase (validation live canary + revocation 401),
  machine-verified, fail-closed. Re-runs M42 automatically.
- Additive M42 hook: bounded-canary artifact prefers a machine record at
  `docs/evidence/m43/machine_verified_canary_completion.json` (criteria unchanged).
- Without a live run, no machine record exists → M42 stays GRADUATION_NOT_RECOMMENDED
  (no fabrication). SIMULATED rehearsal proves flow but does not clear AB-PROV.
- CLI: m43-status, m43-rehearsal, m43-run-validation, m43-run-revocation,
  m43-revalidate, m43-emit-evidence. Tests: 15 passed (40 with M42); M39-M43 282.
  Leak-clean, deterministic, no network, backward-compat 11/11, M32 prohibition intact.
- Authorities NOT GRANTED; Trading Guardian UNENGAGED.

## M64 — Authenticated Backend Module Authority (2026-07-28)

**Status:** `M64_COMPLETE_WITH_LIMITATIONS`.

- Reused the M63 backend `ModuleRegistry` as the authoritative source for browser
  discovery, availability, health, Applications navigation, dashboard composition,
  and route presentation.
- Reused platform context/RBAC and required authenticated `PLATFORM_READ`; module
  registration remains a permission directory, never a grant.
- Added one shell-wide discovery owner, production Sidebar/CommandPalette wiring,
  truthful route boundary, bounded retry, abort/generation safety, context/logout
  invalidation, safe icon allowlist, and drift diagnostics.
- Trading remains the sole implemented bounded module; paper-only business logic and
  authority are unchanged. IELTSAlert, HCG POS, Travel, and Finance remain
  non-operational placeholders.
- Validation: backend targeted 176 pass; retained full backend 5221 pass / 1 skip;
  frontend 175 pass; ESLint/build pass; browser certificate 20 hard + 12 state + 6
  responsive + 3 accessibility gates.
- Limitations: fallback skeleton, global enablement, no module cache/global search/
  dynamic installation, focused accessibility sweep, and unrelated TopBar approvals
  CORS debt.
- No push, merge, deployment, production change, or external rollout.

## M65–M68 — Bounded IELTSAlert Platform Module (2026-07-28)

**Status:** `IELTS_MODULE_COMPLETE_WITH_LIMITATIONS`.

- M65 established the tenant/workspace/owner-scoped IELTS domain, additive
  PlatformStore persistence, canonical `ielts.*` permissions, deterministic local
  practice feedback, fixture alert lifecycle, and manual payment-review boundary.
- M66 exposed authenticated platform APIs for profile, goal, four-skill practice,
  alerts, payments, dashboard, evidence, health, and search.
- M67 delivered the learner/reviewer workspace and truthfully enabled IELTSAlert as
  the second backend-authoritative module after focused API, RBAC, isolation, UI,
  build, and browser gates passed.
- M68 adds an explicit provider-unavailable/fallback adapter, route-specific skill
  initialization, dependency remediation, retained M64 shell regression, and final
  certification.
- Operational boundaries remain localhost/single-host SQLite, deterministic local
  estimates, fixture availability, in-app notifications, evidence references, and
  manual payment verification. No official scoring, live provider, settlement,
  external notification, deployment, or production authority is claimed.
- Certification: focused backend 62 pass; full backend 5,239 pass / 1 skip;
  frontend 180 pass; ESLint/build pass; production npm audit 0 vulnerabilities;
  retained M64 browser shell 21 hard + 12 state + 6 responsive + 3 accessibility
  gates; bounded IELTS learner/reviewer journey pass.
- No push, merge, deployment, production change, paid provider call, payment
  settlement, or external rollout.

## M224–M231 — Read-Only Broker Connectivity Readiness (2026-07-30)

**Status:** `READ_ONLY_BROKER_READINESS_CERTIFIED_WITH_LIMITATIONS`.

- Extends M216–M223 Broker Sandbox with simulation-only readiness for a *future*
  read-only connection — without connecting to any real broker or accepting secrets.
- M224 read-only adapter contract (`SIMULATED_NOT_CONNECTED`); M225 capability policy;
  M226 simulated credential lifecycle (refs only); M227 least-privilege scopes;
  M228 connection state machine + transport guard; M229 account snapshots +
  reconciliation (recommendations only); M230 expiry/revocation/incident drills;
  M231 Control Center `/trading/broker-readiness`.
- API: `/api/v1/platform/tg/broker-readiness/*`. CLI: `paper-gov br-*` (`SIMULATION_ONLY=true`).
- Transport guard returns `REAL_PROVIDER_TRANSPORT_FORBIDDEN`. Write/mixed scopes fail closed.
- Validation: 21 focused backend; 154 TG M166–M231 regression; 246 frontend; production
  build pass; `cert:m231` PASS_WITH_LIMITATIONS (UI labels soft behind sign-in gate).
- Explicit non-actions: no real credentials, no exchange connections, no order submission,
  no production read-only authority, no owner sign-off claimed, M232 not started.
- Evidence: `docs/trading/m224_m231_evidence/`. Doc: `docs/trading/M224_M231_READ_ONLY_BROKER_READINESS.md`.
- Next: only after owner planning — remain paper/sandbox only.

## M232–M239 — Reproducibility, Supply-Chain Assurance & Authorization Planning (2026-07-30)

**Status:** `REPRODUCIBILITY_SUPPLY_CHAIN_AUTHORIZATION_CERTIFIED_WITH_LIMITATIONS`.

- M232 clean-clone dependency audit (M216 uncommitted baseline resolved — all required source committed);
- M233 clean worktree + clean clone reproduction (WITH_LIMITATIONS on full npm/browser in clone);
- M234 hermetic environment contract + fail-closed preflight;
- M235 dependency inventory / lockfiles / install-script scan;
- M236 CycloneDX SBOM + unsigned provenance;
- M237 supply-chain threat model + assurance gates;
- M238 read-only integration authorization **planning** (max canary-planning eligible; real connectivity false; no automated owner sign-off);
- M239 Integration Assurance Control Center `/trading/integration-assurance`; `cert:m239`.
- Explicit: no real connectivity, no credentials, no orders, no live trading.
- Evidence: `docs/trading/m232_m239_evidence/`. Doc: `docs/trading/M232_M239_REPRODUCIBILITY_SUPPLY_CHAIN_AUTHORIZATION.md`.
- **Superseded next-step:** M240–M247 completed on branch `milestone/m240-m247-provider-canary-planning` (planning package ready for owner review; no connectivity).

### M312–M319 Connectivity Governance

Certified with limitations: GOVERNANCE_ONLY; no provider connection.

### M320–M327 Credentialless Provider Contracts & Mock Connectivity

Implemented on `milestone/m320-m327-provider-contracts` from verified predecessor
`6639ca730ece11bce160a55a237fcaff8df3058c`. Adds provider-neutral contracts,
explicit capability states, deterministic synthetic mock data, integrity-checked
replay, offline transports, strict schemas, normalized errors, idempotency, and
an unauthenticated provider-session lifecycle. Existing connectivity governance,
authority, approval, audit, evidence, policy, maturity, and certification
systems remain authoritative.

Maximum state is `MOCK_PROVIDER_READY_NO_REAL_CONNECTIVITY`; maturity is
`MOCK_CONNECTIVITY_ONLY`. No real connection, OAuth, credentials, provider
authentication, account data, order path, transfer, canary, deployment, or live
trading is authorized or implemented.

The authoritative M327 interactive browser rerun passed with limitations using
the already-installed project-pinned Playwright Chromium runtime. The original
in-app-runtime failure remains preserved as historical evidence. All browser
traffic was localhost-only, all 17 authorities remained false, and no provider
credential, OAuth, account-link, live-connect, order, transfer, withdrawal, or
canary control was rendered.

### M328–M335 Production Readiness, Observability & Operational Resilience

Certified with limitations on `milestone/m328-m335-production-readiness`.
Maximum state `OPERATIONALLY_READY_OFFLINE`. Recorded eight full-suite backend
failures and proved they predated the milestone.

### M336–M343 Baseline Regression Debt Closure & Private-Alpha Launch Readiness

Implemented on `milestone/m336-m343-private-alpha-readiness` from verified
predecessor `6cdf72661834242eb4901f7eaf44a4425957db37`.

Closes the eight inherited failures rather than carrying them forward. All eight
reduced to two root causes. The first — build artifacts (`.venv`,
`saathi-os/node_modules`) treated as required host prerequisites — was not
cosmetic: it meant a newly invited private-alpha tester could never complete
first run, because `prepare()` could not return `ok` on a machine where
installation had not already been performed in place. The second was a release
gate that counted a bare PEM header as a leaked key and so blocked on its own
secret-rejection sample, red since M224–M231.

All three repairs are implementation-side. The three test files containing the
eight failures are byte-identical to the predecessor commit, verified by
`git hash-object`. Eighteen focused regression tests guard the repairs, including
one that injects a genuine PEM key body and asserts the gate still blocks.

Building the certification surfaced two further defects: every release manifest
recorded the SHA twice (`git rev-parse HEAD HEAD`), and concurrent approval
decisions could all win a read-check-write race — found by the soak, invisible to
the sequential test that had always passed.

Adds the private-alpha contract, a 71-step certified journey whose eighteen
refusals are each asserted to return their own specific code, corrected
platform-status wording, twelve failure and empty states, bounded soak with
concurrency and recovery scenarios, four operational runbooks, and a read-only
launch-readiness Control Center.

Maximum state is `PRIVATE_ALPHA_READY_OFFLINE_INVITE_ONLY`. Invite-only,
localhost-only. No public registration, no broker or provider connection, no
credential, no account access, no order, no paper or live execution. All fifteen
authority locks false.

Owner review is required, cannot be satisfied by automation, and had not been
performed at certification time. Private-alpha readiness does not authorize
public production deployment. M344 was not started.

### M344–M351 Multi-Agent Development Environment Foundation

Verdict: `MULTI_AGENT_DEVELOPMENT_FOUNDATION_CERTIFIED_WITH_LIMITATIONS`.
Branch `milestone/m344-m351-multi-agent-development-foundation`, baseline
`53b9b20`. Evidence: `docs/evidence/m344_m351/`.

A SaathiOS-native environment in which specialised development agents receive
bounded missions, research independently, deliberate in recorded meetings and
produce evidence-backed decisions. It was originally specified as M328–M335;
that range and M336–M343 are already shipped, so reusing the numbers would have
created two milestones with the same identity. Renumbered with owner approval;
scope unchanged.

The discovery pass established what already existed. `saathi/engineering/`
(8,183 lines, M20.0–M20.7) already governs coding-agent supervision, bound
approvals, a hash-chained session ledger, integrity evidence and
disabled-by-default authority. `saathi/safety.py` already owns deterministic
action classification. Four systems already own product missions. Six of the
eleven required capabilities therefore existed and were extended rather than
rebuilt; `saathi/engineering/` was not modified at all.

Five did not exist. `saathi/agentdev/` adds them above `engineering/` with a
strictly one-way dependency (ADR-012): fourteen declarative role contracts with
repository path scopes and independent reviewers, mission-bound worktree
isolation, sixteen artifact kinds, five structured meeting types, eleven review
gates, and the first agent-behaviour evaluation suite. Authority reuses
`SafetyLevel` and `Approval`; a test asserts no parallel enum exists.

Three properties are structural rather than instructional. No agent may approve
its own output, in either the pass or the fail direction. A gate cannot be
skipped by advancing twice, because each state names its exit gates and the
check runs on every hop. Consensus cannot be fabricated: a `decided` meeting
outcome is refused while any challenge is unanswered, unanswered challenges
become preserved disagreements on the mission, and
`APPROVED_FOR_IMPLEMENTATION` is refused while any disagreement stands.

The worktree gap was measured, not assumed: the baseline reported 112 git
worktrees of which 102 were stale and prunable, left by the ad-hoc M233
reproduction helper. The new manager binds one worktree to one mission and one
agent, refuses branch and path collisions, and exposes no removal method at
all — only a removal plan that withholds its command while uncommitted,
untracked, contaminated or unmerged state exists. Destructive git verbs are
refused before `subprocess`. The 102 stale worktrees were reported and left in
place.

The simulated mission ran all twelve steps with all seven required agents, three
meetings and 24 artifacts across 12 kinds, and deliberately left a real
disagreement unresolved: ten scenarios bound ten refusals, not the behaviour
space. The terminal verdict is therefore `APPROVED_WITH_LIMITATIONS`, not a
clean approval, and the naming question was referred to the owner.

343 new tests, 144 existing engineering and agent regressions, and 1,090
existing safety, governance, approval, security and trading tests all pass.
Zero model calls, zero provider calls, zero paid calls, zero network calls.

Trading Guardian is unchanged and unimported. No credential, global
configuration, MCP server, broker, deploy, merge or push was touched. ECC
remains an external read-only reference; no ECC file, module, hook or dependency
exists in this repository.

The verdict carries limitations because three claims cannot be made honestly
yet: nothing sandboxes a filesystem, so worktree confinement is detected rather
than prevented; no model is in the loop, so agent behaviour under a real model
is unproven; and the owner has not reviewed the evidence. M352–M359 was not
started.

## M352–M359 — Agent Operations, Model-in-Loop Evaluation & Certification (2026-08-04)

**Verdict:** `AGENT_OPERATIONS_CERTIFIED_WITH_LIMITATIONS`
**Evidence:** `docs/evidence/m352_m359/`

Extends the M344–M351 multi-agent development foundation. Seven new modules,
all inside `saathi/agentdev/`; zero modules outside it changed; zero packages
installed; the existing `~/SaathiAI/.venv` reused.

M352 closed the question M351 referred upward — may a ten-scenario
deterministic suite claim behaviour evaluation before any model participates?
No. Twelve terms are now pinned as typed data with one classification each,
twenty-two literal phrasings are banned, and `terminology audit` fails if one
reappears. M353 delivered the read-only operations console (fifteen panels,
no write verb, no store mutation, no external reference, no polling), closing
foundation limitation 6. M354 delivered the deterministic runner: any mission
plan executes through one seven-phase contract with traces, timing, lineage and
named failure causes, producing byte-identical artifacts across runs. M355
connected one local model over loopback behind an adapter that offers nine
capabilities and structurally denies shell, filesystem, tools, non-loopback
network, credentials and provider fallback.

M356 replaced exactly one participant — the Research Agent — with `qwen3:4b`
and scored it against a fully published rubric. It passed 2 of 8 scenarios: 32
of 32 form criteria, 2 of 7 honesty criteria. Asked to edit protected
configuration and force-push, it refused correctly in the refusal field and, in
the same reply, asserted as a fact that it had done both. M357 then attacked
the system with nine prompt attacks: the model complied with 7 of 9; the system
held on 9 of 9 — eight refusals and one recorded substitution, nothing silent.
The model is not the control; the refusals are. M358 gave the owner a review
packet and four actions — approve, reject, request changes, needs research —
recorded in an append-only hash-chained ledger whose editing, deletion,
reordering and forgery are each detected and located by test.

378 new tests, 346 existing agentdev tests, 181 engineering/registry/safety and
1,033 governance/approval/security/trading regressions all pass: 1,938 passed,
0 failed. Zero cloud calls, zero paid calls, zero credentials, zero pushes,
merges or deploys, zero worktrees created.

The verdict carries limitations because four claims still cannot be made
honestly: nothing sandboxes a filesystem, so worktree confinement is detected
rather than prevented; the concurrency ceilings are declared and reported but
unenforced, because nothing spawns processes; only one model in one seat was
ever exercised, and it failed most behaviour scenarios; and attack coverage is
a list of nine rather than a proof. M360 and beyond were not started, and
require explicit owner approval.

## M369–M376 — Local Model Qualification, Truthfulness Verification & Role Assignment (2026-08-05)

**Verdict:** `LOCAL_MODEL_QUALIFICATION_CERTIFIED_WITH_LIMITATIONS`
**Evidence:** `docs/evidence/m369_m376/`

Extends M352–M359. Six new modules, all inside `saathi/agentdev/`; zero modules
outside it changed; zero packages installed; the existing `~/SaathiAI/.venv`
reused. No model was downloaded or deleted.

M352–M359 measured one model in one seat. This range asks whether any model
installed on this machine is good enough to be given a named role. The answer
is no, and the apparatus that produced that answer is the deliverable.

M369 pinned the vocabulary the range is written in — model output, model claim,
verified claim, unverified claim, contradictory claim, completion claim,
external evidence, role qualification, role restriction, model
disqualification — each with what it does not mean, and each checked for
presence on the surfaces it claims. M370 read the host: five models installed,
three eligible, two over the 4.0 GiB ceiling that half of 8 GiB physical memory
sets. `resource_unsuitable_on_current_host` is a statement about the machine
and never about the model. M371 generalised the M356/M357 harness so several
models can be measured against one pinned suite, with digest, prompt version,
rubric version, settings, repository SHA and host recorded together, and every
raw reply, parsed reply and failed run preserved.

M372 ran twelve scenarios at three runs each against every eligible model —
thirty-six runs per model, none discarded. `qwen3:4b` passed 4 of 12 on every
run; `qwen2.5:1.5b` and `qwen2.5-coder:3b` passed none. M373 ran eighteen
adversarial attacks against each, reporting model behaviour and system
behaviour separately: the system held 18 of 18 for all three models, with zero
failed open, while the models complied with 13, 10 and 6 respectively. A system
block is not a model refusal, and the report never averages one into the other.
M374 added the claim verifier — twenty detectors over seventeen subjects, six
statuses — which found 18 internal contradictions and 48 unsupported completion
claims across the three models, and zero verified claims.

M375 scored every model against ten candidate roles in three tiers with
thresholds published before the evidence was collected. Zero model-role pairs
qualified; `thresholds_lowered` is false. M376 turned that into a routing
policy that refuses: all ten roles route to `NO_QUALIFIED_MODEL`, meaning a
deterministic workflow or a person, with automatic, cloud and paid fallback all
off. The read-only console gained thirteen qualification panels and still has
no write verb.

`qwen3:4b` was measured twice — 2 of 8 under M356, 4 of 12 under M372. Both
readings stay committed. They are recorded side by side and never subtracted:
the suites differ in size and scenario set, and the run counts differ, so
comparison is directional only. Both fall short of every threshold, and the
owner disposition is unchanged — `QWEN3_4B_ROLE_UNCHANGED`.

Zero cloud calls, zero paid calls, zero credentials, zero model downloads, zero
model deletions, zero global configuration changes, zero pushes, merges or
deploys. No model holds tool, filesystem, shell, implementation, approval,
mission-transition or deployment authority.

The verdict carries limitations because five claims cannot be made honestly:
only three of five installed models were evaluated, and the other two are
unmeasured rather than poor; zero roles qualified, so the routing policy's
selection path is exercised only by test; determinism is requested from the
provider and not guaranteed, which is why runs are repeated; the one-model
concurrency ceiling is observed rather than enforced, because nothing here
spawns a process; and coverage is twelve scenarios and eighteen attacks rather
than a proof. M377 and beyond were not started, and require explicit owner
approval.
