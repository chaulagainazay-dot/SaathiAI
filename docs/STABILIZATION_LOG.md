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

**Daily success rule (measured, not aspirational):** every day SaathiAI should
**decide ≥1** business decision · **automate ≥1** task · **learn from ≥1** real outcome ·
**earn** measurable revenue · **reflect** — answer *"what surprised me today?"*
(`/reflect <observation>`, captured as a reflection Episode). Computed live from Episodes +
Revenue by `saathi/daily_scorecard.py`, shown in the 8 AM Telegram briefing (`/scorecard`):
```
📊  Today 4/5   ✅ decide  ✅ automate  ✅ learn  ✅ earn  ⬜ reflect
🪞  /reflect — what surprised you today?
```
**Reflect is the highest-leverage box** — the surprise captures what the system *didn't*
anticipate, and becomes tomorrow's experiment → eventually permanent knowledge. Examples:
"Travel leads respond faster after 7 PM" · "Dal Bhat demand spikes when it rains" ·
"6-min whiteboards beat 8-min" · "high-sentiment/weak-fundamentals paper trades consistently fail."

A day under 5/5 is a signal, not a failure — log *why* the missing box didn't fire below.

| Date | Decide | Automate | Learn | Earn | Reflect (the surprise) |
|------|--------|----------|-------|------|------------------------|
|      |        |          |       |      |                        |

### End-of-window success questions (ask these, not "how many features?")
- Did the CEO briefing become the first thing I open each morning?
- Did I make decisions faster? Did the platform save measurable time?
- Did revenue improve *because of* recommendations? Did cafeteria waste decrease?
- Did the Learning Runtime produce insights I actually used?
- How often did I ignore SaathiAI's recommendations — and why?
- **The milestone:** do I now instinctively ask *"Saathi, what should I do next?"* before opening
  YouTube Studio / POS / my crypto app / spreadsheets? When yes — it's an operating system, not a project.

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

### Objective: 10 consecutive Mr. Yeti videos through the full platform, NO architectural changes
Not zero manual steps — the *architecture* stays frozen while I learn where operational
improvements are needed. Achieving this validates the design, not just the code. **Do not** change
prompts / models / workflow after every run; run several, collect observations, look for trends.

### Per-run instrumentation matrix (a wiring test, not a quality bar)
One Mr. Yeti run touches: Idea → Script → AI Director → Storyboard → Character Manager → Video Gen
→ Audio → QA → Discovery Gate → Publishing → Analytics → Audience Intelligence → Learning Runtime
→ Knowledge Promotion → Executive Briefing. For each stage record: completed? · duration · human
intervention? · artifact produced · episode recorded? · event emitted? · Mission Control saw it? ·
reflected in next-morning CEO briefing? A stage failing is a valid observation — log it, don't fix mid-window.

**Copy per run:**
```
#### Run <N> — <video title> — <date>
| Stage | Done? | Time | Manual? | Artifact | Episode? | Event? | In Mission Control? | In briefing? |
|-------|-------|------|---------|----------|----------|--------|---------------------|--------------|
| Idea            |  |  |  |  |  |  |  |  |
| Script          |  |  |  |  |  |  |  |  |
| AI Director     |  |  |  |  |  |  |  |  |
| Storyboard      |  |  |  |  |  |  |  |  |
| Character Mgr   |  |  |  |  |  |  |  |  |
| Video Gen       |  |  |  |  |  |  |  |  |
| Audio           |  |  |  |  |  |  |  |  |
| QA              |  |  |  |  |  |  |  |  |
| Discovery Gate  |  |  |  |  |  |  |  |  |
| Publishing      |  |  |  |  |  |  |  |  |
| Analytics       |  |  |  |  |  |  |  |  |
| Audience Intel  |  |  |  |  |  |  |  |  |
| Learning        |  |  |  |  |  |  |  |  |
| Knowledge Promo |  |  |  |  |  |  |  |  |
| Exec Briefing   |  |  |  |  |  |  |  |  |
- Observations from this run:
```

### 10-video progress tracker
| # | Title | Date | Published? | Stages completed | Manual interventions | Key observation |
|---|-------|------|-----------|------------------|----------------------|-----------------|
| 1 |       |      |           |                  |                      |                 |
| 2 |       |      |           |                  |                      |                 |
| 3 |       |      |           |                  |                      |                 |
| 4 |       |      |           |                  |                      |                 |
| 5 |       |      |           |                  |                      |                 |
| 6 |       |      |           |                  |                      |                 |
| 7 |       |      |           |                  |                      |                 |
| 8 |       |      |           |                  |                      |                 |
| 9 |       |      |           |                  |                      |                 |
| 10|       |      |           |                  |                      |                 |

_(per-run matrices + observations below)_


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
