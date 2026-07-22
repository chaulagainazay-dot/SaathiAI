"""Knowledge source adapters (read-only)."""
from saathi.knowledge.adapters.base import SourceAdapter
from saathi.knowledge.adapters.codebase import CodebaseMemoryAdapter
from saathi.knowledge.adapters.docs import DocumentationAdapter
from saathi.knowledge.adapters.provider_meta import ProviderMetaAdapter
from saathi.knowledge.adapters.memory_ltm import MemoryLtmAdapter

__all__ = [
    "SourceAdapter",
    "CodebaseMemoryAdapter",
    "DocumentationAdapter",
    "ProviderMetaAdapter",
    "MemoryLtmAdapter",
]
