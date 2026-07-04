"""Workflows — site-specific sequences of generic primitives.

The Browser Driver never imports a site; a Connector picks a Workflow, the
Workflow drives the primitives. Add a site = add a workflow + a page object.
"""
from .youtube_upload import YouTubeUploadWorkflow
from .linkedin_post import LinkedInPostWorkflow
from .tiktok_upload import TikTokUploadWorkflow

WORKFLOWS = {
    "youtube_upload": YouTubeUploadWorkflow,
    "linkedin_post": LinkedInPostWorkflow,
    "tiktok_upload": TikTokUploadWorkflow,
}

__all__ = ["YouTubeUploadWorkflow", "LinkedInPostWorkflow", "TikTokUploadWorkflow", "WORKFLOWS"]
