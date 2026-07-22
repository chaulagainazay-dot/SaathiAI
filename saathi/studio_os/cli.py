"""M13 AI Studio CLI — `python -m saathi.studio_os.cli <cmd>`.

  inspect / health        storage + provider matrix (read-only)
  projects                list projects (read-only)
  providers               provider capability matrix (read-only)
  storage                 storage health (read-only)
  costs <project-id>      cost summary (read-only)
  stages <project-id>     stage list (read-only)
  artifacts <project-id>  artifact list (read-only)
  render-smoke            REAL local ffmpeg render smoke (writes to a temp
                          project, labeled real vs unavailable)
  publish <project-id> <platform>   approval-enforced (refuses without approval)

Exit codes: 0 ok · 1 unavailable/failed · 2 bad command · 3 approval required.
Read-only commands never mutate. Publish enforces approval.
"""
from __future__ import annotations

import json
import sys

from saathi.studio_os.store import default_store
from saathi.studio_os import storage as S
from saathi.studio_os import providers as P
from saathi.studio_os import ffmpeg_engine as F
from saathi.studio_os import publishing as PUB

EXIT_OK, EXIT_FAIL, EXIT_BAD, EXIT_APPROVAL = 0, 1, 2, 3


def _emit(o) -> None:
    print(json.dumps(o, indent=1, default=str))


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print(__doc__)
        return EXIT_OK
    cmd, *rest = argv
    st = default_store()

    if cmd in ("inspect", "health"):
        _emit({"storage": S.storage_health(), "providers": P.capability_matrix()})
        return EXIT_OK
    if cmd == "providers":
        _emit(P.capability_matrix())
        return EXIT_OK
    if cmd == "storage":
        h = S.storage_health()
        _emit(h)
        return EXIT_OK if h["healthy"] else EXIT_FAIL
    if cmd == "projects":
        _emit({"projects": st.list_projects(limit=50)})
        return EXIT_OK
    if cmd in ("costs", "stages", "artifacts") and rest:
        pid = rest[0]
        if not st.get_project(pid):
            _emit({"error": "project not found"}); return EXIT_BAD
        if cmd == "costs":
            _emit(st.cost_summary(pid))
        elif cmd == "stages":
            _emit({"stages": st.list_stages(pid)})
        else:
            _emit({"artifacts": st.list_artifacts(pid)})
        return EXIT_OK
    if cmd == "render-smoke":
        import tempfile, os
        avail = F.ffmpeg_available()
        if not avail:
            _emit({"layer": "unavailable", "detail": "ffmpeg/ffprobe not installed"})
            return EXIT_FAIL
        r = F.render_slate("cli_smoke", text="SaathiOS", duration_sec=1.0,
                          width=320, height=240)
        _emit({"layer": "real local ffmpeg render", "ok": r.ok,
               "duration_sec": r.duration_sec, "size_bytes": r.size_bytes,
               "ms": round(r.duration_ms)})
        return EXIT_OK if r.ok else EXIT_FAIL
    if cmd == "publish" and len(rest) >= 2:
        pid, platform = rest[0], rest[1]
        if not st.get_project(pid):
            _emit({"error": "project not found"}); return EXIT_BAD
        try:
            # CLI never auto-approves — approval must be recorded first
            r = PUB.publish(st, pid, platform=platform, owner=st.get_project(pid)["owner"],
                            approved=False, live=False)
            _emit({"status": r.status, "detail": r.detail})
            return EXIT_OK
        except PUB.NotApproved:
            _emit({"error": "approval required before publish"})
            return EXIT_APPROVAL
        except (PUB.NoPublishableArtifact, PermissionError) as exc:
            _emit({"error": str(exc)}); return EXIT_FAIL

    print(f"unknown command: {cmd}\n{__doc__}")
    return EXIT_BAD


if __name__ == "__main__":
    raise SystemExit(main())
