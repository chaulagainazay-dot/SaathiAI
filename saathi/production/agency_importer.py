"""Director Importer — convert agency-agents prompts into SaathiAI Directors.

We do NOT plug the agency repo in directly (it is prompt-first; SaathiAI is
operating-system-first). Instead we import curated agent prompts as Directors
registered in the Prompt Registry, runnable through the Model Router with
Content Memory / Character Bible / Evidence context — so external prompt
engineering is reused while SaathiAI stays the source of truth.

Source: github.com/msitarzewski/agency-agents (curated subset in agency_prompts/).
"""
from __future__ import annotations

import re
from pathlib import Path

_DIR = Path(__file__).parent / "agency_prompts"


def _parse(md: str) -> dict:
    """Split YAML frontmatter (name/description) from the system-prompt body."""
    name, desc, body = "", "", md
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", md, re.S)
    if m:
        fm, body = m.group(1), m.group(2)
        for line in fm.splitlines():
            if line.lower().startswith("name:"):
                name = line.split(":", 1)[1].strip()
            elif line.lower().startswith("description:"):
                desc = line.split(":", 1)[1].strip()
    return {"name": name, "description": desc, "body": body.strip()}


def _template(body: str) -> str:
    """Make a render-safe prompt: escape literal braces, append the {task} slot."""
    safe = body.replace("{", "{{").replace("}", "}}")
    return safe + "\n\n---\n## Task\n{task}\n\nComplete the task above for SaathiAI. Reply directly."


def catalog() -> list[dict]:
    """The importable Directors (slug + name + description) from disk."""
    out = []
    if not _DIR.is_dir():
        return out
    for f in sorted(_DIR.glob("*.md")):
        p = _parse(f.read_text(encoding="utf-8"))
        out.append({"slug": f.stem, "name": p["name"] or f.stem, "description": p["description"]})
    return out


def import_directors(registry=None) -> int:
    """Register each curated agent as prompt `director.<slug>` in the Prompt
    Registry (idempotent — only bumps a version when the text changes)."""
    if registry is None:
        from saathi.ai_lab import default_registry
        registry = default_registry()
    n = 0
    for f in sorted(_DIR.glob("*.md")):
        p = _parse(f.read_text(encoding="utf-8"))
        if not p["body"]:
            continue
        if registry.register_or_update(f"director.{f.stem}", _template(p["body"]),
                                       purpose=p["description"][:200], author="agency-agents",
                                       project="director-library") is not None:
            n += 1
    return n
