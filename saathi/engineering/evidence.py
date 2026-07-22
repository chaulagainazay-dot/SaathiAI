"""M20.5 — Integrity evidence records bound to engineering sessions.

Persists snapshot digests and comparison results as durable evidence files
and ledger events. Never stores secrets or full file contents.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

from saathi.engineering.integrity import (
    IntegrityDiff,
    RepoSnapshot,
    capture_snapshot,
    compare_snapshots,
)
from saathi.engineering.session_ledger import SessionLedger


@dataclass
class IntegrityEvidence:
    evidence_id: str
    session_id: str
    kind: str  # baseline | check | violation
    snapshot: dict[str, Any] = field(default_factory=dict)
    diff: dict[str, Any] = field(default_factory=dict)
    ok: bool = True
    created_at: float = field(default_factory=time.time)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class IntegrityEvidenceStore:
    def __init__(self, root: Path | str, ledger: Optional[SessionLedger] = None):
        self.root = Path(root)
        self.dir = self.root / "integrity_evidence"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.ledger = ledger or SessionLedger(self.root)

    def _path(self, evidence_id: str) -> Path:
        safe = "".join(c for c in evidence_id if c.isalnum() or c in ("_", "-"))[:80]
        return self.dir / f"{safe}.json"

    def record_baseline(
        self,
        session_id: str,
        root: Path | str,
        *,
        task_id: str = "",
        item_id: str = "",
    ) -> IntegrityEvidence:
        snap = capture_snapshot(root)
        eid = f"ev_{session_id[:12]}_{int(time.time())}_base"
        ev = IntegrityEvidence(
            evidence_id=eid,
            session_id=session_id,
            kind="baseline",
            snapshot=snap.to_dict(),
            ok=True,
            notes=["readonly_baseline"],
        )
        self._persist(ev)
        self.ledger.append(
            "integrity_baseline",
            session_id=session_id,
            task_id=task_id,
            item_id=item_id,
            payload={
                "evidence_id": eid,
                "head": snap.head[:12] if snap.head else "",
                "branch": snap.branch,
                "tracked_digest": snap.tracked_digest[:24],
            },
            evidence_ref=eid,
        )
        return ev

    def record_check(
        self,
        session_id: str,
        root: Path | str,
        baseline: RepoSnapshot | dict[str, Any],
        *,
        task_id: str = "",
        item_id: str = "",
        quarantine_on_violation: bool = True,
    ) -> IntegrityEvidence:
        if isinstance(baseline, dict):
            base = RepoSnapshot.from_dict(baseline)
        else:
            base = baseline
        after = capture_snapshot(root)
        diff = compare_snapshots(base, after)
        kind = "check" if diff.ok else "violation"
        eid = f"ev_{session_id[:12]}_{int(time.time())}_{kind[:4]}"
        ev = IntegrityEvidence(
            evidence_id=eid,
            session_id=session_id,
            kind=kind,
            snapshot=after.to_dict(),
            diff=diff.to_dict(),
            ok=diff.ok,
            notes=[] if diff.ok else list(diff.mutations),
        )
        self._persist(ev)
        self.ledger.append(
            "integrity_check" if diff.ok else "integrity_violation",
            session_id=session_id,
            task_id=task_id,
            item_id=item_id,
            payload={
                "evidence_id": eid,
                "ok": diff.ok,
                "mutations": list(diff.mutations)[:20],
            },
            evidence_ref=eid,
        )
        if not diff.ok and quarantine_on_violation:
            self.ledger.append(
                "quarantine",
                session_id=session_id,
                task_id=task_id,
                item_id=item_id,
                payload={"reason": "integrity_violation", "evidence_id": eid},
                evidence_ref=eid,
            )
        return ev

    def _persist(self, ev: IntegrityEvidence) -> None:
        path = self._path(ev.evidence_id)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(ev.to_dict(), indent=2, default=str), encoding="utf-8")
        os.replace(tmp, path)

    def load(self, evidence_id: str) -> Optional[IntegrityEvidence]:
        path = self._path(evidence_id)
        if not path.exists():
            return None
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
            return IntegrityEvidence(
                evidence_id=str(d.get("evidence_id") or evidence_id),
                session_id=str(d.get("session_id") or ""),
                kind=str(d.get("kind") or ""),
                snapshot=dict(d.get("snapshot") or {}),
                diff=dict(d.get("diff") or {}),
                ok=bool(d.get("ok", True)),
                created_at=float(d.get("created_at") or 0),
                notes=list(d.get("notes") or []),
            )
        except Exception:
            return None

    def list_for_session(self, session_id: str) -> list[IntegrityEvidence]:
        out = []
        for p in sorted(self.dir.glob("*.json")):
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            if d.get("session_id") == session_id:
                out.append(self.load(str(d.get("evidence_id") or p.stem)))
        return [e for e in out if e is not None]
