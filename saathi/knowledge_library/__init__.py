"""Knowledge Library — SaathiOS's permanent, company-wide learning source. Books,
GitHub repos, papers, docs, SOPs ingested once and searchable by every Director.
"""
from saathi.knowledge_library.store import LibraryStore, default_store, SOURCE_TYPES
from saathi.knowledge_library.importer import import_repo, seed_defaults

__all__ = ["LibraryStore", "default_store", "SOURCE_TYPES", "import_repo", "seed_defaults"]
