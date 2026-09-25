"""Point-in-time NEPSE historical bars and deterministic replay."""
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
import hashlib, json

class CalendarStatus(str, Enum):
    CONFIRMED_SESSION="CONFIRMED_SESSION"; CONFIRMED_CLOSED_CONFLICT="CONFIRMED_CLOSED_CONFLICT"; POTENTIAL_SESSION_HOLIDAY_UNKNOWN="POTENTIAL_SESSION_HOLIDAY_UNKNOWN"; INVALID_WEEKEND="INVALID_WEEKEND"
class RevisionStatus(str, Enum): ORIGINAL="ORIGINAL"; CORRECTED="CORRECTED"; SUPERSEDED="SUPERSEDED"

@dataclass(frozen=True)
class DatasetManifest:
    dataset_id: str; dataset_version: str; source: str; source_reference: str = ""; checksum: str = ""; calendar_version: str = "NEPSE"; schema_version: str = "MD-1"; availability_precision: str = "unknown"; certification_status: str = "UNVERIFIED"

@dataclass
class HistoricalBar:
    instrument_id: str; session_date: date; as_of: datetime; available_at: datetime; received_at: datetime; open: Decimal; high: Decimal; low: Decimal; close: Decimal; volume: Decimal | None; source: str; source_record_id: str; quality_status: str = "VALID"; calendar_status: CalendarStatus = CalendarStatus.POTENTIAL_SESSION_HOLIDAY_UNKNOWN; revision_status: RevisionStatus = RevisionStatus.ORIGINAL; revision_id: str = ""; adjustment_status: str = "UNKNOWN"

    def __post_init__(self):
        if not self.instrument_id.startswith("NEPSE:"): raise ValueError("invalid NEPSE instrument")
        if any(x < 0 for x in (self.open,self.high,self.low,self.close)): raise ValueError("negative price")
        if self.high < max(self.open,self.close,self.low) or self.low > min(self.open,self.close,self.high): raise ValueError("invalid OHLC")
        if self.volume is not None and self.volume < 0: raise ValueError("negative volume")
        if self.as_of.tzinfo is None or self.available_at.tzinfo is None or self.received_at.tzinfo is None: raise ValueError("timestamps must be timezone-aware")
        if self.available_at > self.received_at: raise ValueError("availability after receipt")

@dataclass(frozen=True)
class ReplayClock:
    now: datetime
    def __post_init__(self):
        if self.now.tzinfo is None: raise ValueError("replay clock must be timezone-aware")

class PointInTimeDataset:
    def __init__(self, manifest: DatasetManifest, bars: list[HistoricalBar]):
        self.manifest=manifest; self.bars=tuple(bars); self._validate()
    def _validate(self):
        keys=set()
        for b in self.bars:
            key=(b.instrument_id,b.session_date,b.revision_id or b.source_record_id)
            if key in keys: raise ValueError("duplicate observation")
            keys.add(key)
            if b.session_date.weekday() == 4: b.calendar_status=CalendarStatus.INVALID_WEEKEND; b.quality_status="CALENDAR_CONFLICT"; raise ValueError("NEPSE Friday bar")
    def visible_at(self, replay_time: datetime) -> list[HistoricalBar]:
        return [b for b in self.bars if b.available_at <= replay_time]
    def replay(self, clock: ReplayClock, instruments: set[str] | None = None) -> tuple[HistoricalBar,...]:
        rows=[b for b in self.visible_at(clock.now) if instruments is None or b.instrument_id in instruments]
        return tuple(sorted(rows,key=lambda b:(b.available_at,b.as_of,b.instrument_id,b.source_record_id)))
    def checksum(self) -> str:
        payload=[(b.instrument_id,b.session_date.isoformat(),str(b.close),b.source_record_id,b.revision_status.value) for b in self.bars]
        return hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
