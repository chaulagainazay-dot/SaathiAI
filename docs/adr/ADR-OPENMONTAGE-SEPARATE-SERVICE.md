# ADR: Run OpenMontage as Separate Service (Scenario 1)

**Date:** 2026-07-10
**Status:** ACCEPTED_WITH_LIMITATIONS (FM-C1 normalized from “APPROVED (Stage 1)”)
**Implementation status:** Separate-service isolation decision remains; live deploy depends on environment
**Context:** M5.1 (Infrastructure stabilization) character animation for Mr. Yeti
**Decision:** Embed OpenMontage as **separate HTTP service**, NOT forked/embedded library
**Authority impact:** AGPL isolation only; does not replace ExecutionGateway


---

## Problem

OpenMontage (AGPL-3.0 licensed) provides production-ready character animation pipeline. SaathiOS must integrate without triggering AGPL copyleft on proprietary code.

**Constraints:**
- OpenMontage is AGPL-3.0 + network server clause
- Forking/modifying → AGPL copyleft on SaathiOS
- Single-user, deterministic render needed
- Must allow vendor independence (replace OpenMontage later if needed)

---

## Options Considered

### Option 1: Separate Service (HTTP API) ← **CHOSEN**

**What:** Run unmodified OpenMontage as separate Python process. SaathiOS calls via HTTP API.

**Pros:**
- ✅ AGPL copyleft does NOT apply (no modification, no code linking)
- ✅ OpenMontage can be updated independently
- ✅ Clean separation of concerns (orchestration ← SaathiOS, rendering ← OpenMontage)
- ✅ Easy to replace with alternative later
- ✅ Vendor independence maintained
- ✅ SaathiOS license unrestricted (proprietary, permissive, AGPL, whatever)

**Cons:**
- ⚠️ Network latency between SaathiOS ↔ OpenMontage
- ⚠️ Requires two services running (deployment complexity)
- ⚠️ Requires OpenMontage API (build or use Backlot + wrapper)

### Option 2: Forked Library (Python Import)

**What:** Clone OpenMontage, import lib/ as Python library, embed in SaathiOS.

**Pros:**
- ✅ Low latency (same process)
- ✅ Simpler debugging (stack trace crosses both)

**Cons:**
- ❌ AGPL copyleft triggered (library linking)
- ❌ All modifications must be AGPL-licensed
- ❌ SaathiOS becomes AGPL-licensed (if linking to modified code)
- ❌ Must publish modified source to all users
- ❌ Future updates require forking/merging AGPL changes
- ❌ Lock-in to AGPL licensing forever

### Option 3: Vendor Unmodified (pip install openmontage)

**What:** Include unmodified OpenMontage as dependency, import directly.

**Pros:**
- ✅ AGPL copyleft does NOT apply (unmodified)
- ✅ Lowest deployment complexity
- ✅ SaathiOS license unrestricted

**Cons:**
- ⚠️ Same process latency, but no customization ability
- ⚠️ Backlot board runs inside SaathiOS (network clause edge case)
- ⚠️ Still requires .env credential management

---

## Decision: Option 1 (Separate Service)

**Chosen because:**
1. **Licensing clarity:** No AGPL copyleft trigger
2. **Independence:** Can replace OpenMontage later without code refactor
3. **Separation of concerns:** SaathiOS owns orchestration, OpenMontage owns rendering
4. **Scalability:** Can run multiple OpenMontage workers behind load balancer
5. **Single-user design fit:** OpenMontage is single-user; separate service OK for M5.1

---

## Implementation

### Architecture

```
SaathiOS (ExecutionGateway, ToolIntent, Baadar)
    │
    ├─→ Telegram (Ajay) ← user commands
    │
    ├─→ OpenMontage Service (HTTP API)
    │   │
    │   ├─→ Character-Animation Pipeline
    │   ├─→ Tool Registry (128 tools)
    │   ├─→ Checkpoint Persistence
    │   ├─→ Cost Tracking
    │   └─→ Provider APIs (Google, OpenAI, Runway, etc.)
    │
    ├─→ Finance Layer (tracks costs from OpenMontage)
    │
    └─→ Asset Library (stores rendered videos)
```

### HTTP API Contract (OpenMontage Service)

**Base URL:** `http://localhost:8000` (or configurable)

**Endpoints:**

```python
# Invoke pipeline
POST /api/v1/projects
{
  "pipeline": "character-animation",
  "mission_id": "mission-123",  # From SaathiOS
  "actor_id": "user-ajay",
  "parameters": {
    "script": "...",
    "custom_playbook": {...}
  }
}
→ 202 {"project_id": "proj-789"}

# Get status
GET /api/v1/projects/{project_id}
→ 200 {"status": "in_progress", "current_stage": "proposal"}

# Read checkpoint
GET /api/v1/projects/{project_id}/checkpoints/{stage}
→ 200 {artifact}  # scene_plan.json, render_report.json, etc.

# Submit approval
POST /api/v1/projects/{project_id}/approve
{"decision": "approved", "feedback": "..."}
→ 200 {"status": "proceeding"}

# Get cost estimate
GET /api/v1/projects/{project_id}/costs
→ 200 {"spent": 0.45, "estimated_total": 1.85}
```

### SaathiOS Integration Points

**ExecutionGateway Layer:**
```python
class OpenMontageExecutor:
    def __init__(self, service_url):
        self.service_url = service_url

    def execute_character_animation(self, mission_id, actor_id, scene_input):
        """Invoke pipeline, return project_id"""
        response = requests.post(
            f"{self.service_url}/api/v1/projects",
            json={
                "pipeline": "character-animation",
                "mission_id": mission_id,
                "actor_id": actor_id,
                "parameters": scene_input
            }
        )
        return response.json()["project_id"]

    def get_status(self, project_id):
        """Poll pipeline status"""
        response = requests.get(
            f"{self.service_url}/api/v1/projects/{project_id}"
        )
        return response.json()

    def approve_checkpoint(self, project_id, decision):
        """Submit human approval"""
        response = requests.post(
            f"{self.service_url}/api/v1/projects/{project_id}/approve",
            json={"decision": decision}
        )
        return response.json()
```

**ToolIntent Adapter:**
```python
class OpenMontageToolIntent:
    """Wraps OpenMontage project invocation as ToolIntent"""

    @staticmethod
    def to_tool_intent(mission_id, actor_id, scene_input):
        return ToolIntent.builder()
            .actor(actor_id)
            .mission(mission_id)
            .capability("character-animation")
            .connector_id("openmontage-service")
            .operation("execute-pipeline")
            .parameters(scene_input)
            .reason("Generate rigged character animation for Mr. Yeti")
            .risk(RiskLevel.MEDIUM, ApprovalLevel.L3)  # Needs human approval for visuals
            .build()
```

### Deployment

**Local Development:**
```bash
# Terminal 1: SaathiOS
python -m uvicorn saathi.main:app --port 8765

# Terminal 2: OpenMontage
cd /opt/openmontage
python -m uvicorn backlot.main:app --port 8000
```

**Production:**
```yaml
# docker-compose.yml
services:
  saathios:
    build: .
    ports:
      - "8765:8765"
    environment:
      OPENMONTAGE_SERVICE_URL: http://openmontage:8000

  openmontage:
    build:
      context: ./openmontage
      dockerfile: Dockerfile
    ports:
      - "8000:8000"
    environment:
      GOOGLE_APPLICATION_CREDENTIALS: /secrets/gcp-key.json
      OPENAI_API_KEY: ${OPENAI_API_KEY}
      # ... other provider keys
    volumes:
      - ./openmontage/projects:/app/projects
      - /secrets:/secrets
```

---

## Consequences

### Positive

✅ **AGPL Compliance:** No copyleft trigger. SaathiOS license unrestricted.
✅ **Vendor Independence:** Can replace OpenMontage with alternative video service later.
✅ **Clean Architecture:** Orchestration (SaathiOS) separate from rendering (OpenMontage).
✅ **Scalability:** Can run multiple OpenMontage workers, load balance behind reverse proxy.
✅ **Maintainability:** OpenMontage updates don't require SaathiOS refactoring.

### Tradeoffs

⚠️ **Network Latency:** ~100-500ms per API call (acceptable for M5.1).
⚠️ **Operational Complexity:** Two services to deploy/monitor.
⚠️ **Health Checks:** Must monitor both SaathiOS + OpenMontage service.

---

## Alternatives Considered & Rejected

### Why NOT Option 2 (Forked Library)?

- ❌ AGPL copyleft becomes liability
- ❌ Forces SaathiOS into AGPL licensing
- ❌ Future OpenMontage updates require manual merge/rebase
- ❌ Legal complexity (modified AGPL code must be published)
- ❌ Lock-in to AGPL ecosystem

### Why NOT Option 3 (Vendor Unmodified)?

- ⚠️ Can't customize for Mr. Yeti brand (Option 1 allows custom playbook API)
- ⚠️ Backlot board inside SaathiOS process creates network clause ambiguity
- ⚠️ Less clear separation (still importing AGPL code into SaathiOS)

---

## Implementation Timeline

**Stage 1 (Current):** ADR approval, architecture documentation
**Stage 2:** Build OpenMontage HTTP wrapper + ExecutionGateway adapter
**Stage 2:** Integration tests (SaathiOS ↔ OpenMontage)
**Stage 2:** Deploy to test environment
**M5.2:** Production deployment (character animation for Baadar)

---

## Related ADRs

- [[ADR-TOOLINTENT-IMMUTABLE-CONTRACT]] — Immutable execution contract
- [[ADR-EXECUTIONGATEWAY-SINGLE-AUTHORITY]] — Single execution authority (Phase 3.2)

---

**Approved by:** Production Readiness Review
**Date:** 2026-07-10
**Status:** Ready for Stage 2 implementation
