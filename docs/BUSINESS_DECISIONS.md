# BUSINESS_DECISIONS.md — why we chose this path

The business decision log. Complements the two other records:

- **Production.md** → *How do we improve?* (standards, evaluation, evidence rule)
- **DECISIONS.md** → *architecture* decisions (ADRs: FastAPI, SQLite, memory tiers…)
- **this file** → *why we chose this business/product path*, and when to revisit

> Naming note: `DECISIONS.md` was already an architectural ADR log, so the business
> log lives here. Every entry follows: **Decision · Reason · Evidence · Review after.**
> Per the governing rule (Production.md), no decision ships without a reason, and
> every decision names the evidence that would change it.

---

## 2026-07-05 · Image-based Mr. Yeti videos, not full animation (yet)
- **Decision:** Ship v0.4.1 with branded scene cards (Flux → PIL fallback), not
  character animation.
- **Reason:** Need 7 days of production evidence (retention, CTR) before investing
  in a Character Engine / animation pipeline.
- **Evidence:** None yet — no analytics.
- **Review after:** 100 published videos, or clear retention signal from the PAT.

## 2026-07-05 · Kokoro (local) over ElevenLabs for narration
- **Decision:** Use Kokoro as the voice provider for v0.4.1 (chain: Kokoro → OpenAI
  → ElevenLabs → macOS say).
- **Reason:** Local, free, reproducible, offline; completes an existing provider
  rather than adding API cost/failure modes mid-certification.
- **Evidence:** PAT voice quality acceptable (verified: real Kokoro WAV, full run 0.93).
- **Review after:** First 1,000 subscribers (revisit premium voice for quality lift).

## 2026-07-05 · Draft quality tier only for v0.4.1
- **Decision:** Ship the Draft tier (Kokoro/say · Flux/card · FFmpeg). Defer premium
  providers (ElevenLabs/Runway/Kling/HeyGen/HyperFrames) to v0.5.
- **Reason:** Certify a reliable, zero-cost pipeline first; the pipeline is constant,
  only providers swap.
- **Evidence:** Full autonomous run proven offline end-to-end.
- **Review after:** v0.4.1 tagged + PAT passed; then v0.5 quality work.

## 2026-07-05 · Do NOT integrate Dify (yet); connectors, not centers
- **Decision:** Do not integrate Dify/LibreChat/OpenHands into the platform now.
  When integrated, they are department connectors, never the execution engine.
- **Reason:** Native pipeline already past where Dify starts (Model Router, Connector
  Registry, Browser, Conversation, Automation Center, AI Studio, Prompt Registry).
- **Evidence:** MCP registry has no connectors for this layer; native stack stable.
- **Review after:** Workflow complexity exceeds the native editor (Dify) / the PAT
  produces real workflows to attach LibreChat + OpenHands around.

## 2026-07-05 · Gemini as the conversation brain (Groq key dead)
- **Decision:** Run SaathiAgent on Gemini (`LLM_PROVIDER=gemini`).
- **Reason:** The VM Groq key went invalid (401); the pielts Gemini key is known-good;
  keeps the brain working today.
- **Evidence:** Brain replies verified on VM + local Mac.
- **Review after:** A fresh Groq key is added, or Gemini cost/limits become a problem.

## 2026-07-05 · service_role key for the HCG canteen Supabase
- **Decision:** Saathi reads canteen data with the HCGMS service_role key.
- **Reason:** The anon key 500s on 3 tables due to a recursive RLS policy on
  `profiles`; service_role bypasses RLS. Trusted backend reading its own data.
- **Evidence:** All 6 tables + `/api/v1/hcgms/dashboard` return 200 with the
  service_role key.
- **Review after:** The HCGMS RLS recursion bug is fixed (then reconsider least-privilege).

## 2026-07-05 · Native Prompt Registry + Opik as the Evaluation Center
- **Decision:** Build the Prompt Library native (`ai_lab`); use the already-integrated
  Opik as the Evaluation Center; Langfuse is the reference alternative.
- **Reason:** The substrate must feed Episodes/Learning/`/os`; Opik is already wired
  and Apache-2.0 with fast evals.
- **Evidence:** Registry live + auto-evaluating from studio runs; Opik installed.
- **Review after:** PAT produces real traces; if Opik falls short, evaluate Langfuse.

## 2026-07-05 · 365-day fixed curriculum (exam-section order), spiral deferred
- **Decision:** IELTS Mastery v1 uses exam-section ordering (grammar→vocab→speaking→
  writing→strategy); the spiral model is v0.5.
- **Reason:** Ship a coherent syllabus now; evolve to spiral from real learner +
  personal-exam evidence, not assumption.
- **Evidence:** None yet — program starts 2026-07-06.
- **Review after:** PAT week + Ajay's own exam (~mid-July 2026) + learner analytics.

## 2026-07-05 · No merge to master until the 7-day PAT passes
- **Decision:** Keep everything on `milestone/m5.1-infrastructure`; tag
  `v0.4.1-infrastructure` only after the PAT merge checklist is all-YES for several days.
- **Reason:** v0.4.1 certifies an operating system in real daily use, not a green
  test suite.
- **Evidence:** 584 tests pass, but no production run yet.
- **Review after:** 7 days of PAT.

---

## How to use this file
Add an entry whenever a business/product path is chosen (a tool, a quality bar, a
sequencing call, a "do not build yet"). Keep architecture (code/structure) in
DECISIONS.md. When a "Review after" trigger fires, revisit the entry, and record the
new decision below the old one rather than editing history.
