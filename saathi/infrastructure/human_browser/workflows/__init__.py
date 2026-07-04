"""Workflows — site-specific sequences of generic primitives.

The Browser Driver never imports a site; a Connector picks a Workflow, the
Workflow drives the primitives. Add a site = add a workflow + a page object.
"""
from .youtube_upload import YouTubeUploadWorkflow

WORKFLOWS = {"youtube_upload": YouTubeUploadWorkflow}

__all__ = ["YouTubeUploadWorkflow", "WORKFLOWS"]
