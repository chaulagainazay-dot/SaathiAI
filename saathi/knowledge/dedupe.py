"""Deterministic deduplication by content fingerprint and path."""
from __future__ import annotations

from saathi.knowledge.types import KnowledgeResult


def dedupe_results(results: list[KnowledgeResult]) -> tuple[list[KnowledgeResult], dict]:
    """Keep strongest primary per fingerprint; attach duplicate refs.

    Does not merge across repositories for MULTI_REPO (same fingerprint still
    collapses, but provenance lists both repos).
    """
    best: dict[str, KnowledgeResult] = {}
    order: list[str] = []
    dup_count = 0

    for r in results:
        key = r.content_fingerprint or f"{r.repository_id}:{r.path}:{r.start_line}"
        if key not in best:
            best[key] = r
            order.append(key)
            continue
        cur = best[key]
        dup_count += 1
        # Prefer higher final_score, then non-generated, then primary code
        if r.final_score > cur.final_score or (
            r.final_score == cur.final_score and not r.is_generated and cur.is_generated
        ):
            r.duplicate_refs = list(dict.fromkeys(
                (cur.duplicate_refs or []) + [cur.result_id]
            ))
            best[key] = r
        else:
            cur.duplicate_refs = list(dict.fromkeys(
                (cur.duplicate_refs or []) + [r.result_id]
            ))
            best[key] = cur

    out = [best[k] for k in order if k in best]
    # Re-sort by score after merge
    out.sort(key=lambda x: (-x.final_score, x.path, x.result_id))
    meta = {
        "input_count": len(results),
        "output_count": len(out),
        "duplicates_collapsed": dup_count,
    }
    return out, meta
