from __future__ import annotations
"""
Market Intelligence Agent for pielts.web.app

Pulls live signals from:
  • Reddit (r/IELTS, r/EnglishLearning, r/studyabroad) via Exa search
  • App store competitor analysis via Gemini grounded search
  • Google Trends signals via grounded search
  • User pain-point extraction + feature-gap analysis

Outputs structured JSON stored in data/market_intel/YYYY-MM-DD.json
"""

import json
import re
from datetime import datetime
from pathlib import Path

from .. import config

INTEL_DIR = config.ROOT / "data" / "market_intel"
INTEL_DIR.mkdir(parents=True, exist_ok=True)

PIELTS_URL = "https://pielts.web.app"

# ── Subreddits to mine ────────────────────────────────────────────────────────
REDDIT_QUERIES = [
    "site:reddit.com r/IELTS practice app problems 2024 2025",
    "site:reddit.com IELTS app review recommend best free",
    "site:reddit.com IELTS preparation features wish list request",
    "site:reddit.com IELTS writing speaking practice online tool",
    "site:reddit.com IELTS band 7 8 9 study method app",
]

COMPETITOR_QUERIES = [
    "best IELTS practice app 2024 2025 comparison features reviews",
    "IELTS app user complaints problems bad reviews Play Store App Store",
    "IELTS Magoosh IELTS IDP British Council practice app weaknesses",
    "IELTS preparation app missing features users want 2024",
]

TREND_QUERIES = [
    "IELTS preparation trends 2024 2025 AI speaking writing feedback",
    "IELTS online practice demand Nepal India student needs",
]

# ── Core extraction ───────────────────────────────────────────────────────────

def _exa_search(query: str, n: int = 5) -> str:
    """Run Exa search via internet_reach."""
    try:
        from .internet_reach import web_search
        r = web_search(query, num_results=n)
        return r.get("output", "") or r.get("error", "")
    except Exception as e:
        return f"[search error: {e}]"


def _grounded_search(prompt: str) -> str:
    """Ask Gemini with live Google Search grounding."""
    try:
        from .research import _grounded
        return _grounded(prompt, max_tokens=900)
    except Exception as e:
        return f"[grounded error: {e}]"


def _ask_llm(prompt: str, system: str = "") -> str:
    """Use Groq LLM for extraction/synthesis."""
    try:
        from ._llm_helper import ask_llm
        return ask_llm(prompt, system=system, timeout=60)
    except Exception as e:
        return f"[llm error: {e}]"


def _extract_json(text: str) -> dict | list | None:
    try:
        from ._llm_helper import extract_json
        return extract_json(text)
    except Exception:
        m = re.search(r'\{[\s\S]*\}|\[[\s\S]*\]', text)
        if m:
            try:
                return json.loads(m.group())
            except Exception:
                pass
    return None


# ── Phase 1: Reddit signal mining ────────────────────────────────────────────

def mine_reddit_signals() -> dict:
    """Pull raw Reddit content about IELTS apps and pain points."""
    raw_chunks = []
    for q in REDDIT_QUERIES:
        chunk = _exa_search(q, n=4)
        if chunk and len(chunk) > 50:
            raw_chunks.append(chunk[:1200])

    combined = "\n\n---\n\n".join(raw_chunks)[:5000]

    extraction_prompt = f"""
You are analyzing Reddit posts about IELTS practice apps and user needs.

RAW SEARCH RESULTS:
{combined}

Extract and return JSON with this exact structure:
{{
  "pain_points": [
    {{"issue": "...", "frequency": "high|medium|low", "verbatim_quote": "..."}}
  ],
  "feature_requests": [
    {{"feature": "...", "description": "...", "upvotes_signal": "high|medium|low"}}
  ],
  "competitor_mentions": [
    {{"app": "...", "sentiment": "positive|negative|mixed", "reason": "..."}}
  ],
  "user_segments": ["..."],
  "trending_topics": ["..."],
  "pielts_opportunities": ["..."]
}}

Focus on: what do IELTS students want that existing apps DON'T provide?
Return ONLY valid JSON.
"""
    raw = _ask_llm(extraction_prompt, system="Return ONLY valid JSON.")
    result = _extract_json(raw)
    return result if isinstance(result, dict) else {
        "pain_points": [], "feature_requests": [], "competitor_mentions": [],
        "user_segments": [], "trending_topics": [], "pielts_opportunities": [],
        "_raw_preview": combined[:300],
    }


# ── Phase 2: Competitor intelligence ─────────────────────────────────────────

def analyze_competitors() -> dict:
    """Deep competitor feature gap analysis."""
    raw_chunks = []
    for q in COMPETITOR_QUERIES:
        chunk = _grounded_search(q)
        if chunk and len(chunk) > 50:
            raw_chunks.append(chunk[:1200])

    combined = "\n\n---\n\n".join(raw_chunks)[:4000]

    prompt = f"""
Analyze the IELTS app market based on this research:

{combined}

Return JSON:
{{
  "top_competitors": [
    {{
      "name": "...",
      "strengths": ["..."],
      "weaknesses": ["..."],
      "monthly_users_estimate": "...",
      "price_model": "free|freemium|paid"
    }}
  ],
  "market_gaps": [
    {{"gap": "...", "opportunity_size": "high|medium|low", "difficulty": "easy|medium|hard"}}
  ],
  "feature_benchmark": {{
    "ai_feedback": "who has it",
    "speaking_practice": "who has it",
    "mock_tests": "who has it",
    "community": "who has it",
    "nepal_localization": "who has it",
    "free_tier": "who has it"
  }},
  "pielts_competitive_advantages": ["..."],
  "pielts_missing_vs_competitors": ["..."]
}}
Return ONLY valid JSON.
"""
    raw = _ask_llm(prompt, system="Return ONLY valid JSON.")
    result = _extract_json(raw)
    return result if isinstance(result, dict) else {
        "top_competitors": [], "market_gaps": [], "feature_benchmark": {},
        "pielts_competitive_advantages": [], "pielts_missing_vs_competitors": [],
    }


# ── Phase 3: Trend signals ────────────────────────────────────────────────────

def capture_trend_signals() -> dict:
    """Capture what IELTS students are searching for right now."""
    chunks = []
    for q in TREND_QUERIES:
        chunk = _grounded_search(q)
        if chunk:
            chunks.append(chunk[:1000])

    combined = "\n\n".join(chunks)[:3000]

    prompt = f"""
Based on this IELTS market trend research:
{combined}

Return JSON:
{{
  "rising_topics": ["..."],
  "declining_topics": ["..."],
  "seasonal_patterns": ["..."],
  "geographic_demand": {{"nepal": "...", "india": "...", "global": "..."}},
  "ai_opportunity": "...",
  "content_format_trends": ["..."],
  "recommended_pielts_priorities": [
    {{"priority": 1, "action": "...", "rationale": "..."}}
  ]
}}
Return ONLY valid JSON.
"""
    raw = _ask_llm(prompt, system="Return ONLY valid JSON.")
    result = _extract_json(raw)
    return result if isinstance(result, dict) else {
        "rising_topics": [], "recommended_pielts_priorities": [],
    }


# ── Phase 4: Feature + UI improvement generation ─────────────────────────────

def generate_improvement_tasks(reddit: dict, competitors: dict, trends: dict) -> list[dict]:
    """
    Synthesize all signals into ranked UI/feature improvement tasks for pielts.
    """
    context = json.dumps({
        "reddit_pain_points": reddit.get("pain_points", [])[:5],
        "feature_requests": reddit.get("feature_requests", [])[:5],
        "market_gaps": competitors.get("market_gaps", [])[:5],
        "missing_vs_competitors": competitors.get("pielts_missing_vs_competitors", [])[:5],
        "trend_priorities": trends.get("recommended_pielts_priorities", [])[:5],
        "rising_topics": trends.get("rising_topics", [])[:5],
    }, indent=2)

    prompt = f"""
You are the product lead for pielts.web.app, a free IELTS practice app targeting Nepali and South Asian students.
Goal: Make pielts the #1 IELTS practice app by combining AI feedback, community, gamification, and simplicity.

Current market signals:
{context}

Generate exactly 10 ranked improvement tasks. Mix of:
- UI/UX improvements (make it cleaner, more attractive, easier)
- New features (based on Reddit pain points and market gaps)
- Content/SEO improvements
- Growth/retention mechanics

Return JSON array:
[
  {{
    "rank": 1,
    "category": "ui_ux|feature|content|growth|ai",
    "title": "...",
    "description": "...",
    "impact": "high|medium|low",
    "effort": "small|medium|large",
    "rationale": "specific market signal that justifies this",
    "implementation_hint": "brief technical approach",
    "target_metric": "what KPI this improves"
  }}
]

Prioritize: high-impact + small-effort first (quick wins), then high-impact + large-effort.
Return ONLY valid JSON array.
"""
    raw = _ask_llm(prompt, system="Return ONLY valid JSON array.")
    result = _extract_json(raw)
    if isinstance(result, list):
        return result
    return [{"rank": 1, "title": "Run market research again", "impact": "high",
              "effort": "small", "category": "feature", "description": "Research parse failed"}]


# ── Phase 5: Goal plan ────────────────────────────────────────────────────────

def generate_goal_plan(improvements: list[dict], competitors: dict, trends: dict) -> dict:
    """Generate a strategic 90-day roadmap to become #1 IELTS app."""
    top_tasks = json.dumps(improvements[:5], indent=2)
    gaps = json.dumps(competitors.get("market_gaps", [])[:3], indent=2)

    prompt = f"""
Create a strategic 90-day goal plan for pielts.web.app to become the #1 IELTS practice app.

Top priority improvements:
{top_tasks}

Market gaps to exploit:
{gaps}

Return JSON:
{{
  "vision": "one sentence mission",
  "north_star_metric": "the one KPI that proves #1 status",
  "phases": [
    {{
      "phase": 1,
      "name": "...",
      "duration": "weeks 1-4",
      "theme": "...",
      "goals": ["..."],
      "key_deliverables": ["..."],
      "success_criteria": "..."
    }},
    {{
      "phase": 2,
      "name": "...",
      "duration": "weeks 5-8",
      "theme": "...",
      "goals": ["..."],
      "key_deliverables": ["..."],
      "success_criteria": "..."
    }},
    {{
      "phase": 3,
      "name": "...",
      "duration": "weeks 9-12",
      "theme": "...",
      "goals": ["..."],
      "key_deliverables": ["..."],
      "success_criteria": "..."
    }}
  ],
  "quick_wins_this_week": ["..."],
  "moat_strategy": "what makes pielts impossible to copy",
  "growth_channels": ["..."],
  "kpis": {{
    "week_4": {{}},
    "week_8": {{}},
    "week_12": {{}}
  }}
}}
Return ONLY valid JSON.
"""
    raw = _ask_llm(prompt, system="Return ONLY valid JSON.")
    result = _extract_json(raw)
    return result if isinstance(result, dict) else {
        "vision": "Make pielts the #1 free IELTS app for South Asian students",
        "phases": [],
    }


# ── Main pipeline ─────────────────────────────────────────────────────────────

def run_full_research(save: bool = True) -> dict:
    """
    Full market intelligence pipeline.
    Returns structured dict with all signals + improvement tasks + goal plan.
    """
    today = datetime.now().strftime("%Y-%m-%d")
    print(f"🔍 pielts Market Intel — {today}")

    print("  Phase 1: Mining Reddit signals…")
    reddit = mine_reddit_signals()

    print("  Phase 2: Competitor analysis…")
    competitors = analyze_competitors()

    print("  Phase 3: Trend signals…")
    trends = capture_trend_signals()

    print("  Phase 4: Generating improvement tasks…")
    improvements = generate_improvement_tasks(reddit, competitors, trends)

    print("  Phase 5: Building goal plan…")
    goal_plan = generate_goal_plan(improvements, competitors, trends)

    result = {
        "date": today,
        "generated_at": datetime.now().isoformat(),
        "reddit_signals": reddit,
        "competitor_intel": competitors,
        "trend_signals": trends,
        "improvement_tasks": improvements,
        "goal_plan": goal_plan,
        "summary": {
            "pain_points_found": len(reddit.get("pain_points", [])),
            "features_requested": len(reddit.get("feature_requests", [])),
            "market_gaps": len(competitors.get("market_gaps", [])),
            "tasks_generated": len(improvements),
        },
    }

    if save:
        path = INTEL_DIR / f"{today}.json"
        path.write_text(json.dumps(result, indent=2, ensure_ascii=False))
        # Also write "latest" for quick access
        (INTEL_DIR / "latest.json").write_text(json.dumps(result, indent=2, ensure_ascii=False))
        print(f"  ✅ Saved → {path}")

    return result


def get_latest() -> dict | None:
    """Load the most recent market intel report."""
    p = INTEL_DIR / "latest.json"
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            pass
    return None


def get_top_tasks(n: int = 5) -> list[dict]:
    """Get top N improvement tasks from latest research."""
    latest = get_latest()
    if not latest:
        return []
    tasks = latest.get("improvement_tasks", [])
    return sorted(tasks, key=lambda x: x.get("rank", 99))[:n]
