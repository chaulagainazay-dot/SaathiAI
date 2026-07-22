"""M13 AI Studio — canonical Project state machine + Artifact model.

Studio never forks the orchestrator, memory, approvals, or gateway: workflows
run on the M10 Orchestrator, provider/FFmpeg calls go through ExecutionGateway,
approvals resolve through the M10 approval store.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


class ProjectState(str, Enum):
    DRAFT = "draft"
    PLANNING = "planning"
    RUNNING = "running"
    AWAITING_REVIEW = "awaiting_review"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    RENDERING = "rendering"
    EXPORTING = "exporting"
    PUBLISHING = "publishing"
    COMPLETED = "completed"
    PARTIALLY_COMPLETED = "partially_completed"
    PAUSED = "paused"
    CANCELLED = "cancelled"
    FAILED = "failed"
    ARCHIVED = "archived"


_TERMINAL = {ProjectState.COMPLETED, ProjectState.CANCELLED, ProjectState.FAILED,
             ProjectState.ARCHIVED, ProjectState.PARTIALLY_COMPLETED}

_TRANSITIONS: dict[ProjectState, set[ProjectState]] = {
    ProjectState.DRAFT: {ProjectState.PLANNING, ProjectState.CANCELLED, ProjectState.ARCHIVED},
    ProjectState.PLANNING: {ProjectState.RUNNING, ProjectState.AWAITING_REVIEW,
                            ProjectState.PAUSED, ProjectState.CANCELLED, ProjectState.FAILED},
    ProjectState.RUNNING: {ProjectState.AWAITING_REVIEW, ProjectState.AWAITING_APPROVAL,
                           ProjectState.RENDERING, ProjectState.PAUSED, ProjectState.FAILED,
                           ProjectState.CANCELLED, ProjectState.PARTIALLY_COMPLETED,
                           ProjectState.COMPLETED},
    ProjectState.AWAITING_REVIEW: {ProjectState.RUNNING, ProjectState.AWAITING_APPROVAL,
                                   ProjectState.CANCELLED, ProjectState.FAILED},
    ProjectState.AWAITING_APPROVAL: {ProjectState.APPROVED, ProjectState.RUNNING,
                                     ProjectState.CANCELLED, ProjectState.FAILED},
    ProjectState.APPROVED: {ProjectState.RENDERING, ProjectState.EXPORTING,
                            ProjectState.PUBLISHING, ProjectState.CANCELLED},
    ProjectState.RENDERING: {ProjectState.EXPORTING, ProjectState.AWAITING_REVIEW,
                             ProjectState.COMPLETED, ProjectState.FAILED,
                             ProjectState.PARTIALLY_COMPLETED, ProjectState.CANCELLED},
    ProjectState.EXPORTING: {ProjectState.PUBLISHING, ProjectState.COMPLETED,
                             ProjectState.FAILED, ProjectState.CANCELLED},
    ProjectState.PUBLISHING: {ProjectState.COMPLETED, ProjectState.PARTIALLY_COMPLETED,
                              ProjectState.FAILED, ProjectState.CANCELLED},
    ProjectState.PAUSED: {ProjectState.RUNNING, ProjectState.CANCELLED, ProjectState.ARCHIVED},
    ProjectState.COMPLETED: {ProjectState.ARCHIVED},
    ProjectState.PARTIALLY_COMPLETED: {ProjectState.RUNNING, ProjectState.ARCHIVED,
                                       ProjectState.CANCELLED},
    ProjectState.FAILED: {ProjectState.RUNNING, ProjectState.ARCHIVED, ProjectState.CANCELLED},
    ProjectState.CANCELLED: {ProjectState.ARCHIVED},
    ProjectState.ARCHIVED: set(),
}


def is_terminal(state: ProjectState) -> bool:
    return state in _TERMINAL


def can_transition(src: ProjectState, dst: ProjectState) -> bool:
    return dst in _TRANSITIONS.get(src, set())


class IllegalProjectTransition(Exception):
    pass


def validate_transition(src: ProjectState, dst: ProjectState) -> None:
    if not can_transition(src, dst):
        raise IllegalProjectTransition(f"illegal transition {src.value} → {dst.value}")


ARTIFACT_TYPES = {
    "research_report", "source_citation", "content_brief", "outline", "script",
    "script_version", "scene", "storyboard", "image", "video_clip", "avatar_clip",
    "voice_clip", "music_track", "sound_effect", "subtitle_file", "caption_track",
    "thumbnail", "seo_package", "social_caption", "blog_post", "render_manifest",
    "final_video", "export_package", "publishing_receipt", "analytics_snapshot",
}


class ArtifactStatus(str, Enum):
    PENDING = "pending"
    GENERATING = "generating"
    READY = "ready"
    FAILED = "failed"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


@dataclass
class ProjectSpec:
    title: str = ""
    objective: str = ""
    brand: str = ""
    audience: str = ""
    language: str = "en"
    platforms: list[str] = field(default_factory=lambda: ["youtube"])
    aspect_ratios: list[str] = field(default_factory=lambda: ["16:9"])
    content_type: str = "short_video"   # script_only|social_post|short_video|long_video|avatar|repurpose
    duration_target_sec: int = 60
    workflow: str = ""
    providers: dict = field(default_factory=dict)
    budget_usd: float = 5.0
    deadline: Optional[float] = None
    approval_policy: str = "review_then_approve"

    def to_dict(self) -> dict:
        return asdict(self)


# Studio agent roles added to the M10 registry (not a new agent system).
STUDIO_AGENTS = (
    "content_strategist", "script_writer", "storyboard_agent", "visual_director",
    "image_agent", "video_agent", "voice_agent", "editor", "subtitle_agent",
    "thumbnail_agent", "seo_agent", "publisher", "analytics_agent",
    "brand_reviewer", "compliance_reviewer",
)
