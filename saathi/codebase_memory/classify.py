"""File classification for indexing policy and ranking."""
from __future__ import annotations

from enum import Enum
from pathlib import Path


class FileClass(str, Enum):
    SOURCE_CODE = "SOURCE_CODE"
    TEST_CODE = "TEST_CODE"
    DOCUMENTATION = "DOCUMENTATION"
    ARCHITECTURE = "ARCHITECTURE"
    ROADMAP = "ROADMAP"
    CONFIGURATION = "CONFIGURATION"
    SCHEMA = "SCHEMA"
    MIGRATION = "MIGRATION"
    SCRIPT = "SCRIPT"
    STYLE_GUIDE = "STYLE_GUIDE"
    BUSINESS_CONTEXT = "BUSINESS_CONTEXT"
    GENERATED = "GENERATED"
    VENDORED = "VENDORED"
    BINARY = "BINARY"
    SECRET = "SECRET"
    PROHIBITED = "PROHIBITED"
    UNKNOWN = "UNKNOWN"


# Trust / rank boost (higher = preferred)
CLASS_RANK_WEIGHT: dict[FileClass, float] = {
    FileClass.SOURCE_CODE: 1.0,
    FileClass.TEST_CODE: 0.95,
    FileClass.ARCHITECTURE: 1.15,
    FileClass.ROADMAP: 1.1,
    FileClass.DOCUMENTATION: 1.05,
    FileClass.STYLE_GUIDE: 1.05,
    FileClass.BUSINESS_CONTEXT: 1.1,
    FileClass.CONFIGURATION: 0.85,
    FileClass.SCHEMA: 0.9,
    FileClass.MIGRATION: 0.85,
    FileClass.SCRIPT: 0.8,
    FileClass.GENERATED: 0.2,
    FileClass.VENDORED: 0.15,
    FileClass.BINARY: 0.0,
    FileClass.SECRET: 0.0,
    FileClass.PROHIBITED: 0.0,
    FileClass.UNKNOWN: 0.5,
}

CANONICAL_DOCS = frozenset({
    "brain.md",
    "business.md",
    "writing and speaking style.md",
    "mcp_inventory.md",
    "external_capability_status.md",
    "autonomous_roadmap.md",
    "technical_debt.md",
    "capability_maturity_matrix.md",
})

_CODE_EXT = {
    ".py": "python", ".js": "javascript", ".ts": "typescript",
    ".jsx": "javascript", ".tsx": "typescript", ".sh": "shell",
    ".bash": "shell", ".zsh": "shell", ".sql": "sql",
    ".go": "go", ".rs": "rust", ".java": "java",
}
_DOC_EXT = {".md", ".rst", ".txt", ".adoc"}
_CFG_EXT = {".toml", ".yaml", ".yml", ".json", ".ini", ".cfg", ".env.example"}
_BINARY_EXT = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf",
    ".mp4", ".mov", ".wav", ".mp3", ".zip", ".tar", ".gz", ".whl",
    ".so", ".dylib", ".dll", ".exe", ".bin", ".pt", ".onnx", ".gguf",
    ".sqlite", ".db", ".pyc", ".pyo", ".class",
}


def language_for(path: Path) -> str:
    return _CODE_EXT.get(path.suffix.lower(), "")


def classify_path(rel_path: str | Path) -> FileClass:
    """Classify a repository-relative path."""
    p = Path(str(rel_path).replace("\\", "/"))
    parts = [x.lower() for x in p.parts]
    name = p.name.lower()
    suf = p.suffix.lower()

    # secrets / prohibited by name
    if name in (".env", ".env.local", ".env.production", "credentials.json",
                "secrets.yaml", "id_rsa", "id_ed25519") or name.endswith(".pem"):
        return FileClass.SECRET
    if name.startswith(".env.") and name != ".env.example":
        return FileClass.SECRET
    if any(x in parts for x in ("secrets", "private_keys", "browser_profiles")):
        return FileClass.PROHIBITED

    # vendored / generated / build
    vendor_dirs = {
        "node_modules", ".venv", "venv", "vendor", "third_party",
        "__pycache__", ".tox", ".mypy_cache", ".pytest_cache", "dist",
        "build", ".next", "coverage", "htmlcov", ".git", "site-packages",
        "wheels", ".cache", "artifacts",
    }
    if any(x in vendor_dirs for x in parts):
        if "vendor" in parts or "third_party" in parts or "node_modules" in parts:
            return FileClass.VENDORED
        return FileClass.GENERATED

    if suf in _BINARY_EXT:
        return FileClass.BINARY

    if name in CANONICAL_DOCS or name == "writing and speaking style.md":
        if "style" in name:
            return FileClass.STYLE_GUIDE
        if name == "business.md":
            return FileClass.BUSINESS_CONTEXT
        if "roadmap" in name or "debt" in name or "capability" in name:
            return FileClass.ROADMAP
        if name == "brain.md":
            return FileClass.ARCHITECTURE
        return FileClass.DOCUMENTATION

    if "migration" in parts or name.endswith(".sql") and "migration" in str(p).lower():
        return FileClass.MIGRATION
    if suf == ".sql":
        return FileClass.SCHEMA
    if any(x in name for x in ("schema", "openapi", "swagger")):
        return FileClass.SCHEMA

    if "test" in parts or name.startswith("test_") or name.endswith("_test.py") \
            or name.endswith(".test.ts") or name.endswith(".spec.ts"):
        return FileClass.TEST_CODE

    if suf in _DOC_EXT:
        low = str(p).lower()
        if any(k in low for k in ("architecture", "ses-", "audit", "adr", "m17_", "m18_")):
            return FileClass.ARCHITECTURE
        if any(k in low for k in ("roadmap", "debt", "maturity", "changelog")):
            return FileClass.ROADMAP
        return FileClass.DOCUMENTATION

    if suf in _CFG_EXT or name in (
        "dockerfile", "makefile", "pyproject.toml", "package.json",
        "requirements.txt", "cargo.toml", "go.mod",
    ):
        return FileClass.CONFIGURATION

    if suf in (".sh", ".bash", ".zsh") or parts[:1] == ["scripts"]:
        return FileClass.SCRIPT

    if suf in _CODE_EXT:
        return FileClass.SOURCE_CODE

    return FileClass.UNKNOWN


def is_indexable_class(fc: FileClass) -> bool:
    return fc not in (
        FileClass.BINARY, FileClass.SECRET, FileClass.PROHIBITED,
        FileClass.GENERATED, FileClass.VENDORED,
    )
