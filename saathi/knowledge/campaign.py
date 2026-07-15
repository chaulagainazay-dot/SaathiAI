"""M19.2 — Deterministic shadow evaluation campaign.

Extends M19.0/M19.1 evaluation infrastructure. Does **not** create a parallel
framework. Legacy remains the baseline; unified runs for comparison only when
using shadow mode. No sensitive retrieved content is stored in aggregates.
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

from saathi.knowledge.eval_set import CAMPAIGN_CASES, CampaignCase
from saathi.knowledge.shadow import ShadowComparison, compare_retrieval
from saathi.knowledge.types import RetrievalProfile


# Sampling policy for expensive dual-path runs.
# full: every case once with legacy+unified
# half: every other case dual; others legacy-only (documented)
DEFAULT_SAMPLING = "full"
MIN_SAMPLES_FOR_P95 = 20


@dataclass
class CampaignCaseResult:
    case_id: str
    category: str
    ok: bool
    compared: bool
    top1_agreement: float = 0.0
    top3_overlap: float = 0.0
    top5_overlap: float = 0.0
    path_jaccard: float = 0.0
    legacy_latency_ms: float = 0.0
    unified_latency_ms: float = 0.0
    shadow_overhead_ms: float = 0.0
    legacy_hit_count: int = 0
    unified_hit_count: int = 0
    primary_evidence_ratio: float = 0.0
    generated_summary_ratio: float = 0.0
    duplicate_rate: float = 0.0
    canonical_hit: bool = False
    permission_denial_correct: bool | None = None
    context_budget_ok: bool | None = None
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CampaignReport:
    """Aggregate metrics only — no result bodies."""
    ok: bool
    sampling_policy: str
    query_count: int
    successful_comparison_count: int
    top1_agreement: float
    top3_overlap: float
    top5_overlap: float
    path_jaccard_mean: float
    canonical_source_hit_rate: float
    exact_symbol_hit_rate: float
    primary_evidence_ratio_mean: float
    generated_summary_ratio_mean: float
    duplicate_rate_mean: float
    no_result_rate_legacy: float
    no_result_rate_unified: float
    partial_result_rate: float
    permission_denial_correctness: float
    context_budget_compliance: float
    deterministic_repeatability: float | None
    p50_legacy_latency_ms: float | None
    p95_legacy_latency_ms: float | None
    p50_unified_latency_ms: float | None
    p95_unified_latency_ms: float | None
    p50_shadow_overhead_ms: float | None
    insufficient_sample_for_p95: bool
    cases: list[dict] = field(default_factory=list)
    profiles: dict[str, dict] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    result_fingerprint: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return round(values[0], 2)
    ordered = sorted(values)
    k = (len(ordered) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(ordered) - 1)
    if f == c:
        return round(ordered[f], 2)
    return round(ordered[f] + (ordered[c] - ordered[f]) * (k - f), 2)


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 4)


def _paths_from_legacy_dict(d: dict | None) -> list[str]:
    if not d:
        return []
    out = []
    for h in d.get("hits") or []:
        if isinstance(h, dict):
            p = h.get("path") or ""
        else:
            p = getattr(h, "path", "") or ""
        if p:
            out.append(str(p))
    return out


def run_shadow_campaign(
    *,
    legacy_fn: Callable[[CampaignCase], dict],
    unified_fn: Callable[[CampaignCase], Any],
    cases: list[CampaignCase] | None = None,
    sampling_policy: str = DEFAULT_SAMPLING,
    repeat_for_determinism: int = 0,
    sample_seed: int = 19,
) -> CampaignReport:
    """Run dual-path shadow campaign. Never alters legacy authoritative results.

    legacy_fn / unified_fn must be pure retrieval — no tool execution, no trades.
    """
    cases = list(cases or CAMPAIGN_CASES)
    sampling_policy = (sampling_policy or DEFAULT_SAMPLING).strip().lower()
    if sampling_policy not in ("full", "half"):
        sampling_policy = DEFAULT_SAMPLING

    case_results: list[CampaignCaseResult] = []
    leg_lat: list[float] = []
    uni_lat: list[float] = []
    overhead: list[float] = []
    top1s: list[float] = []
    top3s: list[float] = []
    top5s: list[float] = []
    jaccards: list[float] = []
    primary_ratios: list[float] = []
    gen_ratios: list[float] = []
    dup_rates: list[float] = []
    canonical_hits = 0
    symbol_hits = 0
    symbol_total = 0
    compared = 0
    leg_empty = 0
    uni_empty = 0
    partial = 0
    perm_ok = 0
    perm_total = 0
    budget_ok = 0
    budget_total = 0
    profile_acc: dict[str, list[dict]] = {}
    warnings: list[str] = []
    fingerprints: list[str] = []

    for idx, case in enumerate(cases):
        dual = True
        if sampling_policy == "half" and (idx + sample_seed) % 2 == 1:
            dual = False

        t0 = time.time()
        try:
            leg = legacy_fn(case) or {}
        except Exception as e:
            leg = {"ok": False, "hits": [], "error": type(e).__name__}
        lms = (time.time() - t0) * 1000
        leg_lat.append(lms)
        leg_paths = _paths_from_legacy_dict(leg)
        if not leg_paths:
            leg_empty += 1

        uni = None
        ums = 0.0
        shadow: ShadowComparison | None = None
        if dual:
            t1 = time.time()
            try:
                uni = unified_fn(case)
            except Exception as e:
                uni = None
                warnings.append(f"{case.id}:unified_exc:{type(e).__name__}")
            ums = (time.time() - t1) * 1000
            uni_lat.append(ums)
            shadow = compare_retrieval(
                legacy=leg,
                unified=uni,
                top_k=case.top_k,
                legacy_latency_ms=lms,
                unified_latency_ms=ums,
            )
            compared += 1
            top1s.append(shadow.top1_agreement)
            top3s.append(shadow.top3_overlap)
            top5s.append(shadow.top5_overlap)
            jaccards.append(shadow.path_jaccard)
            primary_ratios.append(shadow.primary_evidence_ratio_unified)
            gen_ratios.append(shadow.generated_summary_ratio_unified)
            dup_rates.append(shadow.duplicate_rate_unified)
            overhead.append(shadow.shadow_overhead_ms)
            if shadow.canonical_hit_unified:
                canonical_hits += 1
            if shadow.unified_count == 0:
                uni_empty += 1
            if shadow.truncated_unified:
                partial += 1
            fp_src = "|".join(shadow.unified_paths[:5] + shadow.legacy_paths[:5])
            fingerprints.append(hashlib.sha256(fp_src.encode()).hexdigest()[:12])
        else:
            warnings.append(f"{case.id}:sampled_legacy_only")

        # Category-specific checks (aggregate only)
        perm_correct: bool | None = None
        if case.expect_permission_denial or case.category == "permission_denial":
            perm_total += 1
            denied = False
            if uni is not None:
                denied = bool(getattr(uni, "denied", False)) or (
                    isinstance(uni, dict) and bool(uni.get("denied"))
                )
            # Correct when unified denies OR returns no secret paths
            bad_paths = any(
                s in p.lower()
                for p in (shadow.unified_paths if shadow else [])
                for s in (".env", "id_rsa", "credentials")
            )
            perm_correct = denied or not bad_paths
            if case.forbidden_path_substrings:
                forb = any(
                    s.lower() in p.lower()
                    for p in (shadow.unified_paths if shadow else [])
                    for s in case.forbidden_path_substrings
                )
                perm_correct = perm_correct and not forb
            if perm_correct:
                perm_ok += 1

        budget_correct: bool | None = None
        if case.check_context_budget and uni is not None:
            budget_total += 1
            ctx = getattr(uni, "context", None) if not isinstance(uni, dict) else uni.get("context")
            if isinstance(ctx, dict):
                budget = int(ctx.get("budget") or case.max_context_chars or 0)
                chars = int(ctx.get("char_count") or 0)
                budget_correct = budget <= 0 or chars <= budget + 80
            else:
                budget_correct = True
            if budget_correct:
                budget_ok += 1

        if case.category == "exact_symbol":
            symbol_total += 1
            paths = " ".join(shadow.unified_paths if shadow else leg_paths).lower()
            if any(s.lower() in paths for s in case.expected_path_substrings):
                symbol_hits += 1

        cr = CampaignCaseResult(
            case_id=case.id,
            category=case.category,
            ok=True,
            compared=dual and shadow is not None,
            top1_agreement=shadow.top1_agreement if shadow else 0.0,
            top3_overlap=shadow.top3_overlap if shadow else 0.0,
            top5_overlap=shadow.top5_overlap if shadow else 0.0,
            path_jaccard=shadow.path_jaccard if shadow else 0.0,
            legacy_latency_ms=round(lms, 2),
            unified_latency_ms=round(ums, 2),
            shadow_overhead_ms=round(lms + ums, 2) if dual else round(lms, 2),
            legacy_hit_count=len(leg_paths),
            unified_hit_count=shadow.unified_count if shadow else 0,
            primary_evidence_ratio=shadow.primary_evidence_ratio_unified if shadow else 0.0,
            generated_summary_ratio=shadow.generated_summary_ratio_unified if shadow else 0.0,
            duplicate_rate=shadow.duplicate_rate_unified if shadow else 0.0,
            canonical_hit=bool(shadow and shadow.canonical_hit_unified),
            permission_denial_correct=perm_correct,
            context_budget_ok=budget_correct,
            notes=list(shadow.notes) if shadow else [],
        )
        # Expectation soft checks (do not fail campaign; record)
        if case.expected_path_substrings and dual and shadow:
            paths = " ".join(shadow.unified_paths + shadow.legacy_paths).lower()
            if not any(s.lower() in paths for s in case.expected_path_substrings):
                cr.notes.append("expected_path_miss")
        if case.forbidden_path_substrings and dual and shadow:
            paths = " ".join(shadow.unified_paths).lower()
            if any(s.lower() in paths for s in case.forbidden_path_substrings):
                cr.ok = False
                cr.notes.append("forbidden_path_hit")
        case_results.append(cr)

        prof = case.profile.value if isinstance(case.profile, RetrievalProfile) else str(case.profile)
        profile_acc.setdefault(prof, []).append(cr.to_dict())

    # Deterministic repeatability (optional second pass of first N dual cases)
    det: float | None = None
    if repeat_for_determinism > 0 and cases:
        n = min(repeat_for_determinism, len(cases))
        matches = 0
        checks = 0
        for case in cases[:n]:
            try:
                a = _paths_from_legacy_dict(legacy_fn(case))
                b = _paths_from_legacy_dict(legacy_fn(case))
                checks += 1
                if a == b:
                    matches += 1
            except Exception:
                checks += 1
        det = round(matches / checks, 3) if checks else None

    n = len(cases)
    insuff = len(uni_lat) < MIN_SAMPLES_FOR_P95
    if insuff:
        warnings.append(
            f"insufficient_sample_for_p95:n={len(uni_lat)}<min={MIN_SAMPLES_FOR_P95}"
        )

    profiles_out: dict[str, dict] = {}
    for prof, rows in profile_acc.items():
        profiles_out[prof] = {
            "case_count": len(rows),
            "mean_top5_overlap": _mean([r["top5_overlap"] for r in rows if r["compared"]]),
            "mean_legacy_latency_ms": _mean([r["legacy_latency_ms"] for r in rows]),
            "mean_unified_latency_ms": _mean(
                [r["unified_latency_ms"] for r in rows if r["compared"]]
            ),
        }

    report = CampaignReport(
        ok=all(c.ok for c in case_results),
        sampling_policy=sampling_policy,
        query_count=n,
        successful_comparison_count=compared,
        top1_agreement=_mean(top1s),
        top3_overlap=_mean(top3s),
        top5_overlap=_mean(top5s),
        path_jaccard_mean=_mean(jaccards),
        canonical_source_hit_rate=round(canonical_hits / compared, 4) if compared else 0.0,
        exact_symbol_hit_rate=round(symbol_hits / symbol_total, 4) if symbol_total else 0.0,
        primary_evidence_ratio_mean=_mean(primary_ratios),
        generated_summary_ratio_mean=_mean(gen_ratios),
        duplicate_rate_mean=_mean(dup_rates),
        no_result_rate_legacy=round(leg_empty / n, 4) if n else 0.0,
        no_result_rate_unified=round(uni_empty / compared, 4) if compared else 0.0,
        partial_result_rate=round(partial / compared, 4) if compared else 0.0,
        permission_denial_correctness=round(perm_ok / perm_total, 4) if perm_total else 1.0,
        context_budget_compliance=round(budget_ok / budget_total, 4) if budget_total else 1.0,
        deterministic_repeatability=det,
        p50_legacy_latency_ms=_percentile(leg_lat, 50),
        p95_legacy_latency_ms=_percentile(leg_lat, 95) if not insuff else _percentile(leg_lat, 95),
        p50_unified_latency_ms=_percentile(uni_lat, 50),
        p95_unified_latency_ms=_percentile(uni_lat, 95),
        p50_shadow_overhead_ms=_percentile(overhead, 50),
        insufficient_sample_for_p95=insuff,
        cases=[c.to_dict() for c in case_results],
        profiles=profiles_out,
        warnings=warnings,
        result_fingerprint=hashlib.sha256(
            "|".join(fingerprints).encode()
        ).hexdigest()[:16] if fingerprints else "",
    )
    return report


def decision_ready_for_unified_fallback(report: CampaignReport, *, min_comparisons: int = 5) -> dict:
    """Gate before promoting a caller from shadow → unified_with_fallback.

    Returns structured decision evidence (not automatic promotion).
    """
    reasons: list[str] = []
    ok = True
    if report.successful_comparison_count < min_comparisons:
        ok = False
        reasons.append("insufficient_comparisons")
    if report.permission_denial_correctness < 1.0:
        ok = False
        reasons.append("permission_denial_incorrect")
    if report.context_budget_compliance < 1.0:
        ok = False
        reasons.append("context_budget_violation")
    if not report.ok:
        ok = False
        reasons.append("campaign_case_failures")
    # Prefer evidence quality over exact ranking match
    if report.successful_comparison_count >= min_comparisons and report.canonical_source_hit_rate < 0.1:
        reasons.append("low_canonical_hit_rate_advisory")
    return {
        "ready": ok and not reasons,
        "advisory_only": True,
        "reasons": reasons,
        "comparisons": report.successful_comparison_count,
        "permission_denial_correctness": report.permission_denial_correctness,
        "context_budget_compliance": report.context_budget_compliance,
        "top5_overlap": report.top5_overlap,
        "canonical_source_hit_rate": report.canonical_source_hit_rate,
    }
