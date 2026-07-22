"""Indexing scope, resource limits, and exclusion policy (M18.2)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from saathi.codebase_memory.classify import FileClass, classify_path, is_indexable_class

# Resource limits (8 GB Apple Silicon — conservative)
MAX_FILE_BYTES = 400_000           # ~400 KB per file
MAX_FILES_PER_BATCH = 80
MAX_CHUNKS_PER_FILE = 40
MAX_TOTAL_CHUNKS = 50_000
MAX_QUERY_RESULTS = 25
MAX_EMBED_BATCH = 32
MAX_WORKERS = 1                    # single-threaded default
MAX_INDEX_BYTES = 200 * 1024 * 1024  # 200 MB sqlite target

SECRET_POLICY_VERSION = "m18.2.s1"

# Path prefixes always excluded (relative, posix)
EXCLUDE_DIR_NAMES = frozenset({
    ".git", ".hg", ".svn",
    "node_modules", ".venv", "venv", "__pycache__",
    ".tox", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "dist", "build", ".next", "coverage", "htmlcov",
    "site-packages", "wheels", ".cache",
    "vendor", "third_party",
    ".saathi",  # runtime data
})

EXCLUDE_GLOBS_SUFFIX = (
    ".pyc", ".pyo", ".so", ".dylib", ".dll", ".exe",
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico",
    ".mp4", ".mov", ".wav", ".mp3", ".zip", ".tar", ".gz",
    ".pt", ".onnx", ".gguf", ".whl", ".pdf",
    ".sqlite", ".db", ".sqlite3",
)

# Explicit allow for key docs at repo root
FORCE_INCLUDE_NAMES = frozenset({
    "Brain.md", "Business.md", "Writing and Speaking Style.md",
    "README.md", "AGENTS.md", "Claude.md", "CLAUDE.md",
})


@dataclass(frozen=True)
class Limits:
    max_file_bytes: int = MAX_FILE_BYTES
    max_files_per_batch: int = MAX_FILES_PER_BATCH
    max_chunks_per_file: int = MAX_CHUNKS_PER_FILE
    max_total_chunks: int = MAX_TOTAL_CHUNKS
    max_query_results: int = MAX_QUERY_RESULTS
    max_embed_batch: int = MAX_EMBED_BATCH
    max_workers: int = MAX_WORKERS
    max_index_bytes: int = MAX_INDEX_BYTES


def default_limits() -> Limits:
    return Limits(
        max_file_bytes=int(os.getenv("SAATHI_CBM_MAX_FILE_BYTES", MAX_FILE_BYTES)),
        max_files_per_batch=int(os.getenv("SAATHI_CBM_BATCH", MAX_FILES_PER_BATCH)),
        max_chunks_per_file=int(os.getenv("SAATHI_CBM_CHUNKS_PER_FILE", MAX_CHUNKS_PER_FILE)),
        max_query_results=int(os.getenv("SAATHI_CBM_MAX_RESULTS", MAX_QUERY_RESULTS)),
    )


def should_exclude_dir(name: str) -> bool:
    return name in EXCLUDE_DIR_NAMES or name.startswith(".")


def path_exclusion_reason(rel: str, *, root: Path | None = None) -> str | None:
    """Return exclusion reason or None if path may be considered for indexing."""
    rel_posix = rel.replace("\\", "/")
    while rel_posix.startswith("./"):
        rel_posix = rel_posix[2:]
    rel_posix = rel_posix.lstrip("/")  # do not lstrip '.' — breaks .env names
    parts = rel_posix.split("/")
    name = parts[-1] if parts else rel_posix

    if name in FORCE_INCLUDE_NAMES or Path(name).name in FORCE_INCLUDE_NAMES:
        # still classify — may be secret name collision rare
        pass
    else:
        for part in parts[:-1]:
            if should_exclude_dir(part):
                return f"excluded_dir:{part}"
        if any(name.endswith(s) for s in EXCLUDE_GLOBS_SUFFIX):
            return f"excluded_suffix:{Path(name).suffix}"

    fc = classify_path(rel_posix)
    if fc == FileClass.SECRET:
        return "secret_path"
    if fc == FileClass.PROHIBITED:
        return "prohibited_path"
    if fc == FileClass.BINARY:
        return "binary"
    if fc == FileClass.VENDORED:
        return "vendored"
    if fc == FileClass.GENERATED:
        return "generated"
    if not is_indexable_class(fc) and name not in FORCE_INCLUDE_NAMES:
        return f"class:{fc.value}"
    return None


def classify_included(rel: str) -> FileClass:
    return classify_path(rel)
