"""Point-in-time dataset revision resolution for research backtests."""
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

@dataclass(frozen=True)
class DatasetRevision:
    dataset_id: str
    revision_id: str
    source_record_id: str
    event_as_of: datetime
    available_at: datetime
    content_hash: str
    supersedes_revision_id: str = ""
    status: str = "ORIGINAL"
    def __post_init__(self):
        if self.available_at.tzinfo is None or self.event_as_of.tzinfo is None:
            raise ValueError("revision timestamps must be timezone-aware")
        if not self.revision_id or not self.content_hash:
            raise ValueError("revision identity and content hash are required")
        if self.status not in {"ORIGINAL", "CORRECTED", "SUPERSEDED", "RETRACTED", "UNKNOWN"}:
            raise ValueError("invalid revision status")

def validate_revision_lineage(revisions: Iterable[DatasetRevision]) -> tuple[DatasetRevision, ...]:
    rows=tuple(revisions); by_id={r.revision_id:r for r in rows}
    if len(by_id)!=len(rows): raise ValueError("duplicate revision id")
    for r in rows:
        seen=set(); cur=r
        while cur.supersedes_revision_id:
            if cur.revision_id in seen: raise ValueError("cyclic revision lineage")
            seen.add(cur.revision_id)
            cur=by_id.get(cur.supersedes_revision_id)
            if cur is None: raise ValueError("unknown superseded revision")
    return rows

def visible_revision_at(revisions: Iterable[DatasetRevision], decision_time: datetime, *, source_record_id: str | None = None) -> DatasetRevision | None:
    """Return the latest revision knowable at ``decision_time`` for one fact."""
    if decision_time.tzinfo is None: raise ValueError("decision_time must be timezone-aware")
    rows=validate_revision_lineage(revisions)
    candidates=[r for r in rows if r.available_at<=decision_time and (source_record_id is None or r.source_record_id==source_record_id) and r.status!="RETRACTED"]
    if not candidates: return None
    return max(candidates,key=lambda r:(r.available_at,r.revision_id))

def visible_revisions_at(revisions: Iterable[DatasetRevision], decision_time: datetime) -> tuple[DatasetRevision, ...]:
    rows=validate_revision_lineage(revisions); grouped={}
    for r in rows:
        if r.available_at<=decision_time and r.status!="RETRACTED":
            prior=grouped.get(r.source_record_id)
            if prior is None or (r.available_at,r.revision_id)>(prior.available_at,prior.revision_id): grouped[r.source_record_id]=r
    return tuple(sorted(grouped.values(),key=lambda r:(r.event_as_of,r.source_record_id)))
