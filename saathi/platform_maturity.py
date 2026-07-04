"""Platform Maturity — an honest mirror, not a scoreboard.

Deliberately computed from REAL signals so the low numbers stay low. Infrastructure
is ~built; the point of this view is to keep it visible that Applications, Real
Data, and Learning Confidence are what actually matter and are still early. It
enforces the rule: prove one application improved from real data before building
more platform.
"""
from __future__ import annotations

import time


# infra components that are built AND wired/deployed
_INFRA = ["model_router", "browser", "sessions", "connectors", "conversation",
          "diagnostics", "automation_center", "selector_registry", "teach_mode"]
# departments that COULD use the platform
_APPS = ["ai_studio", "finance", "cafeteria", "travel", "learning",
         "knowledge", "discovery", "crypto"]


def snapshot(*, run_store=None, sel_registry=None, registry=None, now=None) -> dict:
    now = time.time() if now is None else now

    # ── automation: the flight recorder (real) ──────────────────────────
    try:
        from saathi.infrastructure.human_browser.run_store import default_store
        rs = run_store or default_store()
        rstats = rs.stats(window_hours=24, now=now)
    except Exception:
        rstats = {"runs": 0, "successes": 0, "success_rate": 1.0, "failures": 0}
    runs_today = rstats["runs"]
    automation_success = round(100 * rstats["success_rate"]) if runs_today else 0  # 0 = unproven

    # ── selector knowledge (real) ───────────────────────────────────────
    try:
        from saathi.infrastructure.human_browser.selector_registry import default_registry
        sr = sel_registry or default_registry()
        ov = sr.overview()
    except Exception:
        ov = []
    taught = [e for e in ov if "taught" in e.get("sources", [])]
    knowledge_added = len(taught)
    verified = [e for e in ov if e.get("confidence", 0) >= 0.9]
    learning_confidence = round(100 * len(verified) / len(ov)) if ov else 0

    # ── connectors actually authenticated (real vs mock) ────────────────
    try:
        from saathi.infrastructure.connectors import default_registry as _creg
        reg = registry or _creg()
        conns = reg.diagnostics()
        live_conns = [c for c in conns if c.get("authenticated")]
        real_data = round(100 * len(live_conns) / len(conns)) if conns else 0
    except Exception:
        real_data = 0

    # ── episodes today (best-effort) ────────────────────────────────────
    episodes_today = _episodes_today(now)
    human_overrides = knowledge_added                # taught selectors == human corrections
    revenue_today = _revenue_today()

    # ── coarse layer scores ─────────────────────────────────────────────
    infrastructure = 100                             # built + deployed
    apps_active = 1 if runs_today else 0             # only AI Studio has touched it, honestly
    applications = round(100 * apps_active / len(_APPS))

    return {
        "infrastructure": infrastructure,
        "applications": applications,
        "real_data": real_data,
        "learning_confidence": learning_confidence,
        "revenue_today": revenue_today,
        "automation_success": automation_success,
        "episodes_today": episodes_today,
        "knowledge_added": knowledge_added,
        "human_overrides": human_overrides,
        "runs_today": runs_today,
        "note": "Infrastructure is built; Applications/Real Data/Learning are what matter now.",
    }


def _episodes_today(now: float) -> int:
    try:
        from saathi.integration import get_platform_memory
        mem = get_platform_memory()
        # count episodes since local midnight if the store supports it
        for attr in ("episodes_since", "count_since", "recent_count"):
            fn = getattr(mem, attr, None)
            if callable(fn):
                return int(fn(now - 86400))
    except Exception:
        pass
    return 0


def _revenue_today() -> float:
    try:
        from saathi import pielts
        d = pielts.dashboard()
        return float(d.get("revenue_today", 0) or 0)
    except Exception:
        return 0.0
