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

---

## Principle: connectors, not centers

External AI-product tools are **department tools behind the Connector Registry**,
never the platform. SaathiAI stays the OS; a tool can be swapped for its successor
by changing one driver — never a department, dashboard, or the learning loop.

```
SaathiAI → Connector Registry → { OpenHands · LibreChat · Dify · Opik } drivers
```

## Tooling decisions (researched Jul 2026)

| Capability | Use | Why | Status |
|---|---|---|---|
| **Prompt Library + versioning** | **native `saathi/ai_lab.py`** (built) | one registry every project renders from; already wired to AI Studio + auto-evals | ✅ built |
| **Evaluation Center / tracing** | **Opik** (Comet, Apache-2.0) | ALREADY integrated (`tools/opik_tracer.py`); LLM-as-judge, datasets from traces, experiments, ~14× faster evals than Langfuse | ⚙️ present, enable it |
| _(alt eval/observability)_ | Langfuse (MIT, 28k★) | prompt UI + playground + datasets + evals if we ever outgrow Opik | reference only |
| **Eval-in-CI / red-team** | Promptfoo | config-driven assertions for prompt regressions in the test suite | reference only |
| **Dataset annotation** | Argilla / Label Studio | human labelling for PIELTS bands, HCG trade outcomes | reference only |
| **Visual Workflow editor** | Dify / Flowise / Langflow | study the UX; the AI Studio pipeline backend already exists | later (Phase, after PAT) |
| **Universal AI console** | LibreChat / Open WebUI | compare Claude/GPT/Gemini/DeepSeek/Qwen without code | connector, later |
| **Dev worker** | OpenHands / Aider | "fix bug #321" from the Engineering dept | connector, later |

> Native for the substrate (Prompt Registry — it must feed Episodes/Learning/`/os`);
> connector for the heavy UIs (Dify/LibreChat/OpenHands) and the eval engine (Opik).

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

## Roadmap (evidence-first; M5.1 frozen)

- **Phase A — Production Intelligence** (highest ROI, helps every product):
  Prompt Library ✅ → Evaluation Center (enable Opik) → Dataset Manager →
  Experiment Tracker. **Do the 7-day PAT FIRST** so these tables fill with real
  prompts/datasets/failures/evals instead of being empty.
- **Phase B — AI Studio:** use Production Intelligence to improve scripts,
  thumbnails, titles, hooks, retention.
- **Phase C — PIELTS:** biggest short-term return — feed essays/speaking/grammar/
  vocab into datasets; every human result improves `pielts.writing-eval`.
- **Phase D — HCG Live Signal:** strategy evaluation, prompt A/B, trade replay,
  signal-quality scoring — once Production Intelligence is mature.

**The discipline:** let evidence drive the next layer. Build the substrate native,
attach the tools as connectors around real workflows, and never let a department
depend on a tool that could be swapped in a year.
