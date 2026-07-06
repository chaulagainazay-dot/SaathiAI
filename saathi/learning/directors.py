"""The three Learning Directors — independent systems, one law: RECOMMEND ONLY.

Each reads the Evidence Store, finds patterns deterministically (honest averages
over real rows — never fabricated numbers, never an LLM guess), and emits
Recommendations. They never edit a prompt, workflow, menu, or curriculum. The CEO
decides; acceptance is what flows to the Prompt Registry.

  Technical   → how SaathiAI itself should improve (prompts/directors/providers)
  Educational → how Mr. Yeti should teach better (IELTS: struggle topics)
  Business    → how each company should operate better (HCG/Cafeteria/Travel)
"""
from __future__ import annotations

from collections import defaultdict

from saathi.learning.recommendation import Recommendation

# below this average confidence, a director's output is worth a proposal
_TECH_THRESHOLD = 0.85
_MIN_SAMPLE = 3          # never recommend from too little evidence


def _by_director(rows: list[dict]) -> dict:
    agg = defaultdict(lambda: {"conf": [], "cost": [], "ids": [], "provider": ""})
    for r in rows:
        d = r.get("director") or "unknown"
        agg[d]["conf"].append(r.get("confidence", 0) or 0)
        agg[d]["cost"].append(r.get("cost", 0) or 0)
        agg[d]["ids"].append(r.get("id"))
        agg[d]["provider"] = r.get("provider", "") or agg[d]["provider"]
    return agg


def _priority(gap: float) -> str:
    return "high" if gap >= 0.3 else "medium" if gap >= 0.15 else "low"


# ── 1. Technical Learning ─────────────────────────────────────────────────────
def technical(rows: list[dict] | None = None) -> list[Recommendation]:
    """Low-confidence Directors → concrete improvement proposals."""
    if rows is None:
        rows = _load("ai_studio")
    stage_rows = [r for r in rows if r.get("director") and r["director"] != "studio_executive"]
    recs = []
    for director, a in _by_director(stage_rows).items():
        n = len(a["conf"])
        if n < _MIN_SAMPLE:
            continue
        avg = round(sum(a["conf"]) / n, 3)
        if avg >= _TECH_THRESHOLD:
            continue
        gap = round(_TECH_THRESHOLD - avg, 3)
        recs.append(Recommendation(
            category="technical", department="ai_studio", affected_director=director,
            priority=_priority(gap), confidence=round(min(0.95, 0.55 + gap), 2),
            problem=f"{director.title()} Director avg output quality {avg:.0%} across {n} runs "
                    f"(below {_TECH_THRESHOLD:.0%} bar).",
            recommendation=f"Draft a new prompt version for the {director} Director: tighten the "
                           f"weakest artifact fields; A/B the new version against the current one.",
            expected_improvement=f"+{gap:.0%} artifact completeness",
            estimated_cost="low", risk="low",
            evidence=[i for i in a["ids"] if i][:20]))
    return recs


# ── 2. Educational Learning ───────────────────────────────────────────────────
def educational(studio_rows: list[dict] | None = None, pielts_rows: list[dict] | None = None) -> list[Recommendation]:
    """IELTS struggle signals → teaching improvements (Mr. Yeti gets better)."""
    if studio_rows is None:
        studio_rows = _load("ai_studio")
    if pielts_rows is None:
        pielts_rows = _load("pielts")
    recs = []

    # PIELTS: topics where the graded band runs low → teach them harder
    band_by_topic = defaultdict(list)
    ids_by_topic = defaultdict(list)
    for r in pielts_rows:
        m = r.get("metrics") or {}
        band = m.get("band")
        topic = m.get("topic") or r.get("episode") or "general"
        if isinstance(band, (int, float)):
            band_by_topic[topic].append(band); ids_by_topic[topic].append(r.get("id"))
    for topic, bands in band_by_topic.items():
        if len(bands) < _MIN_SAMPLE:
            continue
        avg = round(sum(bands) / len(bands), 2)
        if avg >= 6.5:
            continue
        recs.append(Recommendation(
            category="educational", department="pielts", affected_director="educational",
            priority="high" if avg < 5.5 else "medium", confidence=0.8,
            problem=f"Students average band {avg} on '{topic}' across {len(bands)} essays — a struggle area.",
            recommendation=f"Commission a Mr. Yeti episode on '{topic}': more worked examples, slower "
                           f"narration, an on-screen animation, and 3 practice exercises.",
            expected_improvement="higher student band on this topic",
            evidence=[i for i in ids_by_topic[topic] if i][:20]))

    # AI Studio: research surfaced common mistakes → make sure they become lessons
    mistakes = defaultdict(int)
    for r in studio_rows:
        for m in (r.get("metrics") or {}).get("common_mistakes", []) or []:
            mistakes[str(m)[:60]] += 1
    for mistake, n in sorted(mistakes.items(), key=lambda x: -x[1])[:3]:
        if n < 2:
            continue
        recs.append(Recommendation(
            category="educational", department="pielts", affected_director="educational",
            priority="medium", confidence=0.72,
            problem=f"Recurring learner mistake surfaced {n}× in research: {mistake}.",
            recommendation="Add a dedicated correction beat + example to the next relevant episode.",
            expected_improvement="fewer repeat mistakes"))
    return recs


# ── 3. Business Learning ──────────────────────────────────────────────────────
def business(rows_by_dept: dict | None = None) -> list[Recommendation]:
    """Per-company metrics → operational recommendations."""
    depts = {"hcg": "win rate / profit", "cafeteria": "waste / profit", "travel": "CTR / bookings"}
    recs = []
    for dept, focus in depts.items():
        rows = (rows_by_dept or {}).get(dept) if rows_by_dept else _load(dept)
        rows = rows or []
        if len(rows) < _MIN_SAMPLE:
            continue
        # HCG win rate
        if dept == "hcg":
            wins = sum(1 for r in rows if r.get("status") in ("win", "won"))
            wr = round(wins / len(rows), 2)
            if wr < 0.5:
                recs.append(Recommendation(
                    category="business", department="hcg", affected_director="signal_engine",
                    priority="high", confidence=0.78,
                    problem=f"HCG win rate {wr:.0%} across {len(rows)} signals — below break-even.",
                    recommendation="Raise the confidence threshold for published signals; review losing setups.",
                    expected_improvement="higher win rate",
                    evidence=[r.get("id") for r in rows][:20]))
        # Cafeteria waste
        elif dept == "cafeteria":
            wastes = [(r.get("metrics") or {}).get("waste") for r in rows]
            wastes = [w for w in wastes if isinstance(w, (int, float))]
            if wastes and sum(wastes) / len(wastes) > 0:
                recs.append(Recommendation(
                    category="business", department="cafeteria", affected_director="menu_planner",
                    priority="medium", confidence=0.7,
                    problem=f"Cafeteria averaging measurable food waste across {len(wastes)} days.",
                    recommendation="Trim prep quantity for the lowest-selling 2 items; re-check after a week.",
                    expected_improvement="less waste, higher profit",
                    evidence=[r.get("id") for r in rows][:20]))
        else:  # travel — generic low-conversion flag
            recs.append(Recommendation(
                category="business", department=dept, affected_director="campaign",
                priority="low", confidence=0.6,
                problem=f"{dept.title()}: {len(rows)} campaign records collected — ready for conversion review.",
                recommendation=f"Compare best vs worst campaign on {focus}; scale the winner.",
                expected_improvement="better campaign ROI",
                evidence=[r.get("id") for r in rows][:20]))
    return recs


def _load(department: str, limit: int = 200) -> list[dict]:
    try:
        from saathi.evidence.store import default_store
        return default_store().query(department=department, limit=limit)
    except Exception:
        return []


def analyze_all(*, persist: bool = True) -> dict:
    """Run all three Learning Directors, persist pending recommendations, return them."""
    recs = {"technical": technical(), "educational": educational(), "business": business()}
    if persist:
        from saathi.learning.recommendation import default_store
        st = default_store()
        for group in recs.values():
            for r in group:
                st.upsert_unique(r)
    return {k: [r.as_dict() for r in v] for k, v in recs.items()}
