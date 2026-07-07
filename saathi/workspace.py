"""Saathi Workspace — conversation as the operating system.

One chat that can research, plan, and act on a Mission. It is Mission-aware
(injects the Knowledge Graph + twin + pending recommendations as context), has
MODES that gate what it may do (research/planning = read-only; implementation =
may propose concrete steps; cowork = the SaathiOS team answers together), and
auto-runs the Repo Analysis Pipeline when a GitHub URL is pasted: fetch README →
extract capabilities → compare with Saathi's own architecture → detect overlap vs
gaps → store in the Research Library → recommend how to integrate.

It reuses the brain (Model Router), the Knowledge Importer, the Knowledge Graph,
and the Library — it does not itself write code or run workflows.
"""
from __future__ import annotations

import re

MODES = ("research", "planning", "implementation", "cowork")

_GH = re.compile(r"https?://github\.com/[\w.-]+/[\w.-]+", re.I)

# Saathi's own capabilities → keywords, so we can detect what a repo DUPLICATES
_SAATHI_CAPS = {
    "Prompt Registry": ["prompt", "version", "registry", "eval", "promptfoo"],
    "Knowledge Graph": ["knowledge", "memory", "graph", "rag", "vector", "embedding", "retrieval"],
    "Evidence Store": ["evidence", "observability", "metrics", "telemetry", "tracing", "opik"],
    "Learning Directors": ["learning", "feedback", "evaluation", "recommendation", "rlhf"],
    "Director Registry": ["agent", "director", "orchestration", "multi-agent", "crew", "autogen", "langgraph"],
    "Mission OS": ["project", "mission", "workspace"],
    "Workflow Engine": ["workflow", "pipeline", "dag", "chain", "dify"],
    "Event Bus": ["event", "bus", "pubsub", "webhook"],
    "Model Router": ["model", "provider", "llm", "router", "gateway", "openai", "gemini", "claude"],
    "Connector Registry": ["connector", "integration", "telegram", "slack", "mcp", "a2a"],
    "Skill Library": ["skill", "tool", "function"],
}

_MODE_INSTRUCTION = {
    "research": ("RESEARCH MODE — implementation and execution are DISABLED. You may only research, "
                 "compare, read, summarise, analyse, and recommend. Never propose writing code or "
                 "say you will build/wire/implement anything. End with a recommendation, not a plan."),
    "planning": ("PLANNING MODE — no code. Produce architecture, roadmap, dependencies, risks, timeline, "
                 "and a recommendation. Do not implement."),
    "implementation": ("IMPLEMENTATION MODE — you may propose a concrete, ordered implementation plan and "
                       "steps. Do not claim work is done; the CEO approves before execution."),
    "cowork": ("COWORK MODE — answer as the SaathiOS team. Give 2–4 short labelled perspectives "
               "(Research Director, Architecture Director, Business Director, Engineering Director), "
               "then a single 'CEO recommendation:' line. Keep each perspective to one sentence."),
}


def detect_github(text: str) -> str | None:
    m = _GH.search(text or "")
    return m.group(0) if m else None


_URL = re.compile(r"https?://[^\s]+", re.I)


def _all_urls(text: str) -> list[str]:
    return [u.rstrip(".,) ") for u in _URL.findall(text or "")]


def _detect_website(text: str) -> str | None:
    for u in _all_urls(text):
        if "github.com" not in u.lower():
            return u
    return None


# ── Repo Analysis Pipeline ────────────────────────────────────────────────────
def analyze_repo(url: str, *, mission_id: str = "") -> dict:
    """Fetch README → capabilities → compare with Saathi → overlap/gaps → store → recommend."""
    from saathi.knowledge_library.importer import import_repo
    res = import_repo(url, category="AI Engineering")
    src = res.get("source", {})
    tags = src.get("tags", [])
    text = " ".join([src.get("summary", ""), " ".join(tags), src.get("title", "")]).lower()

    overlap, gaps = [], []
    for cap, kws in _SAATHI_CAPS.items():
        if any(k in text for k in kws):
            overlap.append(cap)
    # gaps = notable capability tags not covered by any Saathi cap
    covered = {k for kws in _SAATHI_CAPS.values() for k in kws}
    gaps = [t for t in tags if t not in covered][:6]

    if any(t in text for t in ("openhands", "code", "engineer", "pr ", "commit", "repository", "sandbox")):
        integration = "Engineering Tool (coding agent) — NOT runtime"
    elif any(t in text for t in ("tts", "voice", "speech", "image", "video", "diffusion")):
        integration = "Provider adapter (behind the Model/Render/Voice router)"
    elif "workflow" in text or "dify" in text:
        integration = "Workflow prototyping tool — export to Saathi Workflow Engine (not runtime)"
    else:
        integration = "Research Library reference (ideas/interfaces only)"

    recommendation = (f"Import as: {integration}. "
                      f"{'Overlaps ' + ', '.join(overlap[:4]) + ' — do not duplicate. ' if overlap else ''}"
                      f"{'New capabilities worth adopting: ' + ', '.join(gaps) + '.' if gaps else 'No genuinely new capability detected.'}")

    if mission_id:
        try:
            from saathi.missions.timeline import default_store as tl
            tl().record(mission_id, "research", f"Analysed repo: {src.get('title', url)}",
                        detail=recommendation[:160])
        except Exception:
            pass

    return {"kind": "repo_analysis", "url": url, "title": src.get("title", ""),
            "summary": src.get("summary", ""), "tags": tags, "overlap": overlap, "gaps": gaps,
            "integration": integration, "recommendation": recommendation,
            "stored_in_library": bool(res.get("ok")), "related_directors": src.get("related_directors", [])}


# ── Mission context (what the chat already knows) ─────────────────────────────
def mission_context(mission: dict) -> str:
    if not mission:
        return "No Mission selected (general SaathiOS context)."
    mid = mission.get("id", "")
    lines = [f"Mission: {mission.get('name')} (key={mission.get('key')}, dept={mission.get('department')})"]
    ident = mission.get("identity") or {}
    if ident.get("industry"):
        lines.append(f"Industry: {ident['industry']}")
    if mission.get("objectives"):
        lines.append("Objectives: " + "; ".join(mission["objectives"][:3]))
    try:
        from saathi.missions.knowledge import default_graph
        cov = default_graph().coverage(mid)
        lines.append(f"Knowledge coverage: {int(cov['overall']*100)}% ({cov['node_count']} nodes)")
    except Exception:
        pass
    try:
        from saathi.missions.twin import default_store as tw
        t = tw().get(mid) or {}
        b = t.get("briefing", {})
        if b.get("top_risks"):
            lines.append("Top risks: " + "; ".join(b["top_risks"][:2]))
        if b.get("top_opportunities"):
            lines.append("Top opportunities: " + "; ".join(b["top_opportunities"][:3]))
    except Exception:
        pass
    try:
        from saathi.learning.recommendation import default_store as rec
        pend = rec().list(status="pending", limit=3)
        if pend:
            lines.append("Pending recommendations: " + "; ".join(r["problem"][:50] for r in pend))
    except Exception:
        pass
    return "\n".join(lines)


# ── The workspace turn ────────────────────────────────────────────────────────
def handle(message: str, *, mission_key: str = "", mode: str = "cowork") -> dict:
    mode = mode if mode in MODES else "cowork"
    mission = None
    if mission_key:
        try:
            from saathi.missions.store import default_store as m_store
            mission = m_store().get(mission_key) or m_store().get_by_key(mission_key)
        except Exception:
            mission = None

    # Website Intelligence — a non-GitHub URL + design/analyse intent
    site = _detect_website(message)
    if site and any(w in message.lower() for w in ("website", "design", "analyze", "analyse", "redesign", "ui", "ux")):
        from saathi.missions.website import intelligence
        urls = _all_urls(message)
        compare = urls[1] if len(urls) > 1 else ""
        rep = intelligence(mission_key, site, compare_url=compare)
        r = rep["reference"]
        ds = rep["design_system"]
        reply = (f"**Website analysis — {r['url']}**\n"
                 f"Stack: {', '.join(r['stack']) or 'not detected'}\n"
                 f"SEO: {r['seo'].get('score')}/100 · UX: {r['ux']['cta_count']} CTAs, "
                 f"{'responsive' if r['ux']['responsive'] else 'not responsive'}, "
                 f"{'animated' if r['ux']['animated'] else 'static'}\n"
                 f"Patterns: {', '.join(rep['design_patterns']) or 'none detected'}\n\n"
                 f"**Original design system for {mission_key or 'this Mission'}** (not copied):\n"
                 f"Mood: {ds['mood']} · Palette: {', '.join(ds['palette'][:4])} · "
                 f"Type: {ds['typography']['heading']} / {ds['typography']['body']}\n"
                 f"Pages: {', '.join(w['page'] for w in rep['wireframes'])}\n"
                 f"Stack to build: {', '.join(rep['blueprint']['stack'])}\n\n"
                 f"Stored in the Knowledge Graph + Research Library. {rep['principle']}")
        return {"reply": reply, "mode": mode, "mission": mission_key,
                "website": rep, "actions": ["knowledge_graph", "research_library", "timeline"]}

    # Repo Analysis Pipeline — fires whenever a GitHub URL is present
    gh = detect_github(message)
    if gh:
        analysis = analyze_repo(gh, mission_id=(mission or {}).get("id", ""))
        reply = (f"**{analysis['title'] or gh}**\n"
                 f"{analysis['summary'][:220]}\n\n"
                 f"Overlaps: {', '.join(analysis['overlap']) or 'none'}\n"
                 f"New capabilities: {', '.join(analysis['gaps']) or 'none'}\n"
                 f"→ {analysis['recommendation']}\n\n"
                 f"Stored in the Research Library. Useful for: "
                 f"{', '.join(analysis['related_directors']) or 'research'}.")
        return {"reply": reply, "mode": mode, "mission": (mission or {}).get("key", ""),
                "analysis": analysis, "actions": ["stored_in_library", "timeline_recorded" if mission else ""]}

    # Otherwise → mission-aware brain call, gated by mode
    ctx = mission_context(mission)
    if mode == "cowork":
        out = _cowork(message, ctx)
    else:
        system = (f"You are Saathi, the CEO's AI operating workspace.\n{_MODE_INSTRUCTION[mode]}\n\n"
                  f"MISSION CONTEXT:\n{ctx}\n\n"
                  "Ground answers in the platform SaathiOS already has (Mission OS, Knowledge Graph, Evidence, "
                  "Learning, Directors, Prompt/Skill/Knowledge Libraries, Workflow Engine, Event Bus). "
                  "Prefer reusing existing subsystems over building new ones. Be concise.")
        out = _brain(message, system, 700)

    # implementation mode → extract an ordered plan the CEO can turn into tasks
    plan = _extract_steps(out) if mode == "implementation" else []

    # auto-capture: record the turn to the Mission (Timeline + a decision node if one was made)
    actions = _capture(mission, message, out, mode)

    return {"reply": out, "mode": mode, "mission": (mission or {}).get("key", ""),
            "context_used": ctx, "plan": plan, "actions": actions}


def _brain(message: str, system: str, max_tokens: int = 400) -> str:
    try:
        from saathi.infrastructure.llm import generate
        from saathi.infrastructure.model_router import ModelLabel
        return generate(ModelLabel.STANDARD, message, system, max_tokens=max_tokens).text.strip()
    except Exception as e:
        return f"(brain unavailable: {str(e)[:80]})"


def _cowork(message: str, ctx: str) -> str:
    """Each Director contributes a real perspective (its own focused call), then the CEO synthesises."""
    directors = [
        ("Research Director", "In ONE sentence: what does prior art / the Knowledge & Research Library suggest here?"),
        ("Business Director", "In ONE sentence: the business / ROI angle for this Mission."),
        ("Engineering Director", "In ONE sentence: feasibility + rough effort, reusing existing SaathiOS subsystems."),
    ]
    lines = []
    for name, q in directors:
        out = _brain(f"{message}\n\n{q}", f"You are the {name} of SaathiOS.\nMISSION CONTEXT:\n{ctx}", 120)
        if out and not out.startswith("(brain"):
            lines.append(f"**{name}:** {out}")
    synth = _brain(message + "\n\nThe team said:\n" + "\n".join(lines),
                   "You are the CEO of SaathiOS. Give ONE decisive recommendation line.", 120)
    if synth and not synth.startswith("(brain"):
        lines.append(f"**CEO recommendation:** {synth}")
    return "\n\n".join(lines) if lines else "(team unavailable right now)"


_STEP = re.compile(r"^\s*(?:\d+[.)]|[-*])\s+(.+)$")


def _extract_steps(text: str) -> list[str]:
    steps = []
    for ln in (text or "").splitlines():
        m = _STEP.match(ln)
        if m:
            steps.append(m.group(1).strip()[:80])
    return steps[:12]


_DECISION_HINT = re.compile(r"\b(recommend|decision|proceed|approve|choose|should|conclusion)\b", re.I)


def _capture(mission: dict | None, message: str, reply: str, mode: str) -> list[str]:
    """Record valuable turns to the Mission — Timeline always, a Decision node when one was made."""
    if not mission:
        return []
    mid = mission.get("id", "")
    done = []
    try:
        from saathi.missions.timeline import default_store as tl
        tl().record(mid, "decision" if _DECISION_HINT.search(reply) else "note",
                    f"Workspace ({mode}): {message[:60]}", detail=reply[:180])
        done.append("timeline")
    except Exception:
        pass
    if _DECISION_HINT.search(reply):
        try:
            import uuid
            from saathi.missions.knowledge import default_graph
            default_graph().upsert(mid, "decision", f"dec-{uuid.uuid4().hex[:6]}",
                                   label=message[:60], data={"question": message[:120], "outcome": reply[:200],
                                                             "mode": mode}, source="workspace")
            done.append("decision_node")
        except Exception:
            pass
    return done


def save_plan_as_workflow(mission_key: str, name: str, steps: list[str]) -> dict:
    """Turn an implementation-mode plan into a real Workflow + Tasks on the Mission."""
    from saathi.missions.store import default_store as m_store
    ms = m_store()
    m = ms.get(mission_key) or ms.get_by_key(mission_key)
    if not m:
        return {"ok": False, "error": "mission not found"}
    if not steps:
        return {"ok": False, "error": "no steps to save"}
    from saathi.missions.workflow import default_store as wf_store, WorkflowStore, TEMPLATES  # noqa
    ws = wf_store()
    wf = ws.create(m["id"], director="workspace", name=name or "Plan")
    # replace template tasks with the plan's steps
    import sqlite3, time, uuid
    with ws._conn() as c:
        c.execute("DELETE FROM task WHERE workflow_id=?", (wf["id"],))
        for i, s in enumerate(steps):
            c.execute("INSERT INTO task VALUES(?,?,?,?,?,?,?,?,?)",
                      (uuid.uuid4().hex[:16], wf["id"], m["id"], s, "todo", i, "workspace", "", time.time()))
    try:
        from saathi.missions.timeline import default_store as tl
        tl().record(m["id"], "decision", f"Plan saved as workflow: {name}", detail=f"{len(steps)} tasks")
    except Exception:
        pass
    return {"ok": True, "workflow": ws.get(wf["id"])}
