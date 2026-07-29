"""Allowlisted knowledge source discovery (bounded, no recursive runaway)."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .models import (
    ALLOWED_SUFFIXES,
    KnowledgeSourceSpec,
    Sensitivity,
    SourceAuthority,
    SourceType,
)
from .security import is_denied_path, resolve_repo_root, safe_join

# Explicit allowlist of relative paths / directory globs (one level or two).
# Protected design-spec is intentionally absent.
STATIC_SOURCE_SPECS: list[KnowledgeSourceSpec] = [
    KnowledgeSourceSpec(
        source_id="auto_loop_state",
        title="Autonomous LOOP_STATE",
        source_type=SourceType.AUTONOMOUS_RUNTIME,
        authority=SourceAuthority.AUTHORITATIVE_RUNTIME,
        relative_path="docs/autonomous/LOOP_STATE.json",
    ),
    KnowledgeSourceSpec(
        source_id="auto_current_goal",
        title="Current Autonomous Goal",
        source_type=SourceType.AUTONOMOUS_RUNTIME,
        authority=SourceAuthority.AUTHORITATIVE_RUNTIME,
        relative_path="docs/autonomous/CURRENT_GOAL.md",
    ),
    KnowledgeSourceSpec(
        source_id="auto_task_queue",
        title="Autonomous Task Queue",
        source_type=SourceType.AUTONOMOUS_RUNTIME,
        authority=SourceAuthority.AUTHORITATIVE_RUNTIME,
        relative_path="docs/autonomous/TASK_QUEUE.md",
    ),
    KnowledgeSourceSpec(
        source_id="auto_decisions",
        title="Autonomous Decisions",
        source_type=SourceType.AUTONOMOUS_RUNTIME,
        authority=SourceAuthority.AUTHORITATIVE_RUNTIME,
        relative_path="docs/autonomous/DECISIONS.md",
    ),
    KnowledgeSourceSpec(
        source_id="auto_blockers",
        title="Autonomous Blockers",
        source_type=SourceType.AUTONOMOUS_RUNTIME,
        authority=SourceAuthority.AUTHORITATIVE_RUNTIME,
        relative_path="docs/autonomous/BLOCKERS.md",
    ),
    KnowledgeSourceSpec(
        source_id="auto_final_report",
        title="Autonomous Final Report",
        source_type=SourceType.AUTONOMOUS_RUNTIME,
        authority=SourceAuthority.AUTHORITATIVE_RUNTIME,
        relative_path="docs/autonomous/FINAL_REPORT.md",
    ),
    KnowledgeSourceSpec(
        source_id="auto_roadmap",
        title="Autonomous Roadmap",
        source_type=SourceType.ROADMAP,
        authority=SourceAuthority.AUTHORITATIVE_DOCUMENTATION,
        relative_path="docs/AUTONOMOUS_ROADMAP.md",
    ),
    KnowledgeSourceSpec(
        source_id="capability_maturity",
        title="Capability Maturity Matrix",
        source_type=SourceType.CAPABILITY,
        authority=SourceAuthority.AUTHORITATIVE_DOCUMENTATION,
        relative_path="docs/CAPABILITY_MATURITY_MATRIX.md",
    ),
    KnowledgeSourceSpec(
        source_id="capability_matrix_root",
        title="Capability Matrix",
        source_type=SourceType.CAPABILITY,
        authority=SourceAuthority.AUTHORITATIVE_DOCUMENTATION,
        relative_path="CAPABILITY_MATRIX.md",
        optional=True,
    ),
    KnowledgeSourceSpec(
        source_id="technical_debt",
        title="Technical Debt",
        source_type=SourceType.REPOSITORY_DOCUMENTATION,
        authority=SourceAuthority.AUTHORITATIVE_DOCUMENTATION,
        relative_path="TECHNICAL_DEBT.md",
        optional=True,
    ),
    KnowledgeSourceSpec(
        source_id="brain",
        title="Brain",
        source_type=SourceType.REPOSITORY_DOCUMENTATION,
        authority=SourceAuthority.AUTHORITATIVE_DOCUMENTATION,
        relative_path="Brain.md",
        optional=True,
        max_bytes=200_000,
    ),
    KnowledgeSourceSpec(
        source_id="business",
        title="Business",
        source_type=SourceType.REPOSITORY_DOCUMENTATION,
        authority=SourceAuthority.AUTHORITATIVE_DOCUMENTATION,
        relative_path="Business.md",
        optional=True,
        max_bytes=120_000,
    ),
    KnowledgeSourceSpec(
        source_id="agents_md",
        title="Agent Instructions",
        source_type=SourceType.REPOSITORY_DOCUMENTATION,
        authority=SourceAuthority.AUTHORITATIVE_DOCUMENTATION,
        relative_path="AGENTS.md",
        optional=True,
    ),
    KnowledgeSourceSpec(
        source_id="voice_backend_config",
        title="Voice Backend Configuration",
        source_type=SourceType.APPLICATION_DOMAIN,
        authority=SourceAuthority.AUTHORITATIVE_DOCUMENTATION,
        relative_path="docs/autonomous/VOICE_BACKEND_CONFIGURATION.md",
        optional=True,
    ),
    KnowledgeSourceSpec(
        source_id="voice_backend_decision",
        title="Voice Backend Decision",
        source_type=SourceType.APPLICATION_DOMAIN,
        authority=SourceAuthority.AUTHORITATIVE_DOCUMENTATION,
        relative_path="docs/autonomous/VOICE_BACKEND_DECISION.md",
        optional=True,
    ),
    KnowledgeSourceSpec(
        source_id="docs_decisions",
        title="Platform Decisions Log",
        source_type=SourceType.REPOSITORY_DOCUMENTATION,
        authority=SourceAuthority.AUTHORITATIVE_DOCUMENTATION,
        relative_path="docs/DECISIONS.md",
        optional=True,
    ),
    KnowledgeSourceSpec(
        source_id="docs_external_capability",
        title="External Capability Status",
        source_type=SourceType.CAPABILITY,
        authority=SourceAuthority.AUTHORITATIVE_DOCUMENTATION,
        relative_path="docs/EXTERNAL_CAPABILITY_STATUS.md",
        optional=True,
    ),
]

# Directory packs: enumerate files under these dirs with filters
DIRECTORY_PACKS: list[tuple[str, SourceType, SourceAuthority, int]] = [
    (
        "docs/autonomous/milestones",
        SourceType.CERTIFICATION,
        SourceAuthority.AUTHORITATIVE_EVIDENCE,
        2,
    ),
    (
        "docs/evidence/m86",
        SourceType.EVIDENCE,
        SourceAuthority.AUTHORITATIVE_EVIDENCE,
        1,
    ),
    (
        "docs/evidence/m79",
        SourceType.EVIDENCE,
        SourceAuthority.AUTHORITATIVE_EVIDENCE,
        1,
    ),
    (
        "docs/evidence/m78",
        SourceType.EVIDENCE,
        SourceAuthority.AUTHORITATIVE_EVIDENCE,
        1,
    ),
    (
        "docs/evidence/m77",
        SourceType.EVIDENCE,
        SourceAuthority.AUTHORITATIVE_EVIDENCE,
        1,
    ),
    (
        "docs/evidence/m72",
        SourceType.EVIDENCE,
        SourceAuthority.AUTHORITATIVE_EVIDENCE,
        1,
    ),
]


def _is_allowed_file(path: Path) -> bool:
    if not path.is_file():
        return False
    if path.suffix.lower() not in ALLOWED_SUFFIXES:
        return False
    name = path.name.lower()
    if name.startswith("."):
        return False
    # Prefer certification summaries over huge dumps
    if path.suffix.lower() == ".json" and "cert" not in name and "summary" not in name and "loop_state" not in name:
        # allow small json state files only when named allowlisted
        if path.stat().st_size > 80_000:
            return False
    return True


def discover_sources(repo_root: str | Path | None = None) -> list[KnowledgeSourceSpec]:
    root = resolve_repo_root(repo_root)
    found: list[KnowledgeSourceSpec] = []
    seen: set[str] = set()

    for spec in STATIC_SOURCE_SPECS:
        path = safe_join(root, spec.relative_path)
        if path is None or not path.is_file():
            if not spec.optional:
                # still register for health failed tracking
                found.append(spec)
            continue
        if is_denied_path(path, root=root):
            continue
        if spec.source_id not in seen:
            seen.add(spec.source_id)
            found.append(spec)

    for dir_rel, stype, authority, depth in DIRECTORY_PACKS:
        base = safe_join(root, dir_rel)
        if base is None or not base.is_dir():
            continue
        files = _walk_bounded(base, root=root, max_depth=depth)
        for path in files:
            if not _is_allowed_file(path):
                continue
            rel = str(path.relative_to(root)).replace("\\", "/")
            sid = f"file:{rel}"
            if sid in seen:
                continue
            seen.add(sid)
            found.append(
                KnowledgeSourceSpec(
                    source_id=sid,
                    title=path.stem.replace("_", " "),
                    source_type=stype,
                    authority=authority,
                    relative_path=rel,
                    optional=True,
                )
            )
    return found


def _walk_bounded(base: Path, *, root: Path, max_depth: int) -> list[Path]:
    """Non-recursive runaway walk with depth bound."""
    out: list[Path] = []
    base = base.resolve()
    if is_denied_path(base, root=root):
        return out
    stack: list[tuple[Path, int]] = [(base, 0)]
    visited = 0
    max_files = 200
    while stack and visited < max_files:
        current, depth = stack.pop()
        try:
            entries = sorted(current.iterdir(), key=lambda p: p.name)
        except OSError:
            continue
        for entry in entries:
            visited += 1
            if visited > max_files:
                break
            if entry.is_symlink():
                continue
            if entry.is_dir():
                if depth < max_depth and not is_denied_path(entry, root=root):
                    stack.append((entry, depth + 1))
            elif entry.is_file():
                if not is_denied_path(entry, root=root):
                    out.append(entry)
    return out


def specs_by_id(specs: Iterable[KnowledgeSourceSpec]) -> dict[str, KnowledgeSourceSpec]:
    return {s.source_id: s for s in specs}
