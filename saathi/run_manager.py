"""Run Manager + Artifact Workspace — the reproducibility backbone.

Every automated run (AI Studio video, HCG signal, cafeteria report, itinerary)
gets a Run ID and an owned workspace. Subsystems receive only the `Run` and ask
it where to save/read artifacts — no module knows the folder layout. Each stage
records a timeline entry and can verify its expected output exists, so a missing
artifact becomes a structured failure instead of a silent gap.

    rm = RunManager()
    run = rm.new_run(prefix="PAT")           # runs/PAT-20260705-001/
    run.stage_start("research")
    run.save_text("research.md", notes)
    run.stage_end("research", ok=run.verify("research.md"), artifact="research.md")
    ...
    run.finalize("published")                # writes run.json manifest

Filesystem, deterministic, no external deps. Workspace root defaults to
`$SAATHI_RUNS_DIR` or `~/SaathiAI/runs` (git-ignored, inspectable).
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path


def _root() -> Path:
    env = os.getenv("SAATHI_RUNS_DIR")
    if env:
        return Path(env).expanduser()
    return Path(os.path.expanduser("~/SaathiAI/runs"))


@dataclass
class Run:
    id: str
    dir: Path
    prefix: str
    created: float = field(default_factory=time.time)
    timeline: list[dict] = field(default_factory=list)
    status: str = "in_progress"

    # ── artifact I/O — callers never build paths themselves ──
    def path(self, name: str) -> Path:
        p = self.dir / name
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def save_text(self, name: str, text: str) -> Path:
        p = self.path(name)
        p.write_text(text if isinstance(text, str) else str(text), encoding="utf-8")
        return p

    def save_json(self, name: str, obj) -> Path:
        return self.save_text(name, json.dumps(obj, indent=2, default=str))

    def save_bytes(self, name: str, data: bytes) -> Path:
        p = self.path(name)
        p.write_bytes(data)
        return p

    def adopt(self, name: str, src: str) -> Path:
        """Copy an externally-produced file into the workspace under `name`."""
        import shutil
        p = self.path(name)
        shutil.copyfile(src, p)
        return p

    def subdir(self, name: str) -> Path:
        d = self.dir / name
        d.mkdir(parents=True, exist_ok=True)
        return d

    def exists(self, name: str) -> bool:
        return (self.dir / name).exists()

    def verify(self, name: str) -> bool:
        """An artifact counts only if it exists AND is non-empty."""
        p = self.dir / name
        try:
            if p.is_dir():
                return any(p.iterdir())
            return p.exists() and p.stat().st_size > 0
        except OSError:
            return False

    # ── timeline ──
    def stage_start(self, name: str) -> None:
        self.timeline.append({"stage": name, "started": time.time(),
                              "finished": None, "ok": None, "artifact": None, "note": ""})

    def stage_end(self, name: str, ok: bool, artifact: str | None = None, note: str = "") -> None:
        for e in reversed(self.timeline):
            if e["stage"] == name and e["finished"] is None:
                e.update(finished=time.time(), ok=bool(ok), artifact=artifact, note=note)
                return
        # stage_end without a start — still record it
        self.timeline.append({"stage": name, "started": time.time(), "finished": time.time(),
                              "ok": bool(ok), "artifact": artifact, "note": note})

    def artifacts(self) -> dict:
        """name → verified? for every artifact any stage claimed to produce."""
        out = {}
        for e in self.timeline:
            if e.get("artifact"):
                out[e["artifact"]] = self.verify(e["artifact"])
        return out

    def stage_flags(self) -> dict:
        """stage → ok, in timeline order — what the Factory card renders."""
        return {e["stage"]: e["ok"] for e in self.timeline if e["ok"] is not None}

    def manifest(self) -> dict:
        return {"id": self.id, "prefix": self.prefix, "status": self.status,
                "created": self.created, "finished": time.time(),
                "timeline": self.timeline, "artifacts": self.artifacts()}

    def finalize(self, status: str) -> dict:
        self.status = status
        m = self.manifest()
        self.save_json("run.json", m)
        return m

    def archive(self) -> Path:
        import shutil
        dest = self.dir.parent / "archive" / self.id
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            shutil.rmtree(dest)
        shutil.move(str(self.dir), str(dest))
        self.dir = dest
        return dest


class RunManager:
    def __init__(self, root: str | Path | None = None):
        self.root = Path(root).expanduser() if root else _root()
        self.root.mkdir(parents=True, exist_ok=True)

    def new_run(self, prefix: str = "RUN", now: float | None = None) -> Run:
        now = now or time.time()
        day = time.strftime("%Y%m%d", time.localtime(now))
        stem = f"{prefix}-{day}-"
        existing = [p.name for p in self.root.glob(f"{stem}*") if p.is_dir()]
        seq = 1
        for n in existing:
            try:
                seq = max(seq, int(n.rsplit("-", 1)[1]) + 1)
            except (ValueError, IndexError):
                continue
        rid = f"{stem}{seq:03d}"
        d = self.root / rid
        d.mkdir(parents=True, exist_ok=True)
        return Run(id=rid, dir=d, prefix=prefix, created=now)

    def get(self, run_id: str) -> Run | None:
        d = self.root / run_id
        if not d.is_dir():
            return None
        run = Run(id=run_id, dir=d, prefix=run_id.split("-", 1)[0])
        mf = d / "run.json"
        if mf.exists():
            try:
                m = json.loads(mf.read_text())
                run.timeline = m.get("timeline", [])
                run.status = m.get("status", "in_progress")
                run.created = m.get("created", run.created)
            except (json.JSONDecodeError, OSError):
                pass
        return run

    def recent(self, limit: int = 15) -> list[dict]:
        dirs = sorted([p for p in self.root.glob("*-*-*") if p.is_dir()],
                      key=lambda p: p.stat().st_mtime, reverse=True)[:limit]
        out = []
        for d in dirs:
            run = self.get(d.name)
            if run:
                out.append(run.manifest())
        return out


_default = None
def default_manager() -> RunManager:
    global _default
    if _default is None:
        _default = RunManager()
    return _default
