from __future__ import annotations
"""
Baadar Skills Dispatcher — auto-routes tasks to installed Claude Code skills.

Maps intent keywords → skill name → reads SKILL.md → returns invocation prompt.
Used by Baadar chat to auto-pick the best skill for any task.
"""

import os
import subprocess
from pathlib import Path

SKILLS_DIR = Path.home() / ".claude" / "skills"

# Intent → skill name routing table (mirrors ~/.claude/CLAUDE.md)
SKILL_ROUTES = {
    # Video
    "caption":             "embedded-captions",
    "subtitle":            "embedded-captions",
    "explainer video":     "faceless-explainer",
    "faceless":            "faceless-explainer",
    "product video":       "product-launch-video",
    "launch video":        "product-launch-video",
    "html video":          "hyperframes",
    "render video":        "hyperframes",
    "animation":           "hyperframes-animation",
    "motion graphic":      "motion-graphics",
    "general video":       "general-video",
    "website to video":    "website-to-video",
    "pr to video":         "pr-to-video",
    # Design
    "banner":              "ckm-banner-design",
    "social image":        "ckm-banner-design",
    "ui component":        "ckm-ui-styling",
    "interface":           "ui-ux-pro-max",
    "logo":                "ckm-brand",
    "brand":               "ckm-brand",
    "design system":       "ckm-design-system",
    "slide":               "ckm-slides",
    "presentation":        "ckm-slides",
    "art":                 "algorithmic-art",
    # Documents
    "word doc":            "docx",
    "docx":                "docx",
    "pdf":                 "pdf",
    "excel":               "xlsx",
    "spreadsheet":         "xlsx",
    "powerpoint":          "pptx",
    "pptx":                "pptx",
    # Engineering
    "prd":                 "prd",
    "product spec":        "prd",
    "autonomous":          "ralph",
    "loop agent":          "ralph",
    "parallel":            "dispatching-parallel-agents",
    "code review":         "requesting-code-review",
    "debug":               "systematic-debugging",
    "execute plan":        "executing-plans",
    "write plan":          "writing-plans",
    "finish branch":       "finishing-a-development-branch",
    "brainstorm":          "brainstorming",
    "tdd":                 "test-driven-development",
    "test driven":         "test-driven-development",
    "web app test":        "webapp-testing",
    "mcp":                 "mcp-builder",
    "react artifact":      "web-artifacts-builder",
    "seo":                 "seo-audit",
    "karpathy":            "karpathy-guidelines",
}

# Skills that always apply to every session
ALWAYS_ON = [
    "karpathy-guidelines",
    "verification-before-completion",
]


def route(task: str) -> str | None:
    """Return the best skill name for a given task description."""
    task_lower = task.lower()
    for keyword, skill in SKILL_ROUTES.items():
        if keyword in task_lower:
            return skill
    return None


def skill_prompt(skill_name: str) -> str | None:
    """Read and return the SKILL.md content for a given skill."""
    skill_path = SKILLS_DIR / skill_name / "SKILL.md"
    if skill_path.exists():
        return skill_path.read_text()
    # Try flat .md file
    flat = SKILLS_DIR / f"{skill_name}.md"
    if flat.exists():
        return flat.read_text()
    return None


def auto_dispatch(task: str) -> dict:
    """
    Auto-pick the best skill for a task and return the invocation context.

    Returns:
      {
        skill: str | None,
        prompt: str | None,   # SKILL.md content to prepend
        always_on: list[str], # always-on skills to also inject
        suggestion: str,      # human-readable suggestion
      }
    """
    skill = route(task)
    prompt = skill_prompt(skill) if skill else None

    always_prompts = {}
    for s in ALWAYS_ON:
        p = skill_prompt(s)
        if p:
            always_prompts[s] = p

    suggestion = f"Auto-dispatching to /{skill}" if skill else "No specific skill matched — using general reasoning"

    return {
        "skill":       skill,
        "prompt":      prompt,
        "always_on":   ALWAYS_ON,
        "always_prompts": always_prompts,
        "suggestion":  suggestion,
    }


def list_skills() -> list[str]:
    """Return all installed skill names."""
    if not SKILLS_DIR.exists():
        return []
    return sorted(p.name for p in SKILLS_DIR.iterdir() if p.is_dir() and (p / "SKILL.md").exists())


def search_skills(query: str) -> list[str]:
    """Search installed skills by keyword match in name or SKILL.md."""
    results = []
    q = query.lower()
    for skill_dir in SKILLS_DIR.iterdir():
        if not skill_dir.is_dir():
            continue
        if q in skill_dir.name.lower():
            results.append(skill_dir.name)
            continue
        skill_md = skill_dir / "SKILL.md"
        if skill_md.exists() and q in skill_md.read_text().lower():
            results.append(skill_dir.name)
    return sorted(results)
