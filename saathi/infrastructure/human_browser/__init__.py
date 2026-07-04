"""Human Browser Driver — publish through your real, logged-in Chrome, safely.

Third execution mode after API and headless Browser. The VM signs jobs and drops
them on a queue; the Mac Agent (on your trusted machine) verifies and drives your
actual Chrome profile. Departments stay provider-agnostic; the Connector Registry
picks the mode by `best()` ranking (API ★ > Browser > Human), and your cookies
never leave the Mac.

    # VM side
    proxy = HumanBrowserProxy(queue, secret=SECRET)
    proxy.execute("publish_video", profile="ajay/youtube", path="clip.mp4")

    # Mac side (separate process)
    MacAgent(queue, ChromeBackend(), secret=SECRET).run_forever()
"""
from .jobs import HumanJob, sign, verify, NonceStore, JobError, BadSignature, JobExpired, JobReplayed
from .queue import JobQueue, InMemoryQueue, HttpQueueClient, Envelope, JobResult

# Process-wide queue shared by the VM proxy (producer) and the VM's
# /api/v1/human/* endpoints (which the remote Mac Agent polls).
default_queue = InMemoryQueue()
from .driver import HumanBrowser, CAPS
from .proxy import HumanBrowserProxy
from .agent import MacAgent
from .profiles import ProfileStore
from .chrome_backend import ChromeBackend
from .primitives import BrowserPrimitives, Step, BrowserActionError
from .workflows import (YouTubeUploadWorkflow, LinkedInPostWorkflow,
                        TikTokUploadWorkflow, WORKFLOWS)
from .keyed import KeyedBrowser
from .publish import publish
from .daily import publish_next, next_in_queue
from .vision_verifier import VisionVerifier, default_verifier
from .run_store import RunStore, default_store
from .selector_registry import SelectorRegistry, KnownSelector, default_registry as default_selector_registry
from .teach import TeachRequest, TeachCapture, learn_from_capture
from .teach_mode import TeachMode, TeachSession, TeachState, TeachSessionStore, default_teacher
from .teach_ai import suggest_selectors
from . import automation

__all__ = [
    "HumanJob", "sign", "verify", "NonceStore",
    "JobError", "BadSignature", "JobExpired", "JobReplayed",
    "JobQueue", "InMemoryQueue", "HttpQueueClient", "Envelope", "JobResult", "default_queue",
    "HumanBrowser", "CAPS", "HumanBrowserProxy", "MacAgent",
    "ProfileStore", "ChromeBackend",
    "BrowserPrimitives", "Step", "BrowserActionError",
    "YouTubeUploadWorkflow", "LinkedInPostWorkflow", "TikTokUploadWorkflow",
    "WORKFLOWS", "KeyedBrowser", "publish",
    "VisionVerifier", "default_verifier",
    "RunStore", "default_store", "automation",
    "SelectorRegistry", "KnownSelector", "default_selector_registry",
    "TeachRequest", "TeachCapture", "learn_from_capture",
    "TeachMode", "TeachSession", "TeachState", "TeachSessionStore",
    "default_teacher", "suggest_selectors",
]
