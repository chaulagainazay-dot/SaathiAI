"""M214 — Immutable evidence bundles and campaign certification."""
from __future__ import annotations

import time
import uuid
from typing import Any

from saathi.platform.tg.paper_activation.durable.events import fingerprint, make_event
from saathi.platform.tg.paper_activation.durable.service import DurableGovError
from saathi.platform.tg.paper_activation.ops.models import CampaignCertOutcome, StrategyClassification


def _id(prefix: str = "evb") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:14]}"


class EvidenceService:
    def __init__(
        self,
        gov: Any,
        *,
        graduation: Any | None = None,
        monitor: Any | None = None,
        analytics: Any | None = None,
        simulation: Any | None = None,
        campaign_mgr: Any | None = None,
    ):
        self.gov = gov
        self.store = gov.store
        self.graduation = graduation
        self.monitor = monitor
        self.analytics = analytics
        self.simulation = simulation
        self.campaign_mgr = campaign_mgr

    def build_campaign_bundle(self, campaign_id: str) -> dict[str, Any]:
        c = self.store.get_campaign(campaign_id)
        if not c:
            raise DurableGovError("NOT_FOUND", "campaign not found")
        ext = self.campaign_mgr.get_ext(campaign_id) if self.campaign_mgr else {}
        health = self.monitor.campaign_health(campaign_id) if self.monitor else {}
        system_health = self.monitor.assess(persist=False) if self.monitor else {}
        grad = None
        if self.graduation:
            grad = self.graduation.evaluate(campaign_id, actor="system")
        analytics = {}
        journal = {}
        recon = {}
        if c.get("portfolio_id"):
            try:
                analytics = self.gov.analytics(c["portfolio_id"])
            except Exception as e:
                analytics = {"error": str(e)}
            try:
                journal = self.gov.list_journal(c["portfolio_id"])
            except Exception:
                journal = {}
            try:
                recon = self.gov.reconcile(c["portfolio_id"], auto_halt=False)
            except Exception as e:
                recon = {"error": str(e)}
        recovery = {"readiness": system_health.get("components", {}).get("recovery_readiness", {})}
        bundle = {
            "schema": "m214.campaign_evidence.v1",
            "campaign": {**c, **ext},
            "strategy": {"slug": c.get("strategy_slug"), "version": c.get("strategy_version")},
            "risk": {
                "portfolio_halt": None,
                "kill_switch": self.store.kill_switch_active(),
            },
            "journal": journal,
            "reconciliation": recon,
            "analytics": analytics,
            "health": health,
            "system_health": system_health,
            "recovery": recovery,
            "graduation": grad,
            "browser": {"note": "browser evidence attached separately when certified"},
            "paper_only": True,
            "live_authorized": False,
            "created_at": time.time(),
        }
        if c.get("portfolio_id"):
            p = self.store.get_portfolio(c["portfolio_id"])
            if p:
                bundle["risk"]["portfolio_halt"] = p.get("halt_reason")
        fp = fingerprint(bundle)
        bundle["fingerprint"] = fp
        return bundle

    def certify_campaign(
        self,
        campaign_id: str,
        *,
        actor: str = "operator:system",
        browser_evidence: dict | None = None,
    ) -> dict[str, Any]:
        bundle = self.build_campaign_bundle(campaign_id)
        if browser_evidence:
            bundle["browser"] = {**bundle.get("browser", {}), **browser_evidence}
            bundle["fingerprint"] = fingerprint(bundle)

        grad = bundle.get("graduation") or {}
        classification = grad.get("classification", StrategyClassification.MORE_EVIDENCE_REQUIRED.value)
        gates = grad.get("gates") or {}
        recon = bundle.get("reconciliation", {}).get("reconciliation", {})
        fail_closed = recon.get("fail_closed", False)

        if classification == StrategyClassification.REJECTED.value or fail_closed:
            outcome = CampaignCertOutcome.FAILED_VALIDATION.value
            if classification == StrategyClassification.REJECTED.value:
                outcome = CampaignCertOutcome.REJECTED.value
        elif classification == StrategyClassification.PAPER_GRADUATE.value and all(
            gates.get(k) for k in ("min_duration", "min_trades", "recon_ok", "drawdown_ok")
        ):
            outcome = CampaignCertOutcome.VALIDATED.value
        elif classification in (
            StrategyClassification.PAPER_VALIDATED.value,
            StrategyClassification.PAPER_GRADUATE.value,
        ):
            outcome = CampaignCertOutcome.VALIDATED_WITH_LIMITATIONS.value
        elif classification in (
            StrategyClassification.MORE_EVIDENCE_REQUIRED.value,
            StrategyClassification.PAPER_ACTIVE.value,
            StrategyClassification.RESEARCH_ONLY.value,
        ):
            outcome = CampaignCertOutcome.MORE_EVIDENCE_REQUIRED.value
        else:
            outcome = CampaignCertOutcome.FAILED_VALIDATION.value

        cert = {
            "id": _id("cert"),
            "campaign_id": campaign_id,
            "kind": "campaign_certification",
            "outcome": outcome,
            "bundle": bundle,
            "classification": classification,
            "live_authorized": False,
            "auto_promoted_to_live": False,
            "immutable": True,
            "actor": actor,
            "created_at": time.time(),
            "paper_only": True,
            "disclaimer": (
                "THE SYSTEM REMAINS PAPER ONLY. "
                "LIVE TRADING IS NOT AUTHORIZED. "
                "NO STRATEGY IS AUTOMATICALLY PROMOTED TO LIVE EXECUTION."
            ),
        }
        cert["fingerprint"] = fingerprint({
            "id": cert["id"],
            "campaign_id": campaign_id,
            "outcome": outcome,
            "bundle_fp": bundle.get("fingerprint"),
        })
        self._persist(cert)
        # stamp campaign evidence
        c = self.store.get_campaign(campaign_id)
        if c:
            c["evidence"] = {
                **(c.get("evidence") or {}),
                "certification_id": cert["id"],
                "outcome": outcome,
                "fingerprint": cert["fingerprint"],
                "not_live_eligible": True,
                "live_authorized": False,
            }
            self.store.save_campaign(c)
        self.store.append_event(make_event(
            "snapshot.created",
            aggregate_type="certification",
            aggregate_id=cert["id"],
            payload={
                "campaign_id": campaign_id,
                "outcome": outcome,
                "live_authorized": False,
            },
            actor_type="operator",
            actor_id=actor,
            idempotency_key=f"cert:{campaign_id}:{cert['fingerprint'][:16]}",
        ))
        return cert

    def _persist(self, cert: dict[str, Any]) -> None:
        import json

        def _do(store):
            store.execute(
                """INSERT INTO pg_ops_evidence(id, campaign_id, kind, outcome, bundle_json, fingerprint, immutable, created_at)
                VALUES (?,?,?,?,?,?,1,?)""",
                (
                    cert["id"], cert["campaign_id"], cert["kind"], cert["outcome"],
                    json.dumps(cert["bundle"], sort_keys=True, default=str),
                    cert["fingerprint"], cert["created_at"],
                ),
            )

        self.store.with_tx(_do)

    def list_evidence(self, *, campaign_id: str = "", limit: int = 50) -> dict[str, Any]:
        import json
        with self.store._lock:
            if campaign_id:
                rows = self.store.execute(
                    "SELECT * FROM pg_ops_evidence WHERE campaign_id=? ORDER BY created_at DESC LIMIT ?",
                    (campaign_id, limit),
                ).fetchall()
            else:
                rows = self.store.execute(
                    "SELECT * FROM pg_ops_evidence ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return {
            "evidence": [
                {
                    "id": r["id"], "campaign_id": r["campaign_id"], "kind": r["kind"],
                    "outcome": r["outcome"], "fingerprint": r["fingerprint"],
                    "immutable": bool(r["immutable"]), "created_at": r["created_at"],
                    "paper_only": True,
                    # omit full bundle in list for size; fetch by id if needed
                }
                for r in rows
            ],
            "paper_only": True,
            "immutable": True,
        }

    def get_evidence(self, evidence_id: str) -> dict[str, Any]:
        import json
        with self.store._lock:
            r = self.store.execute(
                "SELECT * FROM pg_ops_evidence WHERE id=?", (evidence_id,)
            ).fetchone()
        if not r:
            raise DurableGovError("NOT_FOUND", "evidence not found")
        return {
            "id": r["id"], "campaign_id": r["campaign_id"], "kind": r["kind"],
            "outcome": r["outcome"],
            "bundle": json.loads(r["bundle_json"] or "{}"),
            "fingerprint": r["fingerprint"],
            "immutable": bool(r["immutable"]),
            "created_at": r["created_at"],
            "paper_only": True,
        }
