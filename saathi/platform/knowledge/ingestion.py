"""Safe, incremental, idempotent knowledge ingestion."""
from __future__ import annotations

import json
import re
import subprocess
import time
from pathlib import Path
from typing import Any

from .index import KnowledgeIndex
from .models import (
    MAX_CHUNKS_PER_DOCUMENT,
    MAX_CHUNK_CHARS,
    MAX_FILE_BYTES,
    MAX_TOTAL_CHUNKS,
    CHUNK_OVERLAP_CHARS,
    FreshnessStatus,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeSourceSpec,
    Sensitivity,
    SourceAuthority,
    content_hash,
    stable_id,
)
from .security import (
    decode_text_safely,
    path_looks_secret,
    resolve_repo_root,
    safe_join,
    text_contains_secrets,
)
from .sources import discover_sources


_MILESTONE_RE = re.compile(r"\bM\d{2,3}\b")
_SHA_RE = re.compile(r"\b[0-9a-f]{7,40}\b", re.I)


class KnowledgeIngestionService:
    def __init__(
        self,
        index: KnowledgeIndex,
        *,
        repo_root: str | Path | None = None,
    ):
        self.index = index
        self.repo_root = resolve_repo_root(repo_root)
        self.last_stats: dict[str, Any] = {}

    def current_repo_sha(self) -> str:
        try:
            out = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=str(self.repo_root),
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
            if out.returncode == 0:
                return (out.stdout or "").strip()
        except (OSError, subprocess.SubprocessError):
            pass
        return ""

    def ingest_all(self, *, force: bool = False) -> dict[str, Any]:
        t0 = time.time()
        specs = discover_sources(self.repo_root)
        sha = self.current_repo_sha()
        stats = {
            "discovered": len(specs),
            "indexed": 0,
            "skipped_unchanged": 0,
            "failed": 0,
            "tombstoned": 0,
            "chunks": 0,
            "errors": [],
            "repository_sha": sha,
            "force": force,
        }
        active_source_ids: set[str] = set()
        for spec in specs:
            active_source_ids.add(spec.source_id)
            try:
                result = self.ingest_source(spec, force=force, commit_sha=sha)
                if result.get("status") == "indexed":
                    stats["indexed"] += 1
                    stats["chunks"] += int(result.get("chunk_count") or 0)
                elif result.get("status") == "skipped_unchanged":
                    stats["skipped_unchanged"] += 1
                elif result.get("status") == "failed":
                    stats["failed"] += 1
                    stats["errors"].append(
                        {"source_id": spec.source_id, "error": result.get("error")}
                    )
            except Exception as exc:  # noqa: BLE001 — bounded per-source failure
                stats["failed"] += 1
                stats["errors"].append(
                    {"source_id": spec.source_id, "error": type(exc).__name__}
                )

        # Tombstone sources no longer discoverable that were previously indexed
        for doc in self.index.list_documents():
            if doc.source_id not in active_source_ids and not doc.source_id.startswith(
                "platform:"
            ):
                self.index.tombstone_source(doc.source_id)
                stats["tombstoned"] += 1

        elapsed = (time.time() - t0) * 1000
        stats["latency_ms"] = round(elapsed, 2)
        stats["total_chunks"] = self.index.count_chunks()
        stats["total_documents"] = self.index.count_documents()
        self.index.set_meta("last_ingestion_at", str(time.time()))
        self.index.set_meta("last_ingestion_sha", sha)
        self.index.set_meta("last_ingestion_stats", json.dumps(stats))
        self.last_stats = stats
        return stats

    def ingest_source(
        self,
        spec: KnowledgeSourceSpec,
        *,
        force: bool = False,
        commit_sha: str = "",
    ) -> dict[str, Any]:
        if path_looks_secret(spec.relative_path):
            return {"status": "failed", "error": "secret_path_denied"}
        if self.index.count_chunks() >= MAX_TOTAL_CHUNKS and not force:
            return {"status": "failed", "error": "chunk_budget_exhausted"}

        path = safe_join(self.repo_root, spec.relative_path)
        if path is None or not path.is_file():
            # missing optional/required → tombstone prior if any
            existing = self.index.get_document_by_source(spec.source_id)
            if existing:
                self.index.tombstone_source(spec.source_id)
                return {"status": "failed", "error": "source_missing_tombstoned"}
            return {"status": "failed", "error": "source_missing"}

        try:
            raw = path.read_bytes()
        except OSError as exc:
            return {"status": "failed", "error": f"read_error:{type(exc).__name__}"}

        max_bytes = min(spec.max_bytes, MAX_FILE_BYTES)
        if len(raw) > max_bytes:
            return {"status": "failed", "error": "file_too_large"}

        text = decode_text_safely(raw, max_bytes=max_bytes)
        if text is None:
            return {"status": "failed", "error": "decode_failed"}
        if text_contains_secrets(text):
            return {"status": "failed", "error": "secret_content_denied"}
        if spec.sensitivity == Sensitivity.SECRET:
            return {"status": "failed", "error": "secret_sensitivity"}

        c_hash = content_hash(text)
        document_id = stable_id(spec.source_id, prefix="kdoc_")
        existing = self.index.get_document(document_id)
        if existing and existing.content_hash == c_hash and not force and not existing.tombstoned:
            return {
                "status": "skipped_unchanged",
                "document_id": document_id,
                "content_hash": c_hash,
            }

        # Cap very large docs for M2 (Brain etc.) — keep head + tail markers
        body = text
        if len(body) > max_bytes:
            body = body[: max_bytes - 200] + "\n\n[truncated for index bound]\n"

        milestone = self._extract_milestone(body, path.name)
        sha = commit_sha or self.current_repo_sha()
        try:
            st = path.stat()
            created = float(getattr(st, "st_birthtime", st.st_ctime))
            modified = float(st.st_mtime)
        except OSError:
            created = modified = time.time()

        freshness = FreshnessStatus.FRESH.value
        # Content-based: LOOP_STATE and CURRENT_GOAL are treated as current runtime
        if spec.authority == SourceAuthority.AUTHORITATIVE_RUNTIME:
            freshness = FreshnessStatus.FRESH.value
        elif "evidence" in (spec.source_type.value if hasattr(spec.source_type, "value") else str(spec.source_type)):
            # Historical evidence remains useful but marked if older than runtime
            freshness = FreshnessStatus.FRESH.value

        chunks = self._chunk_text(
            body,
            document_id=document_id,
            source_id=spec.source_id,
            title=spec.title,
            authority=spec.authority.value,
            source_type=spec.source_type.value,
            relative_path=spec.relative_path,
            milestone=milestone,
            commit_sha=sha,
            freshness=freshness,
            sensitivity=spec.sensitivity.value,
        )

        doc = KnowledgeDocument(
            document_id=document_id,
            source_id=spec.source_id,
            title=spec.title,
            source_type=spec.source_type.value,
            authority=spec.authority.value,
            relative_path=spec.relative_path,
            content_hash=c_hash,
            created_at=created,
            modified_at=modified,
            indexed_at=time.time(),
            milestone=milestone,
            commit_sha=sha,
            tenant_id="platform",
            workspace_scope="*",
            sensitivity=spec.sensitivity.value,
            chunk_count=len(chunks),
            byte_size=len(raw),
            tombstoned=False,
            freshness=freshness,
            metadata={"suffix": path.suffix.lower()},
        )
        self.index.upsert_document(doc, chunks)
        return {
            "status": "indexed",
            "document_id": document_id,
            "chunk_count": len(chunks),
            "content_hash": c_hash,
            "milestone": milestone,
        }

    def ingest_platform_record(
        self,
        *,
        source_id: str,
        title: str,
        text: str,
        authority: str = SourceAuthority.AUTHORITATIVE_PLATFORM_RECORD.value,
        source_type: str = "platform_state",
        tenant_id: str = "platform",
        workspace_scope: str = "*",
        sensitivity: str = Sensitivity.TENANT_INTERNAL.value,
        milestone: str = "",
    ) -> dict[str, Any]:
        """Ingest a bounded in-memory platform state snapshot (not raw DB copy)."""
        if text_contains_secrets(text or ""):
            return {"status": "failed", "error": "secret_content_denied"}
        body = (text or "")[:MAX_FILE_BYTES]
        c_hash = content_hash(body)
        document_id = stable_id(source_id, prefix="kdoc_")
        existing = self.index.get_document(document_id)
        if existing and existing.content_hash == c_hash and not existing.tombstoned:
            return {"status": "skipped_unchanged", "document_id": document_id}
        relative_path = f"platform://{source_id}"
        chunks = self._chunk_text(
            body,
            document_id=document_id,
            source_id=source_id,
            title=title,
            authority=authority,
            source_type=source_type,
            relative_path=relative_path,
            milestone=milestone,
            commit_sha=self.current_repo_sha(),
            freshness=FreshnessStatus.FRESH.value,
            sensitivity=sensitivity,
            tenant_id=tenant_id,
            workspace_scope=workspace_scope,
        )
        doc = KnowledgeDocument(
            document_id=document_id,
            source_id=source_id,
            title=title,
            source_type=source_type,
            authority=authority,
            relative_path=relative_path,
            content_hash=c_hash,
            created_at=time.time(),
            modified_at=time.time(),
            indexed_at=time.time(),
            milestone=milestone,
            commit_sha=self.current_repo_sha(),
            tenant_id=tenant_id,
            workspace_scope=workspace_scope,
            sensitivity=sensitivity,
            chunk_count=len(chunks),
            byte_size=len(body.encode("utf-8", errors="replace")),
            freshness=FreshnessStatus.FRESH.value,
        )
        self.index.upsert_document(doc, chunks)
        return {"status": "indexed", "document_id": document_id, "chunk_count": len(chunks)}

    def _chunk_text(
        self,
        text: str,
        *,
        document_id: str,
        source_id: str,
        title: str,
        authority: str,
        source_type: str,
        relative_path: str,
        milestone: str,
        commit_sha: str,
        freshness: str,
        sensitivity: str,
        tenant_id: str = "platform",
        workspace_scope: str = "*",
    ) -> list[KnowledgeChunk]:
        text = text or ""
        chunks: list[KnowledgeChunk] = []
        if not text.strip():
            return chunks
        # Prefer paragraph-ish splits then hard caps
        parts: list[tuple[int, str]] = []
        cursor = 0
        paragraphs = re.split(r"\n{2,}", text)
        for para in paragraphs:
            if not para.strip():
                cursor += len(para) + 2
                continue
            start = text.find(para, cursor)
            if start < 0:
                start = cursor
            if len(para) <= MAX_CHUNK_CHARS:
                parts.append((start, para.strip()))
            else:
                step = MAX_CHUNK_CHARS - CHUNK_OVERLAP_CHARS
                for i in range(0, len(para), max(1, step)):
                    piece = para[i : i + MAX_CHUNK_CHARS].strip()
                    if piece:
                        parts.append((start + i, piece))
            cursor = start + len(para)

        for ordinal, (start, body) in enumerate(parts[:MAX_CHUNKS_PER_DOCUMENT]):
            body = body[:MAX_CHUNK_CHARS]
            ch_hash = content_hash(body)
            chunk_id = stable_id(document_id, str(ordinal), ch_hash, prefix="kch_")
            chunks.append(
                KnowledgeChunk(
                    chunk_id=chunk_id,
                    document_id=document_id,
                    source_id=source_id,
                    ordinal=ordinal,
                    text=body,
                    content_hash=ch_hash,
                    authority=authority,
                    source_type=source_type,
                    relative_path=relative_path,
                    title=title,
                    start_char=start,
                    end_char=start + len(body),
                    tenant_id=tenant_id,
                    workspace_scope=workspace_scope,
                    sensitivity=sensitivity,
                    milestone=milestone,
                    commit_sha=commit_sha,
                    freshness=freshness,
                )
            )
        return chunks

    def _extract_milestone(self, text: str, filename: str) -> str:
        for candidate in (filename, text[:2000]):
            m = _MILESTONE_RE.search(candidate or "")
            if m:
                return m.group(0)
        return ""
