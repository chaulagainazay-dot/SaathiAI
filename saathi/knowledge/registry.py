"""Registered knowledge sources — only registered sources may be queried."""
from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from saathi.knowledge.types import TrustLevel


@dataclass
class KnowledgeSource:
    source_id: str
    source_type: str  # codebase_index | documentation | memory_ltm | provider_metadata | decision_docs
    repository_id: str
    location: str  # path or logical
    trust: TrustLevel = TrustLevel.HIGH
    enabled: bool = True
    health: str = "unknown"
    adapter: str = ""
    query_modes: list[str] = field(default_factory=lambda: ["lexical"])
    permission_scope: str = "internal"
    data_classification: str = "internal"
    is_generated: bool = False
    owner: str = "saathios"
    retrieval_cost: str = "low"  # low | medium
    freshness_hint: str = "index_or_fs"
    tenant_id: str = "default"
    workspace_id: str = "default"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["trust"] = self.trust.value
        return d


def _default_saathi_root() -> str:
    # Prefer CWD if it looks like SaathiAI, else package parent chain
    cwd = Path.cwd()
    if (cwd / "saathi").is_dir() and (cwd / "docs").is_dir():
        return str(cwd.resolve())
    # saathi/knowledge/registry.py → parents[2] = repo root
    return str(Path(__file__).resolve().parents[2])


def default_source_registry(
    *,
    saathi_root: str | Path | None = None,
    extra_repos: list[dict] | None = None,
) -> list[KnowledgeSource]:
    """Built-in registry. Agents cannot inject unregistered repos via query alone."""
    root = str(Path(saathi_root or _default_saathi_root()).resolve())
    sources = [
        KnowledgeSource(
            source_id="saathiai.codebase_index",
            source_type="codebase_index",
            repository_id="saathiai",
            location=root,
            trust=TrustLevel.HIGH,
            adapter="codebase_memory",
            query_modes=["lexical", "symbol", "path"],
            owner="saathios",
        ),
        KnowledgeSource(
            source_id="saathiai.documentation",
            source_type="documentation",
            repository_id="saathiai",
            location=str(Path(root) / "docs"),
            trust=TrustLevel.HIGH,
            adapter="documentation",
            query_modes=["lexical", "path"],
            owner="saathios",
        ),
        KnowledgeSource(
            source_id="saathiai.decision_docs",
            source_type="decision_docs",
            repository_id="saathiai",
            location=str(Path(root) / "docs"),
            trust=TrustLevel.HIGH,
            adapter="decision_docs",
            query_modes=["lexical"],
            owner="saathios",
            data_classification="internal",
        ),
        KnowledgeSource(
            source_id="saathiai.provider_insforge",
            source_type="provider_metadata",
            repository_id="insforge",
            location="saathi.providers.insforge",
            trust=TrustLevel.MEDIUM,
            adapter="provider_meta",
            query_modes=["metadata"],
            owner="saathios",
            enabled=True,  # adapter returns disabled status if provider off
            retrieval_cost="low",
        ),
        # Long-term memory — registered but only for MISSION_CONTEXT profile
        KnowledgeSource(
            source_id="saathiai.memory_ltm",
            source_type="memory_ltm",
            repository_id="saathiai",
            location="saathi.memory.engine",
            trust=TrustLevel.MEDIUM,
            adapter="memory_ltm",
            query_modes=["semantic_or_keyword"],
            owner="saathios",
            is_generated=False,
        ),
    ]
    for er in extra_repos or []:
        # Only explicit constructor registration — not from free query params
        sources.append(KnowledgeSource(
            source_id=str(er["source_id"]),
            source_type=str(er.get("source_type") or "codebase_index"),
            repository_id=str(er["repository_id"]),
            location=str(er["location"]),
            trust=TrustLevel(er.get("trust") or "medium"),
            adapter=str(er.get("adapter") or "codebase_memory"),
            enabled=bool(er.get("enabled", True)),
            owner=str(er.get("owner") or "external"),
            tenant_id=str(er.get("tenant_id") or "default"),
            workspace_id=str(er.get("workspace_id") or "default"),
        ))
    return sources


def registry_by_id(sources: list[KnowledgeSource]) -> dict[str, KnowledgeSource]:
    return {s.source_id: s for s in sources}


def filter_by_tenant(
    sources: list[KnowledgeSource],
    *,
    tenant_id: str,
    workspace_id: str,
) -> list[KnowledgeSource]:
    out = []
    for s in sources:
        if s.tenant_id not in (tenant_id, "default", "*"):
            continue
        if s.workspace_id not in (workspace_id, "default", "*"):
            continue
        out.append(s)
    return out
