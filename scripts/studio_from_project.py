#!/usr/bin/env python3
"""Produce AI Studio content for a client project — the Intake → AI Studio wire.

Pulls a project's strategy content ideas (studio-topics) and runs AIStudio for
each, tagging every run with the project so its videos, confidence, and cost roll
up to that client. Mac-side (generation + browser publish live here).

  export SAATHI_BASE_URL=https://140-245-193-190.nip.io
  export CHROME_CDP_URL=http://localhost:9222
  .venv/bin/python scripts/studio_from_project.py <project_id> [--limit 3] [--generate]
"""
import os
import sys

sys.path.insert(0, os.path.expanduser("~/SaathiAI"))

import httpx  # noqa: E402
from saathi.ai_studio import AIStudio  # noqa: E402
from saathi.run_manager import default_manager  # noqa: E402


def main():
    if len(sys.argv) < 2:
        print("usage: studio_from_project.py <project_id> [--limit N] [--generate]"); return 2
    pid = sys.argv[1]
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else 3
    generate = "--generate" in sys.argv
    base = os.getenv("SAATHI_BASE_URL", "http://localhost:8765")

    plan = httpx.get(f"{base}/api/v1/intake/projects/{pid}/studio-topics", timeout=30).json()
    topics = (plan.get("topics") or [])[:limit]
    print(f"▶ {plan.get('project','?')} — {len(topics)} topic(s). Direction: {plan.get('direction','')[:80]}")
    if not topics:
        print("no topics — run AI research on the project first."); return 1

    studio = AIStudio(run_manager=default_manager() if generate else None)
    for i, topic in enumerate(topics, 1):
        print(f"\n[{i}/{len(topics)}] {topic}")
        run = studio.run(topic=topic, mode="assisted", approver="Ajay",
                         confidence_threshold=0.7, generate=generate,
                         run_prefix="CLIENT", project_id=pid)
        print(f"  status {run.status} · confidence {run.overall_confidence} · "
              f"cost ${run.cost_total:.2f}" + (f" · {run.video_url}" if run.video_url else ""))
        token = os.getenv("SAATHI_TOKEN")
        if token and base != "http://localhost:8765":   # sync to the VM dashboard
            try:
                httpx.post(f"{base}/api/v1/studio/report", headers={"x-saathi-token": token},
                           json=run.as_dict(), timeout=20)
            except Exception:
                pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
