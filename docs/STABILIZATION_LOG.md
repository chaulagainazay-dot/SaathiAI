# Stabilization Log — post `v0.4.0-finance`

> **Purpose:** Operational observations from running SaathiAI on real/paper data during the
> 2–4 week stabilization window. **Not a bug tracker.** These are usability, missing-signal, and
> "could I actually run my business from this?" notes. Over the month they accumulate into the
> **M5.1 improvement backlog** — evidence-driven, from real usage, not guessed from unit tests.

**Window opened:** 2026-07-03 (release `v0.4.0-finance` frozen)
**Rule during this window:** NO new agents, memory layers, orchestration, databases, or
infrastructure. Observe and log only. Refinements are proposed, batched, and shipped as M5.1
*after* the window closes.

**Success question, asked every morning:** *If I only had this briefing, could I run my
businesses today?* Every "No" is logged below and becomes a high-value improvement.

---

## How to log
Copy the block. Keep it short. One observation per entry.

```
### YYYY-MM-DD — <one-line title>
- **Area:** AI Studio | Cafeteria | Paper Trading | CEO Briefing | Cross-cutting
- **Observation:** what happened / what was missing
- **Priority:** High | Medium | Low
- **Suggestion:** the smallest change that would fix it
- **Capability:** which registered capability it touches (for the M5.1 backlog)
```

---

## Week 1 — AI Studio (real publishing workflow)
Metrics to watch: Discovery-gate block rate · publishing success · learning episodes generated ·
improvement proposals generated · revenue attribution.

_(observations below)_


## Week 2 — HCG Cafeteria (real daily data)
Metrics to watch: production · sales · waste · savings, plus —
- **Forecast accuracy:** recommended production vs. actual demand
- **Recommendation adoption rate:** did I follow the AI's suggestion?
- **Impact of adopted recommendations:** e.g. waste % before → after following the advice
Key question: do the AI's suggestions *consistently improve* operations, or are they merely plausible?

_(observations below)_


## Week 3 — Paper Trading (continuous — calibration, NOT a competition; do NOT optimize)
Metrics to watch: research quality · portfolio health · learning proposals, plus —
- **Recommendation precision** (of BUYs that played out)
- **Due-diligence pass rate**
- **Average confidence vs. actual outcome** (is the system well-calibrated?)
- **False positives** (recommended, lost) / **False negatives** (rejected/held, would have won)
These tell us where the Research Department and scoring models need refinement.

_(observations below)_


## Week 4 — CEO Dashboard (highest-value week)
Every morning: could I run my businesses from this briefing alone? Log every "No".

_(observations below)_

---

## Recommendation Outcome Ledger — did the advice actually improve results?
The other half of the loop. Observations capture what was *missing*; this captures whether the
system's recommendations were *good*. Log every recommendation I acted on (or deliberately didn't)
and its real-world result. Over a month this measures whether SaathiAI's advice improves outcomes.

| Date | Area | Recommendation | Followed? | Result |
|------|------|----------------|-----------|--------|
| _e.g._ Jul 5 | Cafeteria | Reduce Dal Bhat by 6 portions | Yes | Waste 5% → 3% |
| _e.g._ Jul 8 | AI Studio | Approve marketing allocation | Yes | CTR +17% |
| _e.g._ Jul 10 | Paper Trading | Hold Opportunity #218 | Yes | Asset fell 12% after |
|      |      |                |           |        |

> Roll-up at window close: **adoption rate** (Followed? = Yes / total) and **hit rate** (good
> Result / Followed). A high hit rate on followed advice is the strongest signal M5 is production-worthy.

---

## Rolling metric snapshots (optional weekly)
| Week | Area | Key metric | Value | Note |
|------|------|-----------|-------|------|
|      |      |           |       |      |

---

## → M5.1 backlog (populated as the window closes)
Rank observations by (frequency × priority). The top cluster becomes M5.1. Everything here should
map to an already-registered capability — if an observation needs brand-new architecture, it is a
future milestone, not M5.1.

---

## v1.0 Readiness checklist (target after M5.1 / before M6)
- [ ] Zero architectural TODOs blocking production
- [ ] Every capability registered and versioned (`saathi/capabilities.py`)
- [ ] Every capability observable through Mission Control
- [ ] Every workflow traceable end-to-end (explainability audit stays green)
- [ ] Daily CEO briefing used in real operations
- [ ] ≥1 real business (cafeteria) + ≥1 real content pipeline (Mr. Yeti) running through the platform
- [ ] Stable operation for several weeks without major architectural changes
