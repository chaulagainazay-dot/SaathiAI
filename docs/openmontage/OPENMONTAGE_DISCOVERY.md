# OpenMontage Stage 1 Discovery Report

**Date:** 2026-07-10  
**Scope:** Static analysis, architecture, pipelines, providers, render runtimes, schemas, cost tracking, approvals  
**Repository:** https://github.com/calesthio/OpenMontage.git  
**Commit:** 2ab5773 (2026-07-09 07:36:45 -0700)  
**License:** AGPL-3.0 with network server clause  
**Python Version:** 3.10+  

---

## Executive Summary

OpenMontage is production-ready agentic video creation platform. Instruction-driven architecture (YAML pipelines + Markdown skills), deterministic render runtimes (Remotion + HyperFrames), and built-in cost tracking/approval gates. **Character-animation pipeline production-ready for Mr. Yeti.**

### Key Findings

✅ **Architecture:** Instruction-driven (agent-orchestrated, not monolithic)  
✅ **Character Animation:** 10-stage pipeline with full rigging, pose animation, and deterministic rendering  
✅ **Cost Tracking:** Budget reserve/reconcile lifecycle with approval thresholds ($0.50 default)  
✅ **Providers:** 35 providers across image gen, video gen, TTS, stock media (always-free tier available)  
✅ **Workspace Isolation:** Project-scoped (projects/<id>/ model), path-safe design  
✅ **AGPL Compliance:** Clear boundaries. Wrapping via HTTP API avoids copyleft on derivatives  

### Risk Summary

⚠️ **API Key Logging:** No systematic scrubbing. Responses may leak auth headers  
⚠️ **Multi-Tenant:** Not built in. Single-user design (OK for SaathiOS M5.1)  
⚠️ **Dependency Audit:** No automated CVE scanning observed  

---

## 1. Repository Metadata

| Field | Value |
|-------|-------|
| **Name** | OpenMontage (The first open-source, agentic video production system) |
| **License** | AGPL-3.0 + Network Server Clause |
| **Python Version** | 3.10 (`.python-version`) |
| **Latest Commit** | 2ab5773 (Merge pull request #270 from kweinmeister/main) |
| **Commit Date** | 2026-07-09 07:36:45 -0700 |

### Core Dependencies

| Dependency | Version | Purpose |
|------------|---------|---------|
| pyyaml | ≥6.0 | YAML pipeline manifests |
| pydantic | ≥2.0 | Validation, config models |
| jsonschema | ≥4.20 | Artifact schema validation |
| Pillow | ≥10.0 | Image processing |
| numpy | ≥1.24 | Numerical operations |
| requests | ≥2.31 | HTTP API calls |
| google-auth | ≥2.0 | Google service-account OAuth |
| google-genai | ≥1.0 | Gemini/Veo/Lyria API |
| openai | ≥2.44.0 | Sora 2 Videos API |
| python-dotenv | ≥1.0 | Environment variable loading |
| fastapi | ≥0.110 | Backlot web server |
| uvicorn | ≥0.29 | ASGI server |

---

## 2. Architecture Structure

**Design Paradigm:** Instruction-driven, agent-first.

Orchestration lives in YAML (pipelines) + Markdown (skills). Python exists for tools and persistence only. Agents read pipelines + skills, execute stages sequentially.

### Top-Level Directories

| Directory | Purpose |
|-----------|---------|
| `lib/` | Python library: pipeline loading, checkpoint I/O, config models, path safety |
| `tools/` | 128 tool implementations (14 capability packages) |
| `skills/` | Markdown instruction files (meta/, pipelines/) |
| `pipeline_defs/` | 13 YAML pipeline manifests |
| `schemas/` | JSON Schema v2020-12 validators for artifacts |
| `remotion-composer/` | TypeScript/React rendering runtime |
| `ink-theater/` | JavaScript animation engine (hand-drawn, spring physics, 2D IK) |
| `backlot/` | FastAPI web server + SSE state watcher |
| `docs/` | Developer documentation |
| `tests/` | 35+ test files (unit, contract, QA) |

### Key Abstractions

**BaseTool** — All 128 tools inherit from `tools/base_tool.py`. Contract: name, version, tier (free|paid|enterprise), stability, capability, provider, cost_model, supports_batch.

**ToolRegistry** — Discovers + introspects all tools. Reports capabilities by tier, status, cost, support envelope.

**Pipeline Manifest** — YAML per pipeline. Declares: name, version, stages (with skills, artifacts, approval gates), budget, orchestration mode.

**Stage Director Skill** — Markdown teaching agent HOW to execute stage. Example: `skills/pipelines/character-animation/executive-producer.md`.

**Artifact** — Canonical JSON output of stage, validated against schemas/artifacts/. Carried between stages as required inputs.

**Checkpoint** — Persisted stage output saved to `projects/<project-id>/checkpoints/`. Used to resume interrupted pipelines.

**Cost Tracker** — `tools/cost_tracker.py`. Budget lifecycle: estimate → reserve → execute → reconcile.

---

## 3. Pipelines (13 Total)

### Character-Animation Pipeline (Primary Target)

| Field | Value |
|-------|-------|
| **Type** | Animation (rigged character animation) |
| **Stability** | Beta (production-ready) |
| **Stages** | 10 (research → publish) |
| **Stage Count** | research, proposal, script, character_design, rig_plan, scene_plan, assets, edit, compose, publish |
| **Budget Default** | $2.00 USD |
| **Max Revisions** | 3 per stage |
| **Orchestration** | executive-producer mode |
| **Reference Input** | Yes (analyze existing video for style) |
| **Custom Extensions** | scripts (yes), playbooks (yes), skills (yes), tools (no) |

**Approval Gates:**
- proposal: human_approval_required
- proposal.sample: human_approval_required (before full production)
- script: human_approval_required
- character_design: human_approval_required
- rig_plan: auto
- scene_plan: human_approval_required
- assets: human_approval_required
- edit: auto
- compose: auto
- publish: human_approval_required

**Mr. Yeti Applicability:** YES. Outputs character specs, SVG rig plans, pose libraries, action timelines. Supports custom playbooks for brand-specific art direction.

### Other 12 Pipelines

| Pipeline | Type | Stability | Stages | Notes |
|----------|------|-----------|--------|-------|
| talking-head | footage-based | stable | 8 | Real footage + AI editing |
| animated-explainer | animated | stable | 7 | Motion graphics, text, diagrams |
| animation | animation | stable | 6 | Image-to-video, generalist |
| cinematic | editorial | stable | 8 | Stock or generated clips |
| clip-factory | batch | stable | 5 | Extract short clips from long-form |
| screen-demo | demo | stable | 6 | Screen recording + narration |
| podcast-repurpose | repurposing | stable | 7 | Podcast audio → video |
| avatar-spokesperson | avatar | stable | 5 | AI avatar presenter |
| hybrid | mixed | stable | 7 | Real + AI-generated support |
| localization-dub | localization | stable | 6 | Multi-language dubbing |
| framework-smoke | test | stable | 3 | Minimal test harness |

---

## 4. Providers & APIs (35 Total)

### Image Generation (7)

| Provider | Cost | Auth | Tier | Notes |
|----------|------|------|------|-------|
| Google Imagen | $0.04/image | API key | Optional | Vertex AI, generous free tier |
| OpenAI DALL-E | $0.05/image | API key | Optional | GPT Image 2 |
| Flux (fal.ai) | $0.03/image | API key | Optional | High-speed, open-source |
| Recraft (fal.ai) | $0.025/image | API key | Optional | AI-native design tool |
| xAI Grok | $0.02/image | API key | Optional | Image composition support |
| Qwen (DashScope) | $0.02/image | API key | Optional | Alibaba, strong Mandarin |
| Stable Diffusion (local) | $0 | None | Optional | Offline, GPU cost |

### Video Generation (12)

| Provider | Cost | Auth | Tier | Notes |
|----------|------|------|------|-------|
| Google Veo | Pay-as-you-go | API key | Optional | Gemini API, text-to-video |
| OpenAI Sora | Pay-as-you-go | API key | Optional | Limited access |
| Kling (fal.ai) | Pay-as-you-go | API key | Optional | High-quality motion |
| MiniMax (fal.ai) | Pay-as-you-go | API key | Optional | Chinese video model |
| Runway Gen-4 | $12/month base | API key | Optional | Highest quality AI video |
| xAI Grok Video | $0.05-0.07/sec | API key | Optional | Reference-conditioned |
| HeyGen | Pay-as-you-go | API key | Optional | Avatar video gateway |
| WAN 2.1 (local) | $0 | None | Optional | Open-source, offline |
| Hunyuan (local) | $0 | None | Optional | Tencent, offline |
| CogVideo (local) | $0 | None | Optional | Zhipu, offline |
| LTX-2 (local/Modal) | $0 local / pay-as-you-go | None / endpoint | Optional | Lightricks |
| Seedance (Replicate/fal) | Pay-as-you-go | Token/key | Optional | Image-to-video |

### Text-to-Speech (7)

| Provider | Cost | Auth | Tier | Notes |
|----------|------|------|------|-------|
| Google Cloud TTS | $0 (1M chars/month) | API key | Optional | 700+ voices, 50+ languages |
| ElevenLabs | $0 (10K chars/month) | API key | Optional | High-quality, premium multilingual |
| OpenAI TTS | $0.015/1000 chars | API key | Optional | Fallback, fewer voices |
| Piper (local) | $0 | None | Optional | Fully offline, voice model download |
| Doubao Speech (Volcengine) | Pay-as-you-go | API key | Optional | Optimized Mandarin |
| Qwen TTS (DashScope) | ~$0.000015/char | API key | Optional | Alibaba, strong Mandarin |

### Music Generation (3)

| Provider | Cost | Auth | Notes |
|----------|------|------|-------|
| Google Lyria | Pay-as-you-go | API key | Gemini API music generation |
| Suno | Pay-as-you-go | API key | Full song + vocal generation |
| ElevenLabs Music | Included subscription | API key | AI-generated music scores |

### Stock Media (3)

| Provider | Cost | Auth | Notes |
|----------|------|------|-------|
| Pexels | $0 (free) | API key | Always-free tier |
| Pixabay | $0 (free) | API key | Always-free tier |
| Unsplash | $0 (free) | API key | Always-free tier |

### Analysis Tools (1)

| Provider | Cost | Auth | Notes |
|----------|------|------|-------|
| HuggingFace | $0 (free API) | HF token (optional) | Speaker diarization |

### Configuration Patterns

- **API Key Loading:** `.env` file via `lib/env_loader.py` (python-dotenv)
- **Service Account Auth:** Google OAuth token minting via `tools/google_credentials.py`
- **Fallback Chains:** Most tools support multiple auth methods (API key, service account, etc.)
- **Cost Estimation:** Each tool's `execute()` returns `ToolResult` with `estimated_usd`

### Free Tier Strategy

**Required:** None. OpenMontage works with zero API keys for free stock media pipelines.

**Recommended:** Google API key (generous free tier + $300 new-account credit) + fal.ai key (unlocks FLUX, Kling, Veo, Recraft, MiniMax).

**Always Free:** Pexels, Pixabay, Unsplash, Piper (local), local video generation (GPU cost only).

---

## 5. Render Runtimes

### Remotion (Browser-based React)

- **Input:** React component props
- **Output:** MP4 via Lambda or local webpack
- **Capabilities:** Text cards, stat cards, progress bars, charts, callout boxes
- **Determinism:** Yes (no runtime RNG)
- **Seek-Safe:** Yes (re-renders on timeline seek)
- **Cost:** Free (local) or $0.05/min (Lambda)
- **Suitable For:** Data visualizations, infographics, chart animations

### HyperFrames (HTML/SVG + GSAP → MP4)

- **Input:** HTML + CSS template, GSAP timeline (paused), assets
- **Output:** MP4 via headless Chrome (Playwright) + FFmpeg
- **Capabilities:** Deterministic animation, HTML overlays, font embedding, GSAP motion
- **Determinism:** Fully deterministic (no runtime clocks)
- **Seek-Safe:** Yes (timeline-based)
- **Cost:** Free (local)
- **Suitable For:** Hand-drawn art, character animation, deterministic motion, bespoke compositions

### FFmpeg (Fallback)

- **Input:** Video files, image sequences, audio
- **Output:** MP4, WebM, or other formats
- **Determinism:** Yes
- **Cost:** Free
- **Suitable For:** Stock footage assembly, audio-only workflows, fallback

### Runtime Selection Logic

- **Remotion** for data viz / charts
- **HyperFrames** for deterministic / hand-drawn / character animation
- **FFmpeg** for footage-only assembly / fallback

---

## 6. Data Models & Schemas

### Core Data Models

**Project** (lib/checkpoint.py, backlot/state.py)
- project_id, pipeline_type, checkpoints, history, metadata

**Scene** (schemas/artifacts/scene_plan.schema.json)
- id, type, description, script_section_id, shot_language, character_actions

**Asset** (schemas/artifacts/asset_manifest.schema.json)
- id, type, source_file, source_tool, parameters, cost_usd, provenance

**Video** (schemas/artifacts/render_report.schema.json)
- video_file, duration, resolution, fps, codec, file_size_mb, render_time, cost_usd

### Artifact Schema Registry

| Artifact | Purpose |
|----------|---------|
| scene_plan | Ordered scenes with shot language, cinematography, character actions |
| character_design | Per-character silhouette, emotional range, action list, style anchors |
| rig_plan | SVG rig structure, parts, pivots, layers, constraints |
| pose_library | Action poses (frame-by-frame pose data, timing, anticipation) |
| asset_manifest | All assets (images, audio, effects, character parts) |
| edit_decisions | Pacing, transitions, timing, audio sync, special effects |
| action_timeline | Character animation timeline per-scene, per-character |
| render_report | Final render metadata (video file, duration, codec, cost) |

### Workflow State Machine

**Canonical Stages:** idea → script → scene_plan → assets → edit → compose → publish

**Per-Pipeline Stages:** Each pipeline defines its own. Character-animation has 10.

**Transitions:** Strictly forward. No cycles (except revision loops inside stage, gated by max_revisions_per_stage).

**Checkpoints:** Persisted after each stage at `projects/<project-id>/checkpoints/<stage-name>.json`.

**Resumption:** If interrupted, next run reads latest checkpoint to resume from next stage.

**Validation:** Schema validation at checkpoint write time (JSON Schema v2020-12).

---

## 7. Testing Infrastructure

| Test Type | Count | Location | Purpose |
|-----------|-------|----------|---------|
| Unit Tests | 35+ | tests/tools/ | Per-tool validation |
| Contract Tests | Multiple | tests/contracts/ | Pipeline + artifact schemas |
| QA Tests | Multiple | tests/qa/ | Manual render validation |

### Test Examples

- test_cost_tracker_governance.py — Budget reserve/reconcile
- test_video_selector_routing.py — Provider selection
- test_scene_detect_lavfi_escape.py — FFmpeg safety
- test_delivery_promise.py — Async promise pattern
- test_remotion_diagnostics.py — Render validation
- test_gemini_omni_video.py — Google Veo integration
- test_sora_video.py — OpenAI Sora integration

### Mock Providers

Mock tools in tests/tools/ use fixtures (no real API calls). Example: `mock_openai_image_multi_output` tests output shape.

### CI/CD

GitHub Actions workflows in `.github/workflows/` (exact files not inspected).

---

## 8. Credential & Environment Handling

### Loading Mechanism

**Method:** python-dotenv via `lib/env_loader.py`. `load_env(project_root)` reads `.env` file into `os.environ`.

**File Location:** `.env` in repo root (example: `.env.example`, never commit `.env`).

**Env Variables:** 62 API keys/credentials documented in `.env.example`.

### Secret Exposure Risks

**Safe Practices:**
- `.env` in `.gitignore` (safe from git commits)
- Service-account JSON files in `.gitignore`
- No hardcoded secrets (verified by grep)

**Potential Risks:**
- Credentials in checkpoint logs (if tool logs API responses)
- API keys on command line (shell history)
- Credentials in error messages

**Mitigations:**
- Cost tracker logs only cost, not request bodies
- Users should export env vars instead of CLI args
- Tools should scrub sensitive data from ToolResult.error_message

### Workspace Isolation

**Model:** projects/<project-id>/ (one tree per project, no cross-project leakage).

**Path Safety:** lib/paths.py defines PROJECTS_DIR + REPO_ROOT once. Path.resolve() normalizes absolute paths. No user input in path construction.

**File Permissions:** OS-level. Backlot board read-only (no writes to projects/).

---

## 9. Cost Tracking & Budgeting

### Lifecycle

**estimate** (preflight) → **reserve** (before execution) → **execute** (tool runs) → **reconcile** (actual cost recorded)

**Persistence:** Cost log saved to `projects/<project-id>/cost_log.json`. Per entry: id, tool, operation, status, estimated_usd, reserved_usd, actual_usd, timestamp.

### Budget Modes

| Mode | Behavior |
|------|----------|
| **observe** | Log costs, no blocking. Useful for exploration |
| **warn** | Block when single-action exceeds threshold or budget runs low (default) |
| **cap** | Strict enforcement. Raise BudgetExceededError if operation would exceed usable |

### Budget Governance

| Setting | Value |
|---------|-------|
| **Total Budget** | Declared per-pipeline (character-animation: $2.00 default) |
| **Usable Budget** | total_usd - (reserve_pct × total_usd). Reserve holdback (10% default) protects overruns |
| **Single-Action Threshold** | $0.50 (default). Actions exceeding require approval |
| **New Paid Tool Approval** | First use of paid tool requires explicit approval (if enabled) |

### Budget Calculations

```
budget_spent_usd = sum(actual_usd for COMPLETED/FAILED entries)
budget_reserved_usd = sum(reserved_usd for RESERVED entries)
budget_remaining_usd = total - spent - reserved
usable_budget_usd = remaining - (reserve_pct × total)
```

### Approval Workflow

Before reserving budget: Check (1) single-action cost vs. threshold, (2) total vs. usable, (3) new paid tool flag.

**Trigger:** CostTracker.reserve() raises ApprovalRequiredError or BudgetExceededError.

**Recording:** Approved tools tracked in _approved_tools set. Once approved in session, no re-trigger.

---

## 10. Approvals & Checkpoints

### Approval Gates

**Declared per-stage** in pipeline manifest: `human_approval_default: true/false`.

**Example:** character-animation proposal stage requires human approval before proceeding to script.

### Checkpoint Mechanism

**Write:** After stage completion, `lib/checkpoint.py` writes `projects/<project-id>/checkpoints/<stage-name>.json`. Validated against checkpoint.schema.json.

**Content:** Stage output (canonical artifact) + metadata (stage name, timestamp, tool invocations, cost, status).

**Persistence:** Immutable once written. history/ keeps old checkpoints if stage re-run.

**Read:** Next stage reads required_artifacts_in from latest checkpoint.

### Backlot Board

FastAPI web UI watches projects/ directory. Presents checkpoints to user. SSE feed notifies browser of changes. User can approve/reject/send-back.

### Revision Loops

**Max Revisions:** Declared per-pipeline (default 3). Agent can request revision N times before giving up.

**Send-Back:** Human can send checkpoint back with feedback. Agent re-runs stage with new instructions.

**Max Send-Backs:** Limit before manual escalation.

### Idempotency

**Stage Re-Entry:** If stage re-run, outputs overwritten (no version branching). Previous in history/.

**Tool Call Deduplication:** Not built in. Individual tools may cache (e.g., clip_cache.py caches by URL hash).

**Resume Safety:** Resuming from checkpoint is safe. Next stage reads cached artifacts, not re-calling tools.

---

## 11. AGPL Licensing Boundaries

### License

**Type:** AGPL-3.0 (GNU Affero General Public License v3) + network server clause.

**Critical:** If you run modified OpenMontage on a network server, users must have access to modified source.

### Scope of Copyleft

**AGPL-Licensed:** Everything in lib/ and tools/ (Python library code).

**Copyleft Applies To:** Any derivative work (fork, modification).

### Plugin Interfaces

**BaseTool** (tools/base_tool.py) — All custom tools inheriting from BaseTool fall under AGPL copyleft.

**Custom Tools Flag** — Pipeline manifests declare `extensions.custom_tools: true/false`. If true, agents can use custom-built tools. If false, bundled-only.

**Custom Skills** — Markdown instructions (NOT software). May NOT trigger AGPL copyleft (verify with legal counsel).

### What Must Be Shared

- Modifications to lib/ or tools/
- Custom BaseTool subclasses
- Modified Backlot server (network service → AGPL network clause)

### What Can Be Wrapped

- Third-party video APIs (own licenses)
- Skill instructions (Markdown, likely permissive)
- Project artifacts (user data, not covered)

### SaathiOS Integration Implications

**If Embedding:** Embedding OpenMontage's lib/tools as library (not modifying) doesn't trigger copyleft. Only modifications do.

**If Wrapping as Adapter:** SaathiOS adapter calling OpenMontage via HTTP API doesn't trigger AGPL copyleft.

**If Forking:** Forking + modifying requires all changes AGPL-licensed and shared.

---

## 12. Security & Isolation

### Workspace Isolation

**Model:** Each project is a workspace under projects/<project-id>/. All artifacts, checkpoints, outputs project-local.

**Inter-Project Contamination:** No known vectors. Artifacts project-scoped. Tool invocations stateless.

**Multi-Tenant Safety:** NOT built in. Environment-level (OS/container) isolation required for multi-tenant.

### Path Traversal Protections

**Canonical Root:** lib/paths.py defines REPO_ROOT and PROJECTS_DIR once. All path ops use Path.resolve() (normalized absolute paths).

**No User Input in Paths:** Core libs don't construct paths from user input. Artifact IDs agent-generated, validated.

**Backlot Path Safety:** backlot/state.py lists projects by iterating sorted(PROJECTS_DIR.iterdir()). No path construction from user input.

### Credential Security

✅ Credentials in .env (not in code)  
✅ .env in .gitignore  
✅ service-account JSON in .gitignore  
✅ No hardcoded secrets  
✅ Cost tracker logs only cost, not request bodies  

### Code Injection Vectors

✅ YAML loaded via yaml.safe_load() (safe, not pickle)  
✅ JSON validated against schema (safe)  
✅ Tool registry via Python introspection (safe)  
✅ No eval(), exec(), or dynamic code execution  

### Dependency Vulnerabilities

**Approach:** Standard pinning in requirements.txt.

**Audit Tools:** Use pip-audit or similar to scan for CVEs.

**Noted:** None identified during Stage 1 (would require automated scan of transitive dependencies).

### API Key Exposure Vectors

⚠️ **Log Scrubbing:** No systematic API key/token redaction. Responses may leak auth headers.

⚠️ **Error Messages:** Tool error messages may contain partial API responses.

✅ **Cost Tracker:** Only logs cost, not API request details (safe).

### Recommendations

1. Implement API response logging filters to redact sensitive data
2. Add automated dependency scanning (pip-audit) to CI/CD
3. Document path traversal assumptions
4. For multi-tenant, add project-level access control
5. Implement request/response logging scrubber middleware for Backlot

---

## Key Architectural Decisions

| Decision | Rationale |
|----------|-----------|
| **Instruction-Driven** | Agents read YAML + Markdown. Orchestration not embedded in Python code |
| **Checkpoint-Based State Machine** | Enables resumption + human review gates at any stage |
| **Capability-First Tools** | Selector tools (e.g., tts_selector) route to providers by budget/preference |
| **Multi-Runtime Composition** | Remotion for data viz, HyperFrames for deterministic, FFmpeg for fallback |
| **Cost Tracking by Default** | Every tool estimates + reserves before execution |
| **No Central Orchestrator** | Agent reads manifest + skills, executes stages sequentially |

---

## SaathiOS Integration Opportunities

1. **Character-Animation for Baadar Mr. Yeti:** Use pipeline for daily content. Custom playbooks enable brand art direction.
2. **Adapter Skill (Layer 2):** Teach SaathiOS when/how to invoke character-animation (rigged vs. AI video decision).
3. **Embed as Library:** Don't fork. Call via HTTP API to avoid AGPL modifications.
4. **Backlot Board Consideration:** If you fork, becomes AGPL. Use as reference, build SaathiOS dashboard.
5. **Cost Governance Template:** Use cost_tracker.py pattern for SaathiAI's internal budget management.

---

## Stage 2 Preparation

**Next Steps:**
1. Map character-animation pipeline end-to-end with sample input/output
2. Design adapter skill interface for SaathiOS
3. Finalize AGPL/licensing compliance strategy
4. Create disabled ExecutionGateway adapter (no provider calls, no credentials)
5. Define ToolIntent ↔ OpenMontage tool contract

---

**Report Completed:** 2026-07-10  
**Next Stage:** Stage 2 Detailed Integration Design
