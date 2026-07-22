# Video Domain Model for SaathiOS ↔ OpenMontage

**Date:** 2026-07-10  
**Scope:** SaathiOS models for video projects, rendering, and asset management  

---

## SaathiOS Video Domain Model

```
Mission (SaathiOS)
├─→ VideoProject (SaathiOS)
│   ├─→ OpenMontage project_id (link)
│   ├─→ SceneList (ordered scenes)
│   │   ├─→ Scene 1 (dialogue, action, intent)
│   │   ├─→ Scene 2
│   │   └─→ Scene N
│   ├─→ CharacterBranding (playbook)
│   │   ├─→ Colors, tone, style
│   │   └─→ Asset library (backgrounds, props)
│   ├─→ RenderCheckpoints (read from OpenMontage)
│   │   ├─→ character_design.json
│   │   ├─→ rig_plan.json
│   │   ├─→ scene_plan.json
│   │   ├─→ render_report.json
│   │   └─→ publish_log.json
│   ├─→ VideoAsset (final output)
│   │   ├─→ file_path (video MP4)
│   │   ├─→ duration_seconds
│   │   ├─→ resolution (1920x1080)
│   │   ├─→ fps (30)
│   │   ├─→ codec (h264)
│   │   ├─→ size_mb
│   │   ├─→ md5_hash (determinism verification)
│   │   ├─→ render_cost_usd
│   │   └─→ render_timestamp
│   └─→ PublishRecord (where it went live)
│       ├─→ platforms (YouTube, Telegram)
│       ├─→ urls (YouTube video, Telegram message)
│       ├─→ publish_timestamp
│       └─→ performance_metrics (views, likes)
```

---

## Model Definitions

### VideoProject

```python
class VideoProject(Base):
    """Represents one video production in SaathiOS"""
    
    id: str = Field(default_factory=uuid4)
    mission_id: str  # FK to Mission
    
    # OpenMontage linkage
    openmontage_project_id: str  # projects/<id> in OpenMontage
    openmontage_service_url: str = "http://localhost:8000"
    
    # Content
    title: str
    description: str
    scenes: List[Scene]
    character_branding: CharacterBranding
    
    # Status
    status: Literal["planning", "in_progress", "completed", "published", "archived"]
    current_stage: Optional[str]  # e.g., "character_design", "compose"
    
    # Approval tracking
    approvals: Dict[str, ApprovalRecord]  # stage → decision + feedback
    
    # Rendered output
    video_asset: Optional[VideoAsset] = None
    publish_records: List[PublishRecord] = []
    
    # Metadata
    created_at: datetime
    updated_at: datetime
    created_by: str  # actor_id
    metadata: Dict = {}
```

### Scene

```python
class Scene(Base):
    """One scene within a video project"""
    
    id: str
    sequence: int  # Order in video
    
    # Content
    script_text: str  # Dialogue, narration
    action_description: str  # What characters do
    duration_estimate_seconds: float
    
    # Intent (why this scene exists)
    narrative_role: Literal["setup", "tension", "climax", "resolution"]
    character_focus: str  # "Mr. Yeti", etc.
    
    # OpenMontage data (read from checkpoint)
    scene_plan_artifact: Optional[Dict] = None  # From scene_plan.json
    
    metadata: Dict = {}
```

### CharacterBranding

```python
class CharacterBranding(Base):
    """Brand specs for character-animation playbook"""
    
    character_name: str  # "Mr. Yeti"
    
    # Visual style
    colors: Dict[str, str] = {
        "primary": "#6C3FCF",
        "accent": "#00BFA5",
        "background": "#1a1a2e"
    }
    character_description: str
    personality_traits: List[str] = ["friendly", "educational", "enthusiastic"]
    emotional_range: List[str] = ["happy", "encouraging", "thoughtful"]
    
    # Brand consistency
    tone: Literal["professional", "casual", "playful", "educational"]
    style: Literal["minimalist", "bold", "illustrative", "realistic"]
    
    # OpenMontage playbook (custom)
    playbook_data: Dict = {}  # Converted to custom playbook for OpenMontage
    
    # Asset library (reusable across videos)
    background_images: List[str] = []  # File paths or URLs
    music_tracks: List[str] = []
    sound_effects: List[str] = []
    logo_file: Optional[str] = None
```

### VideoAsset

```python
class VideoAsset(Base):
    """Final rendered video file"""
    
    project_id: str  # FK to VideoProject
    
    # File info
    file_path: str  # /assets/videos/proj-xyz.mp4
    file_size_mb: float
    md5_hash: str  # For determinism verification
    
    # Technical specs
    duration_seconds: float
    resolution: str  # "1920x1080"
    fps: int  # 30
    codec: str  # "h264"
    bitrate_kbps: int  # Calculated from file size + duration
    
    # Render info
    render_runtime: Literal["remotion", "hyperframes", "ffmpeg"]
    render_timestamp: datetime
    render_time_seconds: float
    
    # Cost
    render_cost_usd: float  # From OpenMontage render_report
    
    # Quality assurance
    qc_passed: bool
    qc_notes: Optional[str]
    determinism_hash: Optional[str]  # Same input → same hash
```

### PublishRecord

```python
class PublishRecord(Base):
    """Where video was published"""
    
    video_asset_id: str  # FK to VideoAsset
    
    # Destination
    platform: Literal["YouTube", "Telegram", "TikTok", "Instagram", "Twitter"]
    platform_url: str  # Full video URL
    platform_id: str  # Video ID on platform (e.g., YouTube video_id)
    
    # Metadata on platform
    title: str
    description: str
    thumbnail_url: Optional[str]
    
    # Performance
    publish_timestamp: datetime
    view_count: int = 0  # Updated periodically
    like_count: int = 0
    comment_count: int = 0
    
    # SaathiOS automation
    automated_via: Optional[str]  # "n8n_workflow", "baadar_agent", "manual"
    schedule_time: Optional[datetime]
```

### ApprovalRecord

```python
class ApprovalRecord(Base):
    """Human approval decision for a stage"""
    
    stage: str  # "character_design", "scene_plan", etc.
    decision: Literal["approved", "rejected", "send_back"]
    
    approved_by: str  # actor_id
    approved_at: datetime
    
    feedback: Optional[str]  # Human comments, suggestions
    
    # If send_back, track revisions
    revision_number: int = 1
    max_revisions: int = 3
    
    checkpoint_artifact: Dict = {}  # The artifact being approved
```

---

## Relationships

### VideoProject ↔ Mission

```python
# In Mission model (SaathiOS)
class Mission:
    video_projects: List[VideoProject] = []  # One mission can spawn multiple videos
```

### VideoProject ↔ OpenMontage Project

```
SaathiOS VideoProject
├─→ mission_id: "mission-123"
├─→ openmontage_project_id: "proj-abc789"  # Link to OpenMontage
└─→ status: "in_progress"

OpenMontage Project (projects/proj-abc789/)
├─→ project.json
├─→ checkpoints/
│   ├─→ script.json
│   ├─→ character_design.json
│   └─→ render_report.json
└─→ cost_log.json
```

### VideoAsset ↔ PublishRecord

```
VideoAsset (rendered MP4)
├─→ file_path: /assets/videos/proj-xyz.mp4
├─→ publish_records: [
│   {platform: "YouTube", url: "https://youtube.com/watch?v=..."},
│   {platform: "Telegram", url: "https://t.me/..."}
│ ]
```

---

## API Contracts

### Create VideoProject

```python
POST /api/v1/missions/{mission_id}/video-projects
{
  "title": "Mr. Yeti Intro Episode",
  "description": "Weekly welcome video",
  "scenes": [
    {
      "sequence": 1,
      "script_text": "Hello! Welcome to PIELTS...",
      "action_description": "Mr. Yeti waves at camera",
      "duration_estimate_seconds": 15,
      "narrative_role": "setup"
    }
  ],
  "character_branding": {
    "character_name": "Mr. Yeti",
    "tone": "educational",
    "style": "friendly"
  }
}
→ 201 VideoProject (with openmontage_project_id populated)
```

### Invoke Pipeline

```python
POST /api/v1/video-projects/{project_id}/invoke-pipeline
{}
→ 202 {
  "openmontage_project_id": "proj-xyz",
  "status": "in_progress",
  "current_stage": "research"
}
```

### Read Checkpoint

```python
GET /api/v1/video-projects/{project_id}/checkpoints/{stage}
→ 200 {artifact}  # character_design.json, scene_plan.json, etc.
```

### Approve Stage

```python
POST /api/v1/video-projects/{project_id}/approve
{
  "stage": "character_design",
  "decision": "approved",
  "feedback": "Great! Matches brand perfectly"
}
→ 200 ApprovalRecord
```

### Get Final Video

```python
GET /api/v1/video-projects/{project_id}/video-asset
→ 200 VideoAsset {
  "file_path": "/assets/videos/proj-xyz.mp4",
  "duration_seconds": 45.0,
  "resolution": "1920x1080",
  "md5_hash": "a1b2c3d4...",
  "render_cost_usd": 1.85
}
```

### Publish Video

```python
POST /api/v1/video-assets/{asset_id}/publish
{
  "platform": "YouTube",
  "title": "PIELTS Weekly: Band Score 9",
  "description": "Learn the secrets to achieving Band 9...",
  "schedule_time": "2026-07-11T08:00:00Z"
}
→ 202 PublishRecord {
  "platform": "YouTube",
  "platform_id": "dQw4w9WgXcQ",
  "platform_url": "https://youtube.com/watch?v=dQw4w9WgXcQ"
}
```

---

## Storage

### Database Tables

```sql
CREATE TABLE video_projects (
  id UUID PRIMARY KEY,
  mission_id UUID NOT NULL,
  openmontage_project_id VARCHAR NOT NULL,
  title VARCHAR NOT NULL,
  status VARCHAR NOT NULL,
  created_at TIMESTAMP,
  updated_at TIMESTAMP,
  created_by VARCHAR
);

CREATE TABLE scenes (
  id UUID PRIMARY KEY,
  project_id UUID NOT NULL REFERENCES video_projects,
  sequence INT NOT NULL,
  script_text TEXT,
  action_description TEXT,
  narrative_role VARCHAR
);

CREATE TABLE video_assets (
  id UUID PRIMARY KEY,
  project_id UUID NOT NULL REFERENCES video_projects,
  file_path VARCHAR NOT NULL,
  md5_hash VARCHAR NOT NULL,
  duration_seconds FLOAT,
  render_cost_usd DECIMAL,
  created_at TIMESTAMP
);

CREATE TABLE publish_records (
  id UUID PRIMARY KEY,
  asset_id UUID NOT NULL REFERENCES video_assets,
  platform VARCHAR NOT NULL,
  platform_url VARCHAR NOT NULL,
  published_at TIMESTAMP
);
```

### File Storage

```
/assets/
├── videos/
│   ├── proj-abc789.mp4 (rendered video)
│   └── proj-def456.mp4
├── playbooks/
│   ├── mr-yeti-brand.json
│   └── ...
└── backgrounds/
    ├── space-bg.png
    └── ...
```

---

## Workflow Integration

```
1. SaathiOS User → Baadar agent
   "Generate intro video for PIELTS weekly"

2. Baadar Agent
   → Creates Mission ("Weekly PIELTS Intro")
   → Creates VideoProject (title, scenes, branding)
   → Invokes OpenMontage pipeline

3. SaathiOS ExecutionGateway
   → POST to OpenMontage service
   → Stores openmontage_project_id in VideoProject

4. OpenMontage Pipeline (10 stages)
   → Each stage writes checkpoint
   → Human approves key stages (character_design, scene_plan, publish)
   → SaathiOS polls for checkpoints

5. Final Render
   → OpenMontage renders video, writes render_report.json
   → SaathiOS creates VideoAsset (stores file path, md5_hash, cost)

6. Publish
   → SaathiOS publishes to YouTube via platform API
   → Creates PublishRecord (tracking URL, performance metrics)
   → n8n distributes to Telegram, TikTok, Instagram

7. Analytics
   → Performance metrics updated periodically (views, likes)
   → Finance layer charged for render_cost_usd
   → Archive after 30 days (if desired)
```

---

## Determinism Verification

For character animation, same input should produce identical video (byte-for-byte).

```python
# Stage 2: Add determinism test
def test_determinism():
    # Run pipeline twice with same input
    result1 = render_character_animation(input_data)
    result2 = render_character_animation(input_data)
    
    # Verify same MD5 hash
    assert result1.md5_hash == result2.md5_hash
    assert result1.duration_seconds == result2.duration_seconds
    assert result1.resolution == result2.resolution
```

---

**Model Status:** Defined (Stage 1)  
**Implementation:** Stage 2  
**Database Schema:** Ready for migration
