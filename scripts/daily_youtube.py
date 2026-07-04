#!/usr/bin/env python3
"""Daily YouTube publisher (Mac-side) — publishes the next queued clip via your
logged-in Chrome (CDP), records it, and reports to the platform dashboard.

Setup (once):
  export CHROME_CDP_URL=http://localhost:9222   # your attached Chrome (see run_agent notes)
  export SAATHI_BASE_URL=https://140-245-193-190.nip.io
  export SAATHI_TOKEN=<VM token>                # to report the run to the dashboard
  mkdir -p ~/SaathiAI/queue/youtube

Queue a video:  drop clip.mp4 (+ optional clip.json {"title","description","visibility"})
                into ~/SaathiAI/queue/youtube/

Run:            .venv/bin/python scripts/daily_youtube.py
Schedule:       load scripts/com.saathi.daily-youtube.plist (launchd, 8pm daily)
"""
import json
import os
import sys

sys.path.insert(0, os.path.expanduser("~/SaathiAI"))

from saathi.infrastructure.human_browser import ChromeBackend, ProfileStore  # noqa: E402
from saathi.infrastructure.human_browser.run_store import default_store  # noqa: E402
from saathi.infrastructure.human_browser.daily import publish_next  # noqa: E402

QUEUE = os.path.expanduser("~/SaathiAI/queue/youtube")
PROFILE = "ajay/youtube"


def _publisher(*, path, title, description, visibility):
    be = ChromeBackend(ProfileStore())    # picks up CHROME_CDP_URL
    return be.execute("publish_video", profile=PROFILE, path=path, title=title,
                      description=description, visibility=visibility, no_vision=True)


def _reporter(run: dict):
    base, token = os.getenv("SAATHI_BASE_URL"), os.getenv("SAATHI_TOKEN")
    if not (base and token):
        return
    import httpx
    httpx.post(f"{base}/api/v1/human/report-run", headers={"x-saathi-token": token},
               json={k: run[k] for k in ("workflow", "capability", "title", "ok", "error",
                                         "video_url", "duration_ms", "started", "timeline")},
               timeout=20)


if __name__ == "__main__":
    result = publish_next(QUEUE, publisher=_publisher, store=default_store(), reporter=_reporter)
    print(json.dumps({k: result[k] for k in result if k != "timeline"}, indent=2, default=str))
