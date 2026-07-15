"""M19.5 — Incremental knowledge refresh and repository change awareness.

Orchestrates M18.2 codebase_memory incremental indexing with:

* commit / branch fingerprint comparison
* changed + deleted file detection (git-aware when available)
* affected-chunk-only refresh (delegates to ``index_repository``)
* multi-repository isolation
* interrupted refresh lease + resume evidence
* deterministic audit evidence (no file bodies / secrets)

Does **not** download embedding models, clone arbitrary repos, or mutate
source trees. Secret paths remain excluded by M18.2 policy.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

from saathi.codebase_memory.indexer import IndexSummary, index_repository, open_store
from saathi.codebase_memory.identity import resolve_identity
from saathi.codebase_memory.policy import path_exclusion_reason
from saathi.codebase_memory.store import IndexStore, index_db_path

REFRESH_VERSION = "m19.5.0"
LEASE_META_KEY = "refresh_lease"
FINGERPRINT_META_KEY = "repository_fingerprint"
CACHE_EPOCH_META_KEY = "cache_epoch"
LAST_REFRESH_META_KEY = "last_refresh_evidence"
LEASE_TTL_SEC = 300.0

_lock = threading.RLock()
# In-process concurrent refresh guard keyed by repository_id
_active_leases: dict[str, str] = {}


@dataclass
class ChangeSet:
    repository_id: str
    current_commit: str
    indexed_commit: str
    branch: str
    changed_files: list[str] = field(default_factory=list)
    deleted_files: list[str] = field(default_factory=list)
    renamed_files: list[dict] = field(default_factory=list)  # {from,to}
    detection_mode: str = "full_walk"  # git_diff | full_walk | fingerprint_match
    commit_match: bool = False
    fingerprint_before: str = ""
    fingerprint_after: str = ""
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RefreshEvidence:
    ok: bool
    refresh_id: str
    version: str = REFRESH_VERSION
    repository_id: str = ""
    namespace: str = ""
    branch: str = ""
    commit_before: str = ""
    commit_after: str = ""
    fingerprint_before: str = ""
    fingerprint_after: str = ""
    action: str = "none"  # none | incremental | rebuild | resume | skipped_fresh
    files_seen: int = 0
    files_indexed: int = 0
    files_unchanged: int = 0
    files_deleted: int = 0
    chunks_written: int = 0
    symbols_written: int = 0
    secret_exclusions: int = 0
    cache_epoch: int = 0
    lease_held: bool = False
    lease_id: str = ""
    change_set: dict = field(default_factory=dict)
    duration_ms: float = 0.0
    error: str = ""
    warnings: list[str] = field(default_factory=list)
    multi_repo_isolated: bool = True
    index_summary: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def repository_fingerprint(
    *,
    repository_id: str,
    commit_sha: str,
    branch: str,
    schema_version: str,
    worktree_id: str = "",
) -> str:
    raw = "|".join([
        repository_id or "",
        commit_sha or "",
        branch or "",
        schema_version or "",
        worktree_id or "",
        REFRESH_VERSION,
    ])
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def _run_git(root: Path, *args: str) -> str | None:
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True, text=True, timeout=30, check=False,
        )
        if proc.returncode != 0:
            return None
        return (proc.stdout or "").strip()
    except (OSError, subprocess.TimeoutExpired):
        return None


def _filter_indexable(paths: Iterable[str]) -> list[str]:
    out = []
    for p in paths:
        rel = str(p).replace("\\", "/").lstrip("./")
        if not rel or rel.endswith("/"):
            continue
        reason = path_exclusion_reason(rel)
        if reason:
            continue
        out.append(rel)
    return out


def detect_changes(
    project_root: str | Path,
    *,
    base_dir: Path | None = None,
    store: IndexStore | None = None,
) -> ChangeSet:
    """Compare indexed state to current repository; list changed/deleted paths."""
    root = Path(project_root).resolve()
    try:
        ident = resolve_identity(root)
    except Exception as e:
        return ChangeSet(
            repository_id="",
            current_commit="",
            indexed_commit="",
            branch="",
            notes=[f"identity_error:{type(e).__name__}"],
        )

    owns = store is None
    st = store
    try:
        st = store or IndexStore(index_db_path(ident, base=base_dir))
        indexed_commit = st.get_meta("last_index_commit") or ""
        indexed_branch = st.get_meta("last_index_branch") or ""
        fp_before = st.get_meta(FINGERPRINT_META_KEY) or ""
        fp_now = repository_fingerprint(
            repository_id=ident.repository_id,
            commit_sha=ident.commit_sha,
            branch=ident.branch,
            schema_version=ident.index_schema_version,
            worktree_id=ident.worktree_id,
        )
        cs = ChangeSet(
            repository_id=ident.repository_id,
            current_commit=ident.commit_sha,
            indexed_commit=indexed_commit,
            branch=ident.branch,
            fingerprint_before=fp_before,
            fingerprint_after=fp_now,
            commit_match=bool(indexed_commit and indexed_commit == ident.commit_sha
                              and not ident.dirty_worktree),
        )

        if cs.commit_match and fp_before == fp_now and not ident.dirty_worktree:
            cs.detection_mode = "fingerprint_match"
            return cs

        # Prefer git diff when commits available
        if ident.is_git and indexed_commit and ident.commit_sha:
            diff = _run_git(
                root, "diff", "--name-status", f"{indexed_commit}..{ident.commit_sha}",
            )
            if diff is not None:
                cs.detection_mode = "git_diff"
                changed, deleted, renamed = [], [], []
                for line in diff.splitlines():
                    parts = line.split("\t")
                    if not parts:
                        continue
                    status = parts[0]
                    if status.startswith("R") and len(parts) >= 3:
                        renamed.append({"from": parts[1], "to": parts[2]})
                        deleted.append(parts[1])
                        changed.append(parts[2])
                    elif status.startswith("D") and len(parts) >= 2:
                        deleted.append(parts[1])
                    elif len(parts) >= 2:
                        changed.append(parts[1])
                # dirty worktree additions
                if ident.dirty_worktree:
                    dirty = _run_git(root, "status", "--porcelain")
                    if dirty:
                        for line in dirty.splitlines():
                            path = line[3:].strip() if len(line) > 3 else ""
                            if " -> " in path:
                                path = path.split(" -> ", 1)[-1]
                            if path and path not in changed:
                                changed.append(path)
                cs.changed_files = _filter_indexable(changed)
                cs.deleted_files = _filter_indexable(deleted)
                cs.renamed_files = [
                    {"from": r["from"], "to": r["to"]}
                    for r in renamed
                    if path_exclusion_reason(r.get("to") or "") is None
                ]
                return cs

        # Fallback: full walk vs store hashes (still incremental at index step)
        cs.detection_mode = "full_walk"
        cs.notes.append("git_diff_unavailable_using_hash_walk")
        return cs
    finally:
        if owns and st is not None:
            try:
                st.close()
            except Exception:
                pass


def _read_lease(st: IndexStore) -> dict:
    raw = st.get_meta(LEASE_META_KEY) or ""
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def _write_lease(st: IndexStore, lease: dict | None) -> None:
    if lease is None:
        st.set_meta(LEASE_META_KEY, "")
    else:
        st.set_meta(LEASE_META_KEY, json.dumps(lease, sort_keys=True))


def acquire_refresh_lease(
    st: IndexStore,
    *,
    repository_id: str,
    ttl_sec: float = LEASE_TTL_SEC,
    force_stale: bool = False,
) -> tuple[bool, str, list[str]]:
    """Acquire exclusive refresh lease. Returns (ok, lease_id, warnings)."""
    warnings: list[str] = []
    now = time.time()
    existing = _read_lease(st)
    if existing:
        exp = float(existing.get("expires_at") or 0)
        lid = str(existing.get("lease_id") or "")
        if exp > now and not force_stale:
            with _lock:
                if _active_leases.get(repository_id) == lid:
                    return False, lid, ["lease_held_same_process"]
            return False, lid, ["lease_held_by_other"]
        if exp <= now or force_stale:
            warnings.append("stale_lease_recovered")
            _write_lease(st, None)

    lease_id = uuid.uuid4().hex[:16]
    lease = {
        "lease_id": lease_id,
        "repository_id": repository_id,
        "acquired_at": now,
        "expires_at": now + ttl_sec,
        "pid": os.getpid(),
    }
    _write_lease(st, lease)
    with _lock:
        _active_leases[repository_id] = lease_id
    return True, lease_id, warnings


def release_refresh_lease(
    st: IndexStore,
    *,
    repository_id: str,
    lease_id: str,
) -> None:
    existing = _read_lease(st)
    if existing and str(existing.get("lease_id")) == lease_id:
        _write_lease(st, None)
    with _lock:
        if _active_leases.get(repository_id) == lease_id:
            _active_leases.pop(repository_id, None)


def invalidate_cache_epoch(st: IndexStore, *, bump: int = 1) -> int:
    """Bump cache epoch so consumers know results may be stale-to-fresh."""
    try:
        cur = int(st.get_meta(CACHE_EPOCH_META_KEY) or "0")
    except ValueError:
        cur = 0
    new = cur + max(1, bump)
    st.set_meta(CACHE_EPOCH_META_KEY, str(new))
    return new


def incremental_refresh(
    project_root: str | Path,
    *,
    base_dir: Path | None = None,
    rebuild: bool = False,
    dry_run: bool = False,
    force: bool = False,
    allow_concurrent_steal_stale: bool = True,
) -> RefreshEvidence:
    """Run incremental (or rebuild) refresh with durable audit evidence."""
    t0 = time.time()
    refresh_id = uuid.uuid4().hex[:12]
    root = Path(project_root).resolve()
    evidence = RefreshEvidence(ok=False, refresh_id=refresh_id)

    try:
        ident = resolve_identity(root)
    except Exception as e:
        evidence.error = f"identity:{type(e).__name__}:{e}"[:200]
        evidence.duration_ms = round((time.time() - t0) * 1000, 2)
        return evidence

    evidence.repository_id = ident.repository_id
    evidence.namespace = ident.project_namespace
    evidence.branch = ident.branch
    evidence.commit_after = ident.commit_sha

    st = None
    lease_id = ""
    try:
        st = open_store(ident, base=base_dir)
        evidence.commit_before = st.get_meta("last_index_commit") or ""
        evidence.fingerprint_before = st.get_meta(FINGERPRINT_META_KEY) or ""

        cs = detect_changes(root, base_dir=base_dir, store=st)
        evidence.change_set = cs.to_dict()

        counts = st.counts() if hasattr(st, "counts") else {}
        has_index_data = (
            int(counts.get("chunks") or 0) > 0
            or int(counts.get("files") or 0) > 0
            or int(counts.get("symbols") or 0) > 0
        )
        if (
            not force
            and not rebuild
            and cs.detection_mode == "fingerprint_match"
            and cs.commit_match
            and has_index_data
        ):
            evidence.ok = True
            evidence.action = "skipped_fresh"
            evidence.fingerprint_after = cs.fingerprint_after
            evidence.cache_epoch = int(st.get_meta(CACHE_EPOCH_META_KEY) or "0")
            evidence.duration_ms = round((time.time() - t0) * 1000, 2)
            return evidence

        ok_lease, lease_id, lw = acquire_refresh_lease(
            st,
            repository_id=ident.repository_id,
            force_stale=allow_concurrent_steal_stale,
        )
        evidence.warnings.extend(lw)
        if not ok_lease:
            evidence.error = "refresh_lease_busy"
            evidence.lease_id = lease_id
            evidence.duration_ms = round((time.time() - t0) * 1000, 2)
            return evidence
        evidence.lease_held = True
        evidence.lease_id = lease_id

        # Mark interrupted-in-progress for resume detection
        st.set_meta("refresh_in_progress", json.dumps({
            "refresh_id": refresh_id,
            "lease_id": lease_id,
            "started_at": time.time(),
        }, sort_keys=True))

        summary: IndexSummary = index_repository(
            root,
            rebuild=rebuild,
            dry_run=dry_run,
            base_dir=base_dir,
            store=st,
            identity=ident,
        )
        evidence.index_summary = summary.to_dict()
        evidence.ok = bool(summary.ok)
        evidence.action = "rebuild" if rebuild else "incremental"
        evidence.files_seen = summary.files_seen
        evidence.files_indexed = summary.files_indexed
        evidence.files_unchanged = summary.files_unchanged
        evidence.files_deleted = summary.files_deleted
        evidence.chunks_written = summary.chunks_written
        evidence.symbols_written = summary.symbols_written
        evidence.secret_exclusions = summary.secret_exclusions
        if not summary.ok:
            evidence.error = summary.error or "index_failed"

        if summary.ok and not dry_run:
            fp = repository_fingerprint(
                repository_id=ident.repository_id,
                commit_sha=ident.commit_sha,
                branch=ident.branch,
                schema_version=ident.index_schema_version,
                worktree_id=ident.worktree_id,
            )
            st.set_meta(FINGERPRINT_META_KEY, fp)
            evidence.fingerprint_after = fp
            evidence.cache_epoch = invalidate_cache_epoch(st)
            # Persist compact evidence (no bodies)
            compact = {
                k: evidence.to_dict()[k]
                for k in (
                    "ok", "refresh_id", "version", "repository_id", "action",
                    "commit_before", "commit_after", "fingerprint_before",
                    "fingerprint_after", "files_indexed", "files_deleted",
                    "files_unchanged", "chunks_written", "cache_epoch",
                    "duration_ms",
                )
            }
            st.set_meta(LAST_REFRESH_META_KEY, json.dumps(compact, sort_keys=True))
            st.set_meta("refresh_in_progress", "")

        return evidence
    except Exception as e:
        evidence.ok = False
        evidence.error = f"{type(e).__name__}:{e}"[:200]
        return evidence
    finally:
        if st is not None and lease_id:
            try:
                release_refresh_lease(
                    st, repository_id=evidence.repository_id, lease_id=lease_id,
                )
            except Exception:
                pass
        if st is not None:
            try:
                st.close()
            except Exception:
                pass
        evidence.duration_ms = round((time.time() - t0) * 1000, 2)


def refresh_registered_repositories(
    *,
    saathi_root: str | Path | None = None,
    base_dir: Path | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Refresh all registered codebase_index sources (isolated per repo)."""
    from saathi.knowledge.registry import default_source_registry

    root = str(Path(saathi_root or Path.cwd()).resolve())
    sources = default_source_registry(saathi_root=root)
    reports: list[dict] = []
    for src in sources:
        if src.adapter != "codebase_memory" or src.source_type != "codebase_index":
            continue
        if not src.enabled:
            reports.append({
                "source_id": src.source_id,
                "ok": False,
                "error": "source_disabled",
            })
            continue
        # Isolation: never pass foreign base paths mixed across repos
        ev = incremental_refresh(src.location, base_dir=base_dir, force=force)
        reports.append({
            "source_id": src.source_id,
            "repository_id": src.repository_id,
            **{k: ev.to_dict()[k] for k in (
                "ok", "action", "refresh_id", "files_indexed", "files_deleted",
                "files_unchanged", "error", "fingerprint_after", "cache_epoch",
            )},
        })
    return {
        "ok": all(r.get("ok") for r in reports if r.get("error") != "source_disabled"),
        "version": REFRESH_VERSION,
        "reports": reports,
    }


def last_refresh_evidence(
    project_root: str | Path,
    *,
    base_dir: Path | None = None,
) -> dict:
    """Load last durable refresh evidence from index meta (aggregate only)."""
    try:
        ident = resolve_identity(project_root)
        st = IndexStore(index_db_path(ident, base=base_dir))
        try:
            raw = st.get_meta(LAST_REFRESH_META_KEY) or ""
            if not raw:
                return {"ok": False, "error": "no_refresh_evidence"}
            return json.loads(raw)
        finally:
            st.close()
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}"}
