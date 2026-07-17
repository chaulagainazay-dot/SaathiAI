"""Research tools — Baadar searches the live web (Gemini google_search grounding)
and builds plans that combine research with everything it knows about Ajay.

M21.3: EXPLICIT_LEGACY_EXCEPTION for Gemini grounding (unique capability not on
ModelRouter). Entry points apply kill-switch + registered caller preflight.
No raw source content logging. Expiry: M22.
"""
from __future__ import annotations

import httpx

from .. import config

_API = "https://generativelanguage.googleapis.com/v1beta/models"
CALLER_ID = "research_tools"
PATH_ID = "tools_research"


def _preflight(prompt: str, max_tokens: int) -> None:
    from saathi.inference.legacy_facade import preflight_inference

    pf = preflight_inference(
        caller_id=CALLER_ID,
        path_id=PATH_ID,
        prompt=prompt or "",
        system="research_grounding",
        max_tokens=max_tokens,
        timeout=90.0,
    )
    if not pf.ok:
        raise RuntimeError(pf.error_message or pf.reason_code or "research_preflight_denied")


def _grounded(prompt: str, max_tokens: int = 800) -> str:
    """Ask Gemini WITH live Google Search grounding (tries models in quota order)."""
    _preflight(prompt, max_tokens)
    last = None
    for model in ("gemini-2.5-flash-lite", "gemini-2.5-flash"):
        # Provider kill for gemini
        try:
            from saathi.inference.provider_policy import is_provider_killed

            if is_provider_killed("gemini"):
                raise RuntimeError("provider gemini killed")
        except RuntimeError:
            raise
        except Exception:
            pass
        r = httpx.post(
            f"{_API}/{model}:generateContent",
            params={"key": config.GOOGLE_API_KEY},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "tools": [{"google_search": {}}],
                "generationConfig": {"maxOutputTokens": max_tokens},
            },
            timeout=90,
        )
        if r.status_code == 429:
            last = r
            continue
        r.raise_for_status()
        parts = r.json()["candidates"][0]["content"]["parts"]
        return " ".join(p.get("text", "") for p in parts).strip()
    if last is not None:
        last.raise_for_status()
    raise RuntimeError("research_grounding_failed")


def research(topic: str, depth: str = "quick") -> dict:
    """Live web research on any topic Ajay asks about."""
    style = (
        "Answer in 3-5 short bullet points with the most useful, current facts."
        if depth == "quick"
        else "Give a thorough but organized answer: key facts, numbers, recent "
        "developments, and practical takeaways. Use short sections."
    )
    try:
        answer = _grounded(
            f"Research this for Ajay (canteen owner in Kathmandu, Nepal): {topic}\n{style}"
        )
        return {"topic": topic, "findings": answer, "caller_id": CALLER_ID, "path_id": PATH_ID}
    except Exception as e:
        # Redacted error — no full provider body
        return {
            "error": type(e).__name__,
            "note": "Search grounding may need quota; try again shortly.",
            "caller_id": CALLER_ID,
            "reason_code": getattr(e, "args", [""])[0]
            if type(e).__name__ == "RuntimeError"
            else type(e).__name__,
        }


def deep_plan(goal: str) -> dict:
    """Build an actionable plan: combines web research with Baadar's memory of Ajay."""
    from ..memory import Memory

    mem = Memory(config.DB_PATH)
    facts = mem.relevant_facts(goal, limit=10)
    context = "\n".join(f"- {f}" for f in facts) or "(no stored facts matched)"
    try:
        plan = _grounded(
            f"Ajay's goal: {goal}\n\nWhat Baadar knows about Ajay:\n{context}\n\n"
            "Research anything needed, then produce a concrete step-by-step plan "
            "tailored to him: numbered steps, realistic timeline, costs in NPR where "
            "relevant, and the single best first action. Keep it tight.",
            max_tokens=1200,
        )
        return {
            "goal": goal,
            "plan": plan,
            "used_memory": facts,
            "caller_id": CALLER_ID,
            "path_id": PATH_ID,
        }
    except Exception as e:
        return {"error": type(e).__name__, "caller_id": CALLER_ID}
