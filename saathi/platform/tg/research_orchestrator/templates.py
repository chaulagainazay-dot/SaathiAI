"""Experiment templates and promotion."""
from __future__ import annotations

import json
import time
from typing import Any

from saathi.platform.tg.research_orchestrator.models import AUTHORITY_VALUES, PromotionState
from saathi.platform.tg.research_orchestrator.storage import OrchestratorStore, config_checksum, _uid


DEFAULT_TEMPLATES = [
    {
        "template_id": "tpl_strategy_compare_v1",
        "name": "strategy_compare_baseline",
        "version": "v1",
        "body": {
            "kind": "strategy_compare",
            "strategy_ids": ["tf_dual_ma", "mom_rs_equity", "mr_bollinger_reversion"],
            "seed": 42,
            "trial_count": 1,
        },
    },
    {
        "template_id": "tpl_lab_bootstrap_v1",
        "name": "research_lab_bootstrap",
        "version": "v1",
        "body": {"kind": "research_lab_bootstrap", "seed": 42},
    },
    {
        "template_id": "tpl_noop_v1",
        "name": "noop_heartbeat",
        "version": "v1",
        "body": {"kind": "noop", "seed": 1},
    },
]


class TemplateRegistry:
    def __init__(self, store: OrchestratorStore):
        self.store = store
        self._bootstrap()

    def _bootstrap(self) -> None:
        for t in DEFAULT_TEMPLATES:
            existing = self.store.fetchone(
                "SELECT template_id FROM orch_templates WHERE template_id=?",
                (t["template_id"],),
            )
            if existing:
                continue
            cs = config_checksum(t["body"])
            self.store.execute(
                "INSERT INTO orch_templates(template_id, name, version, body_json, checksum, promoted, created_at) "
                "VALUES(?,?,?,?,?,?,?)",
                (t["template_id"], t["name"], t["version"],
                 json.dumps(t["body"], sort_keys=True), cs, 0, time.time()),
            )

    def list(self) -> dict[str, Any]:
        rows = self.store.fetchall("SELECT * FROM orch_templates ORDER BY name")
        out = []
        for r in rows:
            out.append({
                "template_id": r["template_id"],
                "name": r["name"],
                "version": r["version"],
                "body": json.loads(r["body_json"]),
                "checksum": r["checksum"],
                "promoted": bool(r["promoted"]),
            })
        return {"ok": True, "count": len(out), "templates": out, **AUTHORITY_VALUES}

    def get(self, template_id: str) -> dict[str, Any]:
        r = self.store.fetchone("SELECT * FROM orch_templates WHERE template_id=?", (template_id,))
        if not r:
            return {"ok": False, "code": "TEMPLATE_NOT_FOUND", **AUTHORITY_VALUES}
        return {
            "ok": True,
            "template_id": r["template_id"],
            "name": r["name"],
            "version": r["version"],
            "body": json.loads(r["body_json"]),
            "checksum": r["checksum"],
            "promoted": bool(r["promoted"]),
            **AUTHORITY_VALUES,
        }

    def register(self, name: str, body: dict, *, version: str = "v1") -> dict[str, Any]:
        cs = config_checksum(body)
        tid = f"tpl_{config_checksum({'name': name, 'version': version, 'body': body})[:12]}"
        existing = self.store.fetchone("SELECT template_id FROM orch_templates WHERE template_id=?", (tid,))
        if existing:
            return {"ok": True, "idempotent": True, "template_id": tid, "checksum": cs, **AUTHORITY_VALUES}
        self.store.execute(
            "INSERT INTO orch_templates(template_id, name, version, body_json, checksum, promoted, created_at) "
            "VALUES(?,?,?,?,?,?,?)",
            (tid, name, version, json.dumps(body, sort_keys=True), cs, 0, time.time()),
        )
        return {"ok": True, "template_id": tid, "checksum": cs, **AUTHORITY_VALUES}

    def promote(self, template_id: str, *, actor: str = "system") -> dict[str, Any]:
        r = self.get(template_id)
        if not r.get("ok"):
            return r
        self.store.execute(
            "UPDATE orch_templates SET promoted=1 WHERE template_id=?",
            (template_id,),
        )
        pid = _uid("promo")
        self.store.execute(
            "INSERT INTO orch_promotions(id, subject_type, subject_id, state, detail_json, created_at) "
            "VALUES(?,?,?,?,?,?)",
            (pid, "template", template_id, PromotionState.PROMOTED_TEMPLATE.value,
             json.dumps({"actor": actor}, sort_keys=True), time.time()),
        )
        return {
            "ok": True,
            "template_id": template_id,
            "state": PromotionState.PROMOTED_TEMPLATE.value,
            "promotion_id": pid,
            **AUTHORITY_VALUES,
        }
