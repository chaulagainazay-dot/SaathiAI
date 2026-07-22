"""M9 Memory Engine — unified, provenance-tracked, privacy-scoped memory.

Lifecycle: observe → extract → classify → store → embed → link → retrieve →
rank → reinforce → decay → forget. Semantic (local numpy embeddings, real
cosine) + keyword hybrid ranking with graph expansion. Cloud/ST/Ollama
embedding adapters are contract-ready but degrade gracefully when absent.
"""
from saathi.memory.engine.schema import MemoryStore, MEMORY_TYPES, PRIVACY_LEVELS
from saathi.memory.engine.embeddings import (
    EmbeddingProvider, LocalDeterministicEmbedder, select_provider, register,
)
from saathi.memory.engine.retrieval import (
    Weights, QueryPlan, RetrievalResult, plan_query, rank,
)
from saathi.memory.engine.core import (
    MemoryEngine, default_engine, extract_candidates, ExtractionCandidate,
    RELATIONS,
)

__all__ = [
    "MemoryStore", "MEMORY_TYPES", "PRIVACY_LEVELS",
    "EmbeddingProvider", "LocalDeterministicEmbedder", "select_provider", "register",
    "Weights", "QueryPlan", "RetrievalResult", "plan_query", "rank",
    "MemoryEngine", "default_engine", "extract_candidates", "ExtractionCandidate",
    "RELATIONS",
]
