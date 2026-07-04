#!/usr/bin/env python3
"""AI Studio — one autonomous run (Mac-side): topic → real AI metadata →
Discovery Gate → publish via your logged-in Chrome → report to the dashboard.

  export CHROME_CDP_URL=http://localhost:9222
  export SAATHI_BASE_URL=https://140-245-193-190.nip.io ; export SAATHI_TOKEN=<vm token>
  .venv/bin/python scripts/ai_studio_run.py "past perfect tense" ~/SaathiAI/queue/youtube/clip.mp4 youtube
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.expanduser("~/SaathiAI"))

from saathi.ai_studio import AIStudio  # noqa: E402
from saathi.infrastructure.human_browser.run_store import default_store  # noqa: E402


def _report(run, topic, platforms, t0):
    base, token = os.getenv("SAATHI_BASE_URL"), os.getenv("SAATHI_TOKEN")
    ok = run.status == "published"
    url = ""
    if run.published:
        url = (run.published[0].get("result") or {}).get("video_url", "")
    default_store().record(workflow="ai_studio", capability="publish_video", title=topic,
                           ok=ok, error="" if ok else run.status, video_url=url,
                           duration_ms=round((time.time() - t0) * 1000), started=t0)
    if base and token:
        import httpx
        httpx.post(f"{base}/api/v1/human/report-run", headers={"x-saathi-token": token},
                   json={"workflow": "ai_studio", "capability": "publish_video", "title": topic,
                         "ok": ok, "error": "" if ok else run.status, "video_url": url,
                         "duration_ms": round((time.time() - t0) * 1000), "started": t0}, timeout=20)


def main():
    if len(sys.argv) < 3:
        print("usage: ai_studio_run.py <topic> <video_path> [platform ...]"); return 2
    topic, video = sys.argv[1], os.path.expanduser(sys.argv[2])
    platforms = sys.argv[3:] or ["youtube"]
    t0 = time.time()
    print(f"▶ AI Studio: '{topic}' → {platforms}  (generating metadata, gating, publishing…)")
    studio = AIStudio()
    run = studio.run(topic=topic, video_path=video, platforms=platforms,
                     approver="Ajay", thumbnail=video)   # thumbnail=video satisfies the gate; swap for a real one
    print("status:", run.status)
    if run.gate_blockers:
        print("gate blockers:", run.gate_blockers)
    for p in run.published:
        print(f"  {p['platform']}: {'✓' if p['ok'] else '✗'} {p.get('result', {}).get('video_url', p.get('result'))}")
    _report(run, topic, platforms, t0)
    return 0 if run.status == "published" else 1


if __name__ == "__main__":
    raise SystemExit(main())
