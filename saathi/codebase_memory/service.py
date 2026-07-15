"""Runtime facade: index + search + health for agents and CLI."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from saathi.codebase_memory.health import capability_negotiation, index_health
from saathi.codebase_memory.identity import resolve_identity
from saathi.codebase_memory.indexer import index_repository, rebuild_index
from saathi.codebase_memory.retrieve import search as memory_search
from saathi.codebase_memory.store import IndexStore, index_db_path
from saathi.mcp_governance.policy import is_enabled, set_enabled
from saathi.mcp_governance.inventory import CANONICAL_CODEBASE_MEMORY_ID


class CodebaseMemoryRuntime:
    def __init__(
        self,
        project_root: str | Path | None = None,
        *,
        base_dir: Path | None = None,
    ):
        self.project_root = str(project_root) if project_root else None
        self.base_dir = base_dir

    def identity(self):
        return resolve_identity(self.project_root)

    def health(self) -> dict:
        return index_health(self.project_root, base_dir=self.base_dir).to_dict()

    def capabilities(self) -> dict:
        return capability_negotiation(self.project_root)

    def index(self, *, rebuild: bool = False, dry_run: bool = False) -> dict:
        if not is_enabled(CANONICAL_CODEBASE_MEMORY_ID):
            return {"ok": False, "error": "disabled", "error_category": "disabled"}
        if rebuild:
            s = rebuild_index(
                self.project_root, dry_run=dry_run, base_dir=self.base_dir,
            )
        else:
            s = index_repository(
                self.project_root, dry_run=dry_run, base_dir=self.base_dir,
            )
        return s.to_dict()

    def refresh(self) -> dict:
        """M19.5: commit-aware incremental refresh with durable evidence.

        Falls back to M18.2 hash-walk indexing when the knowledge refresh
        layer is unavailable.
        """
        try:
            from saathi.knowledge.refresh import incremental_refresh

            ev = incremental_refresh(
                self.project_root, base_dir=self.base_dir, rebuild=False,
            )
            out = ev.to_dict()
            # Preserve M18.2-shaped keys for existing CLI consumers
            out.setdefault("files_indexed", ev.files_indexed)
            out.setdefault("files_unchanged", ev.files_unchanged)
            out.setdefault("files_deleted", ev.files_deleted)
            return out
        except Exception:
            return self.index(rebuild=False)

    def search(self, query: str, **kwargs) -> dict:
        if not is_enabled(CANONICAL_CODEBASE_MEMORY_ID):
            return {
                "ok": False, "degraded": True, "error": "disabled",
                "error_category": "disabled", "hits": [], "consulted_index": False,
            }
        # M19.1: route through adoption gateway (default mode = legacy → same M18.2 path)
        from saathi.knowledge.adoption import adopted_codebase_search
        from saathi.knowledge.rollout import CALLER_CODEBASE_MEMORY_SEARCH

        mode = kwargs.pop("adoption_mode", None)
        mission_id = kwargs.pop("mission_id", "")
        run_id = kwargs.pop("run_id", "")
        return adopted_codebase_search(
            query,
            project_root=self.project_root,
            base_dir=self.base_dir,
            mission_id=mission_id,
            run_id=run_id,
            mode=mode,
            caller_id=CALLER_CODEBASE_MEMORY_SEARCH,
            **kwargs,
        )

    def symbol(self, name: str, *, top_k: int = 15, **kwargs) -> dict:
        from saathi.knowledge.adoption import adopted_symbol_lookup
        mode = kwargs.pop("adoption_mode", None)
        return adopted_symbol_lookup(
            name,
            project_root=self.project_root,
            base_dir=self.base_dir,
            top_k=top_k,
            mode=mode,
            **kwargs,
        )

    def document(self, query: str, *, top_k: int = 10, **kwargs) -> dict:
        from saathi.knowledge.adoption import adopted_document_search
        mode = kwargs.pop("adoption_mode", None)
        return adopted_document_search(
            query,
            project_root=self.project_root,
            base_dir=self.base_dir,
            top_k=top_k,
            mode=mode,
            **kwargs,
        )

    def explain(self, query: str, **kwargs) -> dict:
        kwargs.setdefault("explain", True)
        from saathi.knowledge.rollout import CALLER_CODEBASE_MEMORY_EXPLAIN
        # Force explain caller id for metrics while reusing search adoption
        from saathi.knowledge.adoption import adopted_codebase_search
        mode = kwargs.pop("adoption_mode", None)
        return adopted_codebase_search(
            query,
            project_root=self.project_root,
            base_dir=self.base_dir,
            mode=mode,
            caller_id=CALLER_CODEBASE_MEMORY_EXPLAIN,
            **kwargs,
        )

    def rebuild(self, *, dry_run: bool = False) -> dict:
        return self.index(rebuild=True, dry_run=dry_run)

    def clear_index(self, *, confirm: bool = False) -> dict:
        """Governed clear — requires confirm=True. Does not touch repository files."""
        if not confirm:
            return {"ok": False, "error": "confirm_required"}
        if not is_enabled(CANONICAL_CODEBASE_MEMORY_ID):
            return {"ok": False, "error": "disabled"}
        ident = resolve_identity(self.project_root)
        st = IndexStore(index_db_path(ident, base=self.base_dir))
        try:
            st.clear_all()
            return {"ok": True, "cleared": True, "db_path": str(st.path)}
        finally:
            st.close()


_default: CodebaseMemoryRuntime | None = None


def default_runtime(project_root: str | Path | None = None) -> CodebaseMemoryRuntime:
    global _default
    if project_root is not None:
        return CodebaseMemoryRuntime(project_root)
    if _default is None:
        _default = CodebaseMemoryRuntime()
    return _default


# Agent tool dispatch (strict schemas, read-oriented)
def dispatch_tool(name: str, args: dict | None = None, *, project_root: str | None = None) -> dict:
    """Bounded agent tool entry. No repository file writes."""
    args = args or {}
    rt = CodebaseMemoryRuntime(project_root or args.get("project_root"))
    # never allow write keys
    banned = {"apply_patch", "commit", "push", "shell", "delete_file", "write_file"}
    if name in banned or any(k in banned for k in args):
        return {"ok": False, "error": "write_ops_forbidden", "denied": True}

    if name == "codebase_memory_health":
        return {"ok": True, "data": rt.health()}
    if name == "codebase_memory_index":
        return rt.index(dry_run=bool(args.get("dry_run")))
    if name == "codebase_memory_refresh":
        return rt.refresh()
    if name == "codebase_memory_search":
        return rt.search(
            str(args.get("query") or ""),
            top_k=int(args.get("top_k") or 10),
            path_filter=str(args.get("path_filter") or ""),
            symbol_filter=str(args.get("symbol_filter") or ""),
            documentation_only=bool(args.get("documentation_only")),
            tests_only=bool(args.get("tests_only")),
            current_only=args.get("current_only", True),
            historical=bool(args.get("historical")),
            namespace=args.get("namespace"),
            mission_id=str(args.get("mission_id") or ""),
            run_id=str(args.get("run_id") or ""),
            adoption_mode=args.get("adoption_mode"),
        )
    if name == "codebase_memory_symbol":
        return rt.symbol(
            str(args.get("name") or args.get("query") or ""),
            adoption_mode=args.get("adoption_mode"),
        )
    if name == "codebase_memory_document":
        return rt.document(
            str(args.get("query") or ""),
            adoption_mode=args.get("adoption_mode"),
        )
    if name == "codebase_memory_explain":
        return rt.explain(
            str(args.get("query") or ""),
            adoption_mode=args.get("adoption_mode"),
        )
    if name == "codebase_memory_rebuild":
        return rt.rebuild(dry_run=bool(args.get("dry_run")))
    return {"ok": False, "error": f"unknown_tool:{name}", "denied": True}
