"""Lightweight documentation / decision-doc lexical scan (read-only FS)."""
from __future__ import annotations

import re
from pathlib import Path

from saathi.knowledge.permissions import filter_sensitive_results, path_is_sensitive
from saathi.knowledge.registry import KnowledgeSource
from saathi.knowledge.types import (
    EvidenceClass,
    KnowledgeQuery,
    KnowledgeResult,
    content_fingerprint,
)
from saathi.codebase_memory.store import re_tokenize

_SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "dist", "build"}


class DocumentationAdapter:
    name = "documentation"

    def supports(self, query: KnowledgeQuery, source: KnowledgeSource) -> bool:
        return source.adapter in (self.name, "decision_docs") and source.source_type in (
            "documentation", "decision_docs",
        )

    def describe_capabilities(self) -> dict:
        return {"name": self.name, "modes": ["lexical"], "mutates": False}

    def health(self, source: KnowledgeSource) -> dict:
        p = Path(source.location)
        return {"ok": p.is_dir(), "status": "ok" if p.is_dir() else "missing"}

    def retrieve(
        self,
        query: KnowledgeQuery,
        source: KnowledgeSource,
        *,
        limit: int = 8,
    ) -> list[KnowledgeResult]:
        root = Path(source.location)
        if not root.is_dir():
            return []
        tokens = re_tokenize(query.query)
        if not tokens:
            return []
        hits: list[tuple[float, Path, str, int]] = []
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if any(p in _SKIP_DIRS for p in path.parts):
                continue
            if path.suffix.lower() not in (".md", ".txt", ".rst"):
                continue
            rel = str(path.relative_to(root)).replace("\\", "/")
            full_rel = rel
            if path_is_sensitive(full_rel):
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if len(text) > 400_000:
                continue
            low = text.lower()
            score = 0.0
            for t in tokens:
                if t in low:
                    score += 2.0 + low.count(t) * 0.1
                if t in rel.lower():
                    score += 4.0
            if score <= 0:
                continue
            # excerpt around first token
            idx = low.find(tokens[0])
            start = max(0, idx - 80)
            excerpt = text[start:start + 400]
            hits.append((score, path, excerpt, start))
        hits.sort(key=lambda x: -x[0])
        out: list[KnowledgeResult] = []
        is_decision = source.source_type == "decision_docs" or source.adapter == "decision_docs"
        for score, path, excerpt, _ in hits[:limit]:
            try:
                rel = str(path.relative_to(root)).replace("\\", "/")
            except ValueError:
                rel = path.name
            ok, _ = filter_sensitive_results(rel, excerpt)
            if not ok:
                continue
            # Prefer milestone/roadmap under decision_docs
            if is_decision and not any(
                k in rel.lower() for k in (
                    "m17", "m18", "m19", "roadmap", "decision", "ses-", "validation",
                    "audit", "debt", "capability",
                )
            ):
                score *= 0.5
            ev = EvidenceClass.OPERATIONAL_RECORD if is_decision else EvidenceClass.CANONICAL_DOCS
            if any(k in rel.lower() for k in ("brain.md", "ses-", "architecture")):
                ev = EvidenceClass.CANONICAL_DOCS
            out.append(KnowledgeResult(
                result_id=f"{source.source_id}:{content_fingerprint(rel + excerpt)}",
                source_id=source.source_id,
                source_type=source.source_type,
                repository_id=source.repository_id,
                object_id=rel,
                path=rel,
                title=path.name,
                excerpt=excerpt[:500],
                normalized_content=excerpt[:500],
                native_score=score,
                normalized_score=min(1.0, score / 20.0),
                trust_score=0.95,
                freshness_score=0.8,
                final_score=0.0,
                evidence_class=ev,
                is_generated=False,
                provenance={"adapter": self.name, "root": str(root)},
                content_fingerprint=content_fingerprint(excerpt),
            ))
        return out
