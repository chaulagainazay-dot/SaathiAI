# OpenMontage Error Taxonomy for SaathiOS

**Date:** 2026-07-10  
**Status:** Error types defined (M5.2 implementation)  

---

## Error Categories

### 1. Configuration Errors

```python
class ConfigError(Exception):
    """Configuration invalid or missing"""
    pass

class ServiceNotConfigured(ConfigError):
    """OpenMontage service URL not set"""
    pass

class CredentialsMissing(ConfigError):
    """Required API keys not in .env"""
    pass

class PipelineNotFound(ConfigError):
    """Pipeline name not recognized"""
    pass

class PlaybookInvalid(ConfigError):
    """Custom playbook malformed or missing required fields"""
    pass
```

### 2. Service Errors

```python
class ServiceError(Exception):
    """OpenMontage service communication failed"""
    pass

class ServiceUnavailable(ServiceError):
    """HTTP 503: Service not running"""
    pass

class ServiceTimeout(ServiceError):
    """HTTP request timeout (>30s)"""
    pass

class ServiceInternalError(ServiceError):
    """HTTP 500: Server error in OpenMontage"""
    pass

class HealthCheckFailed(ServiceError):
    """Service health check failed"""
    pass
```

### 3. Project Errors

```python
class ProjectError(Exception):
    """Project-level failure"""
    pass

class ProjectNotFound(ProjectError):
    """project_id doesn't exist in OpenMontage"""
    pass

class ProjectAlreadyExists(ProjectError):
    """Project with same ID already running"""
    pass

class ProjectQuotaExceeded(ProjectError):
    """Max concurrent projects exceeded (resource limit)"""
    pass

class ProjectCancelled(ProjectError):
    """Pipeline cancelled by user"""
    pass
```

### 4. Stage Errors

```python
class StageError(Exception):
    """Stage execution failed"""
    pass

class StageFailed(StageError):
    """Stage tools returned error status"""
    pass

class StageTimeout(StageError):
    """Stage exceeded max_wall_time_minutes"""
    pass

class StageSkipped(StageError):
    """Stage skipped due to missing required artifacts"""
    pass

class ApprovalTimeout(StageError):
    """Human approval not received within timeout"""
    pass

class ApprovalRejected(StageError):
    """Human rejected checkpoint"""
    pass

class MaxRevisionsExceeded(StageError):
    """Max send-backs exceeded; manual escalation needed"""
    pass
```

### 5. Tool Errors

```python
class ToolError(Exception):
    """Tool execution failed"""
    pass

class ToolNotAvailable(ToolError):
    """Tool disabled (missing provider key)"""
    pass

class ToolExecutionFailed(ToolError):
    """Tool returned error status"""
    pass

class ToolOutputInvalid(ToolError):
    """Tool output doesn't match expected schema"""
    pass

class ToolCrashError(ToolError):
    """Tool crashed (exception, OOM, segfault)"""
    pass

class ToolTimeout(ToolError):
    """Tool exceeded timeout"""
    pass
```

### 6. Provider Errors

```python
class ProviderError(Exception):
    """External provider (API) failure"""
    pass

class ProviderAuthError(ProviderError):
    """API key invalid, expired, or rate-limited"""
    pass

class ProviderRateLimited(ProviderError):
    """Provider rate limit hit; retry later"""
    pass

class ProviderUnavailable(ProviderError):
    """Provider service down or unreachable"""
    pass

class ProviderQuotaExceeded(ProviderError):
    """Account quota exhausted (e.g., monthly limit)"""
    pass

class ProviderOutputError(ProviderError):
    """Provider returned invalid output (e.g., corrupted image)"""
    pass
```

### 7. Budget Errors

```python
class BudgetError(Exception):
    """Cost/budget exceeded"""
    pass

class ApprovalRequired(BudgetError):
    """Action cost > approval_threshold_usd"""
    pass

class BudgetExceeded(BudgetError):
    """Usable budget exhausted"""
    pass

class CostEstimateMismatch(BudgetError):
    """Actual cost significantly differs from estimate"""
    pass
```

### 8. Data Errors

```python
class DataError(Exception):
    """Data corruption or schema violation"""
    pass

class CheckpointMissing(DataError):
    """Required checkpoint artifact not found"""
    pass

class CheckpointCorrupted(DataError):
    """Checkpoint file unreadable or malformed JSON"""
    pass

class ArtifactValidationError(DataError):
    """Artifact doesn't validate against JSON Schema"""
    pass

class ArtifactDependencyMissing(DataError):
    """Artifact requires upstream artifact that's missing"""
    pass
```

### 9. Credential Errors

```python
class CredentialError(Exception):
    """API credential problem"""
    pass

class CredentialNotFound(CredentialError):
    """API key not in .env"""
    pass

class CredentialExpired(CredentialError):
    """API key or service account expired"""
    pass

class CredentialInvalid(CredentialError):
    """API key format invalid"""
    pass

class CredentialLeakRisk(CredentialError):
    """Possible credential exposure (e.g., in log file)"""
    pass
```

### 10. Render Errors

```python
class RenderError(Exception):
    """Video rendering failed"""
    pass

class RenderRuntimeUnavailable(RenderError):
    """Render runtime not installed (e.g., Chrome, FFmpeg)"""
    pass

class RenderLaunchFailed(RenderError):
    """Failed to start render process"""
    pass

class RenderOOM(RenderError):
    """Out of memory during render"""
    pass

class RenderCrashed(RenderError):
    """Render process crashed"""
    pass

class RenderQualityIssue(RenderError):
    """Rendered video has quality issues (artifacts, corruption)"""
    pass

class RenderNonDeterministic(RenderError):
    """Same input produced different video (detected at verification)"""
    pass
```

### 11. Storage Errors

```python
class StorageError(Exception):
    """File system problem"""
    pass

class StorageNotWritable(StorageError):
    """projects/ directory not writable"""
    pass

class StorageQuotaExceeded(StorageError):
    """Disk full or quota exceeded"""
    pass

class StorageFileNotFound(StorageError):
    """Checkpoint or video file missing"""
    pass

class StorageCorrupted(StorageError):
    """File system integrity issue"""
    pass
```

---

## Error Response Format

### HTTP Error Response

```json
{
  "error": "ToolExecutionFailed",
  "error_code": "tool_execution_failed_001",
  "message": "Image generation tool returned error status",
  "details": {
    "stage": "character_design",
    "tool": "google_imagen",
    "tool_error": "Quota exceeded for today"
  },
  "remediation": "Retry tomorrow or switch to flux_image provider",
  "timestamp": "2026-07-10T14:30:00Z"
}
```

### SaathiOS Handling

```python
class ErrorHandler:
    """Translate OpenMontage errors to SaathiOS actions"""
    
    @staticmethod
    def handle_error(error: Exception) -> Dict:
        """
        Returns:
        {
          "error_type": "tool_execution_failed",
          "user_message": "Image generation failed. Retrying with different provider...",
          "action": "retry" | "escalate" | "fallback" | "cancel",
          "logs": [...error details...]
        }
        """
        raise OpenMontageExecutionDisabled(
            "OpenMontage execution is unavailable during Stage 1."
        )
    
    @staticmethod
    def is_retriable(error: Exception) -> bool:
        """True if error should trigger automatic retry"""
        retriable = [
            ProviderRateLimited,
            ServiceTimeout,
            ToolTimeout
        ]
        return type(error) in retriable
    
    @staticmethod
    def escalate_to_human(error: Exception, stage: str) -> Dict:
        """Require human intervention"""
        raise OpenMontageExecutionDisabled(
            "OpenMontage execution is unavailable during Stage 1."
        )
```

---

## Error Recovery Strategies

| Error | Retriable | Fallback | Escalate |
|-------|-----------|----------|----------|
| ProviderRateLimited | ✅ Yes (with backoff) | ✅ Try alternate provider | ❌ |
| ProviderAuthError | ❌ No | ❌ Check credentials | ✅ |
| ServiceUnavailable | ✅ Yes (connection) | ❌ | ✅ Alert ops |
| ApprovalRequired | ❌ No | ❌ Await human decision | ✅ |
| BudgetExceeded | ❌ No | ❌ Increase budget | ✅ |
| ToolTimeout | ✅ Yes (retry) | ✅ Increase timeout | ✅ |
| RenderCrashed | ✅ Yes (retry) | ✅ Try different runtime | ✅ |
| ApprovalRejected | ❌ No | ✅ Human sends back with feedback | ✅ |

---

## Error Codes (Reference)

Format: `<category>_<type>_<number>`

```
config_*
  - config_service_not_configured_001
  - config_credentials_missing_001
  - config_pipeline_not_found_001

service_*
  - service_unavailable_001
  - service_timeout_001
  - service_internal_error_001

project_*
  - project_not_found_001
  - project_already_exists_001
  - project_quota_exceeded_001

stage_*
  - stage_failed_001
  - stage_timeout_001
  - stage_approval_rejected_001

tool_*
  - tool_not_available_001
  - tool_execution_failed_001
  - tool_timeout_001

provider_*
  - provider_auth_error_001
  - provider_rate_limited_001
  - provider_unavailable_001

budget_*
  - budget_approval_required_001
  - budget_exceeded_001

data_*
  - data_checkpoint_missing_001
  - data_artifact_validation_error_001

render_*
  - render_oom_001
  - render_crashed_001
  - render_non_deterministic_001

storage_*
  - storage_not_writable_001
  - storage_quota_exceeded_001
```

---

## Stage 1 Status

✅ Error taxonomy defined  
✅ Error hierarchy (base → specific)  
✅ Recovery strategies documented  

❌ ErrorHandler implementation: Stage 2  
❌ Automatic retry logic: Stage 2  
❌ Error alerting: Stage 2  

---

**Error Handling:** Deferred to Stage 2  
**For now:** All execution raises OpenMontageExecutionDisabled
