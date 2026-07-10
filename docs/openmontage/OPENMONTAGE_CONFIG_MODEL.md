# OpenMontage Configuration Model for SaathiOS

**Date:** 2026-07-10  
**Status:** Contracts defined (M5.2 implementation)  

---

## Configuration Sources (Merge Order)

1. **Defaults** (lib/config_model.py hardcoded)
2. **config.yaml** (repo root)
3. **.env** (environment variables, overrides config.yaml)
4. **Runtime parameters** (API call, overrides everything)

---

## SaathiOS Config

```yaml
# /Users/macbookpro/SaathiAI/config/openmontage.yaml

openmontage:
  service_url: "http://localhost:8000"
  
  credentials:
    # Stage 1: disabled; providers only loaded via .env
    load_from_env: true
    env_file: /Users/macbookpro/.env
  
  pipelines:
    character_animation:
      enabled: true
      budget_default_usd: 2.0
      timeout_minutes: 30
      max_revisions: 3
      
      # Brand playbook for Mr. Yeti
      custom_playbook:
        character_name: "Mr. Yeti"
        colors:
          primary: "#6C3FCF"
          accent: "#00BFA5"
          background: "#1a1a2e"
        tone: "educational"
        style: "friendly"
  
  providers:
    # Provider preferences + fallback chain
    image_generation:
      primary: "google_imagen"
      fallback: ["flux_image", "openai_image"]
      enabled: true
    
    video_generation:
      primary: "hyperframes"  # Local rendering
      fallback: []
      enabled: true
    
    tts:
      primary: "google_tts"
      fallback: ["piper_local", "elevenlabs"]
      enabled: true
    
    stock_media:
      primary: "pexels"
      fallback: ["pixabay", "unsplash"]
      enabled: true
      always_free: true
  
  cost:
    mode: "warn"  # observe | warn | cap
    budget_default_usd: 2.0
    approval_threshold_usd: 0.50
    reserve_pct: 0.10  # Hold back 10% for overruns
  
  render:
    default_runtime: "hyperframes"
    output_format: "mp4"
    resolution: "1920x1080"
    fps: 30
    codec: "h264"
  
  storage:
    projects_dir: "/opt/openmontage/projects"
    max_disk_usage_percent: 85
    cleanup_orphaned_after_days: 30
  
  monitoring:
    health_check_interval_seconds: 60
    log_level: "info"
    enable_prometheus_metrics: true
```

---

## Pydantic Config Models

```python
from pydantic import BaseModel, Field
from typing import Dict, List, Literal, Optional

class OpenMontageCredentialsConfig(BaseModel):
    """Credential loading strategy"""
    load_from_env: bool = True
    env_file: Optional[str] = None
    
    # Stage 1: No direct credential management
    # All credential access deferred to Stage 2

class OpenMontageProviderConfig(BaseModel):
    """Provider routing + preferences"""
    primary: str
    fallback: List[str] = []
    enabled: bool = True

class OpenMontageProvidersConfig(BaseModel):
    """All provider preferences"""
    image_generation: OpenMontageProviderConfig
    video_generation: OpenMontageProviderConfig
    tts: OpenMontageProviderConfig
    stock_media: OpenMontageProviderConfig

class OpenMontageBudgetConfig(BaseModel):
    """Budget + cost tracking"""
    mode: Literal["observe", "warn", "cap"] = "warn"
    budget_default_usd: float = 2.0
    approval_threshold_usd: float = 0.50
    reserve_pct: float = 0.10
    
    # Calculated
    @property
    def usable_budget_usd(self) -> float:
        holdback = self.budget_default_usd * self.reserve_pct
        return self.budget_default_usd - holdback

class OpenMontageRenderConfig(BaseModel):
    """Render output settings"""
    default_runtime: Literal["remotion", "hyperframes", "ffmpeg"] = "hyperframes"
    output_format: str = "mp4"
    resolution: str = "1920x1080"
    fps: int = 30
    codec: str = "h264"
    crf: int = 23  # Quality (0-51, lower=better)

class OpenMontageStorageConfig(BaseModel):
    """Storage + disk management"""
    projects_dir: str
    max_disk_usage_percent: float = 85.0
    cleanup_orphaned_after_days: int = 30

class OpenMontageMonitoringConfig(BaseModel):
    """Monitoring + logging"""
    health_check_interval_seconds: int = 60
    log_level: Literal["debug", "info", "warning", "error"] = "info"
    enable_prometheus_metrics: bool = False

class OpenMontagePlaybookConfig(BaseModel):
    """Custom brand playbook"""
    character_name: str
    colors: Dict[str, str]
    tone: str
    style: str

class OpenMontagePipelineConfig(BaseModel):
    """Pipeline-specific settings"""
    enabled: bool = True
    budget_default_usd: float = 2.0
    timeout_minutes: int = 30
    max_revisions: int = 3
    custom_playbook: Optional[OpenMontagePlaybookConfig] = None

class OpenMontageConfig(BaseModel):
    """Complete OpenMontage configuration"""
    service_url: str = "http://localhost:8000"
    credentials: OpenMontageCredentialsConfig
    pipelines: Dict[str, OpenMontagePipelineConfig] = {
        "character_animation": OpenMontagePipelineConfig()
    }
    providers: OpenMontageProvidersConfig
    cost: OpenMontageBudgetConfig
    render: OpenMontageRenderConfig
    storage: OpenMontageStorageConfig
    monitoring: OpenMontageMonitoringConfig
```

---

## Environment Variables

```bash
# .env (never committed)

# Service
OPENMONTAGE_SERVICE_URL=http://localhost:8000

# Google
GOOGLE_API_KEY=...
GOOGLE_CLOUD_PROJECT=my-project
GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json

# OpenAI
OPENAI_API_KEY=sk-...

# fal.ai (Flux, Kling, Recraft, etc.)
FAL_KEY=fal-...

# ElevenLabs
ELEVENLABS_API_KEY=...

# Runway
RUNWAY_API_KEY=...

# xAI Grok
XAI_API_KEY=...

# DashScope (Alibaba Qwen)
DASHSCOPE_API_KEY=...

# Volcano Engine (Doubao Speech)
DOUBAO_SPEECH_API_KEY=...

# Replicate (Seedance)
REPLICATE_API_TOKEN=...

# HuggingFace
HF_TOKEN=...

# Local models
VIDEO_GEN_LOCAL_ENABLED=true
VIDEO_GEN_LOCAL_MODEL=wan  # or hunyuan, cogvideo, ltx_local

# Modal (LTX-2 serverless)
MODAL_LTX2_ENDPOINT_URL=...

# Cost tracking
OPENMONTAGE_BUDGET_MODE=warn
OPENMONTAGE_BUDGET_USD=2.0
OPENMONTAGE_APPROVAL_THRESHOLD_USD=0.50
```

---

## Runtime Parameter Overrides

```python
# When invoking pipeline, pass overrides
POST /api/v1/projects
{
  "pipeline": "character-animation",
  "parameters": {...},
  
  # Override config for this run
  "config_overrides": {
    "budget_default_usd": 5.0,  # Increase for this project
    "render.resolution": "3840x2160",  # 4K for premium
    "render.default_runtime": "remotion"  # Force Remotion
  }
}
```

---

## SaathiOS Integration

```python
# In SaathiOS config manager
from pydantic import ConfigDict
from pathlib import Path

class SaathiOSOpenMontageConfig(BaseModel):
    """Bridge between SaathiOS + OpenMontage config"""
    
    model_config = ConfigDict(env_file=".env")
    
    # Load from YAML + env
    @staticmethod
    def load_from_yaml(path: Path) -> OpenMontageConfig:
        """Load config.yaml, merge with .env"""
        import yaml
        with open(path) as f:
            data = yaml.safe_load(f)
        
        # Merge with env vars (env overrides YAML)
        data = SaathiOSOpenMontageConfig._merge_env(data)
        
        return OpenMontageConfig(**data["openmontage"])
    
    @staticmethod
    def _merge_env(data: Dict) -> Dict:
        """Overlay .env variables onto YAML data"""
        import os
        
        # Map env var names to YAML paths
        env_map = {
            "OPENMONTAGE_SERVICE_URL": ("openmontage.service_url",),
            "OPENMONTAGE_BUDGET_USD": ("openmontage.cost.budget_default_usd",),
            "OPENMONTAGE_APPROVAL_THRESHOLD_USD": ("openmontage.cost.approval_threshold_usd",),
        }
        
        for env_var, yaml_path in env_map.items():
            if env_var in os.environ:
                value = os.environ[env_var]
                # Set nested key in data
                current = data
                for key in yaml_path[:-1]:
                    current = current.setdefault(key, {})
                current[yaml_path[-1]] = value
        
        return data
```

---

## Validation on Load

```python
class ConfigValidator:
    """Validate config before use"""
    
    @staticmethod
    def validate(config: OpenMontageConfig) -> List[str]:
        """
        Returns list of validation errors, or empty list if valid.
        Raises OpenMontageExecutionDisabled for Stage 1.
        """
        raise OpenMontageExecutionDisabled(
            "OpenMontage execution is unavailable during Stage 1."
        )
    
    @staticmethod
    def validate_service_reachable(service_url: str) -> bool:
        """Check if service is running"""
        raise OpenMontageExecutionDisabled(
            "OpenMontage execution is unavailable during Stage 1."
        )
    
    @staticmethod
    def validate_storage_writable(projects_dir: str) -> bool:
        """Check if projects directory is writable"""
        raise OpenMontageExecutionDisabled(
            "OpenMontage execution is unavailable during Stage 1."
        )
```

---

## Example: Mr. Yeti Brand Playbook

```yaml
# config/mr-yeti-playbook.yaml

character_name: "Mr. Yeti"

colors:
  primary: "#6C3FCF"      # Deep purple
  accent: "#00BFA5"       # Teal
  background: "#1a1a2e"   # Dark
  text: "#FFFFFF"         # White

character_description: |
  Friendly Yeti with white fur, round glasses, teacher suit.
  Warmth and encouragement in every gesture.

personality_traits:
  - friendly
  - educational
  - enthusiastic
  - supportive
  - patient

emotional_range:
  - happy
  - encouraging
  - thoughtful
  - surprised
  - curious

visual_style:
  tone: "professional yet playful"
  aesthetic: "minimalist flat design"
  camera: "warm, close-up, eye-level"

animation_preferences:
  default_runtime: "hyperframes"
  deterministic: true  # Same input = same video
  loop_safe: true      # Can loop without artifacts

constraints:
  max_personality_shift: 0.2  # 0-1, how much emotion can vary per scene
  brand_consistency_required: true
```

---

## Stage 2: Implementation

```python
# saathi/openmontage/config.py

def load_config() -> OpenMontageConfig:
    """Load config from YAML + env"""
    raise OpenMontageExecutionDisabled(
        "OpenMontage execution is unavailable during Stage 1."
    )

def validate_config(config: OpenMontageConfig) -> List[str]:
    """Validate before use"""
    raise OpenMontageExecutionDisabled(
        "OpenMontage execution is unavailable during Stage 1."
    )

def merge_config_overrides(config: OpenMontageConfig, 
                          overrides: Dict) -> OpenMontageConfig:
    """Apply runtime overrides"""
    raise OpenMontageExecutionDisabled(
        "OpenMontage execution is unavailable during Stage 1."
    )
```

---

**Status:** Config models locked (Stage 1)  
**Implementation:** Stage 2  
**File:** /Users/macbookpro/SaathiAI/config/openmontage.yaml
