# Claude Code Video Toolkit Discovery Report

**Date:** 2026-07-10  
**Repository:** https://github.com/digitalsamba/claude-code-video-toolkit  
**Commit SHA:** Latest main (v0.17.0, Jun 10, 2026)  
**License:** MIT  
**Stars:** 1.7k | Forks:** 291  
**Tech Stack:** Python (58.1%), TypeScript (40.2%), Dockerfile (1.7%)

---

## Executive Summary

The Claude Code Video Toolkit is a **practical, cost-optimized AI-native video production system** emphasizing skill-based orchestration over complex multi-stage pipelines. It prioritizes **immediate affordability** (voiceovers ~$0.01, video clips ~$0.23) while maintaining flexible integration with Claude Code capabilities. Unlike OpenMontage's 10-stage character-animation pipeline, this toolkit focuses on **rapid template-driven video creation** with optional advanced features. 

**Key Fit:** Sprint reviews, product demos, vertical shorts, screen recordings with narration, YouTube automation.

**Not Ideal For:** Sophisticated rigged character animation, approval-gate workflows, production budgeting with reconciliation.

---

## 1. Repository Metadata

| Field | Value |
|-------|-------|
| **Project Name** | claude-code-video-toolkit |
| **Owner** | digitalsamba |
| **License** | MIT |
| **Python Version** | 3.9+ (recommended) |
| **Node.js Version** | 18+ (required) |
| **Latest Release** | v0.17.0 (Jun 10, 2026) |
| **Primary Language** | Python (tools), TypeScript/React (frontend) |

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────┐
│         CLAUDE CODE (Skills Interface)      │
│  • /setup, /video, /template, /design, etc. │
└────────────────┬────────────────────────────┘
                 │
┌────────────────▼────────────────────────────┐
│       Claude Code Skills (.claude/)         │
│  • remotion, ffmpeg, elevenlabs             │
│  • ltx2, sadtalker, ideogram4, etc. (12)    │
└────────────────┬────────────────────────────┘
                 │
┌────────────────▼────────────────────────────┐
│    Project System (lib/project/)            │
│  • State persistence (project.json)         │
│  • Phase tracking (7 phases)                │
│  • Asset management                         │
│  • Multi-session resumption                 │
└────────────────┬────────────────────────────┘
                 │
┌────────────────▼────────────────────────────┐
│    Python Tools (tools/)                    │
│  • 20+ CLI tools for audio/image/video      │
│  • Cloud GPU orchestration (Modal/RunPod)   │
│  • YouTube publishing                       │
└────────────────┬────────────────────────────┘
                 │
┌────────────────▼────────────────────────────┐
│    Render Runtime Selection                 │
│  • Remotion (React → MP4)                   │
│  • FFmpeg (fallback)                        │
│  • Cloud GPU (LTX-2, SadTalker)             │
└────────────────┬────────────────────────────┘
                 │
         ┌───────▼───────┐
    ┌────▼─┐        ┌────▼─────┐
    │Modal │        │Provider   │
    │GPU   │        │APIs (35)  │
    └──────┘        └───────────┘
```

**Design Pattern:** Linear skill-based workflow, Claude-driven decisions, state managed through project.json and filesystem.

---

## 3. Directory Structure & Module Breakdown

```
claude-code-video-toolkit/
├── .claude/                          # Skills configuration
│   ├── settings.json                 # Project-level settings
│   └── agents/*.md                   # Agent instructions
│
├── lib/                              # Core libraries
│   ├── project/                      # Project state management
│   │   ├── Project class             # Handles project.json I/O
│   │   ├── Phase management          # 7-phase lifecycle
│   │   └── Asset tracking            # Asset status states
│   ├── theme/                        # Visual branding system
│   ├── components/                   # Reusable React components
│   └── utils/                        # Common utilities
│
├── tools/                            # Python CLI tools (20+)
│   ├── audio/
│   │   ├── voiceover.py              # TTS (Qwen3, ElevenLabs)
│   │   ├── music.py                  # Music composition
│   │   ├── music_gen.py              # AI music generation
│   │   ├── addmusic.py               # Audio mixing
│   │   ├── sfx.py                    # Sound effects
│   │   └── sync_timing.py            # Audio/video sync
│   │
│   ├── video/
│   │   ├── chain_video.py            # Video concatenation
│   │   ├── pacing.py                 # Speed/timing adjustment
│   │   ├── redub.py                  # Audio replacement
│   │   ├── align_captions.py         # Caption synchronization
│   │   ├── align_captions_srt.py     # SRT subtitle handling
│   │   └── locate_watermark.py       # Watermark detection
│   │
│   ├── image/
│   │   ├── flux2.py                  # FLUX.2 image generation
│   │   ├── ideogram4.py              # Ideogram 4 image gen
│   │   ├── image_edit.py             # Image manipulation
│   │   ├── upscale.py                # Resolution enhancement
│   │   └── dewatermark.py            # ProPainter integration
│   │
│   ├── special/
│   │   ├── sadtalker.py              # Talking head animation
│   │   ├── notebooklm_brand.py       # Branding/styling
│   │   └── ace_step.py               # AI animation
│   │
│   ├── infrastructure/
│   │   ├── cloud_gpu.py              # Modal/RunPod orchestration
│   │   ├── file_transfer.py          # Cloudflare R2 integration
│   │   ├── config.py                 # Configuration loading
│   │   └── verify_setup.py           # System validation
│   │
│   ├── publishing/
│   │   └── youtube_upload.py         # YouTube OAuth + upload
│   │
│   └── playwright-recording.py        # Screen recording
│
├── templates/                        # Video structure blueprints
│   ├── sprint-review/                # Sprint review template
│   ├── product-demo/                 # Product demo template
│   ├── concept-explainer/            # Vertical shorts template
│   ├── screen-walk/                  # Screen recording template
│   ├── [template]/
│   │   ├── src/
│   │   │   ├── Root.tsx              # Entry component
│   │   │   ├── config/types.ts       # Configuration schema
│   │   │   ├── components/           # Slide components
│   │   │   └── theme.ts              # Branding config
│   │   ├── public/                   # Static assets
│   │   └── package.json              # Dependencies
│   │
│   └── _internal/
│       └── toolkit-registry.json      # Template discovery
│
├── brands/                           # Visual identity profiles
│   ├── [brand-name]/
│   │   ├── brand.ts                  # Brand configuration
│   │   ├── colors.json               # Color palette
│   │   ├── fonts/                    # Font files
│   │   └── assets/                   # Logo, images
│   │
│   └── default/                      # Default branding
│
├── examples/                         # Showcase projects
│   ├── hello-world/                  # Minimal example
│   ├── sprint-review-demo/
│   ├── product-demo-showcase/
│   └── [example]/
│       ├── project.json              # Project config
│       ├── src/                      # Video components
│       ├── public/                   # Assets
│       └── demos/                    # Demo videos
│
├── docs/                             # Documentation
│   ├── getting-started.md
│   ├── creating-templates.md
│   ├── creating-brands.md
│   ├── modal-setup.md
│   ├── runpod-setup.md
│   ├── ltx2.md
│   ├── sadtalker.md
│   ├── optional-components.md
│   ├── youtube-upload.md
│   └── qwen-edit-patterns.md
│
├── _internal/                        # Toolkit registry & roadmap
│   ├── toolkit-registry.json
│   └── roadmap.md
│
├── package.json                      # Node.js dependencies
├── requirements.txt                  # Python dependencies
└── .github/workflows/                # CI/CD (if any)
```

### Core Module Purposes

| Module | Responsibility |
|--------|-----------------|
| **lib/project/** | Project lifecycle, state persistence, phase tracking, asset status |
| **tools/** | CLI Python utilities for every media operation |
| **templates/** | Reusable video blueprints (TypeScript React) |
| **brands/** | Visual identity configuration (colors, fonts, logos) |
| **.claude/skills/** | Claude Code instructions for each domain |
| **_internal/toolkit-registry.json** | Template discovery + versioning |

---

## 4. Core Dependencies

### Python Dependencies (tools)

| Package | Version | Purpose |
|---------|---------|---------|
| requests | ≥2.28 | HTTP API calls (ElevenLabs, cloud GPU) |
| pydantic | ≥2.0 | Config validation |
| python-dotenv | ≥1.0 | Environment variable loading (.env) |
| moviepy | ≥1.0 | Video editing (FFmpeg wrapper) |
| pillow | ≥10.0 | Image processing |
| google-auth | ≥2.0 | Google OAuth for YouTube |
| google-auth-httplib2 | ≥0.1 | Google API client |
| google-auth-oauthlib | ≥1.0 | OAuth token handling |
| google-api-python-client | ≥2.0 | YouTube Data API v3 |
| pyyaml | ≥6.0 | Project config parsing |
| click | ≥8.0 | CLI argument parsing |
| pathlib | Built-in | Cross-platform path handling |

### TypeScript/React Dependencies (templates)

| Package | Version | Purpose |
|---------|---------|---------|
| react | ≥18.0 | Component library |
| remotion | ≥4.0 | Video rendering engine |
| framer-motion | ≥10.0 | Animation primitives (optional) |
| tailwindcss | ≥3.0 | Styling system |
| typescript | ≥5.0 | Type checking |
| vite | ≥5.0 | Build tool (if using Vite) |

### System Requirements

- **Node.js:** 18+ (ES2024 support required)
- **Python:** 3.9+ (recommended 3.10+)
- **FFmpeg:** Optional (can use Modal GPU instead)
- **Git:** For version control, project tracking

### Optional Integrations

| Integration | Purpose | Dependency |
|-------------|---------|-----------|
| Modal | Cloud GPU compute | modal_client (Python SDK) |
| RunPod | Alternative GPU cloud | runpod_sdk (Python SDK) |
| Cloudflare R2 | File storage/transfer | boto3, botocore |
| ElevenLabs | Premium TTS | elevenlabs (Python SDK) |
| Qwen3-TTS | Open-source TTS | qwen_tts_api (custom wrapper) |
| FLUX.2 | Image generation (fal.ai) | fal_client |
| Ideogram 4 | Image generation (fal.ai) | fal_client |
| LTX-2 | Video generation (Modal) | modal_client |
| SadTalker | Talking head animation | torch, opencv-python |
| YouTube | Publishing | google-auth libraries |

---

## 5. Programmatic Video Generation Approach

### High-Level Flow

```
User Intent
    ↓
Claude Understands Task → Selects Template
    ↓
Project Initialization
    ├─ Create project.json
    ├─ Assign brand
    └─ Set target resolution
    ↓
Phase 1: Planning
    ├─ Define scenes (manual/agent-driven)
    ├─ Gather reference materials
    └─ Store scene list in project.json
    ↓
Phase 2: Assets Collection
    ├─ Record screen demos (via /record-demo Playwright)
    ├─ Generate images (FLUX.2, Ideogram 4)
    ├─ Generate audio (Qwen3-TTS, ElevenLabs)
    ├─ Collect stock media (Pexels, Pixabay)
    └─ Store file references in project.json
    ↓
Phase 3: Scene Review
    ├─ Preview each scene
    ├─ Verify asset completeness
    └─ Update phase to "audio"
    ↓
Phase 4: Audio Generation
    ├─ Generate voiceover from script
    ├─ Sync timing via sync_timing.py
    └─ Generate background music (optional)
    ↓
Phase 5: Editing
    ├─ Adjust pacing/timing
    ├─ Add transitions (via Remotion or FFmpeg)
    ├─ Composite audio sync
    └─ Preview in-browser
    ↓
Phase 6: Rendering
    ├─ Trigger npm run render or CLI render
    ├─ Remotion compiles React → MP4 (local or Lambda)
    ├─ Post-process via FFmpeg if needed
    └─ Save to projects/<id>/output.mp4
    ↓
Phase 7: Publishing
    ├─ Generate thumbnail (optional)
    ├─ Upload to YouTube (oauth)
    ├─ Post to social (optional)
    └─ Mark complete
```

### Interaction Model

1. **Claude Code Skills** orchestrate high-level steps (user-facing)
2. **Python CLI tools** execute lower-level media operations (system-facing)
3. **Templates** provide React/Remotion structure (data-driven)
4. **Project state** (project.json) persists across sessions
5. **Asset filesystem** stores intermediate outputs
6. **Render engines** (Remotion, FFmpeg) produce final MP4

### Template System

Each template is a **complete TypeScript/React project** with:
- **Configuration Schema** (src/config/types.ts) — defines input parameters
- **Entry Component** (Root.tsx) — registers Remotion composition
- **Slide Components** (src/components/) — reusable slide types
- **Branding Integration** (lib/theme) — pulls colors/fonts from brand config
- **Static Assets** (public/) — images, fonts, media files

Example config interface:
```typescript
interface SprintReviewConfig {
  title: string;
  week: number;
  sections: Section[];           // Title, content, duration
  theme: BrandTheme;             // Colors, fonts
  outputResolution: "1080p" | "4K";
}
```

**Rendering:** `npm run studio` (preview) → `npm run render` (export MP4).

---

## 6. Remotion Integration Details

### Remotion Version & Capabilities

- **Version:** 4.0+ (latest stable)
- **Entry Point:** Templates register Composition in Root.tsx
- **Frame Rate:** 30 fps (configurable)
- **Resolution:** 1920×1080 (default), customizable
- **Codec:** H.264 (MP4 output default)

### Animation Model

**Remotion uses frame-based animation:**

```typescript
import { useCurrentFrame, interpolate } from "remotion";

export const AnimatedText: React.FC<{ text: string }> = ({ text }) => {
  const frame = useCurrentFrame();
  const opacity = interpolate(frame, [0, 30], [0, 1]);  // Fade in over 1 second (30 frames at 30fps)
  
  return <div style={{ opacity }}>{text}</div>;
};
```

**Key Concepts:**
- `useCurrentFrame()` — current playback frame number
- `interpolate()` — easing function (maps frame range to value range)
- `Series.Sequence` — orchestrates timing (slide 1 frames 0-90, slide 2 frames 91-180, etc.)
- `TransitionSeries` — applies transitions between sequences (fade, slide, etc.)

### Component Registration

```typescript
// Root.tsx
import { Composition } from "remotion";

export const Root = () => (
  <Composition
    id="sprint-review"
    component={SprintReview}
    durationInFrames={900}         // 30 seconds at 30fps
    fps={30}
    width={1920}
    height={1080}
    defaultProps={defaultConfig}
  />
);
```

### Rendering Options

| Option | Cost | Speed | Use Case |
|--------|------|-------|----------|
| Local (webpack) | $0 | Slow (30 min for 30 sec) | Development |
| Lambda (Remotion Cloud) | ~$0.05/min | Fast (5 min for 30 sec) | Production |
| S3 + Lambda (DIY) | $0 (AWS costs) | Variable | Custom setup |

---

## 7. FFmpeg Orchestration Model

### Orchestration via Python

The toolkit uses **MoviePy** (Python FFmpeg wrapper) for composition:

```python
from moviepy.editor import VideoFileClip, concatenate_videoclips, CompositeVideoClip

# Chain videos
clips = [VideoFileClip(f) for f in video_files]
final = concatenate_videoclips(clips)

# Add audio
audio_clip = AudioFileClip("voiceover.mp3")
final = final.set_audio(audio_clip)

# Adjust pacing
final_paced = final.speedx(1.2)  # Speed up by 20%

# Export
final.write_videofile("output.mp4", codec="libx264", audio_codec="aac")
```

### FFmpeg Tools in Toolkit

| Tool | Operation |
|------|-----------|
| **chain_video.py** | Concatenate video segments (fade/cut between) |
| **sync_timing.py** | Sync audio/video using FFmpeg filters |
| **pacing.py** | Speed up/slow down playback (video + audio) |
| **addmusic.py** | Mix voiceover + background music |
| **align_captions.py** | Burn SRT captions to video (with timing) |
| **upscale.py** | Enhance resolution (via cloud GPU model) |
| **dewatermark.py** | Remove watermarks (via ProPainter GPU model) |

### FFmpeg Filter Chain Example

```bash
# Sync audio to video + add fade transition
ffmpeg -i video1.mp4 -i video2.mp4 -i audio.mp3 \
  -filter_complex "[0][1]xfade=transition=fade:duration=1:offset=3.5[v];[v][a]concat=n=2:v=1:a=0[out]" \
  -map "[out]" -map 0:a -c:v libx264 -c:a aac output.mp4
```

**Toolkit Abstraction:** Users don't write FFmpeg; they call Python CLI tools that handle the filter chains.

---

## 8. Scene Composition System

### Scene Definition Model

Scenes are defined in **project.json** as structured data:

```json
{
  "scenes": [
    {
      "id": "scene-001",
      "type": "title-slide",
      "title": "Sprint Review",
      "subtitle": "Week 42",
      "duration_seconds": 5,
      "assets": ["background.png", "logo.svg"],
      "status": "ready"
    },
    {
      "id": "scene-002",
      "type": "demo",
      "content": "Feature demo video (Playwright recording)",
      "demo_file": "demos/feature-xyz.mp4",
      "narration": "voiceover-001.mp3",
      "duration_seconds": 30,
      "status": "asset-present"
    },
    {
      "id": "scene-003",
      "type": "talking-head",
      "background": "background-xyz.jpg",
      "talking_head_model": "character-003.png",
      "audio": "voiceover-002.mp3",
      "duration_seconds": 45,
      "status": "ready"
    }
  ]
}
```

### Composition in Remotion

Templates compose scenes dynamically:

```typescript
export const SprintReview: React.FC<{ config: SprintReviewConfig }> = ({ config }) => {
  return (
    <Series>
      {config.sections.map((section, idx) => (
        <Series.Sequence key={idx} from={calculateStart(idx)} durationInFrames={section.duration * 30}>
          {section.type === "title" && <TitleSlide {...section} />}
          {section.type === "demo" && <DemoSlide videoPath={section.video} />}
          {section.type === "talking-head" && <TalkingHeadSlide {...section} />}
        </Series.Sequence>
      ))}
    </Series>
  );
};
```

### Asset Types Supported

| Type | Source | Handled By |
|------|--------|-----------|
| **Slide** | Remotion component | Remotion (no file needed) |
| **Demo Video** | Playwright recording | MoviePy chain |
| **Generated Image** | FLUX.2, Ideogram 4 | tools/image/ |
| **Voiceover Audio** | Qwen3-TTS, ElevenLabs | tools/audio/ |
| **Background Music** | Music generation API | tools/audio/music_gen.py |
| **Stock Video/Image** | Pexels, Pixabay, Unsplash | tools/cloud_gpu.py |
| **Custom SVG** | User-created | staticFile() in Remotion |

---

## 9. Asset Pipeline Architecture

### Asset Tracking State Machine

```
┌──────────────┐
│ asset-needed │ (declared but not created)
└──────┬───────┘
       │ (tool runs, creates file)
       │
┌──────▼───────────┐
│ asset-present    │ (file exists on disk, unverified)
└──────┬───────────┘
       │ (Claude verifies)
       │
┌──────▼───────────┐
│ ready            │ (verified, safe to use in render)
└──────────────────┘

(Alternative: asset-missing if previously present but now deleted)
```

### Asset Storage Structure

```
projects/<project-id>/
├── project.json                 # Master config (scenes, brand, metadata)
├── demos/                       # Playwright-recorded demo videos
│   ├── feature-xyz.mp4
│   └── workflow-abc.mp4
├── assets/
│   ├── images/                  # Generated + sourced images
│   │   ├── character-001.png
│   │   ├── background-001.jpg
│   │   └── logo.svg
│   ├── audio/
│   │   ├── voiceover-001.mp3    # Qwen3-TTS or ElevenLabs
│   │   ├── voiceover-002.mp3
│   │   ├── background-music.mp3 # Generated via music_gen.py
│   │   └── sfx/                 # Sound effects
│   │       └── transition-01.wav
│   └── generated-videos/        # LTX-2, SadTalker outputs
│       ├── talking-head-001.mp4
│       └── animated-scene-001.mp4
├── output/
│   ├── output.mp4               # Final rendered video
│   ├── output.webm              # Alternative format
│   └── thumbnail.jpg            # Generated thumbnail
└── .assets_manifest.json        # Asset registry (optional)
```

### Asset Reconciliation

**When resuming a project:**
1. Claude reads project.json (declared assets)
2. Claude scans filesystem (actual assets)
3. Mismatch detection:
   - Declared but missing → `asset-needed`
   - Present but not declared → Log for review
   - Declared and present → `asset-present` (pending verification)
4. Claude updates project.json status
5. CLAUDE.md auto-generated for manual review

---

## 10. Script-to-Video Flow

### Complete Workflow from Concept to Render

```
1. CONCEPT DEFINITION (Claude Code)
   User: "Create a sprint review for Week 42"
   Template Selection: /video → choose "sprint-review"
   ↓
2. PROJECT INITIALIZATION
   • Create projects/sprint-week42/
   • Write project.json (phase: planning)
   • Assign brand (default or custom)
   • Generate CLAUDE.md for context
   ↓
3. SCRIPT PLANNING
   • Define scene sequence (manual or agent-driven)
   • Write narration/dialogue
   • Identify required assets
   • Update project.json
   ↓
4. ASSET GATHERING
   Phase: assets
   
   For each asset type:
   ├─ Demos: /record-demo (Playwright)
   │  └─ Saves to demos/<name>.mp4
   ├─ Images: /design or /ai-image (Flux/Ideogram)
   │  └─ Saves to assets/images/
   ├─ Audio: /voice-clone or /generate-voiceover (Qwen3/ElevenLabs)
   │  └─ Saves to assets/audio/
   └─ Stock: (manual or /fetch-stock)
      └─ Saves to assets/
   ↓
5. SCENE REVIEW
   Phase: review
   • Preview each scene
   • Check asset status (ready/missing/present)
   • Approve or request revisions
   • Update project.json → phase: audio
   ↓
6. AUDIO SYNC
   Phase: audio
   • Generate voiceover from script
   • tools/audio/sync_timing.py (align to scene timing)
   • Add background music (optional)
   • tools/audio/addmusic.py
   • Update asset references in project.json
   ↓
7. EDITING
   Phase: editing
   • Adjust scene durations
   • Add transitions (fade, cut, dissolve)
   • Composite audio (voiceover + music)
   • Preview in Remotion studio (npm run studio)
   • Approve or iterate
   ↓
8. RENDERING
   Phase: rendering
   • npm run render
   • Remotion compiles React → MP4 (local or Lambda)
   • FFmpeg post-processing (if needed)
   • Save to projects/<id>/output/output.mp4
   ↓
9. PUBLISHING
   Phase: complete
   • /publish
   • Generate thumbnail
   • Upload to YouTube (OAuth)
   • Post to social media (optional)
   • Update project.json → phase: complete
```

### Data Persistence

**Phase Tracking:**
```json
{
  "project_id": "sprint-week42",
  "phase": "rendering",
  "phase_history": [
    { "phase": "planning", "timestamp": "2026-07-10T10:00:00Z", "notes": "" },
    { "phase": "assets", "timestamp": "2026-07-10T10:15:00Z", "notes": "" },
    { "phase": "review", "timestamp": "2026-07-10T11:30:00Z", "notes": "Demo missing" },
    { "phase": "assets", "timestamp": "2026-07-10T11:45:00Z", "notes": "Recorded demo" },
    { "phase": "audio", "timestamp": "2026-07-10T12:00:00Z", "notes": "" },
    { "phase": "editing", "timestamp": "2026-07-10T12:30:00Z", "notes": "" },
    { "phase": "rendering", "timestamp": "2026-07-10T13:00:00Z", "notes": "" }
  ]
}
```

---

## 11. Rendering Architecture

### Render Runtime Selection

**Toolkit supports 3 runtimes:**

| Runtime | Use Case | Input | Output | Cost |
|---------|----------|-------|--------|------|
| **Remotion (React/Lambda)** | Charts, data viz, text overlays | React JSX + props | MP4 (H.264) | $0.05/min |
| **FFmpeg (fallback)** | Video composition, audio mixing | MP4/WebM + audio tracks | MP4/WebM | $0 (local) |
| **Cloud GPU (Modal)** | Advanced video generation | Prompt/image + parameters | MP4 | $0.23 per 5-sec clip |

### Rendering Decision Flow

```
Template type?
├─ "sprint-review" (data viz) → Use Remotion
├─ "product-demo" (screen recording) → Use FFmpeg
├─ "concept-explainer" (talking head) → Use SadTalker (Modal) + FFmpeg
└─ Custom → Agent decides based on scene types
```

### Remotion Rendering Process (Local)

```
1. npm run render
2. Remotion webpack bundles React code
3. Headless Chrome renders each frame sequentially
4. Frame outputs → PNG sequence
5. FFmpeg encodes PNG sequence → MP4
6. Time: ~60 minutes for 30-second video on MacBook Pro
```

### Remotion Rendering Process (Lambda)

```
1. npm run render --lambda
2. Remotion bundles React code
3. Upload to S3 bucket
4. Trigger Lambda function
5. Lambda renders MP4 in parallel (split into chunks)
6. Download final MP4
7. Time: ~5 minutes for 30-second video
```

### Modal Cloud GPU Rendering

Used for:
- **LTX-2** (text-to-video): ~2.5 min per 5-second clip ($0.23)
- **SadTalker** (talking head): ~4 min per 1 min audio ($0.05-0.15)
- **Image upscale:** ~30 sec per image ($0.005-0.02)

**Orchestration:** `tools/cloud_gpu.py` routes to Modal endpoints via HTTP POST.

---

## 12. Production Workflow Patterns

### Pattern 1: Sprint Review Automation

```yaml
Trigger: Weekly at Friday 5pm
├─ Gather sprint data (Jira, GitHub)
├─ Generate script (Claude Code agent)
├─ Run /video sprint-review
│  ├─ Template selection → "sprint-review"
│  ├─ Record demo videos (3-5 features)
│  ├─ Generate voiceover (Qwen3-TTS, $0.01)
│  ├─ Compose (Remotion, local)
│  └─ Render (1-2 hours)
├─ Upload to YouTube (oauth)
├─ Post to Slack: "Sprint review ready!"
└─ Notify team
```

### Pattern 2: Product Demo with Live Recording

```yaml
Trigger: New feature shipped
├─ Record demo (Playwright)
├─ Write narration script
├─ /video product-demo
│  ├─ Template: "product-demo"
│  ├─ Use recorded demo video
│  ├─ Generate voiceover
│  ├─ Add transitions (FFmpeg)
│  └─ Render (15 min)
├─ Generate thumbnail
├─ Schedule YouTube upload (24h)
└─ Social preview post (Slack)
```

### Pattern 3: Vertical Short for TikTok/Shorts

```yaml
Trigger: Content calendar
├─ Generate concept (Claude)
├─ /video concept-explainer
│  ├─ Template: "vertical-short" (9:16 aspect)
│  ├─ Generate visuals (Flux + upscale)
│  ├─ Generate voiceover (0.5-1 min)
│  ├─ Add captions (align_captions.py)
│  ├─ Add music (music_gen.py)
│  └─ Render (local Remotion)
├─ Export 4 versions:
│   ├─ TikTok (9:16, MP4)
│   ├─ Instagram Reels (9:16, MP4)
│   ├─ YouTube Shorts (9:16, MP4)
│   └─ Web preview (16:9, MP4)
└─ Publish to all platforms
```

### Pattern 4: Character Animation (Mr. Yeti)

```yaml
Trigger: Marketing campaign
├─ Write script (Mr. Yeti persona)
├─ /video talking-head
│  ├─ Template: "talking-head" (Mr. Yeti character)
│  ├─ Generate character image (Flux, style-consistent)
│  ├─ Generate narration (ElevenLabs, custom voice)
│  ├─ Apply SadTalker (facial animation, Modal GPU)
│  ├─ Add background animation (ACE-Step or LTX-2)
│  ├─ Composite (FFmpeg)
│  └─ Render (total: 5-10 minutes)
└─ Publish to YouTube
```

### Cost Profile Example: 30-Second Product Demo

| Step | Tool | Cost | Time |
|------|------|------|------|
| Screen recording | Playwright | $0 | 5 min |
| Voiceover generation | Qwen3-TTS | $0.01 | 1 min |
| Background music | Suno (optional) | $0 | — |
| Composition (FFmpeg) | Local | $0 | 5 min |
| Remotion render (local) | Local | $0 | 30 min |
| YouTube upload | OAuth | $0 | 2 min |
| **Total** | | **$0.01** | **43 min** |

---

## 13. Security Model

### Credential Handling

**YouTube OAuth:**
```
1. User runs: python3 tools/youtube_upload.py --auth
2. Browser opens Google consent screen
3. Token saved to: _internal/.youtube/token_default.json (chmod 600)
4. Token never committed (in .gitignore)
5. Refresh token reused for subsequent uploads
6. Multiple accounts via: --account <name> flag
```

**Cloud GPU API Keys:**
- Modal token: `~/.modal/token.pkl` (Modal CLI)
- RunPod API key: `.env` file (python-dotenv)
- Qwen3-TTS key: `.env` file
- ElevenLabs key: `.env` file

**.env File:**
```bash
# Not in git (.gitignore)
MODAL_TOKEN_ID="token-xxx"
MODAL_TOKEN_SECRET="secret-xxx"
ELEVENLABS_API_KEY="sk-xxx"
QWEN_API_KEY="xxx"
GOOGLE_YOUTUBE_CLIENT_SECRET="xxx"
```

### Path Safety

**No user input in paths:**
```python
# ✅ Safe
project_path = Path("projects") / project_id / "assets"
project_path.resolve()  # Normalize absolute path

# ❌ Unsafe (not done)
project_path = f"projects/{user_input}/assets"
```

### File Permissions

- Token files: `chmod 600` (owner only)
- Project directories: OS default (owner-readable)
- No global write access to projects/

### Risks

1. **API Key Logging:** If tools log API responses, credentials may leak
   - **Mitigation:** Avoid logging response bodies; log only status + cost
2. **Command-Line Arguments:** User might pass API key as CLI arg
   - **Mitigation:** Use `.env` instead
3. **Error Messages:** Exceptions may contain credentials
   - **Mitigation:** Scrub sensitive data from error messages

---

## 14. Testing Strategy

### Test Infrastructure

**Not explicitly documented** in fetched materials. Based on structure, likely includes:

- Unit tests for Python tools (voiceover.py, sync_timing.py, etc.)
- Integration tests for Remotion templates
- Mock tests for cloud GPU APIs (Modal, RunPod)
- End-to-end tests for complete workflows

### Manual Testing Approach

Users typically validate via:
1. **Local preview:** `npm run studio` (Remotion browser preview)
2. **Single-scene render:** Test render of one slide before full video
3. **Dry-run YouTube upload:** `--dry-run` flag checks OAuth + config
4. **Cloud GPU testing:** Modal/RunPod free tier for cost-free experimentation

---

## 15. Licensing & Legal

### License Type: MIT

**Permissive open-source license:**
- ✅ Can use commercially
- ✅ Can modify
- ✅ Can distribute
- ❌ No warranty/liability
- ❌ Must include license text

**Implications for SaathiOS:**
- No copyleft obligations
- Can wrap in proprietary adapter
- Can embed as library
- Must preserve copyright notice

---

## 16. Dependencies Summary

### External Services (Paid/Free)

| Service | Tier | Free Limit | Paid | Used For |
|---------|------|-----------|------|----------|
| Modal | Starter | $30/month | $4-5/hour GPU | Cloud GPU compute |
| RunPod | Community | Variable | Pay-as-go | Alternative GPU |
| Qwen3-TTS | API | ~$0/min (low vol) | ~$0.000015/char | Voiceovers |
| ElevenLabs | Subscription | 10K chars/month | $5-99/month | Premium voices |
| Flux.2 (fal.ai) | API | Free tier | $0.03/image | Image generation |
| Ideogram 4 (fal.ai) | API | Free tier | $0.02/image | Image generation |
| LTX-2 (Modal) | Serverless | N/A | $0.23 per clip | Video generation |
| Pexels/Pixabay/Unsplash | Free | Unlimited | N/A | Stock media (free) |
| YouTube | OAuth | Unlimited uploads | N/A | Publishing |

### Project Dependencies (as of Jun 2026)

- Remotion: Active (latest v4.x)
- FFmpeg: Stable
- Modal: Active (Python SDK maintained)
- ElevenLabs: Active (API stable)
- Google APIs: Stable (YouTube Data v3)

---

## 17. Extensibility & Customization

### Template Extension Points

1. **Custom Slide Component:**
```typescript
export const CustomSlide: React.FC<{ data: any }> = ({ data }) => {
  return <div>{data.content}</div>;
};
```

2. **Brand Extension:**
Create `brands/my-brand/brand.ts` with custom theme.

3. **Python Tool Extension:**
Inherit from base CLI pattern (click + dotenv).

### Known Limitations

1. **No approval gates:** Unlike OpenMontage, no human-in-the-loop checkpoint system
2. **Linear workflow only:** No branching/experimentation loops
3. **Single-machine:** No multi-user workspace isolation
4. **Simple cost tracking:** No budget reserve/reconcile lifecycle

---

## End of Discovery Report

**Next Steps:**
- Compare with OpenMontage in detail (gap analysis)
- Create capability matrix
- Design adapter pattern for SaathiOS integration

