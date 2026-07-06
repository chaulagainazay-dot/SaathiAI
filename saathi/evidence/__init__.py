"""Evidence Service — SaathiOS's shared memory. Universal schema + adapters +
store, so every department writes one shape and the CEO queries one truth.
"""
from saathi.evidence.schema import Evidence, COLUMNS, row_to_dict
from saathi.evidence.store import EvidenceStore, default_store
from saathi.evidence.adapters import ADAPTERS, ingest, from_studio_production

__all__ = ["Evidence", "COLUMNS", "row_to_dict", "EvidenceStore", "default_store",
           "ADAPTERS", "ingest", "from_studio_production"]
