#!/usr/bin/env python3
"""Production Acceptance Test (PAT) — the daily certification loop for v0.4.1.

Certifies the WHOLE factory, not just publishing. Every run gets a Run ID and an
owned workspace (runs/PAT-YYYYMMDD-NNN/) with one artifact per stage, so the chain
research → script → voice → assets → render → metadata → gate → publish →
analytics → learning is exercised and each stage's ✓/✗ is inspectable.

Safe test lane:
  • uploads are Unlisted (default_publisher forces it)
  • title is prefixed "[PAT]" so test videos are unmistakable on the channel
    (create a "PAT / test" playlist in YouTube Studio and drag them in)
  • voice/assets stages are honest: until a TTS/image provider is configured they
    show ✗, and the run falls back to an optional clip so the publish half still
    certifies. Render is the hard gate — no renderer AND no clip → render_failed.

Only merge milestone/m5.1-infrastructure → master when every checklist line is ✅
several days running.

  export CHROME_CDP_URL=http://localhost:9222
  export SAATHI_BASE_URL=https://140-245-193-190.nip.io ; export SAATHI_TOKEN=<vm token>
  .venv/bin/python scripts/pat_run.py "past perfect tense" [optional-fallback-clip.mp4]
"""
import os
import sys
import time

sys.path.insert(0, os.path.expanduser("~/SaathiAI"))

from saathi.ai_studio import AIStudio, default_metadata  # noqa: E402
from saathi.run_manager import default_manager  # noqa: E402
from saathi.infrastructure.human_browser.run_store import default_store  # noqa: E402


def _pat_metadata(topic: str) -> dict:
    m = default_metadata(topic)
    m["title"] = f"[PAT] {m['title']}"[:100]
    return m


def _report(run, topic, t0):
    base, token = os.getenv("SAATHI_BASE_URL"), os.getenv("SAATHI_TOKEN")
    ok = run.status == "published"
    url = getattr(run, "video_url", "")
    default_store().record(workflow="pat", capability="publish_video", title=topic,
                           ok=ok, error="" if ok else run.status, video_url=url,
                           duration_ms=round((time.time() - t0) * 1000), started=t0)
    if base and token:
        import httpx
        h = {"x-saathi-token": token}
        httpx.post(f"{base}/api/v1/human/report-run", headers=h,
                   json={"workflow": "pat", "capability": "publish_video", "title": topic,
                         "ok": ok, "error": "" if ok else run.status, "video_url": url,
                         "duration_ms": round((time.time() - t0) * 1000), "started": t0}, timeout=20)
        try:  # sync the full run → VM dashboard (one system)
            httpx.post(f"{base}/api/v1/studio/report", headers=h, json=run.as_dict(), timeout=20)
        except Exception:
            pass


def _checklist(run):
    published = run.status == "published"
    print("\n── PAT merge-checklist evidence ──")
    for label, val in [
        ("AIStudio.run() completed", run.status in {"published", "awaiting_approval"}),
        ("Video published end-to-end", published),
        ("Confidence recorded", run.overall_confidence > 0),
        ("Cost recorded", run.cost_total >= 0),
        ("Failure recommendation useful", run.failure is None or "recommendation" in run.failure),
    ]:
        print(f"  {'✅' if val else '❌'} {label}")
    print("  (verify manually in the evening: Episodes generated · Executive briefing "
          "updated · CEO dashboard reflects reality · queue moved)")


def main():
    if len(sys.argv) < 2:
        print("usage: pat_run.py <topic> [fallback-clip.mp4]"); return 2
    topic = sys.argv[1]
    clip = os.path.expanduser(sys.argv[2]) if len(sys.argv) > 2 else None
    t0 = time.time()
    print(f"▶ PAT [assisted · Unlisted · full chain]: '{topic}'")
    studio = AIStudio(metadata_gen=_pat_metadata, run_manager=default_manager())
    run = studio.run(topic=topic, video_path=clip, platforms=["youtube"], mode="assisted",
                     approver="Ajay", confidence_threshold=0.7, thumbnail=clip,
                     generate=True, run_prefix="PAT")
    print(f"\nRun {run.run_id}  ·  status {run.status}  ·  confidence {run.overall_confidence}  ·  "
          f"cost ${run.cost_total:.2f}  ·  time {run.duration_ms/1000:.0f}s")
    for s in run.stages:
        print(f"  {s.stage:10} conf {s.confidence:<5} {s.duration_ms:>6}ms  ${s.cost:.2f}  "
              f"{'✓' if s.ok else '✗'} {', '.join(s.reasons)[:60]}")
    if run.failure:
        print(f"  ✗ {run.failure['stage']}: {run.failure['reason']} → {run.failure['recommendation']}")
    if run.video_url:
        print("  → published:", run.video_url)
    _report(run, topic, t0)
    _checklist(run)
    return 0 if run.status == "published" else 1


if __name__ == "__main__":
    raise SystemExit(main())
