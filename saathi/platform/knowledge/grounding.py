"""Grounding context assembly, citations, conflicts, and answer policy."""
from __future__ import annotations

import re
import time
from typing import Any

from .models import (
    MAX_CONTEXT_CHARS,
    ClaimKind,
    Citation,
    FreshnessStatus,
    GroundingContext,
    RetrievedChunk,
    SourceAuthority,
    authority_rank,
)
from .retriever import KnowledgeRetriever
from .security import redact_absolute_paths, scan_injection_flags, wrap_grounded_block

_PRODUCTION_CLAIM = re.compile(
    r"(?i)\b(production[-\s]?authorized|authorized\s+for\s+production|"
    r"production\s+use\s+is\s+authorized|live\s+trading\s+enabled)\b"
)


class GroundingContextBuilder:
    def __init__(self, retriever: KnowledgeRetriever):
        self.retriever = retriever

    def build(
        self,
        query: str,
        *,
        tenant_id: str = "platform",
        workspace_id: str = "",
        domain: str = "general",
        top_k: int = 6,
        allow_restricted: bool = False,
        budget_chars: int = MAX_CONTEXT_CHARS,
    ) -> GroundingContext:
        t0 = time.time()
        q = (query or "").strip()
        hits = self.retriever.search(
            q,
            top_k=top_k,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            expand_adjacent=True,
            allow_restricted=allow_restricted,
        )
        # Domain soft filter preference already handled by scoring; keep hits.
        conflicts = self._detect_conflicts(hits, q)
        stale_warnings = self._stale_warnings(hits)
        injection_flags: list[str] = []
        for h in hits:
            injection_flags.extend(scan_injection_flags(h.chunk.text))
        injection_flags = sorted(set(injection_flags))

        if not hits:
            ctx = GroundingContext(
                query=q,
                chunks=[],
                citations=[],
                prompt_block=wrap_grounded_block(
                    "No authoritative indexed evidence matched this question."
                ),
                claim_kind=ClaimKind.UNAVAILABLE_EVIDENCE.value,
                conflicts=[],
                stale_warnings=[],
                no_evidence=True,
                truncated=False,
                retrieval_ms=(time.time() - t0) * 1000,
                context_chars=0,
                injection_flags=[],
                grounded=False,
            )
            return ctx

        budget = max(800, min(int(budget_chars or MAX_CONTEXT_CHARS), MAX_CONTEXT_CHARS))
        lines: list[str] = []
        citations: list[Citation] = []
        used = 0
        truncated = False
        included: list[RetrievedChunk] = []

        for h in hits:
            text = redact_absolute_paths(h.chunk.text or "")
            flags = scan_injection_flags(text)
            block = (
                f"[source={h.chunk.source_id} authority={h.chunk.authority} "
                f"freshness={h.chunk.freshness} path={h.chunk.relative_path} "
                f"milestone={h.chunk.milestone or '-'}]\n{text}"
            )
            if used + len(block) + 2 > budget:
                truncated = True
                break
            lines.append(block)
            used += len(block) + 2
            included.append(h)
            citations.append(
                Citation(
                    source_id=h.chunk.source_id,
                    document_id=h.chunk.document_id,
                    chunk_id=h.chunk.chunk_id,
                    title=h.chunk.title,
                    source_type=h.chunk.source_type,
                    authority=h.chunk.authority,
                    freshness=h.chunk.freshness,
                    relative_path=h.chunk.relative_path,
                    milestone=h.chunk.milestone,
                    commit_sha=h.chunk.commit_sha,
                    evidence_id=h.chunk.document_id if "evidence" in h.chunk.source_type else "",
                    location=f"chars {h.chunk.start_char}-{h.chunk.end_char}",
                    claim_kind=(
                        ClaimKind.UNRESOLVED_CONFLICT.value
                        if conflicts
                        else ClaimKind.GROUNDED_FACT.value
                    ),
                )
            )

        body = "\n\n".join(lines)
        if conflicts:
            body += "\n\n[CONFLICTS]\n" + "\n".join(
                f"- {c.get('summary')}" for c in conflicts
            )
        if stale_warnings:
            body += "\n\n[STALE]\n" + "\n".join(f"- {s}" for s in stale_warnings)

        claim = ClaimKind.GROUNDED_FACT.value
        if conflicts:
            claim = ClaimKind.UNRESOLVED_CONFLICT.value
        elif not included:
            claim = ClaimKind.UNAVAILABLE_EVIDENCE.value

        prompt_block = wrap_grounded_block(
            body,
            sources=[c.source_id for c in citations],
            injection_flags=injection_flags,
        )
        return GroundingContext(
            query=q,
            chunks=included,
            citations=citations,
            prompt_block=prompt_block,
            claim_kind=claim,
            conflicts=conflicts,
            stale_warnings=stale_warnings,
            no_evidence=False,
            truncated=truncated,
            retrieval_ms=(time.time() - t0) * 1000,
            context_chars=len(prompt_block),
            injection_flags=injection_flags,
            grounded=True,
        )

    def _detect_conflicts(
        self, hits: list[RetrievedChunk], query: str
    ) -> list[dict[str, Any]]:
        if len(hits) < 2:
            return []
        conflicts: list[dict[str, Any]] = []
        # Current vs historical milestone conflicts
        runtime = [
            h
            for h in hits
            if h.chunk.authority == SourceAuthority.AUTHORITATIVE_RUNTIME.value
        ]
        evidence = [
            h
            for h in hits
            if h.chunk.authority
            in {
                SourceAuthority.AUTHORITATIVE_EVIDENCE.value,
                SourceAuthority.AUTHORITATIVE_DOCUMENTATION.value,
            }
        ]
        q = query.lower()
        if runtime and evidence and any(
            w in q for w in ("current", "milestone", "now", "latest", "active")
        ):
            rt_ms = {h.chunk.milestone for h in runtime if h.chunk.milestone}
            ev_ms = {h.chunk.milestone for h in evidence if h.chunk.milestone}
            if rt_ms and ev_ms and rt_ms != ev_ms:
                conflicts.append(
                    {
                        "type": "milestone_state",
                        "summary": (
                            f"Runtime milestones {sorted(rt_ms)} differ from "
                            f"historical/evidence milestones {sorted(ev_ms)}. "
                            "Prefer AUTHORITATIVE_RUNTIME for current state."
                        ),
                        "preferred_authority": SourceAuthority.AUTHORITATIVE_RUNTIME.value,
                    }
                )
        # Production authorization conflicts — evidence saying not authorized vs model claims
        texts = [(h, (h.chunk.text or "").lower()) for h in hits]
        denies = [
            h
            for h, t in texts
            if "not authorized" in t or "production not authorized" in t or "production: not" in t
        ]
        allows = [h for h, t in texts if _PRODUCTION_CLAIM.search(t or "")]
        if denies and allows:
            conflicts.append(
                {
                    "type": "production_authorization",
                    "summary": (
                        "Sources disagree on production authorization. "
                        "Prefer certification/runtime denials over weaker claims."
                    ),
                    "preferred_authority": SourceAuthority.AUTHORITATIVE_EVIDENCE.value,
                }
            )
        # Rank divergence: high-authority vs low-authority contradictory "certified"
        high = [h for h in hits if authority_rank(h.chunk.authority) >= 80]
        low = [h for h in hits if authority_rank(h.chunk.authority) <= 40]
        if high and low:
            for lh in low:
                if "production" in (lh.chunk.text or "").lower() and "authorized" in (
                    lh.chunk.text or ""
                ).lower():
                    conflicts.append(
                        {
                            "type": "weak_vs_strong",
                            "summary": (
                                f"Low-authority source {lh.chunk.source_id} should not "
                                "override high-authority runtime/evidence."
                            ),
                            "preferred_authority": high[0].chunk.authority,
                        }
                    )
                    break
        return conflicts[:5]

    def _stale_warnings(self, hits: list[RetrievedChunk]) -> list[str]:
        out: list[str] = []
        for h in hits:
            if h.chunk.freshness in {
                FreshnessStatus.STALE.value,
                FreshnessStatus.EXPIRED.value,
            }:
                out.append(
                    f"{h.chunk.title} ({h.chunk.relative_path}) is marked "
                    f"{h.chunk.freshness}; treat carefully for current-state questions."
                )
        return out[:8]


class CitationAssembler:
    def assemble(self, grounding: GroundingContext) -> list[dict[str, Any]]:
        return [c.to_public() for c in grounding.citations]


class GroundedAnswerPolicy:
    """Yeti-facing grounded answer policy helpers (prompt + post-checks)."""

    GROUNDED_SYSTEM_ADDENDUM = (
        "Grounding policy: Answer SaathiOS factual questions from GROUNDED_EVIDENCE when present. "
        "Label clearly: grounded fact, inference, recommendation, unresolved conflict, or unavailable evidence. "
        "Prefer AUTHORITATIVE_RUNTIME and AUTHORITATIVE_EVIDENCE over documentation and summaries. "
        "Distinguish current vs historical state, certified vs implemented, local/staging vs production, "
        "adapter-present vs provider-operational. "
        "Never claim production authorization, deployment, or unrestricted tools without evidence. "
        "If evidence is missing, say you do not have indexed evidence rather than inventing facts. "
        "Provide brief source references by title/path when stating grounded facts."
    )

    def system_addendum(self) -> str:
        return self.GROUNDED_SYSTEM_ADDENDUM

    def no_evidence_reply(self, query: str) -> str:
        return (
            "I do not have indexed authoritative evidence that answers that confidently. "
            "I can help rephrase the question or point you to mission status, capability docs, "
            "or certification records if you specify the topic."
        )

    def classify_response_kind(self, grounding: GroundingContext) -> str:
        if grounding.no_evidence:
            return ClaimKind.UNAVAILABLE_EVIDENCE.value
        if grounding.conflicts:
            return ClaimKind.UNRESOLVED_CONFLICT.value
        if grounding.grounded:
            return ClaimKind.GROUNDED_FACT.value
        return ClaimKind.INFERENCE.value
