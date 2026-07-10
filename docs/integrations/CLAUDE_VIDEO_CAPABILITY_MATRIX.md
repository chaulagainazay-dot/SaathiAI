# Claude Video Toolkit ↔ OpenMontage: Capability Matrix

**Date:** 2026-07-10  
**Scope:** Feature-by-feature comparison with SaathiOS integration strategy

---

## Capability Matrix

| Capability | Claude Toolkit | OpenMontage | Notes | SaathiOS Decision |
|---|---|---|---|---|
| **Script Planning** | Claude Code agent-driven | Agent-driven (script_director skill) | Both support text script generation | **WRAP** — Use Claude for ideation, feed to both systems |
| **Scene Planning** | Manual definition in project.json | Agent-driven (scene_planner skill) + cinematography | OpenMontage adds shot language (camera angles, framing) | **ADAPT** — Claude for rapid ideation, OpenMontage for detailed shot lists |
| **Character Design** | Image generation (Flux, Ideogram) | Image generation + SVG silhouette export | OpenMontage generates character_design.json with emotional range specs | **WRAP** — Use Claude for quick character images, OpenMontage for structured rigging |
| **Character Rigging** | None (SadTalker only) | Full SVG rig with pivots, constraints, joints | Character-animation-exclusive pipeline stage 5 | **REPLACE** — Use OpenMontage for any rigged animation (Mr. Yeti) |
| **Pose Animation** | None (SadTalker does facial only) | Pose library + action timeline per stage | 10-stage orchestration of character movement | **REPLACE** — Use OpenMontage for full-body animation |
| **Facial Animation** | SadTalker (phoneme-sync, lip-sync) | Not native (uses LTX-2 for video generation) | Claude toolkit specialized for talking heads; OpenMontage uses video-gen for faces | **REUSE** — Use Claude for quick talking heads, OpenMontage for integrated rigged faces |
| **Remotion Integration** | ✅ Primary render runtime | ✅ Secondary (data viz focus) | Both support React→MP4; Claude prefers it, OpenMontage prefers HyperFrames | **REUSE** — Both systems support; route based on content type |
| **HyperFrames Integration** | ❌ None | ✅ Primary (hand-drawn specialist) | OpenMontage designed for deterministic SVG+GSAP animation | **ADAPT** — Use OpenMontage for hand-drawn Mr. Yeti animation |
| **FFmpeg Orchestration** | ✅ Direct (MoviePy wrapper) | ✅ Via tools (fallback) | Both support video composition; Claude more direct, OpenMontage uses tools layer | **REUSE** — Both adequate; use preferred by workflow |
| **Scene Composition** | React/Remotion components + FFmpeg | React (Remotion) + HyperFrames (hand-drawn) + FFmpeg (fallback) | OpenMontage adds hand-drawn specialist layer (HyperFrames) | **ADAPT** — Use OpenMontage for hand-drawn; Claude for data viz |
| **Subtitle Pipeline** | align_captions.py (burn to video) | Analysis tools + render support | Claude toolkit has explicit SRT handling; OpenMontage delegates to render runtime | **REUSE** — Use Claude for SRT processing, OpenMontage integrates into composition |
| **Voice Generation** | Qwen3-TTS, ElevenLabs | Qwen3-TTS, ElevenLabs, Google Cloud TTS, OpenAI TTS, Piper (local) | Claude toolkit has fewer free options; OpenMontage has 5+ providers | **ADAPT** — Use OpenMontage for cost-sensitive voiceovers (freeentier options) |
| **Voice Cloning** | Manual (use ElevenLabs directly) | Manual (use ElevenLabs directly) | Neither has built-in voice cloning; both rely on external services | **IGNORE** — Handle via ToolIntent wrapper (expose ElevenLabs custom voice API) |
| **Music Generation** | music_gen.py (API-based) | Lyria, Suno, ElevenLabs Music | OpenMontage has more music providers | **ADAPT** — Use OpenMontage if multi-provider music needed |
| **Stock Media Integration** | Pexels, Pixabay, Unsplash (manual fetch) | Pexels, Pixabay, Unsplash (integrated tools) | OpenMontage has toolized discovery; Claude is manual | **ADAPT** — Use OpenMontage for automated stock media retrieval |
| **Image Generation** | FLUX.2, Ideogram 4 (fal.ai) | FLUX.2, Ideogram 4, DALL-E 3, Google Imagen, Recraft, xAI Grok, Stable Diffusion (local) | OpenMontage has 7 providers vs. Claude's 2 | **ADAPT** — Use OpenMontage for diverse image generation options |
| **Image Editing** | image_edit.py (CloudVOD) | enhancement tools (color grade, upscale) | Both support basic image ops; OpenMontage emphasizes color + composition | **REUSE** — Both adequate for basic editing |
| **Image Upscaling** | upscale.py (via Modal GPU) | upscale tool (via cloud GPU) | Both use similar cloud infrastructure | **REUSE** — Either system; route based on availability |
| **Watermark Removal** | dewatermark.py (ProPainter + Modal) | None (not required for generated content) | Claude toolkit has explicit watermark removal; OpenMontage focuses on original content | **REUSE** — Use Claude for third-party content cleanup |
| **Video Generation** | LTX-2 (text-to-video, 5-second clips) | LTX-2, Kling, Runway Gen-4, Google Veo, OpenAI Sora, WAN 2.1, Hunyuan, CogVideo (local), MiniMax | OpenMontage has 12 video providers vs. Claude's 1 | **ADAPT** — Use OpenMontage for diverse video generation |
| **Talking Head Video** | SadTalker (facial animation from portrait) | HeyGen, LTX-2 (video-generation approach) | Claude toolkit specialized; OpenMontage's approach is more generalist | **REUSE** — Use Claude for SadTalker efficiency; OpenMontage for LTX-2 flexibility |
| **Asset Management** | Filesystem-based (projects/<id>/assets/) | Checkpoint-based (projects/<id>/checkpoints/) + asset_manifest.json | OpenMontage tracks assets with cost + provenance; Claude is implicit | **ADAPT** — Use OpenMontage for asset inventory + cost tracking |
| **Asset Reconciliation** | Manual (Claude verifies filesystem vs. project.json) | Automatic (tools inspect + update asset_manifest) | OpenMontage has toolized reconciliation | **ADAPT** — Use OpenMontage for automated asset discovery |
| **Project Persistence** | project.json (single file) | Multiple checkpoints + project.json + cost_log.json | OpenMontage has richer persistence model | **ADAPT** — Use OpenMontage for audit trail + versioning |
| **Phase Tracking** | 7 phases (planning, assets, review, audio, editing, rendering, publishing) | 10+ per pipeline; character-animation has 10 explicit stages | Claude linear; OpenMontage multi-pipeline, each with own stages | **REUSE** — Use Claude for quick workflows, OpenMontage for complex multi-stage |
| **Approval Workflow** | Implicit (Claude asks, human approves manually) | Explicit checkpoints + Backlot board UI + send-back with feedback | OpenMontage has formal approval gates; Claude relies on manual review | **REPLACE** — Use OpenMontage when approval workflow required (Mr. Yeti campaigns) |
| **Cost Tracking** | Logging only (project.json.cost) | Lifecycle tracking (estimate → reserve → execute → reconcile) | OpenMontage enforces budget governance; Claude is informational | **ADAPT** — Use OpenMontage for cost-sensitive campaigns |
| **Budget Governance** | None (no enforcement) | Strict (reserve before execution, block on overspend) | OpenMontage has approval gates for high-cost operations ($0.50 default threshold) | **REPLACE** — Use OpenMontage when budget control required |
| **Credential Management** | .env (python-dotenv) + OAuth tokens in _internal/ | .env (python-dotenv) + service account JSONs | Both use similar patterns; OpenMontage has more service account examples | **REUSE** — Both adequate; wrap in ToolIntent for abstraction |
| **Error Recovery** | Retry logic in tools (manual) | Retry with exponential backoff + checkpoint resumption | OpenMontage more systematic | **ADAPT** — Use OpenMontage for resilient multi-stage pipelines |
| **Retry & Resumption** | Manual (user runs /video on same project) | Automatic (checkpoint reader resumes from last completed stage) | OpenMontage transparent; Claude requires manual re-invocation | **ADAPT** — Use OpenMontage for long-running workflows |
| **Rendering** | Remotion (local or Lambda) + FFmpeg | Remotion (data viz), HyperFrames (hand-drawn), FFmpeg (fallback) | OpenMontage has hand-drawn specialist (HyperFrames) | **ADAPT** — Use OpenMontage for deterministic hand-drawn animation |
| **Rendering Performance** | Local Remotion: 60 min per 30-sec video | Lambda Remotion: 5 min per 30-sec video; HyperFrames: 15-30 min per 30-sec video | Both offer fast cloud rendering options | **REUSE** — Use Lambda for speed, local for development |
| **Template System** | Built-in (React/TypeScript in templates/) | Not explicit (pipelines define workflow, not visual templates) | Claude toolkit emphasizes reusable visual templates; OpenMontage emphasizes reusable pipelines | **REUSE** — Use Claude templates for quick composition, OpenMontage pipelines for workflow |
| **Brand Profiles** | brands/<name>/brand.ts (theme system) | Not explicit (uses custom playbooks per pipeline) | Claude toolkit has dedicated branding system | **REUSE** — Use Claude for brand theme management; OpenMontage respects brand via playbooks |
| **Branding Integration** | Theme applied to all slides via lib/theme | Custom playbooks guide agent decisions (example: character-animation custom playbook for Mr. Yeti brand) | Claude theme-based; OpenMontage skill-based | **WRAP** — Use Claude for theme consistency, OpenMontage for creative brand playbooks |
| **Publishing** | youtube_upload.py (OAuth, scheduled) | youtube_upload tool + social media tools | Both support YouTube; OpenMontage has broader social coverage | **REUSE** — Both adequate; use preferred provider |
| **Social Media Integration** | Manual (can POST to Slack via n8n) | YouTube, social media tools built-in | OpenMontage more integrated | **ADAPT** — Use OpenMontage for automated social publishing |
| **Notification System** | Manual (Claude prints status) | Backlot board SSE feed + webhook callbacks to SaathiOS | OpenMontage event-driven | **ADAPT** — Use OpenMontage callbacks for real-time status |
| **Web UI** | Studio browser preview (Remotion) | Backlot board (project + checkpoint viewer) | Claude has preview; OpenMontage has management board | **WRAP** — Use Remotion studio for preview, Backlot for approval board |
| **CLI Tools** | Python click-based (20+ tools) | Python click-based (128 tools across 14 packages) | OpenMontage more comprehensive tooling | **REUSE** — Both adequate; OpenMontage for breadth |
| **Tool Registry** | Implicit (tools/ directory) | Explicit (tool_registry.py, introspects all tools) | OpenMontage has discovery + versioning | **ADAPT** — Use OpenMontage ToolRegistry for extensibility |
| **Provider API Support** | 15 providers (Qwen, ElevenLabs, Flux, Ideogram, LTX-2, Pexels, Pixabay, Unsplash, YouTube, Modal, RunPod, etc.) | 35 providers (image gen, video gen, TTS, music, stock media, analysis) | OpenMontage has more diverse provider ecosystem | **ADAPT** — Use OpenMontage for provider flexibility |
| **Multi-Provider Fallback** | Implicit (choose one per operation) | Explicit (tools support multiple providers, tier-based selection) | OpenMontage has built-in fallback logic | **ADAPT** — Use OpenMontage for resilient provider selection |
| **Local Execution** | Remotion (local), FFmpeg (local) | Remotion, HyperFrames, FFmpeg (all support local execution) | Both support local execution for privacy + cost | **REUSE** — Both support offline-first workflows |
| **Cloud GPU Support** | Modal, RunPod | Modal (preferred), RunPod, Vast.ai | Both support cloud compute; OpenMontage more flexible | **REUSE** — Both adequate; use preferred provider |
| **Testing Infrastructure** | Implied (manual testing) | 35+ unit + contract + QA tests | OpenMontage has rigorous testing | **ADAPT** — Use OpenMontage for mission-critical workflows |
| **Documentation** | Getting-started.md, creating-templates.md, LTX2.md, SadTalker.md, YouTube upload, Modal setup | 35+ test files, architecture docs, 13 pipeline examples, skills documentation | OpenMontage more comprehensive | **REUSE** — Both have adequate docs; OpenMontage more detailed |
| **CI/CD Integration** | Not observed | GitHub Actions workflows | OpenMontage has CI/CD; Claude relies on Claude Code workflow | **ADAPT** — Use OpenMontage for automated testing + deployment |
| **Licensing** | MIT (permissive) | AGPL-3.0 + network server clause (restrictive) | MIT is more flexible for SaathiOS embedding; AGPL requires source disclosure if modified | **WRAP** (both) — MIT allows direct embedding; AGPL requires HTTP adapter wrapper |
| **Community & Maintenance** | Active (1.7k stars, recent releases) | Active (community-driven, recent commits) | Both actively maintained | **REUSE** — Both suitable for production |
| **Learning Curve** | Moderate (Claude Code skills + React) | High (YAML pipelines + Markdown skills + Python tools) | Claude easier for Claude Code users | **REUSE** — Use Claude for rapid adoption, OpenMontage for rigorous teams |
| **Integration with Claude Code** | Native (skills architecture) | Not native (separate system) | Claude toolkit designed for Claude Code; OpenMontage is standalone | **REUSE** — Use Claude for tightly integrated workflows |
| **Integration with SaathiOS** | Via ToolIntent (skills → tools) | Via HTTP adapter (REST API) | Both integrable; Claude more direct via skills | **WRAP** — Create VideoProductionBackend abstraction over both |

---

## Classification Legend

| Code | Meaning | Explanation |
|------|---------|-------------|
| **REUSE** | Use as-is from system | Capability is adequate in one or both; use existing implementation |
| **WRAP** | Wrap both in abstraction | Both systems offer capability; abstract via SaathiOS ToolIntent |
| **ADAPT** | Modify slightly for integration | Capability exists but needs adaptation (e.g., add credential abstraction) |
| **REPLACE** | Use specific system | One system clearly better; prefer it for this capability |
| **IGNORE** | Not needed for SaathiOS | Capability exists but SaathiOS doesn't need it (or handles differently) |
| **FUTURE** | Not yet implemented | Capability important but deferred to future iteration |

---

## Summary Counts

| Classification | Count | Examples |
|---|---|---|
| **REUSE** | 18 | Script planning, asset management, publishing, error recovery |
| **WRAP** | 6 | Branding, credential management, voice cloning, UI, licensing |
| **ADAPT** | 12 | Scene planning, character design, HyperFrames, stock media, cost tracking |
| **REPLACE** | 8 | Character rigging, pose animation, approval workflow, budget governance |
| **IGNORE** | 1 | Voice cloning (handled external to SaathiOS) |
| **FUTURE** | 0 | All capabilities covered in Matrix |

---

## Key Strategic Decisions

### Decision 1: Separate Quick + Production Paths

**Quick Path (Claude Toolkit):**
- Voiceover generation (Qwen3-TTS, fast)
- Image generation (Flux, Ideogram)
- Composition (Remotion, FFmpeg)
- Talking head (SadTalker)
- Use case: Baadar daily content, quick demos

**Production Path (OpenMontage):**
- Multi-stage approval workflow
- Character rigging + pose animation
- Cost tracking + budget governance
- Deterministic hand-drawn rendering (HyperFrames)
- Use case: Mr. Yeti brand video, campaign launches

### Decision 2: ToolIntent as Abstraction Layer

**SaathiOS ToolIntent:**
```python
ToolIntent(
  capability="video_generation",
  mode="quick" | "production",       # Routes to Claude or OpenMontage
  brand="default" | "custom",        # Brand profile
  character="yeti" | None,           # Character animation (production only)
  budget_usd=2.00,                   # OpenMontage budget
  approval_required=True | False,    # OpenMontage approval gates
  providers={                        # Credential mapping
    "tts": "elevenlabs",
    "image_gen": "flux2",
    "video_gen": "ltx2"
  }
)
```

### Decision 3: Use OpenMontage for Character Animation

**Mr. Yeti Brand Video Workflow:**
```
SaathiOS ExecutionGateway
  ↓
ToolIntent(mode="production", character="yeti", approval_required=True)
  ↓
OpenMontage HTTP Adapter
  ↓
Stage 1-3: Script + Design (with Mr. Yeti playbook)
  ↓
Human Approval (SaathiOS UI)
  ↓
Stage 4-7: Rig + Scene + Assets (with custom playbook constraints)
  ↓
Human Approval (SaathiOS UI)
  ↓
Stage 8-10: Compose + Publish
  ↓
Output: High-quality Mr. Yeti animation MP4
```

---

## End of Capability Matrix

