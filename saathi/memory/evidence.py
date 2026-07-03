"""Evidence Scoring + Knowledge Contradiction Detector (M2 Phase 1b, Stage 4).

Combines deterministic metrics with the extractor's confidence so a single
repeated mistake can't become permanent knowledge, and flags conflicts with
existing knowledge instead of silently overwriting it.

Both are deterministic and LLM-free (AP-12): the contradiction detector is a
flag-for-review heuristic — it never decides truth, it routes likely conflicts
to human review (recall matters more than precision; a false flag just costs a
review, a missed conflict corrupts knowledge).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from saathi.memory.platform import Episode, Knowledge

_DAY = 86400.0
_WEEK = 7 * _DAY

# Weights sum to 1.0 across the six components.
_W_VERIFICATION = 0.20
_W_DIVERSITY = 0.15
_W_TIME = 0.10
_W_CROSS = 0.10
_W_LLM = 0.20
_W_NON_CONTRADICTION = 0.25


@dataclass
class EvidenceScore:
    verification: float        # evidence volume
    source_diversity: float    # distinct (product, department, agent) sources
    time_consistency: float    # spread over time beats a burst
    cross_product: float       # reusability across products
    contradiction_risk: float  # 0 none … 1 many
    llm_confidence: float       # pass-through
    overall: float             # weighted blend, 0..1


def score_evidence(episodes: list[Episode], llm_confidence: float,
                   n_contradictions: int = 0) -> EvidenceScore:
    n = len(episodes)
    verification = min(1.0, n / 10.0)

    sources = {(e.product, e.department, e.agent) for e in episodes}
    source_diversity = min(1.0, len(sources) / 3.0)

    if n >= 2:
        times = [e.created_at for e in episodes]
        time_consistency = min(1.0, (max(times) - min(times)) / _WEEK)
    else:
        time_consistency = 0.0

    products = {e.product for e in episodes}
    cross_product = min(1.0, len(products) / 3.0)

    contradiction_risk = min(1.0, n_contradictions * 0.4)

    overall = (
        _W_VERIFICATION * verification
        + _W_DIVERSITY * source_diversity
        + _W_TIME * time_consistency
        + _W_CROSS * cross_product
        + _W_LLM * llm_confidence
        + _W_NON_CONTRADICTION * (1.0 - contradiction_risk)
    )
    overall = round(max(0.0, min(1.0, overall)), 3)
    return EvidenceScore(
        verification=round(verification, 3),
        source_diversity=round(source_diversity, 3),
        time_consistency=round(time_consistency, 3),
        cross_product=round(cross_product, 3),
        contradiction_risk=round(contradiction_risk, 3),
        llm_confidence=llm_confidence,
        overall=overall,
    )


# ── Knowledge Contradiction Detector ──────────────────────────────────────
_STOPWORDS = {
    "the", "a", "an", "is", "are", "for", "of", "to", "in", "on", "and", "or",
    "with", "it", "this", "that", "be", "should", "use",
}
# Markers that signal opposing polarity / replacement.
_OPPOSING = {
    "not", "never", "avoid", "instead", "outperforms", "worse", "deprecated",
    "stop", "dont", "replace", "over", "better",
}


def _tokens(text: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", text.lower())
            if len(t) >= 3 and t not in _STOPWORDS}


def _entity_tokens(text: str) -> set[str]:
    """Original-case capitalized tokens (e.g. 'Renderer', 'X', 'LTX') minus the
    sentence-initial word, used to detect distinct named entities."""
    words = re.findall(r"[A-Za-z0-9]+", text)
    ents = {w for w in words[1:] if re.match(r"[A-Z][A-Za-z0-9]*$", w)}
    return ents


def _topic_overlap(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    smaller = min(len(a), len(b))
    return len(a & b) / smaller


def find_contradictions(candidate_value: str,
                        existing: list[Knowledge]) -> list[Knowledge]:
    """Flag existing PROMOTED knowledge that likely conflicts with the candidate.
    Deterministic; conflicts go to human review, never auto-resolved."""
    cand_tokens = _tokens(candidate_value)
    cand_markers = cand_tokens & _OPPOSING
    cand_ents = _entity_tokens(candidate_value)
    # Named entities (X, Y, LTX) are dropped by the ≥3-char token filter, but
    # they matter for topic overlap — fold them (lowercased) back in.
    cand_topic = cand_tokens | {e.lower() for e in cand_ents}

    conflicts: list[Knowledge] = []
    for k in existing:
        if k.status != "active" or k.promotion_state.value != "promoted":
            continue
        k_tokens = _tokens(k.value)
        k_topic = k_tokens | {e.lower() for e in _entity_tokens(k.value)}
        if _topic_overlap(cand_topic, k_topic) < 0.4:
            continue   # not about the same thing

        k_markers = k_tokens & _OPPOSING
        # (a) opposing polarity: exactly one side carries a negation/replacement marker
        opposing_polarity = bool(cand_markers) != bool(k_markers)
        # (b) distinct named entities: each mentions an entity the other doesn't
        k_ents = _entity_tokens(k.value)
        distinct_entities = bool(cand_ents - k_ents) and bool(k_ents - cand_ents)

        if opposing_polarity or distinct_entities:
            conflicts.append(k)
    return conflicts
