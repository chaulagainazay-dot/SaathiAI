# OpenMontage Health Check Contract

**Date:** 2026-07-10  
**Status:** Contract defined (M5.2 implementation)  
**Scope:** Service health monitoring for SaathiOS observability  

---

## Health Check Endpoint

### GET /health

**Response (200 OK):**
```json
{
  "status": "healthy",
  "timestamp": "2026-07-10T14:30:00Z",
  "uptime_seconds": 86400,
  "version": "1.0.0",
  
  "services": {
    "backlot_server": {
      "status": "healthy",
      "response_time_ms": 12,
      "requests_per_second": 2.5
    },
    "tool_registry": {
      "status": "healthy",
      "tools_loaded": 128,
      "tools_available": 126
    }
  },
  
  "providers": {
    "google": {
      "status": "healthy",
      "last_call_ms": 450,
      "failed_calls_24h": 0
    },
    "openai": {
      "status": "healthy",
      "last_call_ms": 320,
      "failed_calls_24h": 0
    },
    "runway": {
      "status": "degraded",
      "last_call_ms": 5000,
      "failed_calls_24h": 3,
      "error": "Rate limit approaching"
    },
    "pexels": {
      "status": "healthy",
      "last_call_ms": 150,
      "failed_calls_24h": 0
    }
  },
  
  "storage": {
    "projects_dir": {
      "status": "healthy",
      "total_projects": 42,
      "disk_free_gb": 250,
      "disk_usage_percent": 35
    }
  },
  
  "credentials": {
    "status": "healthy",
    "env_keys_loaded": 18,
    "expired_keys": [],
    "expiring_soon": ["OPENAI_API_KEY (expires 2026-08-10)"]
  }
}
```

---

## Health Status Levels

| Status | Meaning | SaathiOS Action |
|--------|---------|-----------------|
| **healthy** | All systems OK | Proceed with pipeline |
| **degraded** | Some features limited (rate limits, slow) | Warn user, allow proceed with fallback |
| **unhealthy** | Critical failure (auth expired, service down) | Block pipeline, escalate to human |
| **unknown** | Can't determine status | Timeout after 5 seconds, treat as unhealthy |

---

## Per-Provider Health Model

```python
class ProviderHealth:
    """Health of one external provider"""
    
    name: str  # "google", "openai", "runway", etc.
    status: Literal["healthy", "degraded", "unhealthy"]
    
    # Metrics
    last_successful_call_at: datetime
    last_failed_call_at: Optional[datetime]
    failed_calls_24h: int
    
    # Rate limiting
    rate_limit_remaining: Optional[int]
    rate_limit_reset_at: Optional[datetime]
    
    # API errors
    latest_error: Optional[str]
    error_rate_percent: Optional[float]  # Failed / Total calls
    
    # Latency
    last_call_duration_ms: int
    avg_call_duration_ms_1h: int
    p95_call_duration_ms_1h: int
```

---

## Tool Registry Health

```python
class ToolRegistryHealth:
    """Health of tool discovery + loading"""
    
    status: Literal["healthy", "degraded", "unhealthy"]
    
    tools_total: int = 128
    tools_loaded: int  # Should equal 128
    tools_available: int  # Loaded - disabled
    tools_disabled: List[str] = []  # Tools disabled due to missing provider
    
    missing_providers: List[str]  # Providers not configured
    example:
    [
      "RUNWAY_API_KEY missing",
      "HEYGEN_API_KEY missing"
    ]
```

---

## Credential Health

```python
class CredentialHealth:
    """Health of API credentials (.env)"""
    
    status: Literal["healthy", "degraded", "unhealthy"]
    
    env_keys_loaded: int
    required_keys_missing: List[str] = []
    
    # For keys with expiry (e.g., service accounts)
    keys_expired: List[str] = []
    keys_expiring_soon: List[str] = []  # Within 7 days
    
    example_expiring:
    [
      "GOOGLE_SERVICE_ACCOUNT_KEY expires 2026-08-10",
      "OPENAI_API_KEY expires 2026-12-25"
    ]
```

---

## Storage Health

```python
class StorageHealth:
    """Health of projects/ directory"""
    
    status: Literal["healthy", "degraded", "unhealthy"]
    
    projects_dir_readable: bool
    projects_dir_writable: bool
    
    total_projects: int
    disk_free_gb: float
    disk_usage_percent: float  # 0-100
    
    warnings: List[str] = []
    example_warnings:
    [
      "Disk usage > 80%",
      "projects/proj-old is orphaned (no updates in 30 days)"
    ]
```

---

## SaathiOS Integration

### Polling Strategy

```python
class OpenMontageHealthMonitor:
    """Continuously monitor OpenMontage health"""
    
    def __init__(self, service_url: str, check_interval_seconds: int = 60):
        self.service_url = service_url
        self.check_interval = check_interval_seconds
        self.last_status = None
        self.last_check_time = None
    
    async def get_status(self) -> Dict:
        """
        Fetch health check from OpenMontage.
        Raises OpenMontageExecutionDisabled for Stage 1.
        """
        raise OpenMontageExecutionDisabled(
            "OpenMontage execution is unavailable during Stage 1."
        )
    
    async def start_background_monitor(self):
        """
        Periodically check health, log to SaathiOS observability.
        Raises OpenMontageExecutionDisabled for Stage 1.
        """
        raise OpenMontageExecutionDisabled(
            "OpenMontage execution is unavailable during Stage 1."
        )
    
    def should_allow_pipeline(self) -> bool:
        """
        True if OpenMontage healthy enough to start pipeline.
        
        Checks:
        - Backlot server: healthy
        - Tool registry: healthy
        - At least 3 image providers: healthy
        - At least 1 video provider: healthy
        - Storage: disk free > 10GB, usage < 90%
        - Credentials: no expired keys
        """
        if not self.last_status:
            return False  # Unknown state, block
        
        if self.last_status["status"] == "healthy":
            return True
        
        if self.last_status["status"] == "degraded":
            # Allow only if degradation is not critical
            # (e.g., one provider slow, not auth failure)
            return self._is_degradation_acceptable()
        
        return False  # Unhealthy, block
    
    def _is_degradation_acceptable(self) -> bool:
        """Check if degradation is acceptable (not auth/critical)"""
        for provider_name, provider_health in self.last_status["providers"].items():
            if provider_health["status"] == "unhealthy":
                if "auth" in provider_health.get("error", "").lower():
                    return False  # Auth failure is critical
        return True
```

### Dashboard Integration

```python
# In SaathiOS dashboard
class OpenMontageHealthWidget:
    """Display OpenMontage health in CEO dashboard"""
    
    def render(self) -> Dict:
        """
        Returns:
        {
          "status": "healthy" | "degraded" | "unhealthy",
          "summary": "All systems operational",
          "details": {
            "backlot_server": "healthy",
            "providers_healthy": 8,
            "providers_degraded": 1,
            "storage": "250GB free, 35% used"
          }
        }
        """
        raise OpenMontageExecutionDisabled(
            "OpenMontage execution is unavailable during Stage 1."
        )
```

### Alerting

```python
class OpenMontageHealthAlerts:
    """Alert SaathiOS to OpenMontage issues"""
    
    async def notify_status_change(self, old_status: str, new_status: str):
        """
        If status changes (e.g., healthy → degraded), notify.
        Raises OpenMontageExecutionDisabled for Stage 1.
        """
        raise OpenMontageExecutionDisabled(
            "OpenMontage execution is unavailable during Stage 1."
        )
    
    async def notify_credential_expiring(self, credential_name: str, days_until_expiry: int):
        """Alert admin about expiring API key"""
        raise OpenMontageExecutionDisabled(
            "OpenMontage execution is unavailable during Stage 1."
        )
    
    async def notify_provider_failure(self, provider_name: str, error: str):
        """Alert about provider failure (may trigger fallback)"""
        raise OpenMontageExecutionDisabled(
            "OpenMontage execution is unavailable during Stage 1."
        )
```

---

## Performance Baselines (Reference)

| Metric | Healthy | Degraded | Unhealthy |
|--------|---------|----------|-----------|
| Backlot server response time | <100ms | 100-500ms | >500ms |
| Tool registry load time | <500ms | 500-2000ms | >2000ms |
| Provider API latency (Google) | <1000ms | 1-5s | >5s |
| Provider API latency (OpenAI) | <2000ms | 2-10s | >10s |
| Failed calls 24h | 0 | <5 | >5 |
| Disk free | >50GB | 10-50GB | <10GB |
| Disk usage | <60% | 60-85% | >85% |

---

## Stage 2 Implementation

```python
# saathi/openmontage/health.py
class OpenMontageHealthCheck:
    
    async def check_health(self) -> HealthReport:
        # Implement full health check
        # Return detailed status
        pass
    
    async def verify_providers(self) -> Dict[str, ProviderHealth]:
        # Check each provider API
        # Detect auth errors, rate limits, latency
        pass
    
    async def verify_credentials(self) -> CredentialHealth:
        # Load .env, check for expired keys
        # Alert on expiring soon
        pass
    
    async def verify_storage(self) -> StorageHealth:
        # Check disk space, projects/ permissions
        pass
```

---

**Contract Status:** DEFINED  
**M5.2 Implementation:** Required before production character-animation  
**Monitoring:** Continuous background polling recommended

