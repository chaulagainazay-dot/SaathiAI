"""Deterministic ranking and score fusion (weighted fusion v1)."""
from __future__ import annotations

from saathi.knowledge.types import EvidenceClass, KnowledgeResult, RetrievalProfile

# Evidence class base weights
_EVIDENCE_W = {
    EvidenceClass.PRIMARY_CODE: 1.0,
    EvidenceClass.PRIMARY_TESTS: 0.95,
    EvidenceClass.CANONICAL_DOCS: 0.9,
    EvidenceClass.OPERATIONAL_RECORD: 0.85,
    EvidenceClass.PROVIDER_METADATA: 0.7,
    EvidenceClass.GENERATED_SUMMARY: 0.35,
    EvidenceClass.INFERRED: 0.3,
    EvidenceClass.UNVERIFIED_EXTERNAL: 0.2,
}


def fuse_and_rank(
    results: list[KnowledgeResult],
    *,
    profile: RetrievalProfile,
    query: str,
) -> list[KnowledgeResult]:
    q = (query or "").lower()
    tokens = [t for t in q.replace("/", " ").split() if len(t) > 1]

    for r in results:
        signals: list[str] = []
        # Normalize native score to 0..1 roughly
        ns = r.normalized_score if r.normalized_score <= 1.5 else min(1.0, r.normalized_score / 40.0)
        r.normalized_score = max(0.0, min(1.0, ns))

        score = 0.0
        # lexical / native
        score += 0.40 * r.normalized_score
        signals.append(f"native:{r.normalized_score:.2f}")

        # trust & freshness
        score += 0.15 * r.trust_score
        score += 0.10 * r.freshness_score
        signals.append(f"trust:{r.trust_score:.2f}")

        # evidence class
        ew = _EVIDENCE_W.get(r.evidence_class, 0.5)
        if profile == RetrievalProfile.AUDIT_EVIDENCE and r.is_generated:
            ew *= 0.3
            signals.append("audit_penalize_generated")
        score += 0.20 * ew
        signals.append(f"evidence:{r.evidence_class.value}:{ew:.2f}")

        # exact path / symbol boosts
        path_l = (r.path or "").lower()
        title_l = (r.title or "").lower()
        for t in tokens:
            if t == title_l or t == path_l.rsplit(".", 1)[0].rsplit("/", 1)[-1]:
                score += 0.15
                signals.append(f"exact_token:{t}")
            elif t in path_l or t in title_l:
                score += 0.05

        # generated penalty
        if r.is_generated:
            score *= 0.7
            signals.append("generated_penalty")

        # profile tweaks
        if profile == RetrievalProfile.FAST_LOOKUP and r.evidence_class == EvidenceClass.PRIMARY_CODE:
            score += 0.05
        if profile == RetrievalProfile.CODE_EXPLAIN and r.evidence_class == EvidenceClass.CANONICAL_DOCS:
            score += 0.03
        if profile == RetrievalProfile.MISSION_CONTEXT and r.evidence_class == EvidenceClass.OPERATIONAL_RECORD:
            score += 0.04

        r.final_score = round(score, 6)
        r.score_explanation = signals[:12]

    # Stable sort: score desc, then path, then result_id
    results.sort(key=lambda r: (-r.final_score, r.path, r.result_id))
    return results
