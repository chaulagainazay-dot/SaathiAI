"""Deterministic retrieval evaluation set (repository-grounded)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass
class EvalCase:
    id: str
    query: str
    expected_path_substrings: tuple[str, ...]
    forbidden_path_substrings: tuple[str, ...] = ()
    top_k: int = 8
    require_current: bool = True
    docs_only: bool = False
    tests_only: bool = False


EVAL_CASES: list[EvalCase] = [
    EvalCase(
        "event_bus",
        "Where is the canonical event bus defined?",
        ("saathi/events", "saathi/events.py", "eventstream", "test_events", "test_event_bus"),
    ),
    EvalCase(
        "browser_dispatch_tests",
        "Which tests protect browser dispatch governance?",
        ("test_m17_24_browser", "test_m17_23_browser", "test_m17_26"),
        tests_only=True,
    ),
    EvalCase(
        "governed_browser_milestone",
        "What milestone introduced governed browser sessions?",
        ("M17_25", "interactive_browser", "AUTONOMOUS_ROADMAP", "M17.25"),
    ),
    EvalCase(
        "trading_guardian_isolation",
        "Where is Trading Guardian isolation enforced for MCP?",
        ("mcp_governance", "MCP_INVENTORY", "EXTERNAL_CAPABILITY", "codebase_memory",
         "test_m17_25_mcp", "test_m18", "AUTONOMOUS_LOOP", "M17_25_VALIDATION",
         "M18_2", "browser_dispatch"),  # TG isolation asserted across governance tests/docs
        forbidden_path_substrings=("saathi/trade_journal",),
    ),
    EvalCase(
        "external_licensing",
        "Which document defines external repository licensing status?",
        ("EXTERNAL_CAPABILITY_STATUS", "SES-000E", "MCP_INVENTORY"),
        docs_only=True,
    ),
    EvalCase(
        "mission_entry",
        "What is the canonical mission execution entry point?",
        ("mission", "execution", "run_manager", "orchestrat"),
    ),
    EvalCase(
        "disable_codebase_memory",
        "Which configuration disables codebase memory?",
        ("mcp_governance", "policy", "MCP_INVENTORY", "SAATHI_MCP"),
    ),
    EvalCase(
        "critical_checks",
        "Where are critical checks registered?",
        ("critical_checks.json", "repair/manifest"),
    ),
    EvalCase(
        "mcp_namespace_policy",
        "Which files define the MCP namespace policy?",
        ("namespace.py", "mcp_governance", "MCP_INVENTORY"),
    ),
    EvalCase(
        "m18_1_docs",
        "Which documentation describes M18.1 MCP governance?",
        ("MCP_INVENTORY", "M17_25_VALIDATION", "EXTERNAL_CAPABILITY", "AUTONOMOUS_ROADMAP", "M18"),
        docs_only=True,
    ),
]


def run_evaluation(search_fn: Callable[..., dict]) -> dict:
    """Run eval cases against a search function returning RetrievalResult.to_dict()."""
    results = []
    passed = 0
    for case in EVAL_CASES:
        r = search_fn(
            case.query,
            top_k=case.top_k,
            documentation_only=case.docs_only,
            tests_only=case.tests_only,
        )
        hits = r.get("hits") or []
        paths = " ".join(h.get("path", "") for h in hits).lower()
        ok_expect = any(s.lower() in paths for s in case.expected_path_substrings)
        ok_forbid = not any(
            s.lower() in paths for s in case.forbidden_path_substrings
        ) if case.forbidden_path_substrings else True
        # top-k: at least one expected in first top_k (already limited)
        pass_case = bool(r.get("ok")) and ok_expect and ok_forbid and len(hits) <= case.top_k
        if pass_case:
            passed += 1
        results.append({
            "id": case.id,
            "pass": pass_case,
            "ok_expect": ok_expect,
            "ok_forbid": ok_forbid,
            "hit_count": len(hits),
            "top_paths": [h.get("path") for h in hits[:5]],
        })
    total = len(EVAL_CASES)
    return {
        "passed": passed,
        "total": total,
        "pass_rate": round(passed / total, 3) if total else 0.0,
        "cases": results,
    }
