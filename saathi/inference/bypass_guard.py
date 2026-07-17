"""M21.1 — Static AST guards against new direct-provider bypasses.

Scans repository Python under ``saathi/`` (excluding tests) for disallowed
patterns. Explicit allowlist for known adapters and residual paths.

Does not execute code. Deterministic. Reports file + line.
"""
from __future__ import annotations

import ast
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Optional

ROOT = Path(__file__).resolve().parents[2]  # SaathiAI repo root
SCAN_ROOT = ROOT / "saathi"

# Substrings / names that indicate direct provider SDK or HTTP bypass
FORBIDDEN_URL_SUBSTRINGS = (
    "api.openai.com",
    "api.anthropic.com",
    "api.groq.com",
    "generativelanguage.googleapis.com",
    "openrouter.ai/api",
)

FORBIDDEN_CALL_NAMES = frozenset({
    "OpenAI",
    "Anthropic",
})

# Paths relative to repo root allowed to contain the above (existing residuals)
ALLOWLIST_PREFIXES = (
    "saathi/llm.py",
    "saathi/inference/adapters/",
    "saathi/inference/bypass_guard.py",
    "saathi/tools/_llm_helper.py",
    "saathi/tools/cheap_llm.py",  # residual proxy — classified, not expanded
    "saathi/agent.py",
    "saathi/vision.py",
    "saathi/tools/voice.py",
    "saathi/tools/mr_yeti_voice.py",
    "saathi/tools/video_editor.py",
    "saathi/tools/speaking_eval.py",
    "saathi/tools/writing_eval.py",
    "saathi/tools/auto_dev.py",
    "saathi/tools/research.py",  # residual research helper; DEFER_WITH_GUARD
    "saathi/server.py",  # residual HTTP surfaces; DEFER_WITH_GUARD (no new copies)
    "saathi/infrastructure/human_browser/",
    "saathi/inference/provider_policy.py",
    "saathi/inference/path_inventory.py",
    "saathi/inference/residual_paths.py",
    "saathi/inference/contract.py",
    "saathi/inference/caller_policy.py",
    "saathi/inference/bypass_guard.py",
)

# Second InferenceRequest-like class definitions outside request.py are flagged
CANONICAL_REQUEST_FILE = "saathi/inference/request.py"


@dataclass(frozen=True)
class GuardFinding:
    rule: str
    path: str
    line: int
    detail: str
    severity: str = "blocking"  # blocking | warning

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT)).replace("\\", "/")
    except Exception:
        return str(path)


def _is_allowlisted(rel_path: str) -> bool:
    rp = rel_path.replace("\\", "/")
    for pref in ALLOWLIST_PREFIXES:
        if rp == pref or rp.startswith(pref):
            return True
    return False


def _iter_py_files(base: Path) -> Iterable[Path]:
    if not base.is_dir():
        return
    for p in base.rglob("*.py"):
        if "__pycache__" in p.parts:
            continue
        yield p


class _Visitor(ast.NodeVisitor):
    def __init__(self, rel_path: str) -> None:
        self.rel_path = rel_path
        self.findings: list[GuardFinding] = []

    def visit_Constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, str):
            for sub in FORBIDDEN_URL_SUBSTRINGS:
                if sub in node.value and not _is_allowlisted(self.rel_path):
                    self.findings.append(
                        GuardFinding(
                            rule="direct_provider_url",
                            path=self.rel_path,
                            line=getattr(node, "lineno", 0),
                            detail=f"forbidden URL substring {sub!r}",
                        )
                    )
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        name = ""
        if isinstance(node.func, ast.Name):
            name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            name = node.func.attr
        if name in FORBIDDEN_CALL_NAMES and not _is_allowlisted(self.rel_path):
            self.findings.append(
                GuardFinding(
                    rule="direct_sdk_constructor",
                    path=self.rel_path,
                    line=getattr(node, "lineno", 0),
                    detail=f"forbidden constructor {name}()",
                )
            )
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        if node.name in {"InferenceRequest", "GovernedInferenceRequest", "CanonicalInferenceRequest"}:
            if self.rel_path != CANONICAL_REQUEST_FILE and "test" not in self.rel_path:
                self.findings.append(
                    GuardFinding(
                        rule="duplicate_request_model",
                        path=self.rel_path,
                        line=getattr(node, "lineno", 0),
                        detail=f"request model {node.name} outside canonical package",
                    )
                )
        self.generic_visit(node)


def scan_file(path: Path) -> list[GuardFinding]:
    rel = _rel(path)
    try:
        src = path.read_text(encoding="utf-8")
    except Exception as e:
        return [
            GuardFinding(
                rule="read_error",
                path=rel,
                line=0,
                detail=str(e)[:200],
                severity="warning",
            )
        ]
    try:
        tree = ast.parse(src, filename=rel)
    except SyntaxError as e:
        return [
            GuardFinding(
                rule="syntax_error",
                path=rel,
                line=e.lineno or 0,
                detail=str(e),
                severity="warning",
            )
        ]
    v = _Visitor(rel)
    v.visit(tree)
    return v.findings


def scan_repository(
    root: Optional[Path] = None,
    *,
    only_saathi: bool = True,
) -> dict[str, Any]:
    base = (root or SCAN_ROOT) if only_saathi else (root or ROOT)
    findings: list[GuardFinding] = []
    files = 0
    for p in _iter_py_files(base if base.is_dir() else SCAN_ROOT):
        files += 1
        findings.extend(scan_file(p))
    blocking = [f for f in findings if f.severity == "blocking"]
    return {
        "schema": "m21.1.bypass_guard.v1",
        "milestone": "M21.1",
        "files_scanned": files,
        "finding_count": len(findings),
        "blocking_count": len(blocking),
        "ok": len(blocking) == 0,
        "findings": [f.to_dict() for f in findings],
        "allowlist_prefixes": list(ALLOWLIST_PREFIXES),
        "rules": [
            "direct_provider_url",
            "direct_sdk_constructor",
            "duplicate_request_model",
        ],
    }


def main() -> int:
    import json
    import sys

    rep = scan_repository()
    print(json.dumps(rep, indent=1))
    return 0 if rep["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
