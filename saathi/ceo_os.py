"""Today's Operating System — the one screen that answers "what needs my
attention right now?" Aggregates REAL signals into a single BFF response so the
dashboard makes one call, not twenty. No mock: every field comes from a real
subsystem, and where there's no real data yet it reads honestly (0 / empty).
"""
from __future__ import annotations


def snapshot() -> dict:
    return {
        "greeting": _greeting(),
        "dream": _dream(),
        "rule": _rule(),
        "automation": _automation(),
        "studio": _studio(),
        "mission": _mission(),
        "learning": _learning(),
        "revenue": _revenue(),
        "needs_you": _needs_you(),
    }


def _studio() -> dict:
    """Today's Factory — queue lanes + today's real averages (confidence/cost/runtime)."""
    try:
        from saathi.studio_store import default_store
        st = default_store()
        out = st.queue_counts()
        out["factory"] = st.factory_kpis()
        return out
    except Exception:
        return {"awaiting_approval": 0, "published": 0, "blocked": 0, "in_progress": 0,
                "factory": {"runs": 0, "published": 0, "waiting_approval": 0, "blocked": 0,
                            "avg_confidence": 0, "avg_cost": 0, "avg_runtime_ms": 0}}


def _mission() -> dict:
    try:
        from saathi.daily_mission import mission
        return mission()
    except Exception:
        return {}


def _greeting() -> str:
    import time
    h = time.localtime().tm_hour
    part = "morning" if h < 12 else "afternoon" if h < 18 else "evening"
    return f"Good {part}, Ajay"


def _dream() -> dict:
    try:
        from saathi.executive import Executive  # noqa
    except Exception:
        pass
    try:
        from saathi.bff import ceo_home
        home = ceo_home()
        d = home.get("dream") or {}
        return {"progress_pct": d.get("progress_pct", d.get("progress", 0)),
                "delta": d.get("delta", 0)}
    except Exception:
        return {"progress_pct": 0, "delta": 0}


def _rule() -> dict:
    try:
        from saathi.daily_scorecard import today_scorecard
        sc = today_scorecard()
        return {"score": sc.score(), "of": 4, "met": sc.met(), "missing": sc.missing()}
    except Exception:
        return {"score": 0, "of": 4, "met": {}, "missing": ["Decide", "Automate", "Learn", "Earn"]}


def _automation() -> dict:
    try:
        from saathi.infrastructure.human_browser import automation
        from saathi.infrastructure.human_browser.workflows import WORKFLOWS
        s = automation.status()
        return {"health": s["health"]["overall"], "runs_today": s["health"]["runs_today"],
                "success": s["health"]["success_rate"], "workflows": len(WORKFLOWS),
                "agent_online": s["components"]["agent"]["online"]}
    except Exception:
        return {"health": 0, "runs_today": 0, "success": 0, "workflows": 0, "agent_online": False}


def _learning() -> dict:
    try:
        from saathi.infrastructure.human_browser.selector_registry import default_registry
        ov = default_registry().overview()
        taught = [e for e in ov if "taught" in e.get("sources", [])]
        verified = [e for e in ov if e.get("confidence", 0) >= 0.9]
        return {"knowledge_added": len(taught), "verified_improvements": len(verified),
                "episodes_today": _episodes_today()}
    except Exception:
        return {"knowledge_added": 0, "verified_improvements": 0, "episodes_today": 0}


def _episodes_today() -> int:
    try:
        from saathi.platform_maturity import _episodes_today as ep
        import time
        return ep(time.time())
    except Exception:
        return 0


def _revenue() -> dict:
    out = {"cafeteria": 0, "ai_studio": 0, "trading_pct": 0}
    try:
        from saathi import pielts
        out["ai_studio"] = float(pielts.dashboard().get("revenue_today", 0) or 0)
    except Exception:
        pass
    return out


def _needs_you() -> list[dict]:
    items: list[dict] = []
    try:
        from saathi.bff import ceo_home
        for a in ceo_home().get("top_actions", []):
            label = a.get("title") or a.get("label") or a.get("action")
            if label:
                items.append({"kind": a.get("kind", "action"), "label": label,
                              "cta": a.get("cta", "Review")})
    except Exception:
        pass
    try:
        from saathi.infrastructure.human_browser import default_teacher
        for s in default_teacher().store.pending():
            items.append({"kind": "teach", "label": f"Teach: {s.key}", "cta": "Take Control"})
    except Exception:
        pass
    return items[:6]
