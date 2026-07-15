"""Deterministic evaluation for Unified Knowledge Service."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from saathi.knowledge.types import RetrievalProfile


@dataclass
class UKEvalCase:
    id: str
    query: str
    profile: RetrievalProfile
    expected_path_substrings: tuple[str, ...]
    forbidden_path_substrings: tuple[str, ...] = ()
    require_multi_source: bool = False
    top_k: int = 10


EVAL_CASES: list[UKEvalCase] = [
    UKEvalCase(
        "symbol_event_bus",
        "Where is the canonical event bus defined?",
        RetrievalProfile.FAST_LOOKUP,
        ("saathi/events", "event_bus", "test_events"),
    ),
    UKEvalCase(
        "architecture_docs",
        "SaathiOS architecture principles SES",
        RetrievalProfile.CODE_EXPLAIN,
        ("SES-000", "architecture", "AUTONOMOUS", "docs/"),
    ),
    UKEvalCase(
        "tests_browser",
        "browser dispatch governance tests",
        RetrievalProfile.CODE_EXPLAIN,
        ("test_m17_24", "test_m17_23", "browser"),
    ),
    UKEvalCase(
        "milestone_m18",
        "M18.2 codebase memory indexing documentation",
        RetrievalProfile.AUDIT_EVIDENCE,
        ("M18", "codebase_memory", "MCP_INVENTORY", "VALIDATION"),
    ),
    UKEvalCase(
        "provider_insforge",
        "InsForge provider pilot status capability",
        RetrievalProfile.MISSION_CONTEXT,
        ("insforge", "providers"),
    ),
    UKEvalCase(
        "sensitive_env_denied",
        ".env credentials API keys secrets",
        RetrievalProfile.CODE_EXPLAIN,
        (),  # no required hits
        forbidden_path_substrings=(".env", "credentials.json", "id_rsa"),
    ),
]


def run_uk_evaluation(retrieve_fn: Callable) -> dict:
    """retrieve_fn(query, profile) -> KnowledgeResponse-like dict."""
    passed = 0
    cases_out = []
    for c in EVAL_CASES:
        r = retrieve_fn(c.query, c.profile, c.top_k)
        hits = r.get("results") or r.get("hits") or []
        paths = " ".join(
            (h.get("path") if isinstance(h, dict) else getattr(h, "path", "")) or ""
            for h in hits
        ).lower()
        ok_exp = (
            True if not c.expected_path_substrings
            else any(s.lower() in paths for s in c.expected_path_substrings)
        )
        ok_forb = not any(s.lower() in paths for s in c.forbidden_path_substrings)
        # sensitive case: pass if no forbidden paths appear
        if c.id == "sensitive_env_denied":
            ok = ok_forb and r.get("ok", True)
        else:
            ok = bool(r.get("ok", True)) and ok_exp and ok_forb
        if ok:
            passed += 1
        cases_out.append({
            "id": c.id,
            "pass": ok,
            "paths": paths[:200],
            "hit_count": len(hits),
        })
    total = len(EVAL_CASES)
    return {
        "passed": passed,
        "total": total,
        "pass_rate": round(passed / total, 3) if total else 0.0,
        "cases": cases_out,
    }
