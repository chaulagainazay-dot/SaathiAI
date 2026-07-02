```
================================================================================
SaathiAI Engineering Specification (SES)
================================================================================
Document Title      : Storage Intelligence & Lifecycle Management
Document ID         : SES-019A
Version             : 2.0.0
Status              : Draft pending review
Maturity            : L1
Classification      : Internal
Owner               : SaathiAI Architecture Team — Infrastructure Department
Parent Document     : SES-019 Deployment & Infrastructure
Created             : 2026-07-02
Last Updated        : 2026-07-02
Next Review         : 2026-10-02
================================================================================
```

---

## Revision History

| Version | Date | Author | Summary of Changes |
|---------|------|--------|--------------------|
| 1.0.0 | 2026-07-02 | Ajay Chaulagain | Initial draft — tiered storage model, lifecycle pipeline, disk watchdog, cloud archival |
| 2.0.0 | 2026-07-02 | Ajay Chaulagain | Elevated to Storage Intelligence: File Lifecycle Engine (policy-driven classes), Predictive Storage Engine, formal Infrastructure Department ownership, Event Fabric (SES-012) integration, expanded Mission Control storage analytics |

---

## Purpose

SaathiAI runs 24/7 on hardware with finite local disk — today a MacBook, tomorrow a mix of orchestrator and remote render nodes. AI Studio's video production pipeline generates frames, intermediate renders, and cache at a volume that will fill any local SSD within days if left unmanaged.

This document elevates storage management from ad-hoc cleanup scripts to **Storage Intelligence** — a formal platform capability owned by the Infrastructure Department, governed by policy rather than hardcoded logic, that predicts whether a render can finish safely before it starts, and that no other department bypasses by deleting files directly.

**The governing principle:** nothing is stored permanently unless it has permanent value. Every file's lifecycle — where it lives, how long, whether it's backed up, encrypted, or uploaded — is a declared policy, not an inferred convention. No render ever starts if it cannot finish safely.

---

## Audience

| Role | Required Sections |
|------|-------------------|
| AI Studio engineers | All — this governs every file AI Studio writes |
| Infrastructure Department engineers | All — this is their department's specification |
| Platform/Infra engineers | Parts 2, 3, 6, 7, 9, 10 |
| AI coding agents implementing storage code | All |
| Mission Control dashboard implementers | Part 11 |
| Event Fabric (SES-012) implementers | Part 8 |

---

## Document Structure

| Part | Title |
|------|-------|
| Part 1 | File Lifecycle Engine (Lifecycle Classes) |
| Part 2 | Directory Architecture |
| Part 3 | Job Lifecycle & Manifest |
| Part 4 | Predictive Storage Engine |
| Part 5 | Lifecycle Pipeline (Video Production) |
| Part 6 | Infrastructure Department & Service Ownership |
| Part 7 | Disk Watchdog Service |
| Part 8 | Event-Driven Storage (SES-012 Integration) |
| Part 9 | Cleanup Workflows (n8n) |
| Part 10 | Cloud Archival Strategy |
| Part 11 | Mission Control Storage Intelligence Panel |
| Part 12 | Emergency Cleanup Protocol |
| Part 13 | Compute Topology (Orchestrator vs Render Node) |
| Appendix A | SQLite Schema |
| Appendix B | Retention Rules Reference Table |
| Appendix C | Failure Modes & Recovery |
| Appendix D | Event Catalog (SES-012) |

---

# Part 1 — File Lifecycle Engine (Lifecycle Classes)

Every file SaathiAI creates is assigned a **lifecycle class** at creation time. The class is a policy bundle, not a folder convention — the Lifecycle Engine reads the class to decide where a file is stored, how long it lives, whether it's backed up, encrypted, uploaded, and whether it's eligible for automatic deletion. This replaces hardcoded cleanup logic (`if extension == '.mp4'`) with declared policy that any department can inspect and none can override informally.

```
Permanent
   │
   ▼
Archive
   │
   ▼
Working
   │
   ▼
Temporary
   │
   ▼
Disposable
```

## 1.1 Lifecycle Class Policy Table

| Class | Storage Location | TTL | Backed Up | Encrypted | Uploaded to R2 | Auto-Delete Eligible |
|-------|-------------------|-----|-----------|-----------|----------------|----------------------|
| **Permanent** | `databases/`, `models/`, `projects/`, git | Forever | Yes (separate backup procedure, Appendix C) | Yes, at rest | No — canonical copy lives locally/in git | Never |
| **Archive** | `archive/`, Cloudflare R2 | Forever (cloud), until verified (local) | Yes (R2 is the backup) | Yes, in transit + at rest in R2 | Yes, required before local deletion | Only after verified upload |
| **Working** | `temp/jobs/<job_id>/` | Until job completes or fails+ages out | No | No | No — intermediate, never leaves the machine | Yes, on job completion |
| **Temporary** | `temp/`, `cache/` (job-scoped) | Hours (job-scoped) or per Appendix B | No | No | No | Yes, immediately after use |
| **Disposable** | `cache/` (global, not job-scoped) | Rolling window (Appendix B) | No | No | No | Yes, on schedule, no job association required |

## 1.2 Old Tier → Lifecycle Class Mapping

For continuity with existing SES-005 (AI Studio) references to storage tiers T1–T4:

| Legacy Tier | Lifecycle Class |
|-------------|------------------|
| T1 (Permanent) | Permanent |
| T2 (Important Assets) | Archive |
| T3 (Working Directory) | Working / Temporary |
| T4 (Cache) | Disposable |

New code should reference lifecycle classes directly; the T1–T4 shorthand remains valid in cross-references from SES-005 and is not being retired.

## 1.3 The Engine, Not the Convention

The Lifecycle Engine (`saathi/lifecycle_engine.py`) is the only code path permitted to act on a file's class. A department does not decide "this file is 3 days old, I'll delete it" — it asks the Lifecycle Engine, which checks the class policy and either performs the action or refuses it (see Part 6 — no department deletes files directly).

```python
class LifecycleClass(str, Enum):
    PERMANENT = "permanent"
    ARCHIVE = "archive"
    WORKING = "working"
    TEMPORARY = "temporary"
    DISPOSABLE = "disposable"

@dataclass
class LifecyclePolicy:
    lifecycle_class: LifecycleClass
    storage_location: str
    ttl_seconds: int | None       # None = no TTL (Permanent, or Archive pending upload)
    backed_up: bool
    encrypted: bool
    uploaded_to_r2: bool
    auto_delete_eligible: bool

LIFECYCLE_POLICIES: dict[LifecycleClass, LifecyclePolicy] = {
    LifecycleClass.PERMANENT:  LifecyclePolicy(LifecycleClass.PERMANENT, "databases/|models/|projects/", None, True, True, False, False),
    LifecycleClass.ARCHIVE:    LifecyclePolicy(LifecycleClass.ARCHIVE, "archive/|r2://", None, True, True, True, True),   # deletable only post-verify
    LifecycleClass.WORKING:    LifecyclePolicy(LifecycleClass.WORKING, "temp/jobs/{job_id}/", None, False, False, False, True),   # deletable on job completion
    LifecycleClass.TEMPORARY:  LifecyclePolicy(LifecycleClass.TEMPORARY, "temp/|cache/", 7200, False, False, False, True),
    LifecycleClass.DISPOSABLE: LifecycleClass.DISPOSABLE if False else LifecyclePolicy(LifecycleClass.DISPOSABLE, "cache/", 259200, False, False, False, True),
}
```

---

# Part 2 — Directory Architecture

```
~/SaathiAI/storage/
│
├── cache/              (Disposable — auto-delete, rolling)
├── temp/                (Temporary/Working — job-scoped, auto-delete on job completion)
├── projects/            (Permanent — human-managed)
├── exports/             (Archive — pending upload)
├── archive/             (Archive — verified copy exists in cloud)
├── logs/                (Temporary/Disposable — compress after 7 days, delete after 30)
├── models/              (Permanent — LoRAs, trained assets, never auto-deleted)
└── databases/           (Permanent — SQLite, Neo4j, Qdrant)
```

Each directory maps to one or more lifecycle classes, defined in Appendix B, enforced by the Lifecycle Engine regardless of which department wrote the file. Departments write into the tier directory; the Lifecycle Engine, not the department, decides what happens next.

---

# Part 3 — Job Lifecycle & Manifest

AI Studio's Renderer Registry (SES-005 Part 11) writes every production into a dedicated job directory:

```
storage/temp/jobs/2026-07-02_001/
    script.md
    storyboard.json
    frames/
    audio/
    cache/
    output/
    logs/
    manifest.json
```

## 3.1 The Manifest

`manifest.json` is written when the job directory is created and updated at each pipeline stage. It is the single source of truth for what lifecycle class each file in the job belongs to — the Lifecycle Engine reads this instead of inferring class from file extension or folder convention.

```json
{
  "job_id": "2026-07-02_001",
  "product": "mr_yeti",
  "created_at": "2026-07-02T09:00:00Z",
  "status": "in_production",
  "predicted_peak_bytes": 31138512896,
  "files": {
    "script.md":        { "class": "working",   "keep_until": "job_complete" },
    "storyboard.json":  { "class": "working",   "keep_until": "job_complete" },
    "frames/":          { "class": "temporary", "keep_until": "verified_upload" },
    "audio/":           { "class": "temporary", "keep_until": "verified_upload" },
    "cache/":           { "class": "disposable","keep_until": "immediate_on_success" },
    "output/final.mp4":     { "class": "archive",   "keep_until": "archived" },
    "output/subtitle.srt":  { "class": "archive",   "keep_until": "archived" },
    "output/metadata.json": { "class": "permanent", "keep_until": "never" }
  },
  "size_bytes_by_class": { "archive": 0, "working": 0, "temporary": 0, "disposable": 0 },
  "upload_verified": false,
  "cleanup_completed": false
}
```

## 3.2 On Job Completion

When a job reaches `COMPLETE` (per SES-005's Production State Machine), the Lifecycle Engine:

1. Confirms `output/final.mp4`, `output/subtitle.srt`, and `output/metadata.json` exist and are non-zero size
2. Uploads Archive-class files to Cloudflare R2 (Part 10)
3. Verifies the upload (checksum match, not just HTTP 200)
4. On verified success: deletes everything classed `working`, `temporary`, or `disposable` in the job directory
5. Writes the final manifest state to `storage_jobs` (Appendix A) and removes the job directory, leaving only what was promoted to `archive/` or uploaded to R2

On failure, the job directory is retained for 24 hours (Appendix B) to permit debugging, then cleaned by the same engine.

---

# Part 4 — Predictive Storage Engine

This is what makes SaathiAI's storage management smarter than a cleanup cron job: **no render starts unless the platform has already confirmed it can finish.**

```
Storyboard
   │
   ▼
Estimated Duration
   │
   ▼
Estimated Frames
   │
   ▼
Estimated Audio
   │
   ▼
Estimated Disk Usage (peak)
   │
   ▼
Safe? ── No ──▶ Postpone + trigger cleanup, then re-check
   │
  Yes
   │
   ▼
Render
```

## 4.1 Estimation Model

The estimate is derived from the storyboard's scene count, duration, and target resolution, calibrated against the historical average render size for that product/renderer combination (SES-005's Renderer Registry already reports `estimate_cost()` per scene — the Predictive Storage Engine extends that with a disk-footprint estimate alongside the cost estimate).

```python
@dataclass
class StorageEstimate:
    frames_bytes: int
    audio_bytes: int
    video_bytes: int
    cache_bytes: int
    peak_bytes: int          # sum, with a safety margin factor applied
    free_bytes_available: int
    safe: bool
    shortfall_bytes: int      # 0 if safe

def estimate_job_storage(storyboard: StoryboardSpec, renderer: str) -> StorageEstimate:
    historical = get_historical_average(product=storyboard.product, renderer=renderer)  # storage_reports rolling average
    frames = storyboard.scene_count * historical.avg_frame_bytes_per_scene
    audio = storyboard.duration_seconds * historical.avg_audio_bytes_per_second
    video = storyboard.duration_seconds * historical.avg_video_bytes_per_second
    cache = historical.avg_cache_bytes_per_job
    peak = int((frames + audio + video + cache) * 1.15)   # 15% safety margin

    free = psutil.disk_usage("/").free
    safe = free >= peak
    return StorageEstimate(frames, audio, video, cache, peak, free, safe, max(0, peak - free))
```

## 4.2 Example

```
Expected output
  Frames:  18 GB
  Audio:   0.6 GB
  Video:   2.1 GB
  Cache:   9 GB
  Peak Usage: 29 GB   (with 15% safety margin already applied)

Current free space: 22 GB

Result:
  ❌ Rendering postponed
  Need:  29 GB
  Have:  22 GB
  Cleanup required: 7 GB
```

## 4.3 On Postponement

The job is not rejected — it is queued with `status = 'postponed_insufficient_storage'`, the Cleanup Engine (Part 6) is triggered immediately (out of its normal schedule) to try to free the shortfall, and the Predictive Storage Engine re-checks after cleanup completes. If cleanup cannot free enough space, a Telegram alert is sent and the job stays queued until space is available or a human intervenes.

This check runs inside the Studio Director (SES-005 Part 3) as a mandatory gate before a brief transitions from `BRIEFED` to `RESEARCHING` — a job cannot enter the production pipeline without a `safe = True` estimate on file.

---

# Part 5 — Lifecycle Pipeline (Video Production)

```
Generate
   │
   ▼
Intermediate Frames        (Temporary)
   │
   ▼
Final Render                (Archive, pending)
   │
   ▼
Upload to R2
   │
   ▼
Verify Upload (checksum)
   │
   ├─ FAIL → retry (3x, exponential backoff) → alert via Telegram if still failing
   │
   ▼ PASS
Delete Intermediate Files    (Temporary — frames/)
   │
   ▼
Delete Temporary Audio       (Temporary)
   │
   ▼
Delete Frame Cache           (Disposable)
   │
   ▼
Keep Final Asset             (Archive → archived, local copy removed)
```

**The deletion step never runs before verification passes.** This is the single non-negotiable rule in this document: a file is not deleted until its cloud copy has been checksum-verified. An HTTP 200 on upload is not verification — verification means downloading the object header/ETag from R2 and comparing it against the local file's hash.

---

# Part 6 — Infrastructure Department & Service Ownership

Storage Intelligence is formally owned by the **Infrastructure Department** (a department within SES-002's agent system, parallel to AI Studio, Discovery Engine, and Research). **No other department deletes files directly.** Every department that produces disposable output submits a **lifecycle request** to the Infrastructure Department; the department's own services decide whether and when to act.

```
Infrastructure Department
│
├── Disk Watchdog          (Part 7 — safety-critical, 1-minute poll, pause/emergency authority)
├── Storage Manager        (owns storage_jobs state, tier/class bookkeeping)
├── Lifecycle Engine       (Part 1 — policy enforcement, the only deleter)
├── Cleanup Engine          (executes deletions the Lifecycle Engine authorizes)
├── Archive Manager         (Part 10 — upload orchestration + verification)
├── Backup Manager          (Permanent-class backup procedure, Appendix C)
├── Cloud Sync              (R2 client, retry/backoff logic)
├── Predictive Storage Engine (Part 4)
├── Storage Analytics        (Part 11 — metrics for Mission Control)
└── Event Publisher          (Part 8 — publishes all storage events to the Event Fabric)
```

## 6.1 Lifecycle Request Contract

A department (e.g., AI Studio) that wants a file cleaned up, archived, or checked against a threshold sends a request; it does not call `os.remove()` itself.

```python
@dataclass
class LifecycleRequest:
    requesting_department: str     # e.g. "ai_studio"
    job_id: str | None
    action: Literal["cleanup", "archive", "estimate", "check_safe_to_render"]
    target_path: str
    lifecycle_class: LifecycleClass | None   # required for "cleanup" and "archive"

def submit_lifecycle_request(request: LifecycleRequest) -> LifecycleResult:
    ...  # routed to the appropriate Infrastructure Department service
```

This mirrors the platform's Agent Contract convention (SES-002) — the Infrastructure Department's services each have their own AgentContract (agent_id, purpose, inputs, outputs, safety_classification) and are invoked through the same tool-registry pattern every other department uses, not through direct filesystem calls from unrelated code.

---

# Part 7 — Disk Watchdog Service

The Disk Watchdog is a first-class SaathiAI service, not an n8n workflow. Safety-critical decisions — pausing rendering, triggering emergency cleanup — must not depend on an external workflow engine staying healthy; they live inside the same process space as the scheduler that decides whether to start new render jobs.

**Module:** `saathi/storage/watchdog.py` — **BUILT & TESTED** (6 passing tests, `tests/test_storage.py`)
**Mechanism:** stdlib `shutil.disk_usage()` (not psutil — avoids a dependency for Step 1; swap in psutil only if per-process metrics are later needed), polled via APScheduler. The watchdog takes an injectable usage-reader so it is testable without a real disk (AP-12). State transitions are edge-triggered — an event fires once when a threshold is first crossed and once when it clears.

> **Reconciliation note (Dev Rule #1):** this section originally specced `psutil` + `saathi/disk_watchdog.py`. The implemented reality is stdlib `shutil` + `saathi/storage/watchdog.py`. Doc updated to match code.

```python
from apscheduler.schedulers.background import BackgroundScheduler
import psutil

DISK_THRESHOLDS = {
    "notify": 0.80,
    "pause_rendering": 0.90,
    "emergency_cleanup": 0.95,
}

class DiskWatchdogState:
    def __init__(self):
        self.rendering_paused: bool = False
        self.emergency_active: bool = False
        self.last_check: datetime | None = None

def check_disk() -> None:
    usage = psutil.disk_usage("/")
    pct = usage.used / usage.total

    if pct >= DISK_THRESHOLDS["emergency_cleanup"] and not state.emergency_active:
        state.emergency_active = True
        publish_event("storage_critical", {"disk_pct": pct})     # Part 8
        run_emergency_cleanup()          # Part 12
        notify_telegram(f"EMERGENCY: disk at {pct:.0%}, running emergency cleanup")

    elif pct >= DISK_THRESHOLDS["pause_rendering"] and not state.rendering_paused:
        state.rendering_paused = True
        publish_event("storage_warning", {"disk_pct": pct})
        pause_render_queue()             # SES-005 Studio Director honors this flag
        notify_telegram(f"WARNING: disk at {pct:.0%}, rendering paused")

    elif pct >= DISK_THRESHOLDS["notify"]:
        notify_telegram(f"NOTICE: disk at {pct:.0%}")

    elif pct < DISK_THRESHOLDS["pause_rendering"] and state.rendering_paused:
        state.rendering_paused = False
        resume_render_queue()
        notify_telegram(f"Disk back to {pct:.0%}, rendering resumed")

scheduler = BackgroundScheduler()
scheduler.add_job(check_disk, "interval", minutes=1)
```

**Alerting:** every state transition (notify / pause / emergency / resume) fires a Telegram message via Baadar's existing two-way Telegram bot (`@AjayGmailbot`) — storage problems must never be discovered by noticing render jobs silently stalled.

**Studio Director integration:** SES-005's Studio Director checks `disk_watchdog.state.rendering_paused` and the Predictive Storage Engine's per-job `safe` flag (Part 4) before accepting a new job brief. If paused, the brief is queued, not rejected — it resumes automatically when the watchdog clears.

---

# Part 8 — Event-Driven Storage (SES-012 Integration)

Storage Intelligence does not expose its internal functions to other departments as direct calls — it publishes events to the Event Fabric (SES-012, NATS), and other departments (and the Infrastructure Department's own services) subscribe to what they need. This decouples "a render finished" from "someone must now decide what to clean up" — the coupling lives in event subscriptions, not in inline function calls scattered across departments.

## 8.1 Event Flow

```
render_started
      │
      ▼
render_completed ──────► upload_verified ──────► cleanup_requested ──────► cleanup_completed
      │                                                                          │
      ▼                                                                          ▼
storage_warning / storage_critical (Disk Watchdog, any time)          archive_completed
                                                                              │
                                                                              ▼
                                                                     backup_completed
```

## 8.2 Publisher / Subscriber Map

| Event | Published By | Subscribed By |
|-------|---------------|----------------|
| `render_started` | SES-005 Studio Director | Storage Manager (opens `storage_jobs` row), Predictive Storage Engine (records estimate) |
| `render_completed` | SES-005 Renderer Registry | Archive Manager (begins upload) |
| `upload_verified` | Cloud Sync | Cleanup Engine (authorized to delete Working/Temporary/Disposable files) |
| `cleanup_requested` | Any department (via Part 6's Lifecycle Request contract) | Cleanup Engine |
| `cleanup_completed` | Cleanup Engine | Storage Manager (closes `storage_jobs` row), Storage Analytics |
| `storage_warning` | Disk Watchdog (90% threshold) | Studio Director (pause queue), Mission Control, Telegram |
| `storage_critical` | Disk Watchdog (95% threshold) | Studio Director (pause queue), Cleanup Engine (emergency mode), Mission Control, Telegram |
| `archive_completed` | Archive Manager | Publishing Department (SES-005 Part 14 — asset is now safely retrievable from R2) |
| `backup_completed` | Backup Manager | Storage Analytics, weekly storage report (Part 9) |

Full event schemas are in Appendix D.

---

# Part 9 — Cleanup Workflows (n8n)

n8n owns the **scheduled maintenance** workflows — recurring, non-safety-critical cleanup that can tolerate a missed run without causing an outage. The Disk Watchdog (Part 7) owns emergency response; n8n owns hygiene. n8n workflows trigger by subscribing to Event Fabric events (Part 8) where applicable, and by cron schedule for the rest.

## Every Hour
- Remove temporary files older than 2 hours (`temp/` outside active job directories)
- Remove failed render directories older than 24 hours (Appendix B)
- Remove abandoned browser/Playwright sessions

## Every Night
- Compress logs older than 7 days (`gzip`)
- Delete cache older than 3 days (Disposable class)
- Archive completed projects (move verified Archive-class assets from `exports/` to `archive/`)
- Clean ComfyUI temporary outputs
- Clean Playwright download directories

## Weekly
- Verify Cloudflare R2 backups (re-checksum a sample of archived objects against local manifest records)
- Remove verified local archives that have passed the weekly re-verification
- Generate a storage report (write to `storage_reports` table, Appendix A; surfaced in Mission Control, Part 11)
- Run disk health check (SMART status if available, filesystem check)

Each n8n workflow calls into the same Lifecycle Request contract (Part 6) that departments use — n8n is a scheduler/trigger client of the Infrastructure Department, not a second implementation of deletion logic.

---

# Part 10 — Cloud Archival Strategy

**Primary target: Cloudflare R2** (S3-compatible, zero egress fees — matches SES-000F Capability Registry's existing R2 integration for AI Studio assets).

**Fallback targets:** MinIO (self-hosted S3-compatible, for environments without R2 access) or an external SSD/NAS mount for pure local redundancy without cloud dependency.

## 10.1 Upload Contract

```python
def archive_to_r2(local_path: Path, job_id: str, lifecycle_class: LifecycleClass) -> ArchiveResult:
    key = f"{lifecycle_class.value}/{job_id}/{local_path.name}"
    local_hash = sha256_file(local_path)
    r2_client.upload_file(str(local_path), BUCKET, key)
    remote_etag = r2_client.head_object(Bucket=BUCKET, Key=key)["ETag"]
    verified = remote_etag.strip('"') == local_hash
    if verified:
        publish_event("upload_verified", {"job_id": job_id, "key": key})
    return ArchiveResult(key=key, verified=verified, local_hash=local_hash)
```

Local deletion is gated strictly on `verified == True`. A failed verification retries up to 3 times with exponential backoff before escalating to a Telegram alert and leaving the local copy in place (fail-safe: keep local data over losing it).

## 10.2 What Never Goes to R2

Permanent-class files are never migrated to R2 as their primary copy — they live in git (source code, SES docs, `Brain.md`) or in the local database engines (SQLite, Neo4j, Qdrant). R2 backup of Permanent-class data is a separate, explicit backup procedure (Appendix C, owned by the Backup Manager service), not part of the lifecycle deletion pipeline.

---

# Part 11 — Mission Control Storage Intelligence Panel

Per SES-007 (Mission Control), the storage subsystem exposes a panel showing, at a glance, whether intervention is needed — expanded beyond raw disk state into genuine storage analytics:

| Field | Source |
|-------|--------|
| Current (SSD Free) | `psutil.disk_usage()`, live |
| Peak Today | Max recorded usage from `storage_watchdog_events` in the last 24h |
| Peak Week | Max recorded usage from `storage_watchdog_events` in the last 7 days |
| Average Render Size | Rolling average of `storage_jobs.size_bytes_archive + size_bytes_working` per completed job |
| Average Cleanup (bytes freed) | Rolling average from `cleanup_completed` events |
| Estimated Days Remaining | `(free_bytes) / (avg daily net growth rate)` — projects when the disk fills at current pace |
| SSD Health | SMART status (if available) from weekly disk health check |
| Write Amplification | `(bytes actually written to disk) / (bytes of unique final content produced)` — flags inefficient intermediate-file churn |
| Cleanup Success Rate | `cleanup_completed / cleanup_requested` over the trailing 7 days |
| Temporary Cache (size) | Sum of Disposable-class directory sizes |
| Active Renders | Count of `storage_jobs` where `status = 'in_production'` |
| Archived Projects | Count of `storage_jobs` where `status = 'archived'` |
| Cloud Sync Status | Last successful R2 verification timestamp + pending upload count |
| Cleanup Queue | Pending cleanup requests not yet executed |
| Emergency State | `disk_watchdog.state.emergency_active` / `rendering_paused` flags |

This panel is read-only — Mission Control displays state, it does not trigger cleanup directly (that stays inside the Disk Watchdog and Cleanup Engine, per Parts 6–7, to keep a single source of truth for lifecycle decisions).

---

# Part 12 — Emergency Cleanup Protocol

Triggered when disk usage crosses 95% (Part 7). Runs in strict priority order, stopping as soon as usage drops below the emergency threshold — it does not clear every category if the first two already free enough space.

## Priority Order (deletable, most disposable first)

1. Temporary renders (Temporary class, `temp/jobs/*/frames`, `temp/jobs/*/audio` for jobs not currently `in_production`)
2. Render cache (Disposable class, `cache/`)
3. Browser cache / Playwright profiles (Disposable class)
4. AI model cache (Hugging Face cache, Disposable class — re-downloadable)
5. Old logs (uncompressed logs older than 7 days)
6. Old downloads (anything in a `downloads/` staging area older than 24 hours)

## Never Touched, Under Any Circumstance

- Databases (SQLite, Neo4j, Qdrant) — Permanent class
- Source code — Permanent class
- Trained models / LoRAs — Permanent class
- Documentation (SES docs, `Brain.md`, `Business.md`) — Permanent class
- Any file whose manifest class is `permanent`, regardless of what directory it's found in

The emergency cleanup function reads the `class` field from each job's `manifest.json` (Part 3) before deleting anything — it never deletes based on file extension or directory-name pattern-matching alone. If a manifest is missing or corrupt for a directory, that directory is skipped and flagged for human review rather than guessed at.

---

# Part 13 — Compute Topology (Orchestrator vs Render Node)

## 13.1 Current State

The Mac runs everything: n8n, Mission Control, Voice OS, the Agent System, coding, and planning — plus, currently, no GPU rendering (Mr. Yeti content uses Google Flow's cloud rendering, not local compute).

## 13.2 Target State

```
Mac (SaathiAI Brain — orchestrator)
    │
    ├── n8n
    ├── Mission Control
    ├── Voice OS
    ├── Agent System
    ├── Coding & Planning
    │
    ▼ (dispatches render jobs, after Predictive Storage Engine confirms safe)
Remote GPU Node
    ├── ComfyUI
    ├── LTX-2 / Wan / Open-Sora renderers (SES-005 Renderer Registry adapters)
    ├── Disk Watchdog (same module, deployed per-node)
    ▼ (uploads directly, does not round-trip through the Mac)
Cloudflare R2
    ▼
Final Assets (available to Publishing Dept, SES-005 Part 14)
```

**Why this matters for storage:** every gigabyte of intermediate frames and render cache is generated and deleted on the remote GPU node, never touching the Mac's SSD at all. The Mac only ever sees the final, already-verified, already-small output asset (or nothing, if Publishing pulls directly from R2).

## 13.3 Sequencing

This is a **Phase 2 move**, not a Day 1 requirement. The Storage Intelligence system in Parts 1–12 is compute-topology-agnostic — it manages lifecycle regardless of whether rendering happens locally or remotely. Build Storage Intelligence first (it's needed immediately, on the Mac, today); provision the remote GPU node (RunPod, Lambda Labs, Vast.ai, or a paid OCI GPU shape — the Always Free compute created for SaathiAI's orchestrator has no GPU and is not a rendering candidate) when AI Studio's render volume actually requires it.

---

# Appendix A — SQLite Schema

```sql
CREATE TABLE storage_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT UNIQUE NOT NULL,
    product TEXT NOT NULL,
    status TEXT NOT NULL,              -- in_production, complete, failed, archived, postponed_insufficient_storage
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    completed_at DATETIME,
    manifest_path TEXT NOT NULL,
    predicted_peak_bytes INTEGER,
    actual_peak_bytes INTEGER,
    size_bytes_archive INTEGER DEFAULT 0,
    size_bytes_working INTEGER DEFAULT 0,
    size_bytes_temporary INTEGER DEFAULT 0,
    size_bytes_disposable INTEGER DEFAULT 0,
    upload_verified INTEGER DEFAULT 0,
    cleanup_completed INTEGER DEFAULT 0
);

CREATE TABLE storage_archive_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    file_name TEXT NOT NULL,
    r2_key TEXT NOT NULL,
    local_hash TEXT NOT NULL,
    remote_etag TEXT,
    verified INTEGER DEFAULT 0,
    verified_at DATETIME,
    retry_count INTEGER DEFAULT 0
);

CREATE TABLE storage_watchdog_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,          -- notify, pause, emergency, resume
    disk_pct REAL NOT NULL,
    triggered_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    resolved_at DATETIME,
    notes TEXT
);

CREATE TABLE storage_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    generated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    ssd_free_bytes INTEGER,
    cache_size_bytes INTEGER,
    active_renders INTEGER,
    archived_projects INTEGER,
    avg_render_size_bytes INTEGER,
    avg_cleanup_bytes_freed INTEGER,
    estimated_days_remaining REAL,
    write_amplification_ratio REAL,
    cleanup_success_rate REAL,
    cloud_sync_status TEXT,
    report_json TEXT
);

CREATE TABLE storage_lifecycle_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    requesting_department TEXT NOT NULL,
    job_id TEXT,
    action TEXT NOT NULL,              -- cleanup, archive, estimate, check_safe_to_render
    target_path TEXT NOT NULL,
    lifecycle_class TEXT,
    requested_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    completed_at DATETIME,
    result TEXT
);
```

---

# Appendix B — Retention Rules Reference Table

| Category | Lifecycle Class | Retention Rule |
|----------|------------------|-----------------|
| Source code, Brain.md, Business.md, SES docs | Permanent | Never auto-delete |
| SQLite databases, Neo4j, Qdrant | Permanent | Never auto-delete |
| Trained LoRAs, character bibles | Permanent | Never auto-delete |
| Final video/thumbnail/audio/subtitle | Archive | Delete after R2 upload verified |
| Intermediate renders, frame sequences | Temporary | Delete on job completion (post-verify) |
| Failed render directories | Working | Retain 24 hours, then delete |
| Temp audio, FFmpeg intermediates | Temporary | Delete on job completion (post-verify) |
| ComfyUI / Hugging Face cache | Disposable | Delete after 3 days |
| Browser downloads, Playwright profiles | Disposable | Delete after job completion, or 24h if orphaned |
| Uncompressed logs | Temporary | Compress after 7 days |
| Compressed logs | Disposable | Delete after 30 days |

---

# Appendix C — Failure Modes & Recovery

| Failure | Detection | Recovery |
|---------|-----------|----------|
| R2 upload succeeds but checksum mismatch | `verified == False` in archive_to_r2 | Retry 3x exponential backoff; local copy retained; Telegram alert if still failing |
| Job directory has no manifest.json | Cleanup worker scan | Skip deletion, flag for human review, Telegram notice |
| Disk hits 95% during active render | Disk Watchdog 1-min poll | Emergency cleanup (Part 12); render job paused, not killed — resumes when safe |
| n8n instance down, hourly workflow misses | No heartbeat from n8n webhook | Disk Watchdog still operates independently (Part 7 is not n8n-dependent) — worst case is delayed hygiene cleanup, not an outage |
| Permanent-class database corrupted | Health check finds corruption | Never touched by lifecycle cleanup; restored by Backup Manager's separate backup procedure |
| Remote GPU node fills its own disk | Same Disk Watchdog module deployed on the render node | Same threshold/pause/emergency logic applies per-node — the watchdog is not Mac-specific |
| Predictive estimate wrong (job exceeds predicted peak) | `actual_peak_bytes > predicted_peak_bytes * 1.15` recorded post-job | Feeds back into historical average calculation (Part 4.1) — the model self-corrects over time; Disk Watchdog remains the backstop regardless |
| Department bypasses Lifecycle Request contract and deletes a file directly | Code review / lint rule forbidding direct `os.remove()` outside `saathi/lifecycle_engine.py` | Treated as a bug, not a supported path — Part 6 is the only sanctioned deletion route |

---

# Appendix D — Event Catalog (SES-012)

| Event | Payload | Notes |
|-------|---------|-------|
| `render_started` | `{job_id, product, predicted_peak_bytes}` | Opens the `storage_jobs` row |
| `render_completed` | `{job_id, actual_output_files: [...]}` | Triggers Archive Manager upload |
| `upload_verified` | `{job_id, key, local_hash}` | Authorizes Cleanup Engine to delete non-Archive files |
| `cleanup_requested` | `{requesting_department, job_id, target_path, lifecycle_class}` | Matches the Part 6 Lifecycle Request contract |
| `cleanup_completed` | `{job_id, bytes_freed}` | Closes the `storage_jobs` row, feeds Storage Analytics |
| `storage_warning` | `{disk_pct}` | Disk Watchdog, 90% threshold |
| `storage_critical` | `{disk_pct}` | Disk Watchdog, 95% threshold |
| `archive_completed` | `{job_id, r2_keys: [...]}` | Publishing Department may now safely pull from R2 |
| `backup_completed` | `{backup_type, bytes, duration_seconds}` | Permanent-class backup procedure completion |

---

# Acceptance Criteria

| # | Criterion | Verification Method |
|---|-----------|---------------------|
| AC-001 | Every file created by AI Studio has a lifecycle class recorded in its job manifest | Code review of Renderer Registry write paths |
| AC-002 | No Working/Temporary/Disposable file is deleted before its Archive counterpart (if any) is upload-verified | Integration test: kill upload mid-job, confirm no local deletion occurs |
| AC-003 | Disk Watchdog pauses rendering at 90% and resumes automatically when usage drops | Simulated disk-fill test |
| AC-004 | Emergency cleanup never deletes a Permanent-class file | Unit test with a manifest containing a Permanent file inside a Temporary directory |
| AC-005 | Every watchdog state transition produces a Telegram notification and a Event Fabric publish | Integration test against Baadar's Telegram bot and SES-012 event bus |
| AC-006 | Mission Control storage panel reflects live `storage_jobs` state within 60 seconds | Manual verification against dashboard refresh interval |
| AC-007 | Predictive Storage Engine blocks a job when `peak_bytes > free_bytes` and re-checks after triggered cleanup | Integration test: force a low-free-space condition, confirm job is postponed not started |
| AC-008 | No department calls filesystem deletion directly outside the Lifecycle Engine | Static analysis / lint rule across the codebase |

---

# Implementation Checklist

- [ ] Create `storage/` directory structure (Part 2) on the Mac
- [ ] Implement `saathi/lifecycle_engine.py` — the only sanctioned deletion path (Part 1, Part 6)
- [ ] Implement `saathi/disk_watchdog.py` (Part 7) with APScheduler integration
- [ ] Implement `saathi/predictive_storage.py` (Part 4) with historical-average calibration
- [ ] Create SQLite schema (Appendix A)
- [ ] Wire Studio Director (SES-005) to check `disk_watchdog.state.rendering_paused` and Predictive Storage Engine's `safe` flag before accepting new job briefs
- [ ] Publish the 9 Event Fabric events (Part 8, Appendix D) from their respective services
- [ ] Build n8n workflows for hourly/nightly/weekly maintenance (Part 9), calling into the Lifecycle Request contract
- [ ] Add Mission Control Storage Intelligence panel (Part 11)
- [ ] Add Time Machine / Spotlight exclusions for `cache/`, `temp/`, and `jobs/*/frames` on the Mac
- [ ] Write and test emergency cleanup priority ordering (Part 12) against a manifest-tagged test directory tree
- [ ] Add a lint rule forbidding direct filesystem deletion outside `saathi/lifecycle_engine.py`
- [ ] Document remote GPU node provisioning as a tracked Phase 2 item (Part 13) — not blocking this spec's Phase 1 implementation
