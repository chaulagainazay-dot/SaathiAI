"""Experiment and research artefact lineage tracking."""
from __future__ import annotations

import json
import time
from typing import Any

from saathi.platform.tg.research_lab.models import AUTHORITY_VALUES
from saathi.platform.tg.research_lab.storage import ResearchLabStore, _uid


class LineageTracker:
    def __init__(self, store: ResearchLabStore):
        self.store = store

    def record(
        self,
        subject_type: str,
        subject_id: str,
        edge: str,
        *,
        parent_id: str | None = None,
        detail: dict | None = None,
    ) -> dict[str, Any]:
        lid = _uid("lin")
        self.store.execute(
            "INSERT INTO rl_lineage(id, subject_type, subject_id, parent_id, edge, detail_json, created_at) "
            "VALUES(?,?,?,?,?,?,?)",
            (lid, subject_type, subject_id, parent_id, edge,
             json.dumps(detail or {}, sort_keys=True, default=str), time.time()),
        )
        return {"ok": True, "lineage_id": lid, "subject_id": subject_id, "edge": edge, **AUTHORITY_VALUES}

    def for_subject(self, subject_id: str) -> dict[str, Any]:
        rows = self.store.fetchall(
            "SELECT * FROM rl_lineage WHERE subject_id=? OR parent_id=? ORDER BY created_at",
            (subject_id, subject_id),
        )
        return {"ok": True, "subject_id": subject_id, "edges": rows, "count": len(rows), **AUTHORITY_VALUES}
