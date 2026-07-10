# ADR-001: Video Production Backend Architecture Selection

**Status:** Proposed  
**Date:** 2026-07-10  
**Decision Makers:** SaathiOS Architect, Baadar PM  
**Stakeholders:** Mr. Yeti Brand Team, Baadar Social Operations, SaathiAI Executive  
**Reviewers:** OpenMontage Community, Claude Code Toolkit Maintainers (optional)

---

## Problem Statement

SaathiOS needs a video production backend to support two divergent use cases:

1. **Quick Social Content (Baadar):**
   - Mr. Yeti daily talking head videos
   - 15-45 minute turnaround
   - Cost-sensitive (~$0.01-0.30 per video)
   - Linear workflow (no approval gates)
   - Example: Telegram update video, TikTok short

2. **Production-Grade Brand Video (Mr. Yeti Campaign):**
   - Feature-quality character animation
   - 2-4 hour turnaround (includes approvals)
   - Budget-controlled (~$2.00 per video)
   - Multi-stage approval workflow
   - Human-in-the-loop gatekeeping
   - Example: YouTube campaign, product launch

**Constraint:** A single system cannot serve both efficiently.

**Decision Required:** Which backend(s) to use, and how to integrate them?

---

## Options Evaluated

### Option A: Claude Code Video Toolkit Only

**Approach:** Embed claude-code-video-toolkit as SaathiOS library, wrap in HTTP adapter.

**Pros:**
- ✅ Low complexity (single system)
- ✅ Native Claude Code integration
- ✅ Fast setup (skills architecture)
- ✅ MIT license (permissive, no copyleft)
- ✅ Adequate for Baadar daily content
- ✅ Low cost ($0.01-0.30 per video)

**Cons:**
- ❌ No character rigging (SadTalker only)
- ❌ No approval workflow (linear only)
- ❌ No budget governance (logging only)
- ❌ No hand-drawn animation (Remotion focus)
- ❌ Cannot produce professional Mr. Yeti brand video
- ❌ Limited provider ecosystem (2 image providers, 1 video provider)

**Verdict:** **INSUFFICIENT** — Cannot meet Mr. Yeti brand video requirements. Character animation limited to basic talking head.

---

### Option B: OpenMontage Only

**Approach:** Deploy OpenMontage as standalone service, call from SaathiOS via HTTP.

**Pros:**
- ✅ Production-ready character animation (10-stage pipeline)
- ✅ Approval workflow + human gatekeeping
- ✅ Budget governance (reserve/reconcile lifecycle)
- ✅ Deterministic hand-drawn rendering (HyperFrames)
- ✅ Can produce professional Mr. Yeti brand video
- ✅ Comprehensive provider ecosystem (35 providers)
- ✅ Immutable checkpoint history (audit trail)

**Cons:**
- ❌ Overkill for daily Baadar content (2-4 hour turnaround)
- ❌ High complexity (YAML + Markdown + Python orchestration)
- ❌ Expensive learning curve (not native to Claude Code)
- ❌ Long approval workflow (4+ human gates) inappropriate for quick social
- ❌ AGPL-3.0 license (copyleft requires HTTP adapter wrapper)
- ❌ Slower iteration (not ideal for daily content loop)

**Verdict:** **TOO HEAVY** — Excellent for campaigns, poor fit for daily Baadar automation.

---

### Option C: Both Systems with Intelligent Routing (RECOMMENDED)

**Approach:** 
- **Claude Video Toolkit** for quick daily content (Baadar, quick demos)
- **OpenMontage** for production campaigns (Mr. Yeti brand, approvals required)
- **VideoProductionBackend** abstraction layer to route based on `mode` parameter

**Architecture:**

```
SaathiOS ExecutionGateway
    ↓
ToolIntent(
  capability="video_generation",
  mode="quick" | "production",      ← Routes to different backend
  character="yeti" | None,
  approval_required=True | False
)
    ↓
VideoProductionBackend (SaathiOS adapter)
    ├─ If mode="quick":
    │  └─→ Claude Video Toolkit Skills (via ToolIntent)
    │       └─→ Output: MP4 (15-45 min)
    │
    └─ If mode="production":
       └─→ OpenMontage HTTP Adapter
            └─→ 10-stage pipeline with approvals
                 └─→ Output: MP4 (2-4 hours)
```

**Pros:**
- ✅ Best tool for each job
  - Claude for speed + cost
  - OpenMontage for quality + governance
- ✅ Backward compatible (can start with Claude, upgrade to OpenMontage as needed)
- ✅ Meets both use cases
  - Quick daily Baadar content via Claude
  - Professional Mr. Yeti campaigns via OpenMontage
- ✅ Balanced complexity (Claude simple, OpenMontage hidden behind adapter)
- ✅ Credential abstraction in ToolIntent (both systems work with same token model)
- ✅ Extensible (can add third system later without changing SaathiOS logic)

**Cons:**
- ⚠️ Operational overhead (maintain two systems)
- ⚠️ Routing logic in ToolIntent (need clear decision criteria)
- ⚠️ AGPL licensing (OpenMontage requires wrapper; Claude is MIT)
- ⚠️ Team needs familiarity with both systems

**Verdict:** **OPTIMAL** — Serves both use cases efficiently with clear separation of concerns.

---

### Option D: Build Custom Implementation

**Approach:** Implement custom video generator inspired by both systems.

**Pros:**
- ✅ Perfect fit (tailored to SaathiOS needs)
- ✅ No licensing constraints
- ✅ Full control over architecture

**Cons:**
- ❌ 6-12 month development cycle
- ❌ Significant engineering investment
- ❌ No battle-tested rendering runtime
- ❌ Missed market opportunity (1H2026 launch)
- ❌ Maintenance burden (36 months+ support)

**Verdict:** **NOT VIABLE** — Reinventing the wheel. Both existing systems are production-ready.

---

## Decision: Option C (Hybrid Backend)

**SELECTED: Option C — Dual-Backend with Intelligent Routing**

### Rationale

1. **Use Case Fit:** Claude Toolkit (quick) + OpenMontage (production) = 100% coverage
2. **Risk Mitigation:** No single-system dependency risk
3. **Market Agility:** Deploy Claude Toolkit first (weeks), OpenMontage later (months)
4. **Cost Efficiency:** Pay for OpenMontage only when needed (campaigns)
5. **Quality Spectrum:** From rapid daily content to broadcast-quality animations
6. **Team Scalability:** Junior team members use Claude, experts use OpenMontage

### Phased Implementation

**Phase 1 (Weeks 1-4): Claude Toolkit Integration**
- Embed claude-code-video-toolkit as SaathiOS skill
- Create ToolIntent wrapper for credential abstraction
- Deploy for daily Baadar content
- Target: 2-3 videos/day automation

**Phase 2 (Weeks 5-12): OpenMontage Integration**
- Deploy OpenMontage as separate HTTP service
- Create VideoProductionBackend adapter
- Integrate approval workflow with SaathiOS UI
- Test Mr. Yeti character-animation pipeline

**Phase 3 (Weeks 13-16): Unified Interface**
- ToolIntent routing finalized
- Credential mapping complete
- Analytics dashboard (cost, quality, turnaround)
- Go-live for Mr. Yeti campaigns

---

## Implementation Boundaries

### VideoProductionBackend: Core Abstraction

**Location:** `saathios/core/video/backend.py`

**Interface:**

```python
class VideoProductionBackend:
    """Unified video production interface."""
    
    async def generate_video(
        self,
        mode: Literal["quick", "production"],
        intent: ToolIntent,
        content: VideoContent
    ) -> VideoOutput:
        """
        Generate video based on mode.
        
        Args:
          mode: "quick" (Claude) or "production" (OpenMontage)
          intent: Credential + config wrapper
          content: Script, scenes, assets
          
        Returns:
          VideoOutput: MP4 path, metadata, cost
        """
        if mode == "quick":
            return await self._generate_quick(intent, content)
        elif mode == "production":
            return await self._generate_production(intent, content)
        else:
            raise ValueError(f"Unknown mode: {mode}")
    
    async def _generate_quick(self, intent, content) -> VideoOutput:
        """Route to Claude Video Toolkit skills."""
        # Call SaathiOS skill orchestration
        # → .claude/skills/* via ToolIntent
        # → Returns MP4 in 15-45 minutes
        pass
    
    async def _generate_production(self, intent, content) -> VideoOutput:
        """Route to OpenMontage HTTP service."""
        # POST to OpenMontage /v1/execute
        # Poll checkpoints at each approval gate
        # Integrate human approval flow
        # Returns MP4 in 2-4 hours
        pass
    
    async def get_status(self, project_id: str) -> ProjectStatus:
        """Get video generation status."""
        # Route to appropriate backend based on project mode
        pass
    
    async def list_providers(self, mode: str) -> List[Provider]:
        """List available providers (TTS, image gen, etc.) for mode."""
        pass
```

### ToolIntent Mapping

**Data Model:**

```python
class ToolIntent:
    """Video generation intent."""
    
    capability: str = "video_generation"
    mode: Literal["quick", "production"]
    
    # Content specification
    script: str                    # Video script/narration
    scenes: List[Scene]            # Scene definitions
    duration_seconds: Optional[int]
    
    # Branding
    brand_id: str = "default"
    character: Optional[str]       # "yeti" or None
    
    # Control
    approval_required: bool = False
    budget_usd: float = 0.50      # For quick; 2.00 for production
    
    # Credentials (abstracted from SaathiOS)
    credentials: Dict[str, str] = {
        "tts_provider": "qwen3",
        "image_gen_provider": "flux2",
        "video_gen_provider": "ltx2",
        "auth_token": "..."
    }
    
    # Preferences
    quality: Literal["draft", "standard", "high"] = "standard"
    timeout_seconds: int = 3600    # 1 hour for quick, 14400 for production
```

### ExecutionGateway Integration

**How ToolIntent Flows Through SaathiOS:**

```
User/Agent creates ToolIntent(mode="production", character="yeti", approval_required=True)
    ↓
ExecutionGateway.execute(intent)
    ↓
VideoProductionBackend.generate_video(mode="production", intent)
    ↓
OpenMontage HTTP Adapter.create_project(intent)
    ↓
OpenMontage: Stage 1-3 (Research, Proposal, Script)
    ↓
Approval Checkpoint
    ↓
ExecutionGateway notified (via webhook)
    ↓
SaathiOS UI: "Approval Needed" notification
    ↓
Human reviews Backlot board (or SaathiOS Approval UI)
    ↓
Human clicks "Approve" → ExecutionGateway.approve(project_id)
    ↓
OpenMontage: Stages 4-10 continue (Rig, Scene, Assets, Edit, Compose, Publish)
    ↓
OpenMontage: Checkpoint written (compose stage)
    ↓
ExecutionGateway notified: Video ready
    ↓
VideoOutput returned to caller
    ↓
SaathiOS Asset Library: MP4 stored + metadata indexed
```

### Credential Abstraction Pattern

**SaathiOS Manages Credentials:**

```python
# In SaathiOS auth layer
credentials_store = {
    "elevenlabs_api_key": "sk-xxx",
    "qwen_api_key": "xxx",
    "google_credentials": service_account_json,
    "youtube_oauth_token": "...",
    "modal_token": "...",
    "runpod_api_key": "..."
}

# ToolIntent provides mapping
tool_intent.credentials = {
    "tts": "elevenlabs",           # Use ElevenLabs for TTS
    "image_gen": "flux2",          # Use Flux2 for images
    "auth": credentials_store["elevenlabs_api_key"]  # Pass actual credential
}

# VideoProductionBackend unpacks
async def _generate_production(self, intent, content):
    # Build OpenMontage project config
    om_config = {
        "pipeline": "character-animation",
        "env_vars": {
            "ELEVENLABS_API_KEY": intent.credentials["auth"],
            "MODAL_TOKEN": credentials_store["modal_token"],
            "GOOGLE_CREDENTIALS": credentials_store["google_credentials"]
        }
    }
    # POST to OpenMontage service
```

---

## Claude Video Toolkit Integration Details

### Skills-Based Invocation

**From SaathiOS ExecutionGateway:**

```python
# In VideoProductionBackend._generate_quick()

async def _generate_quick(self, intent: ToolIntent, content: VideoContent) -> VideoOutput:
    """Generate video using Claude Video Toolkit skills."""
    
    # 1. Initialize project via skill
    project_id = await self._invoke_skill(
        skill="claude-video/video",
        action="initialize",
        params={
            "template": content.template or "product-demo",
            "brand": intent.brand_id,
            "title": content.title
        }
    )
    
    # 2. Gather/generate assets (parallel)
    assets = await asyncio.gather(
        self._generate_voiceover(intent, content.script),
        self._generate_images(intent, content.scenes),
        self._generate_background_music(intent)
    )
    
    # 3. Render via Remotion
    output_path = await self._invoke_skill(
        skill="claude-video/render",
        action="render",
        params={
            "project_id": project_id,
            "runtime": "remotion-lambda",  # Fast cloud rendering
            "quality": intent.quality
        }
    )
    
    # 4. Return result
    return VideoOutput(
        mp4_path=output_path,
        duration_seconds=content.duration_seconds or 90,
        cost_usd=0.25,
        mode="quick",
        turnaround_minutes=25
    )
```

### Skill Invocation Pattern

```python
async def _invoke_skill(
    self,
    skill: str,             # "claude-video/video", "claude-video/voice-clone", etc.
    action: str,            # "initialize", "render", "record-demo"
    params: Dict
) -> Any:
    """
    Invoke Claude Code skill from SaathiOS.
    
    Pattern: SaathiOS reads skill from .claude/skills/,
    executes via ExecutionGateway, returns result.
    """
    # This would be implemented as:
    # 1. Load .claude/skills/<skill>.md
    # 2. Parse frontmatter (ToolIntent config)
    # 3. Execute via Claude Code CLI (or embedded SDK)
    # 4. Return result JSON
    pass
```

---

## OpenMontage Integration Details

### HTTP Adapter Pattern

**From SaathiOS ExecutionGateway:**

```python
class OpenMontageAdapter:
    """HTTP adapter for OpenMontage service."""
    
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url        # http://openmontage-service:8000
        self.api_key = api_key          # Service API key
        self.client = httpx.AsyncClient()
    
    async def create_project(self, intent: ToolIntent, content: VideoContent) -> str:
        """Create OpenMontage project, return project_id."""
        response = await self.client.post(
            f"{self.base_url}/v1/projects",
            json={
                "pipeline": "character-animation",
                "pipeline_config": {
                    "budget_usd": intent.budget_usd,
                    "approval_default": True,
                    "custom_playbook": {
                        "character": intent.character,
                        "brand_guidelines": self._load_brand_guidelines(intent.brand_id)
                    }
                },
                "initial_input": {
                    "script": content.script,
                    "scene_descriptions": [s.description for s in content.scenes],
                    "character_name": intent.character
                }
            },
            headers={"Authorization": f"Bearer {self.api_key}"}
        )
        return response.json()["project_id"]
    
    async def get_checkpoint(self, project_id: str, stage: str) -> dict:
        """Fetch checkpoint artifact for a stage."""
        response = await self.client.get(
            f"{self.base_url}/v1/projects/{project_id}/checkpoints/{stage}",
            headers={"Authorization": f"Bearer {self.api_key}"}
        )
        return response.json()
    
    async def approve(self, project_id: str, stage: str, feedback: str = "") -> None:
        """Approve stage, allow progression."""
        await self.client.post(
            f"{self.base_url}/v1/projects/{project_id}/approve",
            json={"stage": stage, "feedback": feedback},
            headers={"Authorization": f"Bearer {self.api_key}"}
        )
    
    async def get_status(self, project_id: str) -> dict:
        """Get project status."""
        response = await self.client.get(
            f"{self.base_url}/v1/projects/{project_id}",
            headers={"Authorization": f"Bearer {self.api_key}"}
        )
        return response.json()
```

### Approval Workflow Integration

**In ExecutionGateway:**

```python
async def _execute_with_approvals(self, project_id: str, om_adapter: OpenMontageAdapter):
    """Poll OpenMontage checkpoints, request SaathiOS approvals."""
    
    while True:
        status = await om_adapter.get_status(project_id)
        
        if status["blocked_on_approval"]:
            stage = status["current_stage"]
            checkpoint = await om_adapter.get_checkpoint(project_id, stage)
            
            # Notify SaathiOS approval system
            approval = await self._request_approval(
                actor="human",
                action=f"approve_video_stage_{stage}",
                context={
                    "project_id": project_id,
                    "stage": stage,
                    "checkpoint": checkpoint,
                    "estimated_cost": checkpoint.get("cost_usd")
                }
            )
            
            if approval.approved:
                # Grant approval
                await om_adapter.approve(project_id, stage, feedback=approval.feedback)
            else:
                # Reject (would trigger send-back in OpenMontage)
                await om_adapter.approve(
                    project_id, stage, 
                    feedback=f"Rejected. Reason: {approval.reason}"
                )
                # Handle rejection (restart stage, rollback, etc.)
        
        elif status["complete"]:
            # Video ready
            return status["output_video_path"]
        
        elif status["failed"]:
            # Handle error
            raise VideoGenerationError(status["error"])
        
        # Poll every 30 seconds
        await asyncio.sleep(30)
```

---

## Why This Architecture is Best

### 1. Speed vs. Quality Trade-off

**Claude Toolkit = Fast**
- 15-45 minutes per video
- Suitable for daily automation
- Cost: $0.01-0.30

**OpenMontage = Quality**
- 2-4 hours per video (includes approval gates)
- Suitable for campaigns
- Cost: $0.50-2.00

**SaathiOS chooses based on use case**, not technology limitation.

### 2. Learning Curve Management

**Claude Toolkit** is native to Claude Code users (Baadar team, content creators).

**OpenMontage** handled by SaathiOS backend team (abstracted from content creators).

**Result:** No training burden; each team uses what they know.

### 3. Licensing Compliance

**Claude (MIT):** Can embed directly in SaathiOS code.

**OpenMontage (AGPL):** Wrap via HTTP adapter → no derivative works → no copyleft trigger.

### 4. Extensibility

**Future provider additions:**
- Add new TTS provider? Both systems support.
- Add new image gen? Both systems support.
- Add new render runtime? Claude (Remotion), OpenMontage (HyperFrames).

**New use cases:**
- Localization (dubbing)? Use OpenMontage's localization-dub pipeline.
- Clip extraction? Use OpenMontage's clip-factory pipeline.

### 5. Risk Mitigation

**Single-system failure:**
- Claude unavailable? Fall back to OpenMontage (slower, higher cost).
- OpenMontage unavailable? Fall back to Claude (faster, lower cost).

**Dual-system reduces vendor lock-in.**

---

## Implementation Checklist

### Phase 1: Claude Toolkit (Weeks 1-4)

- [ ] Clone claude-code-video-toolkit repo
- [ ] Create `saathios/integrations/claude_toolkit_adapter.py`
- [ ] Implement `_invoke_skill()` pattern
- [ ] Create ToolIntent for video_generation capability
- [ ] Wire ExecutionGateway → VideoProductionBackend → Claude
- [ ] Test: Daily Mr. Yeti talking head video
- [ ] Monitor: Turnaround time, cost accuracy
- [ ] Deploy: To Baadar content automation

### Phase 2: OpenMontage (Weeks 5-12)

- [ ] Deploy OpenMontage as Docker service
- [ ] Create `saathios/integrations/openmontage_adapter.py`
- [ ] Implement HTTP adapter (create, status, approve, checkpoint)
- [ ] Create approval workflow integration
- [ ] Design Mr. Yeti brand playbook (custom_playbook config)
- [ ] Test: Character-animation pipeline end-to-end
- [ ] Test: Human approval flow (mock user)
- [ ] Validate: Cost tracking, budget enforcement

### Phase 3: Unified Interface (Weeks 13-16)

- [ ] Implement ToolIntent routing (mode="quick" vs. "production")
- [ ] Implement VideoProductionBackend.generate_video()
- [ ] Add SaathiOS UI for approval board (if not using Backlot)
- [ ] Create analytics dashboard (cost, turnaround, quality)
- [ ] Load test: 10 concurrent videos (mix quick/production)
- [ ] Documentation: Operator guide for credential management
- [ ] Go-live: Mr. Yeti campaign pipeline

---

## Success Criteria

| Criterion | Target | Measure |
|-----------|--------|---------|
| **Baadar daily automation** | 3+ videos/day | Count from logs |
| **Turnaround (quick)** | <45 min | End-to-end timing |
| **Cost (quick)** | <$0.30 | Logged in project.json |
| **Mr. Yeti campaign video** | 1-2 videos/week | Schedule adherence |
| **Turnaround (production)** | 2-4 hours (incl. approvals) | Checkpoint timestamps |
| **Cost (production)** | <$2.00 | Cost reconciliation |
| **Approval workflow** | Human gate at 4+ stages | Checkpoint audit log |
| **System reliability** | 99.5% uptime | Monitoring dashboard |
| **Character animation quality** | Professional (broadcast-ready) | Visual QA review |

---

## Risks & Mitigation

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| Claude Toolkit breaking change | Low | Medium | Pin version, monitor releases, test on canary |
| OpenMontage AGPL licensing dispute | Low | High | Legal review of HTTP adapter wrapper pattern |
| Cloud GPU cost overrun | Medium | Medium | Implement cost alerts, budget cap enforcement |
| Approval workflow bottleneck | Medium | Medium | SLA for approvals (1 hour), escalation to CEO |
| Character animation quality insufficient | Low | High | QA review of sample renders (week 5) |
| Concurrent video limit (5+ videos) | Medium | Low | Implement job queue, priority scheduling |

---

## Rollback Plan

**If OpenMontage integration fails (weeks 5-12):**
- Revert to Claude Toolkit only
- Deploy as-is to production
- Defer character-animation campaigns to 2026-Q3

**If approval workflow doesn't integrate (weeks 13-16):**
- Use Backlot board directly (less streamlined)
- Implement webhook callbacks manually
- Escalate to SaathiOS architect for custom integration

---

## Future Enhancements

1. **A/B Testing Pipeline** — Generate multiple video concepts, human picks best
2. **Style Transfer** — Apply custom animation style to characters
3. **Multi-Language Dubbing** — Leverage OpenMontage's localization pipeline
4. **Clip Extraction** — Break long-form content into social shorts
5. **Analytics-Driven Optimization** — Suggest content edits based on engagement metrics

---

## Decision Approved

**Option C: Hybrid Backend (Claude Video Toolkit + OpenMontage)**

**Implementation begins:** 2026-07-15  
**Phase 1 launch:** 2026-08-10 (Baadar daily automation)  
**Phase 3 launch:** 2026-09-15 (Mr. Yeti campaigns live)

---

**End of ADR**

