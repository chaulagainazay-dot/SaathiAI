# OpenMontage Adapter Contracts (Stage 1 Scaffolding)

**Date:** 2026-07-10  
**Status:** Contracts defined; implementations disabled (OpenMontageExecutionDisabled)  
**Scope:** SaathiOS ↔ OpenMontage interface definitions  

---

## HTTP Service Adapter

### Base Service Interface

```python
class OpenMontageService:
    """Calls OpenMontage HTTP API"""
    
    def __init__(self, service_url: str):
        self.service_url = service_url
        self.client = httpx.AsyncClient(base_url=service_url)
    
    async def health_check(self) -> Dict:
        """GET /health"""
        raise OpenMontageExecutionDisabled(
            "OpenMontage execution is unavailable during Stage 1."
        )
    
    async def create_project(self, pipeline: str, mission_id: str, 
                            actor_id: str, parameters: Dict) -> Dict:
        """POST /api/v1/projects"""
        raise OpenMontageExecutionDisabled(
            "OpenMontage execution is unavailable during Stage 1."
        )
    
    async def get_project(self, project_id: str) -> Dict:
        """GET /api/v1/projects/{project_id}"""
        raise OpenMontageExecutionDisabled(
            "OpenMontage execution is unavailable during Stage 1."
        )
    
    async def get_checkpoint(self, project_id: str, stage: str) -> Dict:
        """GET /api/v1/projects/{project_id}/checkpoints/{stage}"""
        raise OpenMontageExecutionDisabled(
            "OpenMontage execution is unavailable during Stage 1."
        )
    
    async def approve_checkpoint(self, project_id: str, decision: str,
                                feedback: Optional[str] = None) -> Dict:
        """POST /api/v1/projects/{project_id}/approve"""
        raise OpenMontageExecutionDisabled(
            "OpenMontage execution is unavailable during Stage 1."
        )
    
    async def get_costs(self, project_id: str) -> Dict:
        """GET /api/v1/projects/{project_id}/costs"""
        raise OpenMontageExecutionDisabled(
            "OpenMontage execution is unavailable during Stage 1."
        )
    
    async def cancel_project(self, project_id: str) -> Dict:
        """POST /api/v1/projects/{project_id}/cancel"""
        raise OpenMontageExecutionDisabled(
            "OpenMontage execution is unavailable during Stage 1."
        )
```

### Expected HTTP Responses

**POST /api/v1/projects → 202 Accepted**
```json
{
  "project_id": "proj-abc789",
  "pipeline": "character-animation",
  "status": "queued",
  "created_at": "2026-07-10T12:00:00Z"
}
```

**GET /api/v1/projects/{project_id} → 200 OK**
```json
{
  "project_id": "proj-abc789",
  "pipeline": "character-animation",
  "status": "in_progress",
  "current_stage": "proposal",
  "stages_completed": ["research"],
  "next_approval_gate": "proposal",
  "checkpoints_available": ["research.json", "research_brief.json"],
  "updated_at": "2026-07-10T12:15:30Z"
}
```

**GET /api/v1/projects/{project_id}/checkpoints/{stage} → 200 OK**
```json
{
  "stage": "character_design",
  "artifact_type": "character_design",
  "data": {
    "id": "char-yeti-v1",
    "characters": [
      {
        "name": "Mr. Yeti",
        "silhouette": "round, friendly",
        "emotional_range": ["happy", "encouraging"],
        "actions": ["wave", "point", "shrug"]
      }
    ]
  },
  "timestamp": "2026-07-10T12:20:00Z",
  "cost_usd": 0.35
}
```

**POST /api/v1/projects/{project_id}/approve → 200 OK**
```json
{
  "status": "approved",
  "stage": "proposal",
  "next_stage": "script",
  "decision_recorded_at": "2026-07-10T12:30:00Z"
}
```

---

## ExecutionGateway Adapter

### ToolIntent → OpenMontage Bridge

```python
class OpenMontageExecutionGateway:
    """Wraps OpenMontage as ExecutionGateway connector"""
    
    def __init__(self, service: OpenMontageService):
        self.service = service
    
    async def execute(self, tool_intent: ToolIntent) -> ExecutionResult:
        """
        Execute ToolIntent against OpenMontage.
        
        Raises OpenMontageExecutionDisabled for Stage 1.
        """
        raise OpenMontageExecutionDisabled(
            "OpenMontage execution is unavailable during Stage 1."
        )
    
    def validate_intent(self, tool_intent: ToolIntent) -> List[str]:
        """
        Pre-flight validation.
        
        Checks:
        - operation in ["execute-pipeline", "get-status", "approve"]
        - connector_id == "openmontage"
        - required parameters present
        """
        errors = []
        
        if tool_intent.connector_id != "openmontage":
            errors.append("Expected connector_id='openmontage'")
        
        if tool_intent.capability != "character-animation":
            errors.append("Only 'character-animation' capability supported in M5.1")
        
        if tool_intent.operation not in ["execute-pipeline", "get-status", "approve"]:
            errors.append(f"Unknown operation: {tool_intent.operation}")
        
        return errors
    
    async def stage_status(self, project_id: str) -> Dict:
        """Poll current stage status"""
        raise OpenMontageExecutionDisabled(
            "OpenMontage execution is unavailable during Stage 1."
        )
```

### Result Types

```python
class ExecutionResult:
    """Result from OpenMontage execution"""
    
    status: Literal["success", "in_progress", "pending_approval", "failed"]
    
    # Success
    output: Optional[Dict] = None  # e.g., render_report.json
    
    # In-progress
    current_stage: Optional[str] = None
    progress_percent: Optional[int] = None
    
    # Pending approval
    checkpoint: Optional[Dict] = None
    required_decision: Optional[str] = None  # "approve", "send_back", "reject"
    
    # Error
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    
    # Metadata
    execution_time_seconds: Optional[float] = None
    cost_usd: Optional[float] = None
```

---

## Character-Animation Skill Adapter

### Stage Director Interface

```python
class CharacterAnimationDirector:
    """Orchestrates character-animation pipeline from SaathiOS"""
    
    def __init__(self, gateway: OpenMontageExecutionGateway):
        self.gateway = gateway
    
    async def invoke_pipeline(self, scene_input: Dict) -> str:
        """
        Create OpenMontage project for scene.
        
        Returns project_id.
        """
        raise OpenMontageExecutionDisabled(
            "OpenMontage execution is unavailable during Stage 1."
        )
    
    async def poll_status(self, project_id: str) -> Dict:
        """Check current stage progress"""
        raise OpenMontageExecutionDisabled(
            "OpenMontage execution is unavailable during Stage 1."
        )
    
    async def wait_for_approval(self, project_id: str, 
                               timeout_seconds: int = 3600) -> Dict:
        """
        Poll until human approval gate.
        
        Returns checkpoint artifact waiting for decision.
        """
        raise OpenMontageExecutionDisabled(
            "OpenMontage execution is unavailable during Stage 1."
        )
    
    async def approve_stage(self, project_id: str, stage: str,
                           decision: Literal["approved", "send_back"],
                           feedback: Optional[str] = None) -> bool:
        """
        Submit human approval decision.
        
        Returns True if pipeline proceeds; False if rejected.
        """
        raise OpenMontageExecutionDisabled(
            "OpenMontage execution is unavailable during Stage 1."
        )
    
    async def get_rendered_video(self, project_id: str) -> Dict:
        """
        Retrieve final render_report.json when complete.
        
        Returns:
        {
          "video_file": "/path/to/video.mp4",
          "duration_seconds": 45.0,
          "resolution": "1920x1080",
          "codec": "h264",
          "cost_usd": 1.85,
          "md5_hash": "a1b2c3d4..."
        }
        """
        raise OpenMontageExecutionDisabled(
            "OpenMontage execution is unavailable during Stage 1."
        )
```

### Custom Playbook Interface

```python
class MrYetiPlaybook:
    """Brand playbook for Mr. Yeti character animation"""
    
    @staticmethod
    def to_openmontage_playbook(brand_specs: Dict) -> Dict:
        """
        Convert SaathiOS brand specs to OpenMontage playbook JSON.
        
        Raises OpenMontageExecutionDisabled for Stage 1.
        """
        raise OpenMontageExecutionDisabled(
            "OpenMontage execution is unavailable during Stage 1."
        )
    
    @staticmethod
    def default_playbook() -> Dict:
        """
        Default Mr. Yeti playbook.
        
        Returns:
        {
          "name": "mr-yeti-brand",
          "colors": {
            "primary": "#6C3FCF",
            "accent": "#00BFA5",
            "background": "#1a1a2e"
          },
          "character_style": "friendly, round, educational",
          "camera": "warm, close-up, eye-level",
          "tone": "encouraging"
        }
        """
        return {
            "name": "mr-yeti-brand",
            "colors": {
                "primary": "#6C3FCF",
                "accent": "#00BFA5",
                "background": "#1a1a2e",
                "text": "#FFFFFF"
            },
            "character": {
                "name": "Mr. Yeti",
                "description": "Friendly, round Yeti with glasses, teacher suit",
                "personality": ["friendly", "educational", "enthusiastic"],
                "emotional_range": ["happy", "encouraging", "thoughtful", "surprised"]
            },
            "visual_style": {
                "tone": "professional yet playful",
                "aesthetic": "minimalist flat design",
                "camera": "warm, close-up, eye-level"
            }
        }
```

---

## Error Handling

```python
class OpenMontageAdapterError(Exception):
    """Base adapter error"""
    pass

class OpenMontageExecutionDisabled(OpenMontageAdapterError):
    """Raised when execution attempted during Stage 1"""
    message = "OpenMontage execution is unavailable during Stage 1. " \
              "Static analysis, contract definitions, and documentation only."

class OpenMontageServiceUnavailable(OpenMontageAdapterError):
    """OpenMontage service not running"""
    pass

class OpenMontageProjectNotFound(OpenMontageAdapterError):
    """Project ID not found in OpenMontage"""
    pass

class OpenMontageInvalidCheckpoint(OpenMontageAdapterError):
    """Checkpoint artifact malformed or missing"""
    pass

class OpenMontageApprovalRejected(OpenMontageAdapterError):
    """Human rejected checkpoint; pipeline stopped"""
    pass
```

---

## Type Definitions

```python
from typing import Dict, List, Optional, Literal

# Tool Intent parameters for OpenMontage
CharacterAnimationParams = Dict[
    Literal[
        "script",                # Narration/dialogue
        "character_branding",    # Brand specs (color, tone, style)
        "reference_video",       # Optional: style reference
        "scene_list",            # Ordered scenes
        "render_runtime",        # "hyperframes", "remotion", "ffmpeg"
        "budget_usd"             # Override default $2.00
    ],
    Any
]

# Checkpoint artifact types
ArtifactType = Literal[
    "research_brief",
    "proposal_packet",
    "script",
    "character_design",
    "rig_plan",
    "scene_plan",
    "asset_manifest",
    "edit_decisions",
    "render_report",
    "publish_log"
]

# Stage names in character-animation pipeline
StageName = Literal[
    "research",
    "proposal",
    "script",
    "character_design",
    "rig_plan",
    "scene_plan",
    "assets",
    "edit",
    "compose",
    "publish"
]
```

---

## Stage 1 Status

✅ **Contracts defined:** All interfaces documented  
✅ **Type definitions:** Python types ready  
✅ **Error handling:** Exception hierarchy  
✅ **Playbook mapping:** Mr. Yeti brand specs → OpenMontage playbook  

❌ **Implementations:** All methods raise OpenMontageExecutionDisabled  
❌ **HTTP calls:** No provider API execution  
❌ **Credential access:** No .env loading  

---

## Stage 2 Implementation Plan

1. Implement OpenMontageService.create_project()
2. Implement polling logic (get_project, get_checkpoint)
3. Implement approval workflow (approve_checkpoint)
4. Build cost aggregation (get_costs → Finance layer)
5. Implement ExecutionGateway adapter
6. Integrate with ToolIntent lifecycle
7. Add determinism verification tests

---

**Contract Status:** LOCKED (Stage 1)  
**Implementation:** Stage 2  
**Testing:** Integration tests defer to Stage 2

