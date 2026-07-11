"""M13 AI Studio — idea → reviewed, exportable, optionally published content.

Reuses M10 (orchestration/approvals), M9 (memory/learning), M12 (voice/TTS),
ExecutionGateway (all provider/FFmpeg calls), and the event bus. Real local
media: Pillow images, FFmpeg render/probe/thumbnail, macOS `say` narration.
Cloud generation and real publishing are honest deterministic/dry-run paths.
"""
from saathi.studio_os.models import (
    ProjectState, ProjectSpec, ArtifactStatus, validate_transition,
    can_transition, is_terminal, IllegalProjectTransition, ARTIFACT_TYPES,
    STUDIO_AGENTS,
)
from saathi.studio_os.store import StudioStore, default_store
from saathi.studio_os.service import StudioService, default_service, WORKFLOWS, WorkflowOutcome
from saathi.studio_os import storage, ffmpeg_engine, providers, budget, publishing, agents

__all__ = [
    "ProjectState", "ProjectSpec", "ArtifactStatus", "validate_transition",
    "can_transition", "is_terminal", "IllegalProjectTransition", "ARTIFACT_TYPES",
    "STUDIO_AGENTS", "StudioStore", "default_store", "StudioService",
    "default_service", "WORKFLOWS", "WorkflowOutcome", "storage", "ffmpeg_engine",
    "providers", "budget", "publishing", "agents",
]
