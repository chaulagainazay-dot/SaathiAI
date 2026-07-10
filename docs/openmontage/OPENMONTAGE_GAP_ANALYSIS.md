# OpenMontage ↔ SaathiOS Gap Analysis

**Date:** 2026-07-10  
**Scope:** What's missing, what needs adaptation, what to ignore  

---

## Gap Classification Framework

| Classification | Definition | Action |
|---|---|---|
| **REUSE** | OpenMontage has it; SaathiOS can use directly | Import + integrate |
| **WRAP** | OpenMontage has it; SaathiOS needs adapter layer | Adapter skill, API wrapper |
| **REPLACE** | OpenMontage missing; SaathiOS must build | New module |
| **IGNORE** | Not needed for M5.1 (Mr. Yeti character animation) | Out of scope |

---

## Gap Analysis by Category

### 1. Character Animation Pipeline

| Item | Status | Classification | Details |
|------|--------|---|---|
| **10-stage pipeline (research → publish)** | ✅ Exists | REUSE | Use character-animation pipeline as-is |
| **Character-animation skills (9 directors)** | ✅ Exists | REUSE | Use skills/pipelines/character-animation/*.md |
| **Pose library generation** | ✅ Exists | REUSE | pose_library.schema.json + pose tool |
| **Deterministic rendering (HyperFrames)** | ✅ Exists | REUSE | HTML + GSAP → MP4, fully deterministic |
| **Custom playbooks** | ✅ Exists | WRAP | SaathiOS creates playbook for Mr. Yeti brand specs |
| **Rigging & IK** | ✅ Exists (ink-theater) | REUSE | JavaScript animation engine, 2D IK built-in |

### 2. Cost Management

| Item | Status | Classification | Details |
|------|--------|---|---|
| **Budget reserve/reconcile** | ✅ Exists | REUSE | CostTracker.py lifecycle, use directly |
| **Cost estimates per tool** | ✅ Exists | REUSE | Each tool reports estimated_usd |
| **Per-stage cost summation** | ✅ Exists | WRAP | Checkpoint includes cost; SaathiOS reads via API |
| **Budget approval gates** | ✅ Exists | WRAP | OpenMontage raises ApprovalRequiredError; SaathiOS handles |
| **SaathiOS internal cost allocation** | ❌ Missing | REPLACE | SaathiOS Finance layer must allocate to missions |
| **Billing to end users** | ❌ Missing | IGNORE | Not in M5.1 scope |

### 3. Approval & Workflow

| Item | Status | Classification | Details |
|------|--------|---|---|
| **Checkpoint presentation** | ✅ Exists (Backlot) | WRAP | Use Backlot board or build SaathiOS approval UI |
| **Human approval gates (4 per pipeline)** | ✅ Exists | WRAP | SaathiOS API: GET checkpoint, POST approval decision |
| **Send-back (revision) handling** | ✅ Exists | WRAP | OpenMontage re-runs stage with feedback |
| **Max revisions enforcement** | ✅ Exists | REUSE | Declared in pipeline manifest (max_revisions_per_stage: 3) |
| **SaathiOS approval UI** | ❌ Missing | REPLACE | Build approval panel in SaathiOS dashboard (optional, Backlot fallback) |

### 4. Data Models & Schemas

| Item | Status | Classification | Details |
|------|--------|---|---|
| **Character design schema** | ✅ Exists | REUSE | character_design.schema.json |
| **Scene plan schema** | ✅ Exists | REUSE | scene_plan.schema.json |
| **Rig plan schema** | ✅ Exists | REUSE | rig_plan.schema.json |
| **Pose library schema** | ✅ Exists | REUSE | pose_library.schema.json |
| **Render report schema** | ✅ Exists | REUSE | render_report.schema.json |
| **SaathiOS Mission model** | ❌ Missing | REPLACE | SaathiOS Mission → OpenMontage Project mapping |
| **SaathiOS Video model** | ❌ Missing | REPLACE | SaathiOS Video model (metadata for rendered MP4) |

### 5. Provider Integration

| Item | Status | Classification | Details |
|------|--------|---|---|
| **Image generation (7 providers)** | ✅ Exists | REUSE | Use image_gen tools; SaathiOS supplies .env keys |
| **Video generation (12 providers)** | ✅ Exists | REUSE | Use video_gen tools; limited need for character-animation |
| **TTS (7 providers)** | ✅ Exists | REUSE | Use tts tools; optional for voiceover |
| **Stock media (3 providers)** | ✅ Exists | REUSE | Use pexels, pixabay, unsplash (always free) |
| **Google service account** | ✅ Exists | WRAP | SaathiOS supplies GOOGLE_APPLICATION_CREDENTIALS |
| **Credential rotation** | ❌ Missing | IGNORE | Not in M5.1 scope |
| **Provider health monitoring** | ❌ Missing | WRAP | OpenMontage reports provider failures; SaathiOS logs |

### 6. Rendering & Composition

| Item | Status | Classification | Details |
|------|--------|---|---|
| **Remotion rendering** | ✅ Exists | REUSE | For data viz (not primary for character-animation) |
| **HyperFrames rendering** | ✅ Exists | REUSE | Primary for character animation + hand-drawn art |
| **FFmpeg composition** | ✅ Exists | REUSE | Fallback, used by HyperFrames internally |
| **Preview capability** | ✅ Exists (HyperFrames) | WRAP | OpenMontage can generate browser preview; SaathiOS views via API |
| **Deterministic playback** | ✅ Exists | REUSE | No runtime RNG; same inputs → same video every time |

### 7. Version Control & Project Management

| Item | Status | Classification | Details |
|------|--------|---|---|
| **OpenMontage project storage** | ✅ Exists | REUSE | projects/<id>/ workspace model |
| **SaathiOS mission tracking** | ❌ Missing | REPLACE | SaathiOS stores mission metadata in git + postgres |
| **Project ↔ Mission mapping** | ❌ Missing | WRAP | ExecutionGateway creates OpenMontage project for SaathiOS mission |
| **Checkpoint versioning** | ✅ Exists | REUSE | history/ directory keeps old checkpoints |
| **Asset versioning** | ❌ Missing | IGNORE | SaathiOS can use asset_manifest.json snapshot |

### 8. Security & Isolation

| Item | Status | Classification | Details |
|------|--------|---|---|
| **Workspace isolation (projects/<id>)** | ✅ Exists | REUSE | Project-scoped, no cross-leakage |
| **Path safety** | ✅ Exists | REUSE | Path.resolve() + no user input in paths |
| **Credential isolation (.env)** | ✅ Exists | REUSE | API keys in .env, not in code |
| **Access control per-project** | ❌ Missing | REPLACE | For M5.1, single-user only. SaathiOS auth handles user isolation |
| **API key rotation** | ❌ Missing | IGNORE | Not in M5.1 scope |
| **Audit logging** | ⚠️ Partial | WRAP | OpenMontage logs cost; SaathiOS adds user/mission context |

### 9. Monitoring & Observability

| Item | Status | Classification | Details |
|------|--------|---|---|
| **Tool execution logging** | ✅ Exists | REUSE | ToolResult reports success/failure |
| **Cost tracking** | ✅ Exists | REUSE | cost_log.json per project |
| **Error messages** | ✅ Exists | WRAP | Tool errors in ToolResult.error_message; SaathiOS surfaces to user |
| **Performance metrics** | ⚠️ Partial | WRAP | render_report.json includes render_time_seconds |
| **Health checks** | ❌ Missing | REPLACE | Build health-check contract for provider status |
| **SaathiOS dashboard integration** | ❌ Missing | REPLACE | Build dashboard panel for character animation status |

### 10. Testing & Quality Assurance

| Item | Status | Classification | Details |
|------|--------|---|---|
| **OpenMontage unit tests (35+)** | ✅ Exists | REUSE | Run OpenMontage test suite in CI/CD |
| **Integration tests** | ⚠️ Limited | REPLACE | Build SaathiOS ↔ OpenMontage integration tests |
| **E2E pipeline tests** | ⚠️ Limited | REPLACE | Full character-animation pipeline from mission to video |
| **Determinism verification** | ❌ Missing | REPLACE | Test framework: run same input twice, compare videos (byte-identical) |

### 11. Publishing & Distribution

| Item | Status | Classification | Details |
|------|--------|---|---|
| **Publish stage (OpenMontage)** | ✅ Exists | WRAP | OpenMontage has publish_director.md skill + tools |
| **YouTube upload tool** | ✅ Exists | WRAP | youtube_upload tool exists; SaathiOS controls scheduling |
| **Social media routing** | ❌ Missing | IGNORE | SaathiOS n8n handles YouTube → Telegram → TikTok distribution |
| **Thumbnail generation** | ⚠️ Partial | WRAP | OpenMontage can call image_gen; SaathiOS owns design |
| **Video metadata (title, desc)** | ❌ Missing | REPLACE | SaathiOS generates via Baadar LLM layer |

### 12. Brand & Customization

| Item | Status | Classification | Details |
|------|--------|---|---|
| **Custom playbooks** | ✅ Exists | WRAP | SaathiOS creates Mr. Yeti playbook (colors, style, tone) |
| **Character specs** | ✅ Exists (schema) | REUSE | character_design.schema.json + branding inputs |
| **Brand consistency enforcement** | ⚠️ Partial | WRAP | Human approval gate verifies brand match |
| **Multiverse character variants** | ❌ Missing | IGNORE | Not in M5.1 scope (single Mr. Yeti persona) |

---

## Gap Summary

### REUSE (Use OpenMontage As-Is)

- ✅ Character-animation pipeline (10 stages)
- ✅ All 128 tools (image gen, video gen, TTS, etc.)
- ✅ Checkpoint persistence + schema validation
- ✅ Cost tracking + budget governance
- ✅ Approval workflow (human gates)
- ✅ Deterministic rendering (HyperFrames)
- ✅ Workspace isolation (projects/<id>)
- ✅ Credential management (.env)

**Effort:** Zero. Import OpenMontage as service.

### WRAP (Adapter Layer)

- ⚠️ SaathiOS ExecutionGateway → OpenMontage HTTP API
- ⚠️ SaathiOS Mission → OpenMontage Project mapping
- ⚠️ SaathiOS approval UI (or use Backlot)
- ⚠️ SaathiOS cost allocation → OpenMontage cost log
- ⚠️ SaathiOS user context → OpenMontage logging
- ⚠️ Custom Mr. Yeti playbook (brand specs)
- ⚠️ Health check contract (provider status)
- ⚠️ Preview pipeline (optional, use Backlot)

**Effort:** Moderate. Build adapter skill + ExecutionGateway implementation.

### REPLACE (Build Custom)

- ❌ SaathiOS Mission model (stores project metadata)
- ❌ SaathiOS Video model (rendered video metadata)
- ❌ Approval UI panel (optional, use Backlot)
- ❌ Dashboard integration (character animation status)
- ❌ Integration tests (SaathiOS ↔ OpenMontage)
- ❌ Determinism verification tests
- ❌ Video metadata generation (title, description)

**Effort:** Low to moderate. Most are optional for M5.1.

### IGNORE (Out of Scope M5.1)

- ❌ Billing to end users
- ❌ Credential rotation
- ❌ Access control per-project (single-user)
- ❌ API key rotation
- ❌ Multiverse character variants
- ❌ Social media routing (n8n handles)

**Effort:** Zero. Skip until M5.2+.

---

## Risk Assessment

| Gap | Risk | Mitigation |
|-----|------|-----------|
| No SaathiOS approval UI | User must use Backlot board | Use Backlot or defer approval UI to M5.2 |
| No SaathiOS Mission model | Manual project tracking | Build lightweight Mission ↔ Project mapper |
| No integration tests | Pipeline failures latent | Write E2E test (invoke → render → verify) |
| No determinism verification | Render inconsistency undetected | Run same input twice, compare byte-hashes |
| No health checks | Provider failures silent | Build health-check contract (optional, M5.2) |

---

## Recommended Phase 1 Scope (M5.1)

**MUST HAVE:**
- Invoke character-animation pipeline via ExecutionGateway
- Read checkpoints via HTTP API
- Submit approvals (via Backlot or API)
- Track costs for Finance layer
- Store final video in asset library

**NICE TO HAVE:**
- SaathiOS approval UI (use Backlot fallback)
- Dashboard panel showing pipeline status
- Determinism verification tests

**OUT OF SCOPE:**
- Health checks
- Provider fallback routing
- Multiverse variants
- Billing to end users

