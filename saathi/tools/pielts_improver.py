from __future__ import annotations
"""
pielts Auto-Improver — translates market intel into concrete UI/UX code improvements.

Reads market_intel/latest.json → picks highest-impact quick-win tasks →
generates specific React/CSS/JS diffs → writes them to a pending improvements queue.

Improvements are staged (not auto-committed) so Ajay can review before applying.
"""

import json
import os
import subprocess
from datetime import datetime
from pathlib import Path

from .. import config

PIELTS_DIR = Path.home() / "Downloads" / "ielts-practice-app"
IMPROVE_DIR = config.ROOT / "data" / "pielts_improvements"
IMPROVE_DIR.mkdir(parents=True, exist_ok=True)

# ── Helpers ───────────────────────────────────────────────────────────────────

def _ask_llm(prompt: str, system: str = "", timeout: int = 90) -> str:
    from ._llm_helper import ask_llm
    return ask_llm(prompt, system=system, timeout=timeout)


def _get_file_content(rel_path: str) -> str:
    """Read a file from the pielts project."""
    p = PIELTS_DIR / rel_path
    if p.exists():
        return p.read_text(encoding="utf-8")[:6000]
    return ""


def _key_files_snapshot() -> dict:
    """Read key pielts files for context."""
    key = {
        "src/index.css": _get_file_content("src/index.css")[:2000],
        "src/App.jsx": _get_file_content("src/App.jsx")[:1500],
        "src/pages/Dashboard.jsx": _get_file_content("src/pages/Dashboard.jsx")[:2000],
        "src/pages/NewDashboard.jsx": _get_file_content("src/pages/NewDashboard.jsx")[:2000],
    }
    return {k: v for k, v in key.items() if v}


# ── UI/UX Improvement generator ───────────────────────────────────────────────

def generate_ui_improvement(task: dict, code_context: dict) -> dict:
    """
    Given one improvement task + current code context,
    generate a specific actionable diff/suggestion.
    """
    ctx_text = "\n\n".join(
        f"--- {fname} ---\n{content}"
        for fname, content in list(code_context.items())[:2]
    )

    prompt = f"""
You are a senior React/CSS developer improving pielts.web.app — a free IELTS practice app.

IMPROVEMENT TASK:
Title: {task.get('title')}
Category: {task.get('category')}
Description: {task.get('description')}
Impact: {task.get('impact')}
Rationale: {task.get('rationale')}
Implementation hint: {task.get('implementation_hint')}
Target metric: {task.get('target_metric')}

RELEVANT CURRENT CODE:
{ctx_text[:3000]}

Generate a SPECIFIC, IMPLEMENTABLE improvement. Return JSON:
{{
  "summary": "one-line description of the change",
  "files_to_modify": ["src/index.css", "src/pages/Dashboard.jsx"],
  "changes": [
    {{
      "file": "src/index.css",
      "type": "css|jsx|js|new_component",
      "description": "what this change does",
      "code_snippet": "the actual CSS/JSX code to add or modify",
      "placement": "add at end|replace class .x|add after line containing '...'"
    }}
  ],
  "expected_outcome": "what users will experience differently",
  "before_after": {{
    "before": "current problematic state",
    "after": "improved state"
  }}
}}
Return ONLY valid JSON. Make the code specific and ready-to-use, not pseudocode.
"""
    from ._llm_helper import extract_json
    raw = _ask_llm(prompt, system="Return ONLY valid JSON with real implementable code.")
    result = extract_json(raw)
    if isinstance(result, dict):
        result["task"] = task
        result["generated_at"] = datetime.now().isoformat()
        return result
    return {"summary": "Parse failed", "task": task, "changes": []}


# ── Feature spec generator ────────────────────────────────────────────────────

def generate_feature_spec(task: dict) -> dict:
    """For new feature tasks, generate a product spec + implementation plan."""
    prompt = f"""
Write a product spec for adding this feature to pielts.web.app (React + Firebase app).

Feature: {task.get('title')}
Description: {task.get('description')}
User rationale: {task.get('rationale')}
Market signal: {task.get('target_metric')}

pielts tech stack: React 18, Vite, Firebase Firestore/Auth, Tailwind CSS, React Router v6.

Return JSON:
{{
  "feature_name": "...",
  "user_story": "As an IELTS student, I want to... so that...",
  "acceptance_criteria": ["..."],
  "ui_mockup_description": "describe the UI in detail",
  "new_components": ["ComponentName.jsx — description"],
  "firebase_schema": {{}},
  "estimated_hours": 0,
  "mvp_scope": ["what to build first"],
  "future_scope": ["what to add later"]
}}
Return ONLY valid JSON.
"""
    from ._llm_helper import extract_json
    raw = _ask_llm(prompt, system="Return ONLY valid JSON.")
    result = extract_json(raw)
    if isinstance(result, dict):
        result["task"] = task
        return result
    return {"feature_name": task.get("title", ""), "task": task}


# ── Batch improvement run ─────────────────────────────────────────────────────

def run_improvement_cycle(max_tasks: int = 5) -> dict:
    """
    Full cycle: load latest market intel → generate improvements → save queue.
    Returns summary of what was generated.
    """
    from .market_intel import get_latest, get_top_tasks

    latest = get_latest()
    if not latest:
        return {"ok": False, "error": "No market intel found. Run market research first."}

    tasks = get_top_tasks(max_tasks)
    if not tasks:
        return {"ok": False, "error": "No improvement tasks in latest market intel."}

    code_ctx = _key_files_snapshot()
    results = []

    for task in tasks:
        print(f"  🔧 Generating improvement: {task.get('title','?')[:60]}…")
        if task.get("category") in ("ui_ux", "content", "growth"):
            improvement = generate_ui_improvement(task, code_ctx)
        else:
            improvement = generate_feature_spec(task)
        results.append(improvement)

    # Save the improvement queue
    today = datetime.now().strftime("%Y-%m-%d_%H%M")
    queue_path = IMPROVE_DIR / f"queue_{today}.json"
    queue = {
        "generated_at": datetime.now().isoformat(),
        "source_report_date": latest.get("date"),
        "improvements": results,
        "status": "pending_review",
    }
    queue_path.write_text(json.dumps(queue, indent=2, ensure_ascii=False))
    (IMPROVE_DIR / "latest_queue.json").write_text(
        json.dumps(queue, indent=2, ensure_ascii=False)
    )

    print(f"  ✅ {len(results)} improvements queued → {queue_path.name}")
    return {
        "ok": True,
        "count": len(results),
        "queue_file": str(queue_path),
        "improvements": [
            {"title": r.get("task", {}).get("title", r.get("feature_name", "?")),
             "summary": r.get("summary", r.get("user_story", "")),
             "category": r.get("task", {}).get("category", "?")}
            for r in results
        ],
    }


def get_pending_queue() -> dict | None:
    """Load the latest pending improvement queue."""
    p = IMPROVE_DIR / "latest_queue.json"
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            pass
    return None


def apply_improvement(improvement_index: int) -> dict:
    """
    Apply a specific improvement from the pending queue to the pielts codebase.
    Returns success/failure with details.
    """
    queue = get_pending_queue()
    if not queue:
        return {"ok": False, "error": "No pending queue found"}

    improvements = queue.get("improvements", [])
    if improvement_index >= len(improvements):
        return {"ok": False, "error": f"Index {improvement_index} out of range ({len(improvements)} improvements)"}

    imp = improvements[improvement_index]
    changes = imp.get("changes", [])
    applied = []
    errors = []

    for change in changes:
        file_path = PIELTS_DIR / change.get("file", "")
        if not file_path.exists():
            errors.append(f"File not found: {change['file']}")
            continue

        placement = change.get("placement", "add at end")
        code = change.get("code_snippet", "")
        if not code:
            continue

        try:
            content = file_path.read_text(encoding="utf-8")
            if placement == "add at end":
                content += f"\n\n/* === Auto-improve: {imp.get('summary','')} === */\n{code}\n"
            elif placement.startswith("add after line containing"):
                marker = placement.split("'")[1] if "'" in placement else ""
                if marker and marker in content:
                    content = content.replace(marker, marker + "\n" + code, 1)
                else:
                    content += f"\n{code}\n"
            # Backup original
            backup = file_path.with_suffix(file_path.suffix + ".bak")
            if not backup.exists():
                backup.write_text(file_path.read_text())
            file_path.write_text(content, encoding="utf-8")
            applied.append(change["file"])
        except Exception as e:
            errors.append(f"{change['file']}: {e}")

    return {
        "ok": len(applied) > 0,
        "applied_to": applied,
        "errors": errors,
        "improvement": imp.get("summary", ""),
    }
