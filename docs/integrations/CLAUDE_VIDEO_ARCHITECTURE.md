# Claude Code Video Toolkit: Technical Architecture Deep Dive

**Date:** 2026-07-10  
**Scope:** System design, data models, pipeline mechanics, rendering choices, extensibility

---

## 1. System Architecture

### Layer Diagram

```
┌──────────────────────────────────────────────────────────┐
│             USER INTERFACE LAYER                         │
│  • Claude Code Skills (.claude/agents/)                  │
│  • CLI Commands: /video, /template, /design, etc.        │
│  • Browser preview (Remotion studio)                     │
└────────────────────┬─────────────────────────────────────┘
                     │
┌────────────────────▼─────────────────────────────────────┐
│           ORCHESTRATION LAYER                            │
│  • Project state machine (lib/project/Project.ts)        │
│  • Phase management (7-phase lifecycle)                  │
│  • Asset tracking & reconciliation                       │
│  • CLAUDE.md auto-generation (context resumption)        │
└────────────────────┬─────────────────────────────────────┘
                     │
┌────────────────────▼─────────────────────────────────────┐
│            TEMPLATE LAYER (React/Remotion)               │
│  • Template registry (_internal/toolkit-registry.json)   │
│  • Configuration schemas (src/config/types.ts)           │
│  • Slide components (src/components/)                    │
│  • Theme system (lib/theme/)                             │
│  • Branding (brands/<name>/)                             │
└────────────────────┬─────────────────────────────────────┘
                     │
┌────────────────────▼─────────────────────────────────────┐
│        TOOLS LAYER (Python CLI + Cloud Orchestration)    │
│  • Audio tools (voiceover, sync, music)                  │
│  • Image tools (generation, editing, upscaling)          │
│  • Video tools (composition, timing, captions)           │
│  • Rendering (Remotion, FFmpeg, cloud GPU)               │
│  • Publishing (YouTube upload)                           │
│  • Cloud GPU orchestration (Modal, RunPod)               │
└────────────────────┬─────────────────────────────────────┘
                     │
┌────────────────────▼─────────────────────────────────────┐
│           PROVIDER LAYER (External APIs)                 │
│  • Model APIs: Qwen3-TTS, ElevenLabs, Flux, Ideogram     │
│  • Cloud Compute: Modal, RunPod                          │
│  • Stock Media: Pexels, Pixabay, Unsplash                │
│  • Publishing: YouTube OAuth                             │
└──────────────────────────────────────────────────────────┘
```

### Design Principles

1. **Skill-Driven:** Claude Code skills orchestrate workflows
2. **State-Persistent:** project.json is source of truth
3. **Asset-Centric:** Filesystem holds intermediate outputs
4. **Tool-Based:** Python CLI for every media operation
5. **Template-Driven:** React/Remotion for flexible composition
6. **Cost-Optimized:** Uses free/cheap providers by default
7. **Credential-Isolated:** .env for secrets, oauth for publishing

---

## 2. Data Models

### Project Data Model

**File:** `projects/<project-id>/project.json`

```json
{
  "id": "sprint-week42",
  "name": "Sprint Review Week 42",
  "template": "sprint-review",
  "brand": "default",
  "created_at": "2026-07-10T10:00:00Z",
  "updated_at": "2026-07-10T13:45:00Z",
  "phase": "rendering",
  "phases_completed": ["planning", "assets", "review", "audio", "editing"],
  
  "config": {
    "resolution": "1080p",
    "fps": 30,
    "codec": "h264",
    "aspect_ratio": "16:9"
  },
  
  "sections": [
    {
      "id": "section-001",
      "name": "Title",
      "type": "title-slide",
      "title": "Sprint Review",
      "subtitle": "Week 42, Jul 1-7",
      "duration_seconds": 5,
      "status": "ready",
      "assets": []
    },
    {
      "id": "section-002",
      "name": "Feature Demo",
      "type": "demo",
      "title": "New Dashboard Features",
      "description": "Live demo of dashboard redesign",
      "duration_seconds": 30,
      "status": "asset-present",
      "assets": [
        {
          "type": "demo-video",
          "file": "demos/dashboard-redesign.mp4",
          "status": "present",
          "source": "playwright",
          "recorded_at": "2026-07-10T10:15:00Z"
        }
      ],
      "audio": {
        "voiceover": "assets/audio/voiceover-demo.mp3",
        "source": "qwen3-tts",
        "speaker_id": "default",
        "cost_usd": 0.01
      }
    },
    {
      "id": "section-003",
      "name": "Talking Head",
      "type": "talking-head",
      "character": "yeti-mascot",
      "duration_seconds": 45,
      "status": "ready",
      "assets": [
        {
          "type": "character-image",
          "file": "assets/images/yeti-001.png",
          "status": "ready",
          "source": "flux2",
          "cost_usd": 0.03
        },
        {
          "type": "background-image",
          "file": "assets/images/bg-mountain.jpg",
          "status": "ready",
          "source": "pexels"
        }
      ],
      "audio": {
        "voiceover": "assets/audio/yeti-narration.mp3",
        "source": "elevenlabs",
        "speaker_id": "custom-yeti-voice",
        "cost_usd": 0.05
      },
      "animation": {
        "type": "sadtalker",
        "model_file": "sadtalker-v0.2.0",
        "expression_scale": 1.0,
        "cost_usd": 0.10
      }
    }
  ],
  
  "audio": {
    "voiceovers": [
      { "id": "vo-001", "text": "...", "file": "assets/audio/vo-001.mp3", "cost_usd": 0.01 },
      { "id": "vo-002", "text": "...", "file": "assets/audio/vo-002.mp3", "cost_usd": 0.01 }
    ],
    "background_music": "assets/audio/bg-music.mp3",
    "music_cost_usd": 0.0
  },
  
  "render": {
    "status": "in-progress",
    "runtime": "remotion-local",
    "output_file": "output/output.mp4",
    "duration_seconds": 90,
    "resolution": "1920x1080",
    "fps": 30,
    "codec": "h264",
    "file_size_mb": 125,
    "render_start_time": "2026-07-10T13:00:00Z",
    "estimated_finish_time": "2026-07-10T14:00:00Z"
  },
  
  "publish": {
    "status": "pending",
    "platforms": ["youtube"],
    "youtube": {
      "title": "Sprint Review Week 42",
      "description": "...",
      "tags": ["sprint", "weekly", "demo"],
      "visibility": "private",
      "scheduled_publish_time": "2026-07-11T17:00:00Z"
    }
  },
  
  "cost": {
    "total_estimated": 0.20,
    "total_actual": 0.18,
    "breakdown": {
      "voiceovers": 0.07,
      "image_generation": 0.03,
      "video_generation": 0.00,
      "cloud_gpu": 0.08,
      "rendering": 0.00
    }
  },
  
  "metadata": {
    "created_by": "claude-code",
    "last_modified_by": "claude",
    "session_count": 3,
    "last_session": "2026-07-10T13:00:00Z"
  }
}
```

### Scene Data Model

**Embedded in project.json sections array:**

```typescript
interface Scene {
  id: string;
  name: string;
  type: "title-slide" | "demo" | "talking-head" | "chart" | "text-overlay" | "custom";
  duration_seconds: number;
  status: "ready" | "asset-needed" | "asset-present" | "asset-missing";
  
  // Title slide specific
  title?: string;
  subtitle?: string;
  
  // Demo video specific
  demo_file?: string;
  narration?: string;
  
  // Talking head specific
  character?: string;
  background_image?: string;
  animation_type?: "sadtalker" | "lipsync" | "static";
  
  // Asset references
  assets: Asset[];
  
  // Audio configuration
  audio?: {
    voiceover: string;           // Path to audio file
    source: "qwen3-tts" | "elevenlabs" | "manual";
    cost_usd: number;
  };
}

interface Asset {
  id: string;
  type: "image" | "video" | "audio" | "font" | "effect";
  file: string;                  // Relative path
  source: "generated" | "sourced" | "recorded" | "manual";
  source_tool?: string;           // "flux2", "elevenlabs", "playwright", etc.
  status: "present" | "missing" | "pending";
  cost_usd?: number;
  metadata?: Record<string, any>;
}
```

### Template Registry

**File:** `_internal/toolkit-registry.json`

```json
{
  "version": "0.17.0",
  "templates": [
    {
      "id": "sprint-review",
      "name": "Sprint Review",
      "description": "Weekly sprint review with demo section",
      "category": "demo",
      "path": "templates/sprint-review",
      "entry_point": "src/Root.tsx",
      "config_schema": "src/config/types.ts",
      "version": "1.0.0",
      "stability": "stable",
      "created_at": "2026-06-01T00:00:00Z",
      "last_updated": "2026-07-01T12:00:00Z",
      "maintainer": "digitalsamba",
      "min_node_version": "18.0.0",
      "dependencies": ["remotion>=4.0", "react>=18.0"],
      "example_project": "examples/sprint-review-demo",
      "default_config": {
        "resolution": "1080p",
        "fps": 30,
        "duration_seconds": 120
      }
    },
    {
      "id": "product-demo",
      "name": "Product Demo",
      "description": "Product feature showcase with screen recording",
      "category": "demo",
      "path": "templates/product-demo",
      "version": "1.1.0",
      "stability": "stable"
    },
    {
      "id": "concept-explainer",
      "name": "Concept Explainer",
      "description": "Vertical short for TikTok/Shorts",
      "category": "short",
      "path": "templates/concept-explainer",
      "version": "1.0.0",
      "stability": "beta"
    }
  ]
}
```

### Brand Configuration Model

**File:** `brands/<brand-name>/brand.ts`

```typescript
export const BrandTheme = {
  colors: {
    primary: "#007AFF",
    secondary: "#5AC8FA",
    accent: "#FF3B30",
    background: "#FFFFFF",
    text: "#000000",
    text_secondary: "#666666"
  },
  
  fonts: {
    heading: {
      family: "Inter",
      weight: 700,
      size_px: 48
    },
    body: {
      family: "Inter",
      weight: 400,
      size_px: 16
    },
    code: {
      family: "Courier New",
      weight: 400,
      size_px: 14
    }
  },
  
  spacing: {
    xs: 4,
    sm: 8,
    md: 16,
    lg: 32,
    xl: 64
  },
  
  assets: {
    logo: "assets/logo.svg",
    favicon: "assets/favicon.ico",
    fonts_dir: "assets/fonts/"
  },
  
  animation: {
    transition_duration_ms: 300,
    ease: "cubic-bezier(0.4, 0.0, 0.2, 1)"
  }
};
```

---

## 3. Video Generation Pipeline

### High-Level Pipeline State Machine

```
IDLE
  │
  └─→ INITIALIZE (project.json created, phase=planning)
       │
       ├─→ ASSET_GATHERING (phase=assets)
       │   │  Videos recorded/sourced
       │   │  Images generated/sourced
       │   │  Audio generated/sourced
       │   │  Status: asset-present or ready
       │   │
       │   └─→ REVIEW (phase=review, human validates)
       │        │
       │        ├─ ✅ APPROVED → proceed
       │        └─ ❌ REJECTED → return to ASSET_GATHERING
       │
       ├─→ AUDIO_SYNC (phase=audio)
       │   │  Voiceover generated/adjusted
       │   │  Timing synchronized
       │   │  Background music added
       │   │  Status: all audio assets ready
       │   │
       │   └─→ EDITING (phase=editing)
       │        │  Pacing finalized
       │        │  Transitions defined
       │        │  Audio composite confirmed
       │        │  Preview via Remotion studio
       │        │
       │        └─→ RENDERING (phase=rendering)
       │             │  Remotion compiles React → MP4
       │             │  FFmpeg post-processes (optional)
       │             │  Final video written to output/
       │             │
       │             └─→ PUBLISHING (phase=complete)
       │                  │  YouTube upload (OAuth)
       │                  │  Social media posting
       │                  │  Project marked complete
       │                  │
       │                  └─→ DONE
```

### Phase Details

| Phase | Duration | Activities | State Persistence |
|-------|----------|------------|-------------------|
| **planning** | 5-10 min | Define scenes, script | project.json.sections |
| **assets** | 15-30 min | Generate/record/source assets | project.json.sections[].assets |
| **review** | 5-15 min | Preview, verify completeness | project.json.phase, status updates |
| **audio** | 5-10 min | Voiceover + sync | project.json.audio |
| **editing** | 10-20 min | Adjust timing, transitions | project.json.sections[].duration_seconds |
| **rendering** | 30-120 min | Compile video | project.json.render |
| **publishing** | 5-10 min | Upload, schedule | project.json.publish |

### Asset Reconciliation

**On project resume:**

```python
# Pseudocode: lib/project/reconcile_assets.ts
function reconcileAssets(project: Project): Project {
  for (const section of project.sections) {
    for (const asset of section.assets) {
      if (fileExists(asset.file)) {
        asset.status = "present";
      } else if (asset.status === "present") {
        asset.status = "missing";  // Previously present, now gone
        WARN(`Asset ${asset.file} missing`);
      }
    }
  }
  
  // Update phase based on completeness
  const allReady = project.sections.every(s => s.status === "ready");
  if (allReady && project.phase === "assets") {
    project.phase = "audio";
  }
  
  return project;
}
```

---

## 4. Rendering Runtime Choices

### Remotion (React-to-MP4)

**When to Use:**
- Data visualizations (charts, graphs, statistics)
- Text-heavy slides (titles, callouts, code snippets)
- Smooth animations (interpolate-based)
- Professional/corporate aesthetics

**Architecture:**
```
React JSX (TypeScript)
    ↓
Remotion webpack bundle
    ↓
Headless Chrome (local) OR AWS Lambda (remote)
    ↓
Frame sequence (PNG or WebM chunks)
    ↓
FFmpeg (H.264 encoding)
    ↓
MP4 output (1920×1080 @ 30fps)
```

**Performance:**
- Local render: ~60 minutes per 30-second video
- Lambda render: ~5 minutes per 30-second video
- Cost: $0 (local) or $0.05/minute (Lambda)

**Configuration in Template:**
```typescript
// Root.tsx
export const Root = () => (
  <Composition
    id="sprint-review"
    component={SprintReview}
    durationInFrames={900}         // 30 seconds @ 30fps
    fps={30}
    width={1920}
    height={1080}
    defaultProps={defaultConfig}
  />
);
```

### FFmpeg (Video Composition)

**When to Use:**
- Concatenating multiple video clips
- Adding audio to silent video
- Adjusting video speed/timing
- Burning captions onto video
- Format conversion (MP4 ↔ WebM)

**Operations:**
- `concat()` — join videos with optional transition
- `xfade` filter — fade between clips
- `overlay` filter — picture-in-picture
- `speed` filter — slow-motion or speed-up
- `drawtext` — burn subtitles

**Example (via MoviePy):**
```python
from moviepy.editor import *

# Chain videos with fade transition
clips = [VideoFileClip(f) for f in video_files]
video = concatenate_videoclips(clips)

# Add audio
audio = AudioFileClip("voiceover.mp3")
video = video.set_audio(audio)

# Speed adjustment
video = video.speedx(1.2)

# Export
video.write_videofile("output.mp4", codec="libx264", audio_codec="aac")
```

**Performance:**
- Depends on video resolution + number of clips
- Typical: 5-15 minutes for 30-second composite

### Cloud GPU (Modal/RunPod)

**When to Use:**
- SadTalker (talking head animation) ~$0.05-0.15 per 1-minute output
- LTX-2 (text-to-video) ~$0.23 per 5-second clip
- Image upscaling ~$0.01-0.05 per image

**Routing Logic (tools/cloud_gpu.py):**
```python
def execute_on_cloud_gpu(operation: str, params: dict) -> dict:
    provider = os.getenv("CLOUD_GPU_PROVIDER", "modal")  # or "runpod"
    
    if provider == "modal":
        return call_modal_endpoint(operation, params)
    elif provider == "runpod":
        return call_runpod_endpoint(operation, params)
```

**Cold Start Behavior:**
- First call: 60-90 seconds (load model weights)
- Subsequent calls: 5-30 seconds
- Idle timeout: 60 seconds (scale-to-zero)

---

## 5. Extensibility Points

### Custom Slide Components

**Create in template:**
```typescript
// templates/sprint-review/src/components/CustomSlide.tsx
import React from "react";
import { useTheme } from "../theme";

export const CustomSlide: React.FC<{ title: string; content: string }> = ({
  title,
  content
}) => {
  const theme = useTheme();
  
  return (
    <div style={{ backgroundColor: theme.colors.background }}>
      <h1 style={{ color: theme.colors.primary }}>{title}</h1>
      <p>{content}</p>
    </div>
  );
};
```

**Register in Root.tsx:**
```typescript
// Add condition to render component
if (section.type === "custom") {
  return <CustomSlide title={section.title} content={section.content} />;
}
```

### Custom Python Tools

**Create Python CLI tool:**
```python
# tools/custom/my_tool.py
import click
import dotenv
import requests

dotenv.load_dotenv()

@click.command()
@click.option("--input", required=True)
def my_tool(input: str):
    """Custom video processing tool."""
    result = requests.post("https://api.example.com/process", json={"data": input})
    print(f"Result: {result.json()}")

if __name__ == "__main__":
    my_tool()
```

### Custom Brand Profiles

**Create in brands/ directory:**
```typescript
// brands/my-brand/brand.ts
export const BrandTheme = {
  colors: {
    primary: "#FF6B35",        // Custom orange
    secondary: "#004E89",      // Custom blue
    accent: "#F7B801",         // Custom gold
    background: "#FFFFFF",
    text: "#1A1A1A"
  },
  fonts: {
    heading: { family: "Playfair Display", weight: 700, size_px: 48 },
    body: { family: "Lato", weight: 400, size_px: 16 }
  }
};
```

### Template Extension

**Create new template:**
```bash
templates/
├── my-custom-template/
│   ├── src/
│   │   ├── Root.tsx           # Entry component
│   │   ├── config/types.ts    # Configuration schema
│   │   └── components/        # Slide types
│   ├── public/                # Static assets
│   └── package.json           # Dependencies
```

---

## 6. Credential Handling Architecture

### YouTube OAuth Flow

```
1. USER INITIATES AUTH
   $ python3 tools/youtube_upload.py --auth
   
2. BROWSER OPENS
   → Google consent screen
   → User logs in
   → Grants permission
   
3. AUTHORIZATION CODE RETURNED
   → tools/youtube_upload.py captures code
   → Exchanges code for access + refresh tokens
   
4. TOKEN STORAGE
   → Saved to: _internal/.youtube/token_<account>.json
   → Permissions: chmod 600 (owner-only readable)
   → Never committed to git (.gitignore)
   
5. SUBSEQUENT UPLOADS
   → tools/youtube_upload.py reads cached token
   → Uses refresh token if access token expired
   → No browser interaction required
```

### Environment Variable Loading

```python
# lib/config.py (pseudocode)
import dotenv
import os

dotenv.load_dotenv()  # Loads .env file

class Config:
    MODAL_TOKEN = os.getenv("MODAL_TOKEN_ID")
    ELEVENLABS_KEY = os.getenv("ELEVENLABS_API_KEY")
    QWEN_KEY = os.getenv("QWEN_API_KEY")
    # ... etc
```

**.env File (Not in Git):**
```
# Modal
MODAL_TOKEN_ID="token-xxx"
MODAL_TOKEN_SECRET="secret-xxx"

# ElevenLabs
ELEVENLABS_API_KEY="sk-xxx"

# Qwen3-TTS
QWEN_API_KEY="xxx"

# Google (YouTube)
GOOGLE_YOUTUBE_CLIENT_ID="xxx.apps.googleusercontent.com"
GOOGLE_YOUTUBE_CLIENT_SECRET="xxx"

# Cloud Storage (Cloudflare R2)
R2_ACCOUNT_ID="xxx"
R2_ACCESS_KEY="xxx"
R2_SECRET_KEY="xxx"
R2_BUCKET="video-toolkit-storage"
```

### Token File Security

**YAML representation:**
```yaml
_internal/
├── .youtube/
│   ├── token_default.json     # chmod 600
│   ├── token_dev.json         # chmod 600
│   └── token_prod.json        # chmod 600
├── .modal/
│   └── config.yaml            # Modal CLI manages
└── .gitignore
   _internal/.youtube/
   _internal/.modal/
   .env
```

---

## 7. Error Recovery & Resilience

### Failure Modes & Recovery

| Failure | Cause | Recovery |
|---------|-------|----------|
| **Network timeout (API call)** | Transient network issue | Retry 3x with exponential backoff |
| **Quota exceeded (TTS/image gen)** | Too many API calls | Pause, wait, retry |
| **Cloud GPU cold start** | Model loading | Wait 60-90s, retry |
| **Asset file missing** | Filesystem corruption | Marked asset-missing, notify user |
| **YouTube auth expired** | Refresh token stale | Re-authenticate via --auth |
| **Render failure (Remotion)** | Webpack error | Return error, user fixes template |

### Retry Logic

```python
# tools/util/retry.py (pseudocode)
def retry_with_backoff(func, max_retries=3, base_delay=1):
    for attempt in range(max_retries):
        try:
            return func()
        except NetworkError as e:
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                print(f"Retry in {delay}s...")
                time.sleep(delay)
            else:
                raise
```

### State Preservation on Failure

**If rendering fails:**
1. Checkpoint phase remains unchanged
2. user resumes via `/video` (same project)
3. Toolkit detects phase, offers retry
4. Optionally modify config and retry

---

## 8. Performance Characteristics

### Bottlenecks

| Operation | Time | Bottleneck | Optimization |
|-----------|------|-----------|--------------|
| Remotion render (local) | 60 min / 30 sec | CPU (webpack + Chrome) | Use Lambda ($) or split scenes |
| SadTalker animation | 4 min / 1 min audio | GPU (Modal cold start) | Batch renders, warm GPU |
| Image generation (Flux) | 5-10 sec | API call | Batch images |
| Voiceover generation | 1-2 sec | API call | Pre-cache common phrases |
| FFmpeg composition | 5-15 min | I/O + encoding | Use local SSD |

### Latency Optimizations

1. **Parallel Asset Generation:**
   - Generate multiple images concurrently (thread pool)
   - Generate multiple voiceovers concurrently

2. **Caching:**
   - Brand theme cache (in memory)
   - Font files (downloaded once, reused)
   - Clip cache (MoviePy caches by URL hash)

3. **Lazy Loading:**
   - Templates only load on first use
   - Cloud GPU models only load on first call

---

## 9. Storage & File Organization

### Disk Usage Estimate (30-Second Video)

| Asset | Size |
|-------|------|
| Remotion React bundle | ~5 MB |
| Chrome caches (webpack) | ~50 MB |
| Temporary PNG frames | ~200 MB (1920×1080 @ 900 frames) |
| Final MP4 output | ~100-150 MB (H.264, high quality) |
| Voiceover audio (30 sec) | ~200 KB |
| Background music (30 sec) | ~2 MB |
| Generated images (5 images) | ~10 MB |
| **Total per project** | ~400 MB |

### Cleanup Strategy

**Temporary files:**
- PNG frame sequences → deleted after FFmpeg encodes
- Webpack cache → safe to delete (rebuilds automatically)

**Persistent files:**
- project.json → never delete
- Assets (images, audio, video) → keep unless manually removed
- Output MP4 → archive after publish

---

## 10. Multi-Project Workflow

### Project Isolation

**Separate directory per project:**
```
projects/
├── sprint-week42/          # Project 1
│   ├── project.json
│   ├── assets/
│   └── output/
├── product-demo-xyz/       # Project 2
│   ├── project.json
│   ├── assets/
│   └── output/
└── vertical-short-001/     # Project 3
    ├── project.json
    ├── assets/
    └── output/
```

**No cross-project leakage:**
- Each project has independent state
- Assets are project-local
- No shared mutable state between projects

**Multi-Session Support:**
```
Session 1 (Mon 10am):
  $ /video sprint-week42
  → Create project
  → Record demos
  → Generate images
  → Save project.json, phase=assets
  → Exit
  
Session 2 (Mon 2pm):
  $ /video sprint-week42
  → Read existing project.json
  → Reconcile assets (what's present on disk)
  → Offer resume options
  → Proceed to next phase (audio)
  → Exit
```

---

## End of Architecture Document

