"""Bounded incremental repository indexer (local-first, restart-safe)."""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

from saathi.codebase_memory.chunking import chunk_file
from saathi.codebase_memory.classify import FileClass, classify_path, language_for
from saathi.codebase_memory.discover import discover_files, file_hash_bytes
from saathi.codebase_memory.identity import (
    INDEX_SCHEMA_VERSION,
    RepoIdentity,
    identity_compatible,
    resolve_identity,
)
from saathi.codebase_memory.policy import (
    SECRET_POLICY_VERSION,
    Limits,
    default_limits,
)
from saathi.codebase_memory.secrets_scan import safe_exclusion_log, scan_content
from saathi.codebase_memory.store import IndexStore, index_db_path
from saathi.codebase_memory.symbols import extract_symbols
from saathi.codebase_memory import events as cbm_events

PARSER_VERSION = "m18.2.p1"


@dataclass
class IndexSummary:
    ok: bool
    dry_run: bool = False
    repository_id: str = ""
    namespace: str = ""
    branch: str = ""
    commit_sha: str = ""
    files_seen: int = 0
    files_indexed: int = 0
    files_skipped: int = 0
    files_unchanged: int = 0
    files_deleted: int = 0
    chunks_written: int = 0
    symbols_written: int = 0
    exclusions: int = 0
    secret_exclusions: int = 0
    duration_sec: float = 0.0
    rebuild: bool = False
    error: str = ""
    db_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def open_store(
    ident: RepoIdentity,
    *,
    base: Path | None = None,
) -> IndexStore:
    path = index_db_path(ident, base=base)
    store = IndexStore(path)
    stored = store.load_identity_meta()
    if stored:
        ok, reason = identity_compatible(
            {
                "index_schema_version": store.get_meta("index_schema_version"),
                "repository_id": stored.get("repository_id"),
                "worktree_id": stored.get("worktree_id"),
            },
            ident,
        )
        if not ok:
            store.clear_all()
            store.set_meta("last_incompatible_reason", reason)
    store.save_identity(ident)
    store.set_meta("parser_version", PARSER_VERSION)
    store.set_meta("secret_policy_version", SECRET_POLICY_VERSION)
    return store


def index_repository(
    project_root: str | Path | None = None,
    *,
    rebuild: bool = False,
    dry_run: bool = False,
    limits: Limits | None = None,
    store: IndexStore | None = None,
    identity: RepoIdentity | None = None,
    base_dir: Path | None = None,
) -> IndexSummary:
    t0 = time.time()
    limits = limits or default_limits()
    try:
        ident = identity or resolve_identity(project_root)
    except Exception as e:
        return IndexSummary(ok=False, error=str(e)[:300])

    cbm_events.emit("index_started", {
        "repository_id": ident.repository_id,
        "branch": ident.branch,
        "rebuild": rebuild,
        "dry_run": dry_run,
    })

    owns_store = store is None
    try:
        st = store or open_store(ident, base=base_dir)
    except Exception as e:
        return IndexSummary(ok=False, error=f"store_open:{e}"[:300])

    summary = IndexSummary(
        ok=True,
        dry_run=dry_run,
        repository_id=ident.repository_id,
        namespace=ident.project_namespace,
        branch=ident.branch,
        commit_sha=ident.commit_sha,
        rebuild=rebuild,
        db_path=str(st.path),
    )

    try:
        if rebuild and not dry_run:
            st.clear_all()
            st.save_identity(ident)
            st.set_meta("parser_version", PARSER_VERSION)
            st.set_meta("secret_policy_version", SECRET_POLICY_VERSION)

        root = Path(ident.repository_root)
        seen: set[str] = set()
        batch = 0

        for rel, abs_p, excl in discover_files(root, limits=limits):
            summary.files_seen += 1
            if excl:
                summary.exclusions += 1
                summary.files_skipped += 1
                if not dry_run:
                    st.record_exclusion(rel, excl)
                    if excl.startswith("secret"):
                        summary.secret_exclusions += 1
                        cbm_events.emit("secret_exclusion", safe_exclusion_log(excl, rel))
                continue

            seen.add(rel)
            try:
                data = abs_p.read_bytes()
            except OSError as e:
                summary.files_skipped += 1
                if not dry_run:
                    st.record_exclusion(rel, f"read_error:{type(e).__name__}")
                continue

            fhash = file_hash_bytes(data)
            prev = st.get_file(rel) if not dry_run else None
            if prev and prev.get("file_hash") == fhash and not prev.get("deleted") and not rebuild:
                summary.files_unchanged += 1
                continue

            # decode
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                try:
                    text = data.decode("utf-8", errors="replace")
                    # if many replacements, skip
                    if text.count("\ufffd") > 20:
                        summary.files_skipped += 1
                        if not dry_run:
                            st.record_exclusion(rel, "decode_uncertain")
                        continue
                except Exception:
                    summary.files_skipped += 1
                    continue

            scan = scan_content(text, path=rel, file_class=classify_path(rel).value)
            if not scan.allowed:
                summary.secret_exclusions += 1
                summary.exclusions += 1
                summary.files_skipped += 1
                if not dry_run:
                    st.record_exclusion(rel, scan.reason)
                    cbm_events.emit("secret_exclusion", safe_exclusion_log(scan.reason, rel))
                continue

            fc = classify_path(rel)
            lang = language_for(Path(rel))
            chunks = chunk_file(rel, text, file_class=fc, language=lang)[
                : limits.max_chunks_per_file
            ]
            syms = extract_symbols(rel, text, lang)

            if dry_run:
                summary.files_indexed += 1
                summary.chunks_written += len(chunks)
                summary.symbols_written += len(syms)
                continue

            st.delete_chunks_for_path(rel)
            now = time.time()
            st.upsert_file({
                "path": rel,
                "file_hash": fhash,
                "classification": fc.value,
                "language": lang,
                "size_bytes": len(data),
                "deleted": 0,
                "generated": 0,
                "vendored": 0,
                "sensitivity": "internal",
                "branch": ident.branch,
                "commit_sha": ident.commit_sha,
                "dirty": int(ident.dirty_worktree),
                "indexed_at": now,
                "last_verified_at": now,
            })
            for ch in chunks:
                st.upsert_chunk({
                    "chunk_id": ch.chunk_id,
                    "path": rel,
                    "start_line": ch.start_line,
                    "end_line": ch.end_line,
                    "symbol": ch.symbol,
                    "symbol_type": ch.symbol_type,
                    "section": ch.section,
                    "text": ch.text,
                    "content_hash": ch.content_hash(),
                    "classification": fc.value,
                    "language": lang,
                    "file_hash": fhash,
                    "branch": ident.branch,
                    "commit_sha": ident.commit_sha,
                    "dirty": int(ident.dirty_worktree),
                    "deleted": 0,
                    "chunk_version": ch.chunk_version,
                    "parser_version": PARSER_VERSION,
                    "schema_version": INDEX_SCHEMA_VERSION,
                    "indexed_at": now,
                    "last_verified_at": now,
                    "sensitivity": "internal",
                })
                summary.chunks_written += 1
            for s in syms:
                st.upsert_symbol(s.to_dict())
                summary.symbols_written += 1
            summary.files_indexed += 1
            batch += 1
            if batch >= limits.max_files_per_batch:
                # checkpoint
                st.set_meta("checkpoint_files", str(summary.files_indexed))
                st.set_meta("checkpoint_at", str(time.time()))
                batch = 0
                # soft resource bound: stop if too many chunks
                if st.counts()["chunks"] >= limits.max_total_chunks:
                    cbm_events.emit("resource_limit_reached", {
                        "chunks": st.counts()["chunks"],
                    })
                    break

        # deletions
        if not dry_run:
            for old in st.list_file_paths():
                if old not in seen:
                    st.mark_deleted(old)
                    summary.files_deleted += 1
            st.set_meta("last_index_commit", ident.commit_sha)
            st.set_meta("last_index_branch", ident.branch)
            st.set_meta("last_successful_index", str(time.time()))
            st.set_meta("last_index_summary", str(summary.files_indexed))

        summary.duration_sec = round(time.time() - t0, 3)
        cbm_events.emit("index_completed", summary.to_dict())
        return summary
    except Exception as e:
        summary.ok = False
        summary.error = str(e)[:300]
        summary.duration_sec = round(time.time() - t0, 3)
        cbm_events.emit("index_failed", {"error": summary.error})
        return summary
    finally:
        if owns_store and store is None:
            try:
                st.close()
            except Exception:
                pass


def rebuild_index(
    project_root: str | Path | None = None,
    **kwargs: Any,
) -> IndexSummary:
    return index_repository(project_root, rebuild=True, **kwargs)
