# OpenMontage Architecture Deep Dive

**Date:** 2026-07-10  
**Scope:** System structure, dependencies, module roles, data flow  

---

## System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                         AGENTS                              │
│             (Read YAML pipelines + Markdown skills)         │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                      ORCHESTRATION LAYER                    │
│                                                              │
│  • pipeline_loader.py (load YAML manifest)                  │
│  • checkpoint.py (read/write state)                         │
│  • env_loader.py (load credentials)                         │
│  • cost_tracker.py (budget lifecycle)                       │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                        TOOLS LAYER                          │
│                                                              │
│  • tool_registry.py (discover + introspect)                 │
│  • base_tool.py (interface contract)                        │
│  • 128 tool implementations (14 packages)                   │
│    - image_gen/, video_gen/, tts/, audio_gen/              │
│    - analysis/, enhancement/, publishers/, ...             │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                    RENDER RUNTIMES                          │
│                                                              │
│  • Remotion (React → MP4 via Lambda/webpack)                │
│  • HyperFrames (HTML + GSAP → MP4 via Chrome + FFmpeg)      │
│  • FFmpeg (fallback video composition)                      │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                    PROVIDER APIs (35)                       │
│                                                              │
│  Image Gen, Video Gen, TTS, Music, Stock Media, Analysis    │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                   PERSISTENCE & UI                          │
│                                                              │
│  • projects/<id>/ (workspace)                               │
│  • checkpoints/ (stage output)                              │
│  • cost_log.json (budget tracking)                          │
│  • backlot/ (FastAPI web UI + SSE watcher)                  │
└─────────────────────────────────────────────────────────────┘
```

---

## Module Organization

### lib/ (Core Library)

| Module | Responsibility |
|--------|-----------------|
| **pipeline_loader.py** | Load YAML manifests, validate schema, expose stage order + skills |
| **checkpoint.py** | Read/write stage outputs to JSON, validate against artifact schemas |
| **env_loader.py** | Load .env file via python-dotenv, expose os.environ |
| **config_model.py** | Pydantic models for LLM, budget, checkpoint, output, paths config |
| **paths.py** | Define REPO_ROOT, PROJECTS_DIR, canonicalize all paths |
| **media_profiles.py** | Platform-specific FFmpeg presets (YouTube, TikTok, Instagram, etc.) |

**Characteristics:**
- Pure Python (no external services)
- No side effects (deterministic, testable)
- Path-safe (no user input in path construction)
- Validated I/O (pydantic, jsonschema)

### tools/ (128 Tool Implementations)

**Structure:**
```
tools/
├── base_tool.py              # Abstract base + contract
├── tool_registry.py          # Discovery + introspection
├── cost_tracker.py           # Budget lifecycle
├── image_gen/                # 7 image generation tools
├── video_gen/                # 12 video generation tools
├── tts/                       # 7 text-to-speech tools
├── audio_gen/                # 3 music generation tools
├── analysis/                 # Scene detect, transcript, etc.
├── enhancement/              # Color grade, upscale, etc.
├── character/                # Rigging, pose animation
├── publishers/               # YouTube, social media upload
├── _comfyui/                 # ComfyUI integration
└── ...
```

**Contract (BaseTool):**
```python
class BaseTool:
    name: str
    version: str
    tier: Literal["free", "paid", "enterprise"]
    stability: Literal["stable", "beta", "experimental"]
    capability: str  # "image_generation", "video_generation", etc.
    provider: str    # "openai", "google", "runway", etc.
    cost_model: Dict[str, float]  # Operation → estimated_usd
    supports_batch: bool
    supports_preview: bool
    
    def execute(self, params: Dict) -> ToolResult:
        """Run tool. Returns ToolResult with status, output, estimated_usd, actual_usd."""
```

**ToolResult:**
```python
class ToolResult:
    status: Literal["success", "partial", "failed"]
    output: Any  # Tool-specific output
    estimated_usd: float
    actual_usd: float
    error_message: Optional[str]
    execution_time_seconds: float
```

### skills/ (Agent Instructions)

**Structure:**
```
skills/
├── meta/
│   ├── checkpoint-protocol.md    # How to present checkpoints
│   ├── revision-protocol.md      # How to handle send-backs
│   └── ...
├── pipelines/
│   ├── character-animation/
│   │   ├── executive-producer.md  # Top-level orchestration
│   │   ├── character-design-director.md
│   │   ├── rig-planner.md
│   │   └── ...
│   ├── talking-head/
│   │   ├── executive-producer.md
│   │   └── ...
│   └── ...
```

**Format:** Markdown instructions agents read and follow. No code (pure instructions).

### pipeline_defs/ (13 Pipeline Manifests)

**Example (character-animation):**
```yaml
name: character-animation
version: 1.0
category: animation
stability: beta
stages:
  - name: research
    skill: skills/pipelines/character-animation/research-director.md
    required_artifacts_in: []
    produces: [research_brief]
    human_approval_default: false
    
  - name: proposal
    skill: skills/pipelines/character-animation/proposal-director.md
    required_artifacts_in: [research_brief]
    produces: [proposal_packet]
    human_approval_default: true
    
  # ... 8 more stages ...

budget_default_usd: 2.0
max_revisions_per_stage: 3
orchestration_mode: executive-producer
```

### schemas/ (JSON Schema Validators)

**Artifact Schemas:**
```
schemas/artifacts/
├── scene_plan.schema.json
├── character_design.schema.json
├── rig_plan.schema.json
├── pose_library.schema.json
├── asset_manifest.schema.json
├── edit_decisions.schema.json
├── action_timeline.schema.json
├── render_report.schema.json
└── checkpoint.schema.json
```

**Pipeline Schemas:**
```
schemas/pipelines/
├── pipeline_manifest.schema.json
├── stage_definition.schema.json
└── tool_result.schema.json
```

### backlot/ (Web UI + State Watcher)

| Module | Purpose |
|--------|---------|
| **main.py** | FastAPI app setup |
| **state.py** | List projects, read checkpoints, SSE feed |
| **api.py** | REST endpoints (GET /projects, GET /projects/{id}/checkpoints, etc.) |
| **templates/** | HTML templates for web UI |
| **static/** | CSS, JavaScript for browser |

**Design:** Read-only watcher. Never writes to projects/ (agent writes checkpoints). Backlot only reads + presents.

### remotion-composer/ (TypeScript/React)

**Purpose:** React component rendering engine.

**Components:**
- TextCard, StatCard, ProgressBar, CalloutBox, ComparisonCard, Charts

**I/O:**
- Input: React component props (JSON)
- Output: MP4 via Remotion Lambda or webpack build

### ink-theater/ (JavaScript Animation)

**Purpose:** Hand-drawn line art + spring physics + 2D IK animation.

**Features:**
- Deterministic animation (no runtime RNG)
- Spring-based motion
- 2D inverse kinematics (character rigging)
- Frame-perfect reproducibility (seek-safe)

---

## Data Flow: Character-Animation Pipeline

```
1. RESEARCH STAGE
   Input: None
   Tool: research_director.md (agent-driven)
   Output: research_brief.json
   Checkpoint: projects/<id>/checkpoints/research.json
   
2. PROPOSAL STAGE
   Input: research_brief
   Tool: proposal_director.md (agent-driven)
   Output: proposal_packet.json (concept, cost estimate, sample plan)
   Checkpoint: projects/<id>/checkpoints/proposal.json
   Human Approval: REQUIRED
   
3. SCRIPT STAGE
   Input: research_brief, proposal_packet
   Tool: script_director.md (agent-driven)
   Output: script.json (narration, dialogue, action beats)
   Checkpoint: projects/<id>/checkpoints/script.json
   Human Approval: REQUIRED
   
4. CHARACTER_DESIGN STAGE
   Input: script
   Tool: character_design_director.md (agent-driven)
   Tools Used: openai_image, google_imagen, flux_image, stable_diffusion_local
   Output: character_design.json (per-character silhouette, emotional range, style)
   Checkpoint: projects/<id>/checkpoints/character_design.json
   Human Approval: REQUIRED
   Cost: ~$0.15-0.50 (3-5 character design iterations)
   
5. RIG_PLAN STAGE
   Input: character_design
   Tool: rig_planner.md (agent-driven)
   Tools Used: character_design_to_svg.py (custom tool)
   Output: rig_plan.json (SVG rig structure, parts, pivots, layers, constraints)
   Checkpoint: projects/<id>/checkpoints/rig_plan.json
   Human Approval: NONE (auto)
   
6. SCENE_PLAN STAGE
   Input: script, character_design
   Tool: scene_planner.md (agent-driven)
   Output: scene_plan.json (ordered scenes, shot language, character actions)
   Checkpoint: projects/<id>/checkpoints/scene_plan.json
   Human Approval: REQUIRED
   
7. ASSETS STAGE
   Input: character_design, rig_plan, scene_plan
   Tool: asset_director.md (agent-driven)
   Tools Used: image gen, stock media, audio gen
   Output: asset_manifest.json (all images, audio, effects, character parts)
   Checkpoint: projects/<id>/checkpoints/assets.json
   Human Approval: REQUIRED
   Cost: ~$0.50-1.00 (various provider calls)
   
8. EDIT STAGE
   Input: script, scene_plan, asset_manifest
   Tool: edit_director.md (agent-driven)
   Output: edit_decisions.json (pacing, transitions, audio sync, render_runtime selection)
   Checkpoint: projects/<id>/checkpoints/edit.json
   Human Approval: NONE (auto)
   
9. COMPOSE STAGE
   Input: asset_manifest, rig_plan, pose_library, edit_decisions
   Tool: compose_director.md (agent-driven)
   Tools Used: HyperFrames render (GSAP animation), FFmpeg (composition)
   Output: render_report.json (video file path, duration, codec, cost)
   Checkpoint: projects/<id>/checkpoints/compose.json
   Human Approval: NONE (auto)
   Cost: ~$0.30 (HyperFrames local render, FFmpeg free)
   
10. PUBLISH STAGE
    Input: render_report
    Tool: publish_director.md (agent-driven)
    Tools Used: youtube_upload, social_media_upload, email_notification
    Output: publish_log.json (platform, thumbnail, title, description, limitations)
    Checkpoint: projects/<id>/checkpoints/publish.json
    Human Approval: REQUIRED
```

---

## Dependency Graph

```
External APIs
├── OpenAI (DALL-E, Sora)
├── Google (Imagen, Veo, Lyria, TTS)
├── Runway (Gen-4 video)
├── fal.ai (Flux, Kling, Recraft, MiniMax)
├── ElevenLabs (TTS, Music)
├── Pexels, Pixabay, Unsplash (stock)
└── HuggingFace (speaker diarization)
    ↑
    └─── tools/ (128 tools, each calls 0-N providers)
         ↑
         └─── tool_registry.py (discovers tools)
              ↑
              └─── checkpoint.py (validates outputs)
                   ↑
                   └─── pipeline_loader.py (loads manifests)
                        ↑
                        └─── Agents (read YAML + Markdown, execute stages)
                             ↑
                             └─── Backlot (presents checkpoints, SSE feed)
```

**No Circular Dependencies:** Library → Tools → APIs. Agents consume output. No reverse imports.

---

## Isolation Boundaries

### Project Isolation

Each project is a workspace:
```
projects/
├── project-1/
│   ├── project.json
│   ├── checkpoints/
│   │   ├── script.json
│   │   ├── character_design.json
│   │   └── ...
│   └── cost_log.json
├── project-2/
│   └── ...
```

**No Cross-Project Leakage:** Artifacts project-local. Tools stateless. Checkpoints isolated.

### Credential Isolation

- `.env` file (not in git)
- Service-account JSONs (not in git)
- os.environ.get() at tool runtime
- No credentials in checkpoints or logs

### Workspace Assumptions

- Projects running on same machine can access each other's projects/ directory (OK for single-user)
- No access control per-project (OS file permissions only)
- Backlot board is read-only (can't corrupt checkpoints)

---

## Extensibility Points

### Custom Tools

Inherit from BaseTool:
```python
class CustomVideoGenerator(BaseTool):
    name = "my_custom_video"
    capability = "video_generation"
    
    def execute(self, params):
        # Generate video
        return ToolResult(status="success", output={...})
```

Pipeline can enable via: `extensions.custom_tools: true`

### Custom Skills

Create Markdown instructions in skills/:
```markdown
# My Custom Skill

## Instructions for Agent

1. Read the reference input
2. Analyze the style
3. Generate prompts for image generation
4. Call image_generator tool with prompts
5. Collect results, write checkpoint
```

### Custom Playbooks

JSON/YAML files describing visual style, color palette, camera work:
```json
{
  "name": "Mr. Yeti Brand",
  "colors": {"primary": "#6C3FCF", "accent": "#00BFA5"},
  "character_style": "friendly, round, educational",
  "camera": "warm, close-up, eye-level"
}
```

---

## Configuration Merge Order

1. Defaults in config_model.py
2. config.yaml in repo root
3. .env environment variables (override config.yaml)
4. Runtime parameters (override everything)

---

## Error Handling & Recovery

### Tool Failures

Tool returns ToolResult with status="failed". Orchestrator (agent) decides:
- Retry with different provider (via selector tool)
- Skip stage (if optional_artifacts_in)
- Fail and escalate to human

### Checkpoint Failures

If checkpoint write fails, stage output not persisted. Agent retries from previous checkpoint.

### Cost Overruns

CostTracker.reserve() raises ApprovalRequiredError. Agent requests human approval before proceeding.

### API Rate Limits

Tool retry logic (5 retries, exponential backoff) built in to most tools. If still failing, escalate.

---

## Performance Characteristics

| Operation | Complexity | Notes |
|-----------|-----------|-------|
| Pipeline Load | O(1) | Manifest is small YAML file |
| Tool Discovery | O(n) | Introspect all 128 tools once at startup |
| Checkpoint Write | O(n) | n = artifact size (typically <10MB) |
| Cost Calculation | O(1) | Lookup + addition |
| Render (Remotion) | O(f) | f = number of frames (~30s for 1min video) |
| Render (HyperFrames) | O(f) | f = number of frames (~3-5s for 1min video) |
| FFmpeg Composition | O(f) | f = number of frames (~1-2s for 1min video) |

---

## Known Constraints

1. **Single-User Design:** No built-in access control per-project
2. **Stateless Tools:** Each tool invocation is independent (no session state)
3. **No Tool Caching:** Results not deduplicated across tool calls (except video_selector clip cache)
4. **Linear Pipeline Progression:** No branching, no parallel stages
5. **YAML Manifest Size:** Scales linearly with stage count (manageable up to 50 stages)

---

**Architecture Locked:** Phase 3.1 (core abstractions stable). Extensions (custom tools, playbooks) available via declared flags.

