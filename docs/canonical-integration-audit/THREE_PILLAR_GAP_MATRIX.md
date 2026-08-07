# THREE_PILLAR_GAP_MATRIX

Classifications: READY | PARTIAL | MISSING | BLOCKED | DUPLICATED | UNVERIFIED

## Pillar A — Real Voice Control

| Item | Status | Notes |
| --- | --- | --- |
| audio ownership | DUPLICATED | VoiceOutputProvider vs chat speechSynthesis |
| microphone lifecycle | DUPLICATED / PARTIAL | runtime + chat + settings; cleanup improved |
| playback lifecycle | PARTIAL | single platform owner improving; chat separate |
| VAD | MISSING | |
| wake word | MISSING | |
| partial transcription | PARTIAL | browser recognition dependent |
| final transcription | PARTIAL | platform + chat paths |
| echo cancellation | MISSING | |
| barge-in (acoustic) | MISSING | |
| speech-detected interruption | PARTIAL | chat yes; platform push-to-interrupt |
| generation cancellation | PARTIAL | speech operation cancel APIs |
| TTS streaming | MISSING / PARTIAL | operation poll + blob; not true stream |
| voice session state machine | PARTIAL | server + client |
| visible transcript | PARTIAL | settings/runtime/chat |
| intent preview | MISSING / PARTIAL | not unified |
| tool governance | PARTIAL | should use normal paths; not voice-elevated |
| approval confirmation | PARTIAL | not voice-native UX |
| latency measurement | PARTIAL | some interrupt latency fields |
| owner audible review | UNVERIFIED | checklist exists; not re-run here |
| Nepali support | BLOCKED / PARTIAL | refused when no local voice |
| English support | READY / PARTIAL | browser + local say path |
| offline mode | PARTIAL | browser recognition not guaranteed offline |
| resource limits | PARTIAL | platform bounds; multi-owner risk |

**Pillar A overall:** PARTIAL — private-alpha capable, not best-in-class conversational control.

**Next bounded milestone:** V-NEXT-1 single audio owner consolidation (see voice inventory).  
**Voice implementation started this audit:** false

## Pillar B — Agentic Trading and Hedge-Fund Management

| Item | Status | Notes |
| --- | --- | --- |
| market data | PARTIAL | observation/fixtures; live providers unauthorized |
| point-in-time data | PARTIAL | research/historical packages |
| research agents | PARTIAL / READY | research lab/orchestrator present |
| strategy registry | PARTIAL | |
| experiment registry | PARTIAL | |
| backtesting | PARTIAL / READY | |
| walk-forward testing | PARTIAL / READY | |
| transaction costs | PARTIAL | sim fees/slippage |
| portfolio ledger | PARTIAL | paper/sim — not institutional multi-book |
| cash ledger | PARTIAL | paper/sim |
| NAV | PARTIAL | paper engines |
| P&L | PARTIAL | realized/unrealized in accounting |
| portfolio construction | PARTIAL | research builders |
| risk engine | PARTIAL / READY | multiple engines |
| hedge optimizer | PARTIAL | research |
| independent risk veto | PARTIAL | halt/lock; not separate desk |
| compliance | PARTIAL | governance policies |
| paper OMS | PARTIAL / READY | sim OMS |
| fill simulation | READY | OrderSimulator |
| reconciliation | PARTIAL / READY | paper + readiness |
| performance attribution | PARTIAL | |
| sandbox provider | PARTIAL | emulator/governance; not authorized live |
| live broker | MISSING / BLOCKED | prohibited |
| kill switch | READY | |

**Separation truth**

| Layer | State |
| --- | --- |
| agent recommendation | present |
| deterministic calculation | present (paper/research) |
| governance authorization | present; fail-closed |
| execution | paper only; live blocked |

**Pillar B overall:** Strong paper/research platform; **not** a live hedge fund.

**Next bounded milestone:** T-NEXT-1 canonical paper fund ledger + single portfolio authority.  
**Trading implementation started this audit:** false  
**Keep paper-only:** true

## Pillar C — Central Command and Control UI

| Item | Status | Notes |
| --- | --- | --- |
| information architecture | PARTIAL | module registry + shell |
| global command surface | PARTIAL | `/command` exists |
| voice command surface | PARTIAL | docks + settings |
| mission operations | PARTIAL | |
| agent operations | PARTIAL | agentdev console + `/agents` |
| approval center | PARTIAL | gates possible |
| investment command center | PARTIAL | trading UIs + TG ops |
| system health | PARTIAL | |
| provider/model health | PARTIAL | |
| evidence viewer | PARTIAL | docs-heavy; productized viewer incomplete |
| audit timeline | PARTIAL / MISSING | not single unified timeline UX |
| mobile experience | PARTIAL | mobile components exist |
| accessibility | UNVERIFIED | not audited here |
| keyboard control | PARTIAL | command palette |
| truthful loading/error states | PARTIAL | UI recovery focus |
| legacy route cleanup | PARTIAL | parity maps; residual legacy |
| design consistency | PARTIAL | foundation from M47; later accretion |

**Pillar C overall:** Usable private-alpha shell; not yet single pane of authority truth.

**Next bounded milestone:** UI-NEXT-1 command composition (authority strip + approvals + health + paper portfolio + voice state).  
**UI redesign started this audit:** false

## Recommended first product pillar after integration

**Pillar C (UI composition)** — lowest authority risk, makes architecture truths visible, unblocks operator confidence for voice and trading work.  
Alternative: Pillar A V-NEXT-1 if owner prioritizes conversational control demos — still after baseline integration.
