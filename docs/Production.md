# Production.md — how ideas become reliable production systems

The fifth reusable asset (alongside Brain.md, Business.md, Style guides). The
permanent playbook for the **Production Intelligence** department: how SaathiAI
turns prompts, workflows, datasets, and evaluations into a compounding advantage
instead of things that live "in your head."

**Core insight (the real bottleneck):** every product's weakness is the same —
data → experiments → evaluation → improvement, not code.

| Product | Real weakness (NOT the code) |
|---|---|
| HCG Live Signal | research consistency (not trading logic) |
| PIELTS | content/answer evaluation (not UI) |
| AI Studio | prompt quality (not FFmpeg) |
| Cafeteria | operational data collection (not the dashboard) |

**What SaathiAI v0.5 actually is:** not better YouTube/PIELTS/HCG — a system that
**continuously improves every business using production evidence.** One learning
system, four products.

---

## THE GOVERNING RULE

> **Every improvement must be justified by production evidence.**

- No new prompt without a measured hypothesis.
- No workflow rewrite without production data.
- No model switch without evaluation results.
- No feature because it's "interesting."
- No architecture expansion unless production evidence shows it solves a
  *recurring* problem.

This single rule is what keeps SaathiAI an operating system instead of a
collection of experiments. It applies to this repo's own development too.

---

## Architecture: Evidence first

Everything in Production Intelligence starts from **Evidence** — the layer above
all the others:

```
Production Intelligence
├── Evidence Store        ← everything starts here
│
├── Prompt Library
├── Workflow Library
├── Dataset Manager
├── Evaluation Center
├── Experiment Tracker
│
└── Improvement Engine    ← consumes evidence, proposes the next version
```

**Opik is one source of evidence, not the truth.** SaathiAI holds evidence Opik
never sees. Evidence is the union:

```
Evidence = Opik traces
         + Episodes (Connector → Event → Episode, already built — just extend to Evidence)
         + Connector events (Telegram approvals, YouTube analytics, …)
         + Business metrics (cafeteria revenue, IELTS scores, crypto PnL, daily scorecard)
         + Human feedback (approvals, corrections)
```

Every PAT stage should emit an evidence object, e.g.:

```
Episode #41 · prompt mr-yeti.metadata v12 · score 0.91 · CTR 5.7% · retention 46%
            · comments 73 · revenue $4.80
```

Then evaluation is never guessing: `prompt v11 vs v12 → evidence → winner`. The
four products become one system over the same Evidence Store:

- AI Studio: prompt → thumbnail → CTR → retention
- PIELTS: essay → band prediction → real IELTS score → difference
- HCG: signal → trade → PnL → risk
- Cafeteria: menu → sales → waste → profit

---

## Principle: connectors, not centers

External AI-product tools are **department tools behind the Connector Registry**,
never the platform. SaathiAI stays the OS; a tool can be swapped for its successor
by changing one driver — never a department, dashboard, or the learning loop.

```
SaathiAI → Connector Registry → { OpenHands · LibreChat · Dify · Opik } drivers
```

## Tooling decisions (researched Jul 2026)

| Capability | Tool | Role |
|---|---|---|
| Prompt versioning | **Native `ai_lab` + Opik** | Core |
| Evaluation | **Opik** (already integrated, Apache-2.0) | Core |
| Datasets | **Native (Evidence Store) + Argilla** | Core |
| Prompt regression | Promptfoo | CI |
| Visual workflow | Dify | Connector — **Workflow Playground only, never the execution engine** |
| AI console | LibreChat | Connector — the AI *comparison workstation* (Claude/GPT/Gemini/DeepSeek/GLM/Qwen/Ollama side by side, winner saved back to the Prompt Library) |
| Dev worker | OpenHands | Connector — lives inside **Engineering** (fix #341 → commit → PAT → eval → approval) |

> Native for the substrate (Evidence Store + Prompt Registry — they must feed
> Episodes/Learning/`/os`); connector for the heavy UIs. **We are already past
> where Dify starts** (Model Router, Connector Registry, Browser, Conversation,
> Automation Center, AI Studio, Prompt Registry all exist) — so Dify is a
> playground, not the platform. Langfuse (MIT) stays the reference alternative to
> Opik. Every model comparison in LibreChat and every OpenHands task is judged
> against the same Evidence Store before acceptance.

---

## Standards

### Prompt engineering
- Every production prompt lives in the **Prompt Registry** (`ai_lab.register`), never
  inline. Code calls `ai_lab.render(name, **vars)` so the active version governs.
- Naming: `project.purpose` (`mr-yeti.metadata`, `pielts.writing-eval`, `hcg.signal`).
- Each version records author + purpose + notes (the changelog / "why").
- Never edit a prompt in place — `register` a new version; `rollback` to redeploy.

### Evaluation methodology
- Every prompt/workflow must be **measurable**: score · latency · cost · failures.
- AI Studio auto-records a run-level eval on `mr-yeti.metadata` per run. Other
  pipelines follow the same pattern (`record_eval` on the version they used).
- A change ships only when its version's score ≥ the current active version's, or
  a human explicitly overrides with a logged reason.
- Prefer evals seeded from **real production traces** (Opik), not synthetic sets.

### Dataset curation
- Datasets are first-class, per project: PIELTS (essay → band + mistakes),
  HCG (trade → entry/exit/outcome/why/emotion/confidence), Mr. Yeti (topic → hook →
  retention/CTR/watch-time). These feed Episodes and Learning.
- Label with a human-in-the-loop; store provenance (who/when/source trace).

### Workflow versioning
- Workflows (AI Studio pipeline, publishers) are versioned artifacts with a
  success-rate, avg-time, and failure breakdown (Automation Center / RunStore).
- Backend first, visual editor later — only once pipelines are stable (post-PAT).

### Quality gates (before "done")
- Tests green + `verification-before-completion`.
- New/changed prompt has a registered version and at least one eval.
- Structured failure has a recommendation.
- No secret in output; `.env`/keys handled by blind file→file copy only.

### Release process
- Work on `milestone/*` branch; `master` untouched until a milestone certifies.
- A milestone certifies via its **acceptance test**, not a green suite alone.
- Tag only after the acceptance test passes several days running.

### PAT procedure (see docs/PAT-CHECKLIST.md)
- One complete run/day for 7 days through the real pipeline; fix only what it
  reveals; the run auto-populates the Prompt Library with live evals.

### Experiment logging
- Every experiment: hypothesis → prompt/workflow version → eval result → decision.
- The Prompt Registry leaderboard + Opik experiments are the log; nothing lives
  only in chat or memory.

---

## The order (evidence-first; M5.1 frozen)

**Step 0 — Run the 7-day PAT exactly as planned.** Do NOT jump into Dify/LibreChat/
OpenHands. The PAT produces the first real Production Intelligence dataset: prompt
versions, Opik traces, Episodes, business metrics, human approvals, failures,
analytics. Only after that is there evidence to organize.

Then the order becomes obvious:

1. **Turn on the Opik Evaluation Center** with the real traces.
2. **Wire PIELTS essay grading** into the same evaluation pipeline (`pielts.writing-eval`).
3. **Add a native Dataset Manager** backed by the **Evidence Store**.
4. **Connect LibreChat** to compare prompts across models using those datasets;
   save the winner back to the Prompt Library.
5. **Connect OpenHands** so engineering tasks are evaluated against the same
   evidence before they're accepted.

**The discipline:** let evidence drive the next layer. Build the substrate native
(Evidence Store, Prompt Registry), attach tools as connectors around *real*
workflows, and never let a department depend on a tool that could be swapped in a
year. Every addition grounded in real usage, not anticipated need.
