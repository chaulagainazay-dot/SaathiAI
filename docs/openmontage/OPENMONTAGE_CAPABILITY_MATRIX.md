# OpenMontage ↔ SaathiOS Responsibility Matrix

**Date:** 2026-07-10  
**Scope:** Who does what in character-animation pipeline + SaathiOS integration  

---

## OpenMontage Capabilities

| Capability | OpenMontage | SaathiOS | Notes |
|------------|-------------|----------|-------|
| **Pipeline Orchestration** | ✅ (YAML manifests) | ❌ | OpenMontage reads pipeline_defs/character-animation.yaml, executes stages in order |
| **Stage Director Skills** | ✅ (Markdown) | ❌ | OpenMontage executes skills/pipelines/character-animation/*.md as agent instructions |
| **Checkpoint Persistence** | ✅ | ❌ | OpenMontage writes projects/<id>/checkpoints/<stage>.json |
| **Artifact Schema Validation** | ✅ | ❌ | OpenMontage validates each checkpoint against JSON Schema |
| **Cost Tracking & Budget** | ✅ | Optional | OpenMontage reserves/reconciles budget per tool execution |
| **Tool Discovery & Routing** | ✅ | ❌ | OpenMontage's tool_registry introspects 128 tools |
| **Provider API Calls** | ✅ | ❌ | OpenMontage calls Google Veo, DALL-E, HyperFrames, FFmpeg, etc. |
| **Credential Management** | ✅ | ❌ | OpenMontage loads .env, manages os.environ |
| **Video Rendering (Remotion)** | ✅ | ❌ | OpenMontage executes React → MP4 |
| **Video Rendering (HyperFrames)** | ✅ | ❌ | OpenMontage executes HTML + GSAP → MP4 |
| **Video Rendering (FFmpeg)** | ✅ | ❌ | OpenMontage falls back to FFmpeg composition |
| **Approval Workflow** | ✅ (Backlot UI) | Optional | OpenMontage presents checkpoints for human review |
| **Version Control** | ❌ | ✅ (git) | SaathiOS stores project metadata in git, tracks changes |
| **Authentication** | ❌ | ✅ | SaathiOS manages user auth, session tokens, API keys |
| **Content Strategy** | ❌ | ✅ | SaathiOS owns Mr. Yeti strategy, tone, brand guidelines |
| **Scene Direction** | ❌ | ✅ | SaathiOS determines what scenes to create, story beats |
| **Approval Authority** | ❌ | ✅ | SaathiOS/human decides approve/reject/send-back |
| **Asset Management** | Partial | ✅ | OpenMontage discovers assets for a stage; SaathiOS manages library |
| **Character Branding** | Partial | ✅ | OpenMontage follows custom playbooks; SaathiOS owns brand specs |
| **Publishing** | ✅ (tools) | ✅ | OpenMontage has YouTube upload tool; SaathiOS owns schedule |

---

## Stage-by-Stage Responsibility

### Research Stage

| Task | Owner | Role |
|------|-------|------|
| Analyze reference input (style, tone) | OpenMontage Agent | Executes research_director.md skill |
| Determine if rigged animation fits | SaathiOS | Domain decision (Mr. Yeti = rigged ✅) |
| Research competing animations | OpenMontage Agent | Calls research_director, uses analysis tools |
| Output: research_brief.json | OpenMontage | Writes checkpoint |

### Proposal Stage

| Task | Owner | Role |
|------|-------|------|
| Generate concept options | OpenMontage Agent | Executes proposal_director.md skill |
| Cost estimate | OpenMontage | Calls cost_tracker.estimate() |
| Sample proof-of-concept render | OpenMontage | Calls hyperframes_compose.py (sub-stage: proposal.sample) |
| Approve/reject proposal | SaathiOS (human) | Backlot board or API call |
| Output: proposal_packet.json | OpenMontage | Writes checkpoint |

### Script Stage

| Task | Owner | Role |
|------|-------|------|
| Write narration/dialogue | OpenMontage Agent | Executes script_director.md |
| Specify action beats | OpenMontage Agent | Uses script_director skill |
| Identify character needs | OpenMontage Agent | Reads research_brief, infers from script |
| Approve script | SaathiOS (human) | Reviews checkpoint |
| Output: script.json | OpenMontage | Writes checkpoint |

### Character Design Stage

| Task | Owner | Role |
|------|-------|------|
| Generate character images | OpenMontage Tools | Calls image_gen tools (DALL-E, Flux, etc.) |
| Cost budget management | OpenMontage | CostTracker.reserve() before each image gen call |
| Select/refine designs | OpenMontage Agent | Reviews outputs, iterates |
| Brand consistency check | SaathiOS (human) | Verifies align with Mr. Yeti brand guidelines |
| Approve final designs | SaathiOS (human) | Send-back if doesn't match brand |
| Output: character_design.json | OpenMontage | Writes checkpoint |

### Rig Plan Stage

| Task | Owner | Role |
|------|-------|------|
| Create SVG rig structure | OpenMontage Tool | character_design_to_svg.py tool |
| Define pivots & constraints | OpenMontage Agent | Executes rig_planner.md skill |
| Output: rig_plan.json | OpenMontage | Writes checkpoint |
| No human approval | — | Auto-proceed |

### Scene Plan Stage

| Task | Owner | Role |
|------|-------|------|
| Translate script to scenes | OpenMontage Agent | Executes scene_planner.md |
| Add shot language (camera, framing) | OpenMontage Agent | Uses cinematography expertise from skill |
| Specify character actions (pose timeline) | OpenMontage Agent | Reads script, infers character movements |
| Approve scene breakdown | SaathiOS (human) | Verifies narrative flow |
| Output: scene_plan.json | OpenMontage | Writes checkpoint |

### Assets Stage

| Task | Owner | Role |
|------|-------|------|
| Generate background images | OpenMontage Tools | image_gen tools |
| Generate or source music | OpenMontage Tools | audio_gen tools or stock media |
| Download stock video/images | OpenMontage Tools | pexels, pixabay, unsplash tools |
| Cost tracking | OpenMontage | CostTracker.reserve() before each call |
| Approve final asset set | SaathiOS (human) | Reviews quality, licensing |
| Output: asset_manifest.json | OpenMontage | Writes checkpoint |

### Edit Stage

| Task | Owner | Role |
|------|-------|------|
| Plan pacing (shot timing) | OpenMontage Agent | Executes edit_director.md skill |
| Specify transitions | OpenMontage Agent | Chooses between fade, cut, dissolve, etc. |
| Plan audio sync | OpenMontage Agent | Aligns narration to scene boundaries |
| Select render runtime | OpenMontage Agent | Chooses Remotion, HyperFrames, or FFmpeg |
| Output: edit_decisions.json | OpenMontage | Writes checkpoint |
| No human approval | — | Auto-proceed |

### Compose Stage

| Task | Owner | Role |
|------|-------|------|
| Render animation (HyperFrames) | OpenMontage | Calls hyperframes_compose.py tool |
| Composite audio + video | OpenMontage Tool | FFmpeg or Remotion compose |
| Quality assurance (frame rate, codec) | OpenMontage | render_report validation |
| Output: render_report.json + video file | OpenMontage | Writes checkpoint + saves MP4 |
| Cost reconciliation | OpenMontage | CostTracker.reconcile() |

### Publish Stage

| Task | Owner | Role |
|------|-------|------|
| Upload to YouTube | OpenMontage Tool | youtube_upload tool (if enabled) |
| Generate thumbnail | OpenMontage Agent | Uses thumbnail_generator skill or tool |
| Schedule social media post | SaathiOS | n8n automation (Telegram notifications) |
| Approval for publication | SaathiOS (human) | Final gate before video goes live |
| Output: publish_log.json | OpenMontage | Writes checkpoint |

---

## Integration Points

### SaathiOS → OpenMontage

| Operation | Type | Example |
|-----------|------|---------|
| **Invoke Pipeline** | HTTP POST | `POST /openMontage/v1/execute` with mission_id, actor_id, task description |
| **Get Status** | HTTP GET | `GET /openMontage/v1/projects/{id}/status` |
| **Read Checkpoint** | HTTP GET | `GET /openMontage/v1/projects/{id}/checkpoints/{stage}` |
| **Submit Approval** | HTTP POST | `POST /openMontage/v1/projects/{id}/approve` with decision |
| **Get Cost Estimate** | HTTP GET | `GET /openMontage/v1/projects/{id}/cost_estimate` |
| **Cancel Pipeline** | HTTP POST | `POST /openMontage/v1/projects/{id}/cancel` |

### OpenMontage → SaathiOS (Callback)

| Event | Type | Trigger |
|-------|------|---------|
| **Stage Complete** | Webhook | POST to SaathiOS callback when checkpoint written |
| **Approval Needed** | Webhook | POST when human_approval_default=true |
| **Cost Exceeded** | Webhook | POST when budget threshold hit |
| **Error** | Webhook | POST on tool failure or recovery |

---

## Data Ownership

| Data | Owner | SaathiOS Access |
|------|-------|-----------------|
| **Pipeline Definition** | OpenMontage | Read-only (immutable in repo) |
| **Checkpoints** | OpenMontage (writes) | SaathiOS reads via API |
| **Cost Log** | OpenMontage (writes) | SaathiOS reads via API for billing |
| **Render Output (MP4)** | OpenMontage (generates) | SaathiOS manages, distributes |
| **Project Metadata** | Both | SaathiOS stores in git, OpenMontage in projects/<id>/project.json |
| **Character Brand Specs** | SaathiOS | Passed to OpenMontage as custom playbook |
| **Scene Instructions** | SaathiOS (owner) | OpenMontage uses to plan animation |
| **Approval Decisions** | SaathiOS (human) | Sent to OpenMontage via API |

---

## Known Constraints

| Constraint | Impact | Mitigation |
|-----------|--------|-----------|
| OpenMontage doesn't understand Mr. Yeti brand without playbook | Character may not match visual identity | SaathiOS provides custom playbook with brand specs |
| Single-user design (no multi-tenant) | Can't run concurrent pipelines for different users | OK for M5.1 (Ajay's personal use) |
| Stateless tools | No tool session state across stages | Plan stages to be independent; use checkpoints |
| Linear progression | Can't branch (e.g., A/B test two concepts) | Manual workaround: run two separate projects |
| 10-stage pipeline is long | Approval workflow creates wait points | 4 human approval gates (normal for video production) |

---

## Deployment Topology

```
┌─────────────────────┐
│    SaathiOS         │
│  (Django/FastAPI)   │
│                     │
│  • ExecutionGateway │
│  • ToolIntent API   │
│  • Approval Flow    │
└──────────┬──────────┘
           │
           │ HTTP (REST API calls)
           │
┌──────────▼──────────────────────┐
│     OpenMontage Service         │
│   (Separate Python process)     │
│                                 │
│  • pipeline_loader              │
│  • tool_registry                │
│  • cost_tracker                 │
│  • checkpoint writer            │
│  • provider API calls           │
│  • Backlot web UI (optional)    │
└──────────┬──────────────────────┘
           │
           │ API calls (provider keys in .env)
           │
     ┌─────▼─────────────────────┐
     │    Provider APIs (35)      │
     │  Google, OpenAI, Runway,   │
     │  fal.ai, ElevenLabs, etc.  │
     └─────────────────────────────┘
```

---

## Success Criteria

- [ ] SaathiOS can invoke character-animation pipeline via HTTP
- [ ] Checkpoints readable via SaathiOS API
- [ ] Approval flow integrated (SaathiOS human decision → OpenMontage proceed)
- [ ] Cost estimates visible in SaathiOS UI
- [ ] Final video stored in SaathiOS asset library
- [ ] Brand playbook correctly applied (character matches Mr. Yeti style)
- [ ] Pipeline completes within budget ($2.00 default)
- [ ] Deterministic render (same inputs → same video)

