# SaathiAI Architectural Decision Log

This file records every significant architectural decision made during the design and development of SaathiAI OS. Each entry documents what was decided, why, and what alternatives were rejected.

---

## Decision Index

| ID | Title | Date | Status |
|---|---|---|---|
| ADR-001 | FastAPI over Django/Flask for the core server | 2026-07 | Accepted |
| ADR-002 | SQLite-first, cloud-optional database strategy | 2026-07 | Accepted |
| ADR-003 | Groq as primary LLM with multi-provider fallback | 2026-07 | Accepted |
| ADR-004 | APScheduler embedded in process over external queue | 2026-07 | Accepted |
| ADR-005 | Firebase RTDB for pielts student data | 2026-07 | Accepted |
| ADR-006 | SaathiAI as OS layer; products as applications on the OS | 2026-07 | Accepted |
| ADR-007 | Memory as three tiers: Working → Episodic → Semantic | 2026-07 | Accepted |
| ADR-008 | OmniVoice over ElevenLabs for TTS | 2026-07 | Accepted |
| ADR-009 | Versioned documentation (v1.x/) over single rolling file | 2026-07 | Accepted |
| ADR-010 | HyperFrames for video assembly over FFmpeg-direct | 2026-07 | Accepted |
| ADR-011 | Mission certification is atomic and evidence-gated | 2026-07 | Accepted |
| ADR-012 | Development agents live in `saathi/agentdev/`, above `saathi/engineering/` | 2026-08 | Accepted |

---

## ADR-001: FastAPI over Django/Flask for the core server

**Date:** 2026-07
**Status:** Accepted

**Context:** The SaathiAI server needs to handle async voice commands, WebSocket IELTS sessions, scheduled jobs, and 60+ REST endpoints simultaneously.

**Decision:** Use FastAPI.

**Rationale:**
- Native async/await support — required for concurrent LLM calls
- Automatic OpenAPI docs generation
- Pydantic validation throughout (consistent with data models)
- Lightweight — no ORM or template engine overhead we don't need
- WebSocket support built-in (IELTS speaking practice)

**Rejected alternatives:**
- **Django:** Heavy ORM and template engine we don't need; async support is bolted on
- **Flask:** No built-in async; would require Quart; ecosystem fragmentation

---

## ADR-002: SQLite-first, cloud-optional database strategy

**Date:** 2026-07
**Status:** Accepted

**Context:** SaathiAI currently runs on a single Mac. The operator is a single person.

**Decision:** Use SQLite as the primary database for all server-side state. Firebase RTDB for pielts student data (real-time sync requirement). Cloud Postgres (Neon) as the planned migration target when always-on cloud deployment is needed.

**Rationale:**
- Zero ops — no connection pooling, no authentication, no network
- WAL mode provides good concurrent read performance
- Single binary — trivially backed up to R2
- Sufficient for single-user, single-server operation

**Rejected alternatives:**
- **Postgres locally:** More ops overhead for no benefit at this scale
- **Supabase immediately:** Cost and complexity before product-market fit

---

## ADR-003: Groq as primary LLM with multi-provider fallback

**Date:** 2026-07
**Status:** Accepted

**Context:** LLM inference cost and latency are the primary operational constraints. The system makes dozens of LLM calls per day across scheduling, chat, content, and evaluation.

**Decision:** Groq (`llama-3.3-70b-versatile`) as primary. Claude (Anthropic) for complex reasoning. Gemini for multimodal. Ollama/Shimmy for local cheap tasks.

**Rationale:**
- Groq has the fastest inference available (tokens/second)
- llama-3.3-70b-versatile matches GPT-4o quality at a fraction of the cost
- Local fallback (Ollama) means the system works offline
- Shimmy (TinyLlama 1.1B) reduces cost for high-volume screening tasks to near zero

**Rejected alternatives:**
- **OpenAI GPT-4o as primary:** Cost is 5-10× higher than Groq for equivalent quality
- **Single provider:** No resilience if provider has an outage

---

## ADR-004: APScheduler embedded in process over external queue

**Date:** 2026-07
**Status:** Accepted

**Context:** SaathiAI runs 25+ autonomous scheduled jobs (content, analytics, dashboards, backups).

**Decision:** APScheduler runs in the same FastAPI process.

**Rationale:**
- No external dependencies (no Redis, no Celery, no separate worker)
- Jobs share the same SQLite connection and in-process memory
- Sufficient for single-server operation
- All jobs are wrapped in try/except; one failed job never crashes the scheduler

**Migration path:** When moving to cloud (Phase 3), replace with Celery + Redis or Cloud Tasks.

**Rejected alternatives:**
- **Celery + Redis:** Significant infrastructure overhead for current scale
- **n8n for all scheduling:** Good for webhook-triggered workflows, less suitable for code-heavy scheduled jobs

---

## ADR-005: Firebase RTDB for pielts student data

**Date:** 2026-07
**Status:** Accepted

**Context:** pielts is a React SPA hosted on Firebase Hosting. Student test scores need to persist across sessions and be queryable from the frontend without an intermediate API call.

**Decision:** Firebase Realtime Database (`results/{uid}`) for student scores and progress. Firebase Auth for authentication.

**Rationale:**
- Real-time sync to the React frontend with no API round-trip
- Firebase Auth handles Google/email sign-in for zero server-side auth code
- Existing Firebase Hosting makes this a natural pairing
- Free tier is sufficient for current user volume

**Rejected alternatives:**
- **SaathiAI server as the scores backend:** Extra round-trip; complicates offline usage
- **Supabase:** Good alternative but would require migrating Firebase Auth

---

## ADR-006: SaathiAI as OS layer; products as applications on the OS

**Date:** 2026-07
**Status:** Accepted

**Context:** Three products exist (pielts, HCGMS, Mr. Yeti) and two more are planned (HCG Live Signal, Travel Platform). Each shares AI inference, memory, scheduling, and voice infrastructure.

**Decision:** Formalise SaathiAI as an "operating system" that all products run on. Products are applications that call the OS's APIs. They do not embed their own agent loops or memory systems.

**Rationale:**
- Prevents duplication of AI infrastructure across products
- A single memory system knows about all products (cross-product intelligence)
- One deployment serves all products
- New products can be added without rebuilding foundational infrastructure

**Implication:** Every new product is specified as `POST /api/v1/<product>/...` routes on the SaathiAI server, not as a separate service.

---

## ADR-007: Memory as three tiers: Working → Episodic → Semantic

**Date:** 2026-07
**Status:** Accepted

**Context:** The BMA agent loop needs context at three timescales: current session (seconds), recent history (days), long-term patterns (months).

**Decision:** Three-tier memory hierarchy:
- **Working:** In-process `deque(maxlen=20)` — zero latency, current session only
- **Episodic:** SQLite — full interaction log, async writes, queryable history
- **Semantic:** SQLite patterns + ChromaDB (Phase 6) — extracted knowledge, slow-changing

**Rationale:**
- Matches human memory architecture (working memory → long-term)
- Each tier is independently upgradeable (e.g., swap Episodic SQLite for Postgres without touching Working)
- ChromaDB is optional — the system works without it (degrades to pattern-count SQL)

---

## ADR-008: OmniVoice over ElevenLabs for TTS

**Date:** 2026-07
**Status:** Accepted

**Context:** Baadar and Mr. Yeti need custom voice clones. TTS must be low-latency for real-time voice interaction.

**Decision:** Self-hosted OmniVoice on port 8920.

**Rationale:**
- One-time cloning cost, zero per-character cost thereafter
- Data stays on-device (Ajay's voice is a biometric — must not leave the Mac)
- Latency is local (~50ms) vs. ElevenLabs API (~200-400ms)
- OmniVoice supports streaming output

**Rejected alternatives:**
- **ElevenLabs:** $0.30/1k characters; at scale becomes significant; biometric data leaves device
- **OpenAI TTS:** Good quality but no custom voice clone; data leaves device

---

## ADR-009: Versioned documentation (v1.x/) over single rolling file

**Date:** 2026-07
**Status:** Accepted

**Context:** The SaathiAI specification is expected to evolve significantly as new products and phases are added. Architecture decisions from v1.0 may be superseded.

**Decision:** Store specs in `docs/v1.0/`, `docs/v1.1/`, etc. Current working spec at `docs/v1.x/`. `CHANGELOG.md` at root of `docs/`.

**Rationale:**
- Enables referencing "the v1.0 decision" when debating a v1.1 change
- Old specs remain readable as historical context
- `DECISIONS.md` (this file) provides the reasoning even when specs change

---

## ADR-010: HyperFrames for video assembly over FFmpeg-direct

**Date:** 2026-07
**Status:** Accepted

**Context:** Mr. Yeti video pipeline needs to assemble 8-second Google Flow clips into 60-second shorts with captions, transitions, and B-roll.

**Decision:** HyperFrames renders HTML compositions to video frames, which are then composited via FFmpeg.

**Rationale:**
- HTML/CSS layout for video frames eliminates complex FFmpeg filter graph authoring
- HyperFrames compositions are version-controlled and reviewable
- Caption positioning, typography, and animation are much easier in CSS than in FFmpeg
- FFmpeg handles the final codec step — no custom encoder needed

**Rejected alternatives:**
- **FFmpeg direct (drawtext, overlay filters):** Powerful but extremely verbose for text-heavy videos; hard to maintain
- **MoviePy:** Python wrapper over FFmpeg; adds abstraction without solving the layout problem

---

## ADR-011: Mission certification is atomic and evidence-gated

**Date:** 2026-07
**Status:** Accepted

**Context:** Autonomous mission task completion alone does not prove that evidence,
independent review, browser/tests, resource accounting, commit references, and the
latest durable checkpoint agree.

**Decision:** The platform server is the only certification author. It verifies the
completed mission snapshot and writes the immutable certificate plus the runtime's
`CERTIFIED` transition in one transaction. Client-supplied certifier identity and
partial certification are rejected.

**Rationale:**
- prevents UI or agent self-certification;
- prevents certificate/runtime split-brain after interruption;
- binds the verdict to tenant-owned passing evidence and independent review;
- ensures recovery state, resource usage, commits, tests, and browser status match.

**Rejected alternatives:**
- **Client certification:** would make browser state authoritative.
- **Task-completion-only certification:** omits verification and checkpoint freshness.
- **Separate certificate/state writes:** permits partial terminal state after failure.

---

## ADR-012: Development agents live in `saathi/agentdev/`, above `saathi/engineering/`

**Date:** 2026-08
**Status:** Accepted
**Milestones:** M344–M351

**Context:** The multi-agent development environment needs role contracts, mission-bound
worktree isolation, structured meetings, durable deliberation artifacts, independent review
gates and agent-behaviour evaluation. SaathiOS already owns a governed engineering
orchestrator (`saathi/engineering/`, M20.0–M20.7), a runtime agent registry
(`saathi/agent_registry.py`), a deterministic governance engine (`saathi/safety.py`), four
product mission systems and a universal evidence schema. Building a second agent operating
system on top of those would create competing sources of truth for authority, approvals and
audit.

**Decision:** Add one new package, `saathi/agentdev/`, that sits strictly above
`saathi/engineering/` with a one-way dependency. Its only runtime imports outside the
standard library are `saathi.safety` (`SafetyLevel`, `Approval`) and `saathi.config` (`ROOT`);
what it takes from `saathi.engineering` is design contract rather than code — the
bound-approval field set, the append-only history shape, the atomic-write-with-backup
pattern, and the denials-re-applied-after-override settings rule, each re-implemented for
different nouns. It follows the `docs/evidence/m<NNN>/` certification convention and the
`tests/test_m<NNN>_*.py` test convention. It adds only what provably does not exist:
development-role contracts with
repository path scopes, a mission-bound worktree manager, deliberation artifacts, structured
meetings with preserved disagreement, no-self-approval gates and offline behaviour
evaluations.

**Rationale:**
- `saathi/engineering/` governs one coding agent executing one backlog item; this layer governs many reasoning agents deliberating over one mission. They compose vertically rather than overlapping.
- Keeping `engineering/` unmodified preserves its M20.0–M20.7 certification surface.
- A one-way dependency makes the authority chain explicit and testable: no module under `engineering/`, `missions/` or `platform/` may import `agentdev`.
- `AgentContract` in the runtime registry has no path scope, prohibited actions, independent reviewer or escalation target. Adding development-only fields to it would couple two unrelated lifecycles.
- ECC is adopted as principles only. No ECC file, module, hook, dependency or managed artifact enters this repository; it stays a read-only reference outside it.

**Rejected alternatives:**
- **Extend `saathi/engineering/` in place:** would enlarge a certified module with a different lifecycle and blur "one coding agent" versus "a council of reasoning agents".
- **Extend `saathi/agent_registry.py`:** conflates runtime product agents with development agents; the two need different fields, different authority and different review rules.
- **Reuse `saathi/missions/`:** a development mission has different participants, artifacts and terminal states than a product mission; sharing the store would make "mission" ambiguous.
- **Import ECC's orchestration, hooks or Memory Vault:** creates a second source of truth for governance and a third-party supply-chain dependency inside the security boundary.
- **Reuse milestone numbers M328–M335 as specified:** those numbers are already taken by shipped milestones; renumbering to M344–M351 preserves single-identity milestones.

---

*New decisions are appended at the bottom. Do not edit past decisions — supersede them with new ADRs.*
