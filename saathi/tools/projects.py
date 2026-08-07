from __future__ import annotations
"""Project awareness — Baadar 'lives inside' Ajay's working projects.

Registers project folders so Baadar knows them by name, can map their structure,
read any file, search the code, and check recent git changes. This is how Baadar
understands what Ajay is building and helps with it by voice.
"""
import json
import subprocess
from pathlib import Path

from .. import config

REGISTRY = config.ROOT / "data" / "projects.json"
SKIP_DIRS = {"node_modules", ".git", "dist", "build", ".next", "__pycache__",
             ".venv", "venv", "coverage", ".cache"}
TEXT_EXT = {".js", ".jsx", ".ts", ".tsx", ".py", ".json", ".md", ".css", ".html",
            ".vue", ".svelte", ".rules", ".yml", ".yaml", ".sql", ".sh", ".txt", ".env.example"}


def _load() -> dict:
    if REGISTRY.exists():
        try:
            return json.loads(REGISTRY.read_text())
        except Exception:
            return {}
    return {}


def _save(reg: dict):
    REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY.write_text(json.dumps(reg, indent=2))


def register_project(name: str, path: str) -> dict:
    p = Path(path).expanduser().resolve()
    if not p.is_dir():
        return {"error": "not a folder", "path": str(p)}
    reg = _load()
    reg[name.lower()] = str(p)
    _save(reg)
    return {"registered": name, "path": str(p)}


def list_projects() -> dict:
    return {"projects": _load()}


def _resolve(name: str) -> Path | None:
    reg = _load()
    if name.lower() in reg:
        return Path(reg[name.lower()])
    # fuzzy: any registered name containing the query
    for k, v in reg.items():
        if name.lower() in k or k in name.lower():
            return Path(v)
    return None


def project_overview(name: str) -> dict:
    """Structure + README + package.json + recent git changes — what the project IS."""
    root = _resolve(name)
    if not root or not root.is_dir():
        return {"error": f"project '{name}' not registered", "known": list(_load())}

    # file tree (skipping junk), capped
    tree = []
    for p in sorted(root.rglob("*")):
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        if p.is_file():
            tree.append(str(p.relative_to(root)))
        if len(tree) >= 200:
            break

    out = {"project": name, "path": str(root), "files": tree[:120],
           "file_count": len(tree)}
    readme = next((root / n for n in ("README.md", "readme.md") if (root / n).exists()), None)
    if readme:
        out["readme"] = readme.read_text(errors="replace")[:4000]
    pkg = root / "package.json"
    if pkg.exists():
        try:
            d = json.loads(pkg.read_text())
            out["stack"] = {"name": d.get("name"),
                            "scripts": list(d.get("scripts", {})),
                            "dependencies": list(d.get("dependencies", {}))[:25]}
        except Exception:
            pass
    # recent git activity
    git = subprocess.run(["git", "-C", str(root), "log", "--oneline", "-8"],
                         capture_output=True, text=True)
    if git.returncode == 0:
        out["recent_commits"] = git.stdout.strip().splitlines()
    return out


def read_project_file(name: str, relpath: str) -> dict:
    root = _resolve(name)
    if not root:
        return {"error": f"project '{name}' not registered"}
    f = (root / relpath).resolve()
    if not str(f).startswith(str(root)) or not f.exists():
        return {"error": "file not found in project", "relpath": relpath}
    return {"file": relpath, "content": f.read_text(errors="replace")[:20000]}


def plan_project_work(name: str, goal: str) -> dict:
    """Make a concrete step-by-step plan to achieve `goal` in the project,
    grounded in the project's actual structure and stack."""
    root = _resolve(name)
    if not root:
        return {"error": f"project '{name}' not registered"}
    ov = project_overview(name)
    ctx = (f"Project: {name} ({ov.get('stack', {}).get('name')})\n"
           f"Stack: {ov.get('stack', {}).get('dependencies')}\n"
           f"Files: {ov.get('files', [])[:60]}\n"
           f"Recent commits: {ov.get('recent_commits', [])}")
    from ..agent import SaathiAgent
    plan = SaathiAgent().complete(
        "You are Baadar, Ajay's coding assistant. Given this real project and a goal, "
        "produce a SHORT numbered plan (3-7 concrete steps) naming the actual files to "
        "create or edit and what to change. Be specific to the stack. End with the "
        "single best first step.",
        f"{ctx}\n\nGOAL: {goal}", max_tokens=600)
    return {"project": name, "goal": goal, "plan": plan,
            "note": "Say 'Baadar, do step 1' (or 'do the plan') to execute. "
                    "Changes are in a git repo, so they're reversible."}


def project_run(name: str, command: str) -> dict:
    """M49.3/M49.4: freeform project shell is always blocked.

    Fail closed before project resolution so unregistered names cannot
    become an alternate execution path. Use allowlisted command manifests
    via ExecutionGateway (m49.allowlisted_command). shell=True is never used.
    """
    return {
        "error": "freeform_shell_blocked",
        "blocked": True,
        "reason": (
            "M49.3/M49.4: freeform project shell (shell=True / arbitrary command "
            "strings) is prohibited. Use m49.allowlisted_command via ExecutionGateway."
        ),
        "message": "Freeform project_run blocked — no shell execution.",
        "outcome_class": "PROHIBITED",
        "project": name,
        "command_preview": str(command)[:80] if command else "",
        "shell": False,
    }


def project_edit_file(name: str, relpath: str, content: str) -> dict:
    """Create or overwrite a file inside the project (confirm before overwriting)."""
    root = _resolve(name)
    if not root:
        return {"error": f"project '{name}' not registered"}
    f = (root / relpath).resolve()
    if not str(f).startswith(str(root)):
        return {"error": "path escapes project"}
    existed = f.exists()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(content)
    return {"file": relpath, "mode": "overwrote" if existed else "created",
            "bytes": len(content.encode()),
            "tip": "Run 'git diff' in the project to review, 'git checkout' to undo."}


def search_project(name: str, query: str) -> dict:
    """Search the project's code for a keyword."""
    root = _resolve(name)
    if not root:
        return {"error": f"project '{name}' not registered"}
    args = ["grep", "-rin", "--max-count=3", query, str(root)]
    for d in SKIP_DIRS:
        args[1:1] = [f"--exclude-dir={d}"]
    r = subprocess.run(args, capture_output=True, text=True, timeout=30)
    lines = [l.replace(str(root) + "/", "") for l in r.stdout.splitlines()][:40]
    return {"query": query, "matches": lines, "count": len(lines)}
