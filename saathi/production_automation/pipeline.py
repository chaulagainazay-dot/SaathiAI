"""Production Automation pipeline — ties the department together into a Production Plan.

Downstream of the Directors (Research→Creative→Script→Storyboard→Render): given a
scene package + render plan, it assigns a provider per scene (credit-aware, cost-
optimised), verifies character consistency, runs the quality gate, computes cost, and
applies the approval mode (auto / semi / manual). It emits a Production Plan manifest
— it decides and reserves, it does not itself call generation APIs (those are adapters).

    check credits → assign providers → verify character → quality gate → approval → queue
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

APPROVAL_MODES = ("auto", "semi", "manual")


def build_plan(scene_package: dict, *, render_plan: dict | None = None, script: dict | None = None,
               publish_plan: dict | None = None, bible: dict | None = None,
               approval_mode: str = "semi", reserve: bool = False) -> dict:
    from saathi.production_automation.scheduler import assign_scenes
    from saathi.production_automation.quality import verify_package, quality_gate
    from saathi.production_automation.credits import default_manager

    scenes = (scene_package or {}).get("scenes", [])
    n = len(scenes)

    sched = assign_scenes(n, kind="video", reserve=reserve)
    character = verify_package(scene_package, bible)
    gate = quality_gate(script=script, render_plan=render_plan, publish_plan=publish_plan,
                        character=character)

    cm = default_manager()
    credits = {p["name"]: {"remaining": p["remaining"], "unlimited": p["unlimited"],
                           "status": p["status"]} for p in cm.status()}

    ready = gate["passed"] and character["all_pass"]
    if approval_mode == "manual":
        action = "hold_for_manual"
    elif approval_mode == "semi":
        action = "notify_then_publish" if ready else "hold_needs_fix"
    else:  # auto
        action = "publish" if ready else "retry"

    return {
        "scene_count": n,
        "assignments": sched["assignments"],
        "providers_used": sched["providers_used"],
        "est_cost": sched["est_cost"],
        "character": {"avg_score": character["avg_score"], "rejected_scenes": character["rejected_scenes"],
                      "all_pass": character["all_pass"]},
        "quality_gate": gate,
        "credits": credits,
        "approval_mode": approval_mode if approval_mode in APPROVAL_MODES else "semi",
        "ready": ready,
        "action": action,
    }


# ── settings (approval mode) + production run log ─────────────────────────────
class ProductionStore:
    def __init__(self, db_path: str | None = None):
        self.db_path = Path(db_path) if db_path else (Path.home() / ".saathi" / "production_automation.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.execute("CREATE TABLE IF NOT EXISTS setting(key TEXT PRIMARY KEY, value TEXT)")
            c.execute("CREATE TABLE IF NOT EXISTS run(id TEXT PRIMARY KEY, episode TEXT, plan TEXT, created REAL)")

    def _conn(self):
        return sqlite3.connect(str(self.db_path))

    def approval_mode(self) -> str:
        with self._conn() as c:
            r = c.execute("SELECT value FROM setting WHERE key='approval_mode'").fetchone()
        return r[0] if r and r[0] in APPROVAL_MODES else "semi"

    def set_approval_mode(self, mode: str) -> bool:
        if mode not in APPROVAL_MODES:
            return False
        with self._conn() as c:
            c.execute("INSERT OR REPLACE INTO setting VALUES('approval_mode', ?)", (mode,))
        return True

    def log_run(self, episode: str, plan: dict) -> str:
        import uuid
        rid = uuid.uuid4().hex[:12]
        with self._conn() as c:
            c.execute("INSERT INTO run VALUES(?,?,?,?)", (rid, episode, json.dumps(plan), time.time()))
        return rid

    def recent_runs(self, limit: int = 10) -> list[dict]:
        with self._conn() as c:
            rows = c.execute("SELECT id,episode,plan,created FROM run ORDER BY created DESC LIMIT ?",
                             (limit,)).fetchall()
        out = []
        for r in rows:
            try:
                p = json.loads(r[2])
            except Exception:
                p = {}
            out.append({"id": r[0], "episode": r[1], "created": r[3],
                        "action": p.get("action"), "cost": p.get("est_cost"),
                        "character": p.get("character", {}).get("avg_score"),
                        "quality": p.get("quality_gate", {}).get("score")})
        return out


_default = None
def default_store() -> ProductionStore:
    global _default
    if _default is None:
        _default = ProductionStore()
    return _default
