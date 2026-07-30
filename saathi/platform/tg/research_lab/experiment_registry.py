"""M272 — Research Experiment Registry and Reproducibility Engine."""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any

from saathi.platform.tg.research_lab.errors import ResearchLabError
from saathi.platform.tg.research_lab.models import (
    AUTHORITY_VALUES,
    CERTIFIED_EXPERIMENT_REQUIRES_PRE_REGISTRATION,
    ENGINE_VERSION,
    EXPERIMENT_REGISTRY_VERSION,
    ExperimentState,
)
from saathi.platform.tg.research_lab.storage import (
    ResearchLabStore,
    config_checksum,
    deterministic_experiment_id,
    evidence_hash,
    _uid,
)

# Config keys that force a new experiment version when changed
VERSION_SENSITIVE_KEYS = (
    "strategy_ids",
    "strategy_versions",
    "dataset_ids",
    "dataset_versions",
    "feature_ids",
    "feature_versions",
    "instrument_universe",
    "benchmark",
    "training_period",
    "validation_period",
    "test_period",
    "embargo_period",
    "purge_period",
    "parameter_definitions",
    "fixed_parameters",
    "tunable_parameters",
    "parameter_search_space",
    "transaction_cost_model",
    "slippage_model",
    "liquidity_assumptions",
    "position_limits",
    "rebalance_frequency",
    "portfolio_objective",
    "risk_limits",
    "random_seed",
    "regime_definitions",
)


def _git_sha(repo_root: Path | None) -> str:
    if not repo_root:
        return "unknown"
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=str(repo_root), text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        return "unknown"


def _normalize_config(raw: dict[str, Any]) -> dict[str, Any]:
    """Extract and normalize experiment configuration for hashing."""
    keys = [
        "description", "research_question", "hypothesis",
        "strategy_ids", "strategy_versions",
        "dataset_ids", "dataset_versions",
        "feature_ids", "feature_versions",
        "instrument_universe", "universe_construction_date", "benchmark",
        "training_period", "validation_period", "test_period",
        "embargo_period", "purge_period", "regime_definitions",
        "parameter_definitions", "fixed_parameters", "tunable_parameters",
        "parameter_search_space", "trial_count", "random_seed",
        "transaction_cost_model", "slippage_model", "liquidity_assumptions",
        "position_limits", "rebalance_frequency", "portfolio_objective",
        "risk_limits", "limitations",
    ]
    cfg: dict[str, Any] = {}
    for k in keys:
        if k in raw:
            cfg[k] = raw[k]
    # Defaults for required research controls
    cfg.setdefault("strategy_ids", ["tf_dual_ma"])
    cfg.setdefault("strategy_versions", {"tf_dual_ma": "v1"})
    cfg.setdefault("dataset_ids", [])
    cfg.setdefault("dataset_versions", {})
    cfg.setdefault("feature_ids", ["sma_10", "sma_20"])
    cfg.setdefault("feature_versions", {"sma_10": "v1", "sma_20": "v1"})
    cfg.setdefault("instrument_universe", ["DEMO"])
    cfg.setdefault("benchmark", "buy_hold")
    cfg.setdefault("training_period", {"ratio": 0.6})
    cfg.setdefault("validation_period", {"ratio": 0.2})
    cfg.setdefault("test_period", {"ratio": 0.2})
    cfg.setdefault("embargo_period", {"bars": 2})
    cfg.setdefault("purge_period", {"bars": 0})
    cfg.setdefault("fixed_parameters", {"sma_fast": 10, "sma_slow": 20})
    cfg.setdefault("tunable_parameters", {})
    cfg.setdefault("parameter_search_space", {})
    cfg.setdefault("trial_count", 1)
    cfg.setdefault("random_seed", 42)
    cfg.setdefault("transaction_cost_model", {"commission_bps": 5.0})
    cfg.setdefault("slippage_model", {"slippage_bps": 8.0})
    cfg.setdefault("liquidity_assumptions", {"min_adv_usd": 1_000_000})
    cfg.setdefault("position_limits", {"max_weight": 1.0})
    cfg.setdefault("rebalance_frequency", "daily")
    cfg.setdefault("portfolio_objective", "research_robustness")
    cfg.setdefault("risk_limits", {"max_leverage": 1.0, "max_drawdown": 0.25})
    cfg.setdefault("regime_definitions", [])
    cfg.setdefault("limitations", [])
    return cfg


class ExperimentRegistry:
    def __init__(self, store: ResearchLabStore, repo_root: Path | None = None):
        self.store = store
        self.repo_root = repo_root

    def create(
        self,
        name: str,
        *,
        actor: str = "system",
        parent_id: str | None = None,
        parent_version: str | None = None,
        experiment_version: str = "v1",
        **kwargs: Any,
    ) -> dict[str, Any]:
        cfg = _normalize_config(kwargs)
        cs = config_checksum(cfg)
        exp_id = deterministic_experiment_id(name, cfg)

        existing = self.store.fetchone(
            "SELECT * FROM rl_experiments WHERE experiment_id=? AND experiment_version=?",
            (exp_id, experiment_version),
        )
        if existing:
            if existing["config_checksum"] == cs:
                return {
                    "ok": True,
                    "idempotent": True,
                    "experiment_id": exp_id,
                    "experiment_version": experiment_version,
                    "status": existing["status"],
                    "config_checksum": cs,
                    **AUTHORITY_VALUES,
                }
            raise ResearchLabError(
                "CONFIG_VERSION_CONFLICT",
                "Changed configuration requires a new experiment version",
                detail={"experiment_id": exp_id, "existing_checksum": existing["config_checksum"], "new_checksum": cs},
            )

        # Duplicate detection across versions with same checksum
        dup = self.store.fetchone(
            "SELECT experiment_id, experiment_version, status FROM rl_experiments WHERE config_checksum=? LIMIT 1",
            (cs,),
        )
        if dup and (dup["experiment_id"] != exp_id or dup["experiment_version"] != experiment_version):
            # same config already registered under another version path — report as duplicate
            self.store.audit("experiment.duplicate_detected", actor=actor, subject=exp_id, detail={"dup": dup, "checksum": cs})

        meta = {
            "experiment_id": exp_id,
            "experiment_version": experiment_version,
            "experiment_name": name,
            "description": kwargs.get("description", ""),
            "research_question": kwargs.get("research_question", ""),
            "hypothesis": kwargs.get("hypothesis", ""),
            "software_version": ENGINE_VERSION,
            "registry_version": EXPERIMENT_REGISTRY_VERSION,
            "git_sha": _git_sha(self.repo_root),
            "configuration_checksum": cs,
            "operator": actor,
            "creation_timestamp": time.time(),
            "execution_timestamp": None,
            "status": ExperimentState.DRAFT.value,
            "evidence_references": [],
            "parent_id": parent_id,
            "parent_version": parent_version,
            "certified_experiment_requires_pre_registration": CERTIFIED_EXPERIMENT_REQUIRES_PRE_REGISTRATION,
            **cfg,
        }
        self.store.execute(
            "INSERT INTO rl_experiments(experiment_id, experiment_version, name, status, config_json, "
            "config_checksum, parent_id, parent_version, actor, created_at, immutable) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,0)",
            (
                exp_id, experiment_version, name, ExperimentState.DRAFT.value,
                json.dumps(meta, sort_keys=True, default=str), cs,
                parent_id, parent_version, actor, time.time(),
            ),
        )
        self.store.audit("experiment.created", actor=actor, subject=exp_id, detail={"version": experiment_version, "checksum": cs})
        if parent_id:
            self.store.execute(
                "INSERT INTO rl_lineage(id, subject_type, subject_id, parent_id, edge, detail_json, created_at) "
                "VALUES(?,?,?,?,?,?,?)",
                (_uid("lin"), "experiment", f"{exp_id}@{experiment_version}", f"{parent_id}@{parent_version or 'v1'}",
                 "child_of", json.dumps({"checksum": cs}), time.time()),
            )
        return {
            "ok": True,
            "experiment_id": exp_id,
            "experiment_version": experiment_version,
            "status": ExperimentState.DRAFT.value,
            "config_checksum": cs,
            "metadata": meta,
            **AUTHORITY_VALUES,
        }

    def pre_register(self, experiment_id: str, experiment_version: str = "v1", *, actor: str = "system") -> dict[str, Any]:
        row = self._require(experiment_id, experiment_version)
        status = row["status"]
        if status not in (ExperimentState.DRAFT.value, ExperimentState.PRE_REGISTERED.value):
            if status == ExperimentState.PRE_REGISTERED.value:
                return {"ok": True, "idempotent": True, "status": status, "experiment_id": experiment_id, **AUTHORITY_VALUES}
            raise ResearchLabError(
                "PRE_REGISTRATION_INVALID_STATE",
                f"Cannot pre-register from status {status}",
                detail={"status": status},
            )
        meta = json.loads(row["config_json"])
        meta["status"] = ExperimentState.PRE_REGISTERED.value
        meta["pre_registered_at"] = time.time()
        meta["pre_registered_by"] = actor
        self.store.execute(
            "UPDATE rl_experiments SET status=?, config_json=? WHERE experiment_id=? AND experiment_version=?",
            (ExperimentState.PRE_REGISTERED.value, json.dumps(meta, sort_keys=True, default=str),
             experiment_id, experiment_version),
        )
        self.store.audit("experiment.pre_registered", actor=actor, subject=experiment_id,
                         detail={"version": experiment_version})
        return {
            "ok": True,
            "experiment_id": experiment_id,
            "experiment_version": experiment_version,
            "status": ExperimentState.PRE_REGISTERED.value,
            "config_checksum": row["config_checksum"],
            "certified_experiment_requires_pre_registration": True,
            **AUTHORITY_VALUES,
        }

    def mark_ready(self, experiment_id: str, experiment_version: str = "v1", *, actor: str = "system") -> dict[str, Any]:
        row = self._require(experiment_id, experiment_version)
        if row["status"] != ExperimentState.PRE_REGISTERED.value:
            raise ResearchLabError(
                "NOT_PRE_REGISTERED",
                "Experiment must be PRE_REGISTERED before READY",
                detail={"status": row["status"]},
            )
        return self._set_status(experiment_id, experiment_version, ExperimentState.READY, actor)

    def assert_runnable(self, experiment_id: str, experiment_version: str = "v1") -> dict[str, Any]:
        """Gate: certified experiments require pre-registration."""
        row = self._require(experiment_id, experiment_version)
        status = row["status"]
        allowed = {
            ExperimentState.PRE_REGISTERED.value,
            ExperimentState.READY.value,
            ExperimentState.COMPLETED.value,  # replay only
            ExperimentState.FAILED.value,  # replay only
        }
        if CERTIFIED_EXPERIMENT_REQUIRES_PRE_REGISTRATION and status == ExperimentState.DRAFT.value:
            raise ResearchLabError(
                "PRE_REGISTRATION_REQUIRED",
                "No certified experiment may run without pre-registration",
                detail={"experiment_id": experiment_id, "status": status},
            )
        if status not in allowed and status != ExperimentState.RUNNING.value:
            raise ResearchLabError(
                "EXPERIMENT_NOT_RUNNABLE",
                f"Experiment status {status} is not runnable",
                detail={"status": status},
            )
        return row

    def begin_run(self, experiment_id: str, experiment_version: str = "v1", *, actor: str = "system") -> dict[str, Any]:
        row = self.assert_runnable(experiment_id, experiment_version)
        if row["status"] in (ExperimentState.COMPLETED.value, ExperimentState.FAILED.value):
            # replay path — do not mutate immutable result; return for read-only replay
            return {
                "ok": True,
                "replay": True,
                "experiment_id": experiment_id,
                "experiment_version": experiment_version,
                "status": row["status"],
                "immutable": bool(row["immutable"]),
                "result": json.loads(row["result_json"]) if row.get("result_json") else None,
                **AUTHORITY_VALUES,
            }
        if row["immutable"]:
            raise ResearchLabError("IMMUTABLE_EXPERIMENT", "Completed experiment versions are immutable")
        return self._set_status(experiment_id, experiment_version, ExperimentState.RUNNING, actor, execution=True)

    def complete(
        self,
        experiment_id: str,
        experiment_version: str,
        result: dict[str, Any],
        *,
        actor: str = "system",
        failed: bool = False,
    ) -> dict[str, Any]:
        row = self._require(experiment_id, experiment_version)
        if row["immutable"]:
            raise ResearchLabError("IMMUTABLE_EXPERIMENT", "Cannot mutate completed experiment version")
        status = ExperimentState.FAILED if failed else ExperimentState.COMPLETED
        eh = evidence_hash(result)
        meta = json.loads(row["config_json"])
        meta["status"] = status.value
        meta["execution_timestamp"] = time.time()
        meta["evidence_references"] = list(meta.get("evidence_references") or []) + [eh]
        self.store.execute(
            "UPDATE rl_experiments SET status=?, config_json=?, result_json=?, evidence_hash=?, "
            "execution_at=?, immutable=1 WHERE experiment_id=? AND experiment_version=?",
            (
                status.value, json.dumps(meta, sort_keys=True, default=str),
                json.dumps(result, sort_keys=True, default=str), eh, time.time(),
                experiment_id, experiment_version,
            ),
        )
        self.store.audit(
            f"experiment.{status.value.lower()}",
            actor=actor,
            subject=experiment_id,
            detail={"version": experiment_version, "evidence_hash": eh},
        )
        return {
            "ok": True,
            "experiment_id": experiment_id,
            "experiment_version": experiment_version,
            "status": status.value,
            "evidence_hash": eh,
            "immutable": True,
            **AUTHORITY_VALUES,
        }

    def invalidate(self, experiment_id: str, experiment_version: str, reason: str, *, actor: str = "system") -> dict[str, Any]:
        row = self._require(experiment_id, experiment_version)
        meta = json.loads(row["config_json"])
        meta["invalidation_reason"] = reason
        meta["status"] = ExperimentState.INVALIDATED.value
        self.store.execute(
            "UPDATE rl_experiments SET status=?, config_json=? WHERE experiment_id=? AND experiment_version=?",
            (ExperimentState.INVALIDATED.value, json.dumps(meta, sort_keys=True, default=str),
             experiment_id, experiment_version),
        )
        self.store.audit("experiment.invalidated", actor=actor, subject=experiment_id, detail={"reason": reason})
        return {"ok": True, "status": ExperimentState.INVALIDATED.value, "reason": reason, **AUTHORITY_VALUES}

    def supersede(
        self,
        experiment_id: str,
        old_version: str,
        new_version: str,
        *,
        actor: str = "system",
        **kwargs: Any,
    ) -> dict[str, Any]:
        old = self._require(experiment_id, old_version)
        meta = json.loads(old["config_json"])
        # merge overrides
        for k, v in kwargs.items():
            meta[k] = v
        name = old["name"]
        created = self.create(
            name,
            actor=actor,
            parent_id=experiment_id,
            parent_version=old_version,
            experiment_version=new_version,
            **{k: meta[k] for k in meta if k not in (
                "experiment_id", "experiment_version", "status", "creation_timestamp",
                "execution_timestamp", "software_version", "registry_version", "git_sha",
                "configuration_checksum", "operator", "evidence_references",
                "parent_id", "parent_version", "certified_experiment_requires_pre_registration",
            )},
        )
        self.store.execute(
            "UPDATE rl_experiments SET status=? WHERE experiment_id=? AND experiment_version=?",
            (ExperimentState.SUPERSEDED.value, experiment_id, old_version),
        )
        self.store.audit("experiment.superseded", actor=actor, subject=experiment_id,
                         detail={"old": old_version, "new": new_version})
        return {
            "ok": True,
            "superseded": f"{experiment_id}@{old_version}",
            "new": created,
            **AUTHORITY_VALUES,
        }

    def get(self, experiment_id: str, experiment_version: str = "v1") -> dict[str, Any]:
        row = self.store.fetchone(
            "SELECT * FROM rl_experiments WHERE experiment_id=? AND experiment_version=?",
            (experiment_id, experiment_version),
        )
        if not row:
            return {"ok": False, "code": "EXPERIMENT_NOT_FOUND", "experiment_id": experiment_id, **AUTHORITY_VALUES}
        return self._public(row)

    def list(self, status: str | None = None, limit: int = 100) -> dict[str, Any]:
        if status:
            rows = self.store.fetchall(
                "SELECT * FROM rl_experiments WHERE status=? ORDER BY created_at DESC LIMIT ?",
                (status, limit),
            )
        else:
            rows = self.store.fetchall(
                "SELECT * FROM rl_experiments ORDER BY created_at DESC LIMIT ?",
                (limit,),
            )
        return {
            "ok": True,
            "count": len(rows),
            "experiments": [self._public(r) for r in rows],
            **AUTHORITY_VALUES,
        }

    def lineage(self, experiment_id: str) -> dict[str, Any]:
        rows = self.store.fetchall(
            "SELECT * FROM rl_lineage WHERE subject_id LIKE ? OR parent_id LIKE ? ORDER BY created_at",
            (f"{experiment_id}%", f"{experiment_id}%"),
        )
        versions = self.store.fetchall(
            "SELECT experiment_id, experiment_version, status, config_checksum, parent_id, parent_version "
            "FROM rl_experiments WHERE experiment_id=? OR parent_id=? ORDER BY created_at",
            (experiment_id, experiment_id),
        )
        return {
            "ok": True,
            "experiment_id": experiment_id,
            "versions": versions,
            "edges": rows,
            **AUTHORITY_VALUES,
        }

    def replay(self, experiment_id: str, experiment_version: str = "v1") -> dict[str, Any]:
        """Reproducible read-only replay of a completed/failed experiment."""
        row = self._require(experiment_id, experiment_version)
        result = json.loads(row["result_json"]) if row.get("result_json") else None
        meta = json.loads(row["config_json"])
        return {
            "ok": True,
            "replay": True,
            "experiment_id": experiment_id,
            "experiment_version": experiment_version,
            "status": row["status"],
            "config_checksum": row["config_checksum"],
            "immutable": bool(row["immutable"]),
            "metadata": meta,
            "result": result,
            "evidence_hash": row.get("evidence_hash"),
            "reproducible": result is not None and bool(row["immutable"]),
            **AUTHORITY_VALUES,
        }

    def export_registry(self) -> dict[str, Any]:
        rows = self.store.fetchall("SELECT * FROM rl_experiments ORDER BY created_at")
        return {
            "schema": "M272_EXPERIMENT_REGISTRY",
            "registry_version": EXPERIMENT_REGISTRY_VERSION,
            "count": len(rows),
            "experiments": [self._public(r) for r in rows],
            "invariant": {"certified_experiment_requires_pre_registration": True},
            **AUTHORITY_VALUES,
        }

    def _require(self, experiment_id: str, experiment_version: str) -> dict[str, Any]:
        row = self.store.fetchone(
            "SELECT * FROM rl_experiments WHERE experiment_id=? AND experiment_version=?",
            (experiment_id, experiment_version),
        )
        if not row:
            raise ResearchLabError("EXPERIMENT_NOT_FOUND", f"{experiment_id}@{experiment_version} not found")
        return row

    def _set_status(
        self,
        experiment_id: str,
        experiment_version: str,
        status: ExperimentState,
        actor: str,
        execution: bool = False,
    ) -> dict[str, Any]:
        row = self._require(experiment_id, experiment_version)
        meta = json.loads(row["config_json"])
        meta["status"] = status.value
        exec_at = time.time() if execution else row.get("execution_at")
        if execution:
            meta["execution_timestamp"] = exec_at
        self.store.execute(
            "UPDATE rl_experiments SET status=?, config_json=?, execution_at=? "
            "WHERE experiment_id=? AND experiment_version=?",
            (status.value, json.dumps(meta, sort_keys=True, default=str), exec_at,
             experiment_id, experiment_version),
        )
        self.store.audit(f"experiment.status.{status.value}", actor=actor, subject=experiment_id,
                         detail={"version": experiment_version})
        return {
            "ok": True,
            "experiment_id": experiment_id,
            "experiment_version": experiment_version,
            "status": status.value,
            **AUTHORITY_VALUES,
        }

    def _public(self, row: dict[str, Any]) -> dict[str, Any]:
        meta = json.loads(row["config_json"]) if row.get("config_json") else {}
        out = {
            "ok": True,
            "experiment_id": row["experiment_id"],
            "experiment_version": row["experiment_version"],
            "name": row["name"],
            "status": row["status"],
            "config_checksum": row["config_checksum"],
            "parent_id": row.get("parent_id"),
            "parent_version": row.get("parent_version"),
            "actor": row.get("actor"),
            "created_at": row.get("created_at"),
            "execution_at": row.get("execution_at"),
            "immutable": bool(row.get("immutable")),
            "evidence_hash": row.get("evidence_hash"),
            "metadata": meta,
        }
        if row.get("result_json"):
            out["has_result"] = True
        return out
