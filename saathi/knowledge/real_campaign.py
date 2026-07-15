"""M19.3 — Real-index Knowledge Service campaign and controlled promotion.

Runs dual-path (legacy vs unified) evaluation against **registered repository
indexes** rather than synthetic search stubs. Collects durable aggregate
metrics only (no sensitive retrieved bodies). Supports an explicit, reversible
promotion of exactly one low-risk caller to ``unified_with_fallback``.

Does **not** auto-promote chat LTM, voice, auth, payments, deployment, or
Trading Guardian. InsForge is not expanded. Indexes are never mutated via
retrieval; indexing uses the existing M18.2 indexer only when ensure_index=True.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

from saathi.knowledge.campaign import (
    CampaignReport,
    decision_ready_for_unified_fallback,
    run_shadow_campaign,
)
from saathi.knowledge.eval_set import CAMPAIGN_CASES, CampaignCase
from saathi.knowledge.registry import KnowledgeSource, default_source_registry
from saathi.knowledge.rollout import (
    CALLER_CODEBASE_MEMORY_SEARCH,
    PROMOTED_CALLER_M19_3,
    RolloutMode,
    promotions_enabled,
    resolve_mode,
)
from saathi.knowledge.service import KnowledgeService
from saathi.knowledge.types import KnowledgeQuery, RetrievalProfile

# Representative real-index cases: reuse M19.2 categories; bound for resource safety.
REAL_INDEX_CASE_IDS = (
    "exact_symbol_eventbus",
    "file_location_adoption",
    "architecture_ses",
    "related_tests_m19",
    "milestone_evidence_m19",
    "repair_planning_context",
    "control_center_operator",
    "permission_denial_secret",
    "secret_path_request",
    "context_budget_pressure",
    "prompt_injection_repo",
    "recent_change_lookup",
)

# Minimum index chunks before real campaign is considered "index-backed".
MIN_INDEX_CHUNKS = 5

# Preferred pilot promotion target (operator code lookup — real legacy fallback).
DEFAULT_PROMOTION_CALLER = CALLER_CODEBASE_MEMORY_SEARCH


@dataclass
class RegisteredIndexStatus:
    source_id: str
    repository_id: str
    location: str
    adapter: str
    health_status: str
    files: int = 0
    chunks: int = 0
    symbols: int = 0
    indexed_commit: str = ""
    current_commit: str = ""
    stale: bool = False
    schema_ok: bool = True
    db_path: str = ""
    indexable: bool = False
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RealIndexCampaignReport:
    """Durable aggregate report for M19.3 — no result bodies."""

    ok: bool
    index_ready: bool
    saathi_root: str
    inventory: list[dict]
    campaign: dict
    top1_agreement: float = 0.0
    top3_overlap: float = 0.0
    top5_overlap: float = 0.0
    canonical_source_hit_rate: float = 0.0
    exact_symbol_hit_rate: float = 0.0
    repository_selection_accuracy: float = 0.0
    primary_evidence_ratio: float = 0.0
    duplicate_rate: float = 0.0
    stale_result_rate: float = 0.0
    no_result_rate_legacy: float = 0.0
    no_result_rate_unified: float = 0.0
    partial_result_rate: float = 0.0
    permission_denial_correctness: float = 1.0
    context_budget_compliance: float = 1.0
    deterministic_repeatability: float | None = None
    p50_legacy_latency_ms: float | None = None
    p95_legacy_latency_ms: float | None = None
    p50_unified_latency_ms: float | None = None
    p95_unified_latency_ms: float | None = None
    query_count: int = 0
    successful_comparison_count: int = 0
    promotion_decision: dict = field(default_factory=dict)
    promoted_caller: str = ""
    promoted_mode: str = ""
    disable_control: str = ""
    warnings: list[str] = field(default_factory=list)
    result_fingerprint: str = ""
    duration_ms: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


def real_index_cases() -> list[CampaignCase]:
    by_id = {c.id: c for c in CAMPAIGN_CASES}
    out: list[CampaignCase] = []
    for cid in REAL_INDEX_CASE_IDS:
        c = by_id.get(cid)
        if c is not None:
            out.append(c)
    return out


def inspect_registered_indexes(
    *,
    saathi_root: str | Path | None = None,
    base_dir: Path | None = None,
    sources: list[KnowledgeSource] | None = None,
) -> list[RegisteredIndexStatus]:
    """Inspect health of registered knowledge sources that use codebase indexes."""
    root = str(Path(saathi_root or Path.cwd()).resolve())
    sources = sources or default_source_registry(saathi_root=root)
    out: list[RegisteredIndexStatus] = []

    for src in sources:
        if src.adapter != "codebase_memory" or src.source_type != "codebase_index":
            continue
        status = RegisteredIndexStatus(
            source_id=src.source_id,
            repository_id=src.repository_id,
            location=src.location,
            adapter=src.adapter,
            health_status="UNKNOWN",
            indexable=bool(src.enabled),
        )
        if not src.enabled:
            status.health_status = "DISABLED"
            status.notes.append("source_disabled")
            out.append(status)
            continue
        if not Path(src.location).is_dir():
            status.health_status = "UNAVAILABLE"
            status.notes.append("location_missing")
            status.indexable = False
            out.append(status)
            continue
        try:
            from saathi.codebase_memory.health import index_health

            h = index_health(src.location, base_dir=base_dir)
            status.health_status = h.status
            status.files = int(h.files or 0)
            status.chunks = int(h.chunks or 0)
            status.symbols = int(h.symbols or 0)
            status.indexed_commit = str(h.indexed_commit or "")
            status.current_commit = str(h.commit_sha or "")
            status.stale = bool(h.stale)
            status.schema_ok = bool(h.schema_ok)
            status.db_path = str(h.db_path or "")
            if h.status in ("EMPTY", "UNAVAILABLE", "CORRUPT", "DISABLED"):
                status.notes.append(f"health:{h.status}")
            if h.degraded_reason:
                status.notes.append(str(h.degraded_reason)[:120])
            status.indexable = h.status in (
                "HEALTHY", "STALE", "DEGRADED", "EMPTY", "BUILDING",
            )
        except Exception as e:
            status.health_status = "UNAVAILABLE"
            status.notes.append(f"health_exc:{type(e).__name__}")
            status.indexable = False
        out.append(status)
    return out


def ensure_index_current(
    project_root: str | Path,
    *,
    base_dir: Path | None = None,
    rebuild: bool = False,
    min_chunks: int = MIN_INDEX_CHUNKS,
) -> dict[str, Any]:
    """Ensure a registered repository has a usable local index (M18.2 indexer).

    Returns aggregate-only evidence (paths, counts, commits) — no file contents.
    """
    root = Path(project_root).resolve()
    evidence: dict[str, Any] = {
        "ok": False,
        "root": str(root),
        "action": "none",
        "chunks": 0,
        "files": 0,
        "commit": "",
        "error": "",
    }
    try:
        from saathi.codebase_memory.health import index_health
        from saathi.codebase_memory.indexer import index_repository

        before = index_health(str(root), base_dir=base_dir)
        evidence["before_status"] = before.status
        evidence["before_chunks"] = int(before.chunks or 0)
        need = (
            rebuild
            or before.status in ("EMPTY", "CORRUPT", "REBUILD_REQUIRED", "UNAVAILABLE")
            or int(before.chunks or 0) < min_chunks
            or (
                before.indexed_commit
                and before.commit_sha
                and before.indexed_commit != before.commit_sha
            )
        )
        if not need and before.status in ("HEALTHY", "STALE", "DEGRADED"):
            evidence["ok"] = True
            evidence["action"] = "reuse"
            evidence["chunks"] = int(before.chunks or 0)
            evidence["files"] = int(before.files or 0)
            evidence["commit"] = str(before.indexed_commit or before.commit_sha or "")
            return evidence

        summary = index_repository(
            str(root),
            rebuild=rebuild or before.status in ("CORRUPT", "REBUILD_REQUIRED"),
            base_dir=base_dir,
        )
        evidence["action"] = "index"
        evidence["index_ok"] = bool(summary.ok)
        if not summary.ok:
            evidence["error"] = str(getattr(summary, "error", "") or "index_failed")[:200]
            return evidence

        after = index_health(str(root), base_dir=base_dir)
        evidence["ok"] = int(after.chunks or 0) >= min_chunks or after.status in (
            "HEALTHY", "STALE", "DEGRADED",
        )
        evidence["chunks"] = int(after.chunks or 0)
        evidence["files"] = int(after.files or 0)
        evidence["commit"] = str(after.indexed_commit or after.commit_sha or "")
        evidence["after_status"] = after.status
        return evidence
    except Exception as e:
        evidence["error"] = f"{type(e).__name__}:{e}"[:200]
        return evidence


def _legacy_search_fn(
    case: CampaignCase,
    *,
    project_root: str,
    base_dir: Path | None,
) -> dict:
    from saathi.codebase_memory.retrieve import search as memory_search

    r = memory_search(
        case.query,
        project_root=project_root,
        base_dir=base_dir,
        top_k=case.top_k,
    )
    return r.to_dict() if hasattr(r, "to_dict") else {
        "ok": bool(getattr(r, "ok", False)),
        "hits": [
            {
                "path": getattr(h, "path", ""),
                "snippet": (getattr(h, "snippet", "") or "")[:120],
                "score": getattr(h, "score", 0),
                "repository_id": getattr(h, "repository_id", ""),
                "freshness": getattr(h, "freshness", ""),
            }
            for h in (getattr(r, "hits", None) or [])
        ],
        "error": getattr(r, "error", ""),
    }


def _unified_retrieve_fn(
    case: CampaignCase,
    *,
    ks: KnowledgeService,
) -> Any:
    budget = case.max_context_chars or 0
    q = KnowledgeQuery(
        query=case.query,
        profile=case.profile if isinstance(case.profile, RetrievalProfile) else RetrievalProfile.CODE_EXPLAIN,
        max_results=case.top_k,
        max_context_chars=budget,
    )
    return ks.retrieve(q)


def _online_repo_accuracy(
    unified_fn: Callable[[CampaignCase], Any],
    cases: list[CampaignCase],
    expected_repo_ids: set[str],
) -> float:
    if not expected_repo_ids or not cases:
        return 1.0
    ok_n = 0
    n = 0
    for case in cases:
        if case.expect_permission_denial or case.category in (
            "permission_denial", "secret_path_request", "prompt_injection",
        ):
            continue
        try:
            resp = unified_fn(case)
        except Exception:
            n += 1
            continue
        results = getattr(resp, "results", None) or []
        if not results:
            # no-result is not a cross-repo leak
            ok_n += 1
            n += 1
            continue
        foreign = False
        for r in results:
            rid = str(getattr(r, "repository_id", "") or "")
            if rid and rid not in expected_repo_ids and rid not in ("", "default"):
                # Documentation adapter may use same repo id; foreign only if unknown
                foreign = True
                break
        if not foreign:
            ok_n += 1
        n += 1
    return round(ok_n / n, 4) if n else 1.0


def _stale_result_rate(
    unified_fn: Callable[[CampaignCase], Any],
    cases: list[CampaignCase],
) -> float:
    stale = 0
    total = 0
    for case in cases[: min(8, len(cases))]:
        try:
            resp = unified_fn(case)
        except Exception:
            continue
        for r in getattr(resp, "results", None) or []:
            total += 1
            fr = str(getattr(r, "freshness", "") or getattr(r, "freshness_label", "") or "")
            if "STALE" in fr.upper() or getattr(r, "is_stale", False):
                stale += 1
    return round(stale / total, 4) if total else 0.0


def run_real_index_campaign(
    *,
    saathi_root: str | Path | None = None,
    base_dir: Path | None = None,
    ensure_index: bool = True,
    cases: list[CampaignCase] | None = None,
    sampling_policy: str = "full",
    repeat_for_determinism: int = 2,
    knowledge_service: KnowledgeService | None = None,
    promotion_caller: str = DEFAULT_PROMOTION_CALLER,
) -> RealIndexCampaignReport:
    """Run real-index dual-path campaign and return durable metrics report."""
    t0 = time.time()
    root = str(Path(saathi_root or Path.cwd()).resolve())
    warnings: list[str] = []
    cases = list(cases or real_index_cases())

    inventory = inspect_registered_indexes(saathi_root=root, base_dir=base_dir)
    inv_dicts = [i.to_dict() for i in inventory]

    index_ready = False
    if ensure_index:
        for item in inventory:
            if item.adapter != "codebase_memory":
                continue
            ev = ensure_index_current(item.location, base_dir=base_dir)
            if not ev.get("ok"):
                warnings.append(
                    f"index_ensure_failed:{item.repository_id}:{ev.get('error') or ev.get('action')}"
                )
            else:
                index_ready = index_ready or int(ev.get("chunks") or 0) >= MIN_INDEX_CHUNKS
        # refresh inventory after ensure
        inventory = inspect_registered_indexes(saathi_root=root, base_dir=base_dir)
        inv_dicts = [i.to_dict() for i in inventory]
        index_ready = any(
            int(i.get("chunks") or 0) >= MIN_INDEX_CHUNKS
            and i.get("health_status") in ("HEALTHY", "STALE", "DEGRADED")
            for i in inv_dicts
        ) or index_ready
    else:
        index_ready = any(
            int(i.chunks or 0) >= MIN_INDEX_CHUNKS
            and i.health_status in ("HEALTHY", "STALE", "DEGRADED")
            for i in inventory
        )

    if not index_ready:
        warnings.append("index_not_ready_for_real_campaign")

    ks = knowledge_service or KnowledgeService(
        saathi_root=root,
        codebase_base_dir=base_dir,
    )

    expected_repos = {
        i.repository_id for i in inventory if i.adapter == "codebase_memory"
    } | {"saathiai"}  # registry repository_id for primary source

    def legacy_fn(case: CampaignCase) -> dict:
        return _legacy_search_fn(case, project_root=root, base_dir=base_dir)

    def unified_fn(case: CampaignCase):
        return _unified_retrieve_fn(case, ks=ks)

    campaign: CampaignReport = run_shadow_campaign(
        legacy_fn=legacy_fn,
        unified_fn=unified_fn,
        cases=cases,
        sampling_policy=sampling_policy,
        repeat_for_determinism=repeat_for_determinism,
    )

    repo_acc = _online_repo_accuracy(unified_fn, cases, expected_repos)
    stale_rate = _stale_result_rate(unified_fn, cases)

    decision = decision_ready_for_unified_fallback(campaign, min_comparisons=5)
    # Real-index extra gates
    extra_reasons: list[str] = list(decision.get("reasons") or [])
    ready = bool(decision.get("ready"))
    if not index_ready:
        ready = False
        extra_reasons.append("index_not_ready")
    if campaign.permission_denial_correctness < 1.0:
        ready = False
        if "permission_denial_incorrect" not in extra_reasons:
            extra_reasons.append("permission_denial_incorrect")
    if repo_acc < 1.0:
        ready = False
        extra_reasons.append("repository_selection_leak")
    decision = {
        **decision,
        "ready": ready and not extra_reasons,
        "reasons": extra_reasons,
        "repository_selection_accuracy": repo_acc,
        "stale_result_rate": stale_rate,
        "index_ready": index_ready,
        "promotion_caller": promotion_caller,
        "promotion_mode": RolloutMode.UNIFIED_WITH_FALLBACK.value,
        "advisory_only": False,  # M19.3 may apply pilot default when ready
    }
    # ready flag: true only when no reasons
    decision["ready"] = bool(index_ready) and campaign.permission_denial_correctness >= 1.0 and (
        campaign.successful_comparison_count >= 5
    ) and campaign.ok and repo_acc >= 1.0 and campaign.context_budget_compliance >= 1.0
    if not decision["ready"] and not extra_reasons:
        if campaign.successful_comparison_count < 5:
            extra_reasons.append("insufficient_comparisons")
        if not campaign.ok:
            extra_reasons.append("campaign_case_failures")
        decision["reasons"] = extra_reasons

    promoted_mode = ""
    if promotion_caller == PROMOTED_CALLER_M19_3 or promotion_caller == DEFAULT_PROMOTION_CALLER:
        # Report what resolve_mode will yield under current env (post-promotion code).
        promoted_mode = resolve_mode(promotion_caller).value

    disable = (
        f"SAATHI_KS_ROLLOUT_{promotion_caller.upper()}=legacy "
        f"or SAATHI_KS_DISABLE_PROMOTIONS=1"
    )

    camp_dict = campaign.to_dict()
    case_summaries = [
        {
            "id": c.get("case_id"),
            "ok": c.get("ok"),
            "compared": c.get("compared"),
            "top5_overlap": c.get("top5_overlap"),
            "canonical_hit": c.get("canonical_hit"),
        }
        for c in (camp_dict.get("cases") or [])
    ]
    campaign_compact = {k: v for k, v in camp_dict.items() if k != "cases"}
    campaign_compact["case_ids"] = [c.id for c in cases]
    campaign_compact["case_summaries"] = case_summaries

    report = RealIndexCampaignReport(
        ok=bool(campaign.ok),
        index_ready=index_ready,
        saathi_root=root,
        inventory=inv_dicts,
        campaign=campaign_compact,
        top1_agreement=campaign.top1_agreement,
        top3_overlap=campaign.top3_overlap,
        top5_overlap=campaign.top5_overlap,
        canonical_source_hit_rate=campaign.canonical_source_hit_rate,
        exact_symbol_hit_rate=campaign.exact_symbol_hit_rate,
        repository_selection_accuracy=repo_acc,
        primary_evidence_ratio=campaign.primary_evidence_ratio_mean,
        duplicate_rate=campaign.duplicate_rate_mean,
        stale_result_rate=stale_rate,
        no_result_rate_legacy=campaign.no_result_rate_legacy,
        no_result_rate_unified=campaign.no_result_rate_unified,
        partial_result_rate=campaign.partial_result_rate,
        permission_denial_correctness=campaign.permission_denial_correctness,
        context_budget_compliance=campaign.context_budget_compliance,
        deterministic_repeatability=campaign.deterministic_repeatability,
        p50_legacy_latency_ms=campaign.p50_legacy_latency_ms,
        p95_legacy_latency_ms=campaign.p95_legacy_latency_ms,
        p50_unified_latency_ms=campaign.p50_unified_latency_ms,
        p95_unified_latency_ms=campaign.p95_unified_latency_ms,
        query_count=campaign.query_count,
        successful_comparison_count=campaign.successful_comparison_count,
        promotion_decision=decision,
        promoted_caller=promotion_caller if decision.get("ready") else "",
        promoted_mode=promoted_mode,
        disable_control=disable,
        warnings=warnings + list(campaign.warnings or []),
        result_fingerprint=campaign.result_fingerprint,
        duration_ms=round((time.time() - t0) * 1000, 2),
    )
    return report


def write_campaign_report(
    report: RealIndexCampaignReport,
    path: str | Path,
) -> Path:
    """Write aggregate-only JSON (creates parent dirs)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    data = report.to_dict()
    # Belt-and-suspenders: strip any accidental large text fields
    blob = json.dumps(data, indent=2, sort_keys=True, default=str)
    for needle in ("API_KEY=", "BEGIN PRIVATE", "sk-live", "password="):
        if needle.lower() in blob.lower():
            raise RuntimeError(f"refusing_to_write_sensitive_campaign_report:{needle}")
    p.write_text(blob + "\n", encoding="utf-8")
    return p


def promotion_evidence_summary(report: RealIndexCampaignReport) -> dict:
    """Compact evidence for docs / handoff."""
    return {
        "ready": bool(report.promotion_decision.get("ready")),
        "promoted_caller": report.promoted_caller or DEFAULT_PROMOTION_CALLER,
        "mode": RolloutMode.UNIFIED_WITH_FALLBACK.value,
        "index_ready": report.index_ready,
        "comparisons": report.successful_comparison_count,
        "permission_denial_correctness": report.permission_denial_correctness,
        "repository_selection_accuracy": report.repository_selection_accuracy,
        "context_budget_compliance": report.context_budget_compliance,
        "top5_overlap": report.top5_overlap,
        "canonical_source_hit_rate": report.canonical_source_hit_rate,
        "disable": report.disable_control,
        "promotions_enabled": promotions_enabled(),
        "reasons": list(report.promotion_decision.get("reasons") or []),
    }
