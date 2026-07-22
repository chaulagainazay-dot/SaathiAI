"""M17.14 trusted internal event triggers — narrow, allowlisted, fail-closed.

A tiny bridge from a SMALL set of TRUSTED internal event types to mission creation.
It is NOT a public webhook, a general message queue, or an arbitrary-payload
deserializer. Only explicitly registered event types (`TRUSTED_EVENT_TYPES`) are
accepted; a trigger subscription statically BINDS one template + owner + static
params, and may map a few ALLOWLISTED scalar payload fields into template
parameters. A payload can NEVER choose the template, change the owner, alter risk,
or grant approval. A repeated source event is deduplicated by a durable receipt, so
one event yields at most one mission. Every accepted event still runs through the
existing MissionEngine (→ pipeline → governed harness execution); this layer only
decides *whether* to create a normal mission, never *how* it executes.
"""
from __future__ import annotations

import hashlib
import re
import uuid
from typing import Optional

from saathi.application_harness import run_ledger as L
from saathi.application_harness.mission import MissionEngine, validate_params

# a payload can never influence these — they are owner/authority/execution controls
_FORBIDDEN_PARAM = {"owner", "owner_id", "template", "mission_template_id", "risk",
                    "risk_level", "approval", "approval_required", "approved",
                    "approved_by"}
# safe non-parameter payload keys tolerated on a trusted internal event
_META_KEYS = {"source_event_id", "event_type", "ts", "occurred_at", "at",
              "owner", "run_id", "pipeline_id", "mission_id", "occurrence_id",
              "schedule_id", "alert_id", "delivery_id", "severity", "state",
              "failure_code", "attempt", "job", "step_index", "status"}
_SECRET_KEY = re.compile(r"(?i)(secret|password|passwd|api[_-]?key|token|"
                         r"authorization|bearer|private[_-]?key|credential)")


def _mission_id_for(dedup_key: str) -> str:
    return "ms_evt_" + hashlib.sha256(dedup_key.encode()).hexdigest()[:20]


class MissionEventTriggerService:
    """Ingests a trusted internal event and, per matching trigger, creates exactly
    one governed mission (idempotently). Deterministic; injectable clock; no sleeps."""

    def __init__(self, *, ledger: L.RunLedger | None = None,
                 engine: MissionEngine | None = None):
        self.ledger = ledger or L.default_ledger()
        self.engine = engine or MissionEngine(ledger=self.ledger)

    # ── registration (delegates to the ledger; owner mandatory) ────────────
    def register(self, *, owner, event_type, mission_template_id, params=None,
                 payload_map=None, cooldown_sec=0.0, description="",
                 trigger_id="", now=None) -> dict:
        if not owner:
            return {"ok": False, "reason": "empty_owner"}
        if event_type not in L.TRUSTED_EVENT_TYPES:
            return {"ok": False, "reason": "untrusted_event_type"}
        tmpl = self.engine.templates.get(mission_template_id)
        if tmpl is None:
            return {"ok": False, "reason": "unknown_template"}
        payload_map = payload_map or {}
        # a mapping target may never be a forbidden authority/execution param
        for pname in payload_map:
            if pname in _FORBIDDEN_PARAM or (isinstance(pname, str) and _SECRET_KEY.search(pname)):
                return {"ok": False, "reason": f"forbidden_mapping:{pname}"}
        # static params must validate against the bound template now
        pv = validate_params(tmpl.parameters, params or {})
        if not pv["ok"]:
            return {"ok": False, "reason": "invalid_parameters", "errors": pv["errors"]}
        tid = trigger_id or ("trg_" + uuid.uuid4().hex[:16])
        created = self.ledger.create_trigger(
            tid, owner=owner, event_type=event_type,
            mission_template_id=mission_template_id, params=pv["values"],
            payload_map=payload_map, cooldown_sec=cooldown_sec,
            description=description, now=now)
        if not created.get("created"):
            return {"ok": False, "trigger_id": tid, "reason": created.get("reason")}
        return {"ok": True, "trigger_id": tid}

    # ── ingestion (the trust boundary) ─────────────────────────────────────
    def ingest_event(self, *, event_type, source_event_id, payload=None,
                     now=None) -> dict:
        now = now if now is not None else L._now()
        payload = payload or {}
        # 1. only allowlisted event types are trusted
        if event_type not in L.TRUSTED_EVENT_TYPES:
            return {"ok": False, "reason": "untrusted_event_type", "created": []}
        if not isinstance(payload, dict):
            return {"ok": False, "reason": "bad_payload", "created": []}
        triggers = self.ledger.triggers_for_event(event_type, now=now)
        if not triggers:
            return {"ok": True, "created": [], "matched": 0}
        created, rejected = [], []
        for trg in triggers:
            out = self._apply(trg, event_type, str(source_event_id), payload, now)
            if out.get("created_mission"):
                created.append(out["mission_id"])
            elif out.get("rejected"):
                rejected.append({"trigger_id": trg["trigger_id"],
                                 "category": out["rejected"]})
        return {"ok": True, "created": created, "rejected": rejected,
                "matched": len(triggers)}

    def _apply(self, trg, event_type, source_event_id, payload, now) -> dict:
        tid, owner = trg["trigger_id"], trg["owner"]
        dedup_key = f"{tid}:{source_event_id}"
        rid = "rcp_" + hashlib.sha256(dedup_key.encode()).hexdigest()[:20]
        # 2. durable dedup — a repeated source event is a no-op (no duplicate mission)
        rc = self.ledger.create_receipt(rid, trigger_id=tid, owner=owner,
                                        event_type=event_type,
                                        source_event_id=source_event_id,
                                        dedup_key=dedup_key, state="processing", now=now)
        if not rc.get("created"):
            return {"deduplicated": True}
        # 3. build params: static params + allowlisted scalar payload fields ONLY
        payload_map = trg["payload_map"] or {}
        allowed_fields = set(payload_map.values()) | _META_KEYS
        for k in payload:                          # reject unexpected / secret-shaped keys
            if _SECRET_KEY.search(str(k)):
                return self._reject(rid, "secret_shaped_payload")
            if k not in allowed_fields:
                return self._reject(rid, "unexpected_payload_field")
        params = dict(trg["params"] or {})
        for pname, field in payload_map.items():
            if pname in _FORBIDDEN_PARAM:          # defence in depth
                return self._reject(rid, "forbidden_param_override")
            if field not in payload:
                return self._reject(rid, "missing_payload_field")
            val = payload[field]
            if isinstance(val, (dict, list)):      # no nested/executable structures
                return self._reject(rid, "non_scalar_payload")
            params[pname] = val
        # 4. validate against the BOUND template (payload can't change the template)
        tmpl = self.engine.templates.get(trg["mission_template_id"])
        if tmpl is None:
            return self._reject(rid, "invalid_template")
        pv = validate_params(tmpl.parameters, params)
        if not pv["ok"]:
            return self._reject(rid, "invalid_parameters")
        # 5. create ONE mission (deterministic id → dedup) under the TRIGGER's owner
        mid = _mission_id_for(dedup_key)
        res = self.engine.create(trg["mission_template_id"], owner=owner,
                                 params=pv["values"], mission_id=mid,
                                 correlation_id=tid)
        if not res.get("ok") and res.get("reason") != "duplicate_mission_id":
            return self._reject(rid, res.get("reason", "mission_create_failed"))
        # 6. drive it through the existing MissionEngine (approval still honoured)
        self.engine.launch(mid, owner=owner, session_id=f"trigger:{rid}")
        self.ledger.update_receipt(rid, state="accepted", mission_id=mid)
        return {"created_mission": True, "mission_id": mid}

    def _reject(self, receipt_id, category) -> dict:
        self.ledger.update_receipt(receipt_id, state="rejected",
                                   rejection_category=category)
        return {"rejected": category}


_default: MissionEventTriggerService | None = None


def default_trigger_service() -> MissionEventTriggerService:
    global _default
    if _default is None:
        _default = MissionEventTriggerService()
    return _default
