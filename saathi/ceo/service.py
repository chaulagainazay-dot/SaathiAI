"""M14 CEOService — the orchestration layer over existing systems.

Reads REAL data (CEO store + missions + M10 runs + M13 studio + ops health)
and produces the Daily Brief with an evidence tier on every item. Missions are
created and executed ONLY through the M10 Orchestrator — there is no CEO-direct
execution path. Review conclusions write back to M9 Memory with provenance.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from saathi.ceo.store import CEOStore
from saathi.ceo.models import EvidenceTier


@dataclass
class BriefItem:
    section: str
    text: str
    tier: str
    evidence: list = None


class CEOService:
    def __init__(self, store: CEOStore | None = None, orchestrator=None, memory=None):
        self.store = store or CEOStore()
        self._orch = orchestrator
        self._memory = memory

    def _orchestrator(self):
        if self._orch is None:
            from saathi.agent_runtime.orchestrator import default_orchestrator
            self._orch = default_orchestrator()
        return self._orch

    def _mem(self):
        if self._memory is None:
            try:
                from saathi.memory.engine import default_engine
                self._memory = default_engine()
            except Exception:
                self._memory = False
        return self._memory or None

    # ── portfolio summary (real data only) ────────────────────────────────
    def portfolio_summary(self, owner: str) -> dict:
        from saathi.ceo import kpi as K
        businesses = self.store.list_businesses(owner)
        goals = self.store.list_goals(owner)
        kpis = []
        for kdef in self.store.list_kpis(owner):
            kv = K.compute_kpi(self.store, kdef["id"])
            kpis.append(kv.to_dict())
        risks = self.store.list_risks(owner, status="open")
        decisions = self.store.list_decisions(owner, status="awaiting_decision")
        alerts = self.store.list_alerts(owner)
        return {
            "businesses": businesses, "goals": goals, "kpis": kpis,
            "open_risks": len(risks), "top_risks": risks[:3],
            "decisions_awaiting": len(decisions),
            "open_alerts": len(alerts),
            "system_health": self._system_health(),
        }

    def _system_health(self) -> dict:
        """Real ops signals — storage + db integrity + active runs."""
        out = {}
        try:
            from saathi.ops.storage import storage_report
            out["storage"] = storage_report()["level"]
        except Exception:
            out["storage"] = "unknown"
        try:
            from saathi.agent_runtime.orchestrator import default_orchestrator
            runs = default_orchestrator().store.list_runs(limit=100)
            out["active_agent_runs"] = sum(
                1 for r in runs if r["state"] in ("running", "awaiting_approval"))
        except Exception:
            out["active_agent_runs"] = 0
        try:
            from saathi.studio_os.store import default_store as sstore
            out["studio_projects"] = len(sstore().list_projects(limit=100))
        except Exception:
            out["studio_projects"] = 0
        return out

    # ── Daily Brief (real data, evidence-tagged) ──────────────────────────
    def daily_brief(self, owner: str, *, persist: bool = True) -> dict:
        from saathi.ceo import kpi as K, priority as PR
        items: list[dict] = []

        def add(section, text, tier, evidence=None):
            items.append({"section": section, "text": text, "tier": tier,
                         "evidence": evidence or []})

        # priorities — deterministic ranking of open decisions + high risks
        ranked = []
        for d in self.store.list_decisions(owner, status="awaiting_decision"):
            ranked.append((f"decision:{d['id']}",
                          PR.PriorityInput(strategic_alignment=0.6, dependency_blocking=True)))
        for r in self.store.list_risks(owner, status="open")[:5]:
            ranked.append((f"risk:{r['id']}",
                          PR.PriorityInput(risk_reduction=r["impact"],
                                          revenue_impact=0.3 if r["category"] == "financial" else 0)))
        top = PR.rank(ranked)[:3]
        for t in top:
            add("Act Now", f"{t['id']} (priority {t['score']})",
                EvidenceTier.CALCULATED.value,
                [f["label"] for f in t["factors"]])
        if not top:
            add("Act Now", "No prioritized items — register goals/decisions/risks to populate.",
                EvidenceTier.UNAVAILABLE.value)

        # KPIs with movement
        for kdef in self.store.list_kpis(owner):
            kv = K.compute_kpi(self.store, kdef["id"])
            if not kv.available:
                add("KPIs", f"{kv.name}: no verified data source.",
                    EvidenceTier.UNAVAILABLE.value)
            elif kv.trend in ("up", "down"):
                add("KPIs", f"{kv.name} {kv.trend} to {kv.value} {kv.unit} "
                    f"({kv.pct_to_target}% of target)", EvidenceTier.CALCULATED.value,
                    [kv.source])

        # pending approvals (from M10 — real)
        try:
            orch = self._orchestrator()
            pending = 0
            for run in orch.store.list_runs(limit=50):
                pending += len(orch.store.pending_approvals(run["id"]))
            if pending:
                add("Approvals", f"{pending} action(s) awaiting your approval.",
                    EvidenceTier.OBSERVED.value)
        except Exception:
            pass

        # alerts
        for a in self.store.list_alerts(owner)[:5]:
            add("Risks" if a["kind"].startswith("risk") else "System Health",
                f"[{a['severity']}] {a['title']}", EvidenceTier.OBSERVED.value,
                a["evidence_refs"])

        # system health
        sh = self._system_health()
        add("System Health",
            f"storage:{sh['storage']} · {sh['active_agent_runs']} active runs · "
            f"{sh['studio_projects']} studio projects", EvidenceTier.OBSERVED.value)

        # M17.21 registry health — only when not GREEN or score below threshold
        try:
            from saathi.application_harness import registry as _reg
            rh = _reg.health()
            if rh.get("include_in_ceo_brief"):
                add(
                    "Registry Health",
                    f"{rh.get('overall_status')} score={rh.get('health_score')} "
                    f"rev={rh.get('registry_revision')} "
                    f"load={rh.get('load_status')} "
                    f"size={rh.get('registry_size_bytes')}/"
                    f"{rh.get('size_limit')} "
                    f"reasons={','.join(rh.get('score_reasons') or []) or 'none'}",
                    EvidenceTier.OBSERVED.value,
                    ["application_harness.registry.health"],
                )
        except Exception:
            pass

        # M17.22 execution gateway — only failures / retries / approval backlog / latency
        try:
            from saathi.execution.universal import default_boundary
            es = default_boundary().ceo_summary()
            if es and es.get("include_in_ceo_brief"):
                add(
                    "Execution",
                    f"failed={es.get('failed', 0)} retries={es.get('retries', 0)} "
                    f"approval_backlog={es.get('approval_backlog', 0)} "
                    f"avg_runtime_s={es.get('average_runtime_sec', 0)} "
                    f"running={es.get('running', 0)} denied={es.get('denied', 0)}",
                    EvidenceTier.OBSERVED.value,
                    ["execution.gateway.metrics"],
                )
        except Exception:
            pass

        # M17.23 browser — only failures / uncertain / backlog / policy / injection
        try:
            from saathi.browser.governed import ceo_browser_summary
            bs = ceo_browser_summary()
            if bs and bs.get("include_in_ceo_brief"):
                add(
                    "Browser",
                    f"failed={bs.get('failed', 0)} "
                    f"uncertain={bs.get('outcome_uncertain', 0)} "
                    f"approval_backlog={bs.get('approval_backlog', 0)} "
                    f"domain_denied={bs.get('domain_denied', 0)} "
                    f"injection={bs.get('prompt_injection_detected', 0)}",
                    EvidenceTier.OBSERVED.value,
                    ["browser.execution.metrics"],
                )
        except Exception:
            pass

        # M18.1/M18.2 MCP + index — only when degraded/unavailable/stale (not when healthy)
        try:
            from saathi.mcp_governance.health import ceo_mcp_summary
            ms = ceo_mcp_summary()
            idx_status = ""
            idx_reason = ""
            try:
                from saathi.codebase_memory.health import index_health
                ih = index_health()
                idx_status = ih.status
                idx_reason = ih.degraded_reason or ""
                if ih.status in (
                    "STALE", "CORRUPT", "UNAVAILABLE", "DEGRADED", "REBUILD_REQUIRED",
                ):
                    ms = dict(ms or {})
                    ms["include_in_ceo_brief"] = True
                    ms["status"] = ih.status
                    ms["degraded_reason"] = idx_reason or ms.get("degraded_reason")
            except Exception:
                pass
            if ms and ms.get("include_in_ceo_brief"):
                add(
                    "MCP Memory",
                    f"status={ms.get('status')} "
                    f"index={idx_status or 'n/a'} "
                    f"reachable={ms.get('reachable')} "
                    f"reason={ms.get('degraded_reason') or idx_reason or ms.get('last_error_category') or 'n/a'} "
                    f"continuum={ms.get('continuum_status')}",
                    EvidenceTier.OBSERVED.value,
                    ["mcp.governance.health", "codebase_memory.index"],
                )
        except Exception:
            pass

        brief = {"owner": owner, "generated_at": time.time(),
                "items": items, "sections": sorted({i["section"] for i in items})}
        if persist:
            self.store.add_brief(owner, brief)
            self.store.event("ceo.brief.generated", {"owner": owner, "items": len(items)})
        return brief

    # ── Mission Control — creates + executes via M10 (no direct path) ─────
    def create_mission(self, owner: str, objective: str, *, strategy: str = "build",
                      source: str = "manual", source_ref: str = "") -> dict:
        """A CEO mission IS an M10 orchestration run. No CEO-direct execution."""
        orch = self._orchestrator()
        rid = orch.create_run(objective, actor=f"user:{owner}", strategy=strategy)
        self.store.event("ceo.mission.created",
                        {"owner": owner, "run_id": rid, "source": source})
        return {"mission_run_id": rid, "objective": objective, "source": source,
                "source_ref": source_ref}

    def run_mission(self, run_id: str) -> dict:
        return self._orchestrator().run(run_id)

    def convert_risk_to_mission(self, owner: str, risk_id: str) -> dict:
        r = self.store.get_risk(risk_id)
        if not r or r["owner"] != owner:
            raise PermissionError("risk not found for this owner")
        return self.create_mission(owner, f"Mitigate risk: {r['title']}",
                                   source="risk", source_ref=risk_id)

    def convert_opportunity_to_project(self, owner: str, opp_id: str) -> dict:
        o = self.store.get_opportunity(opp_id)
        if not o or o["owner"] != owner:
            raise PermissionError("opportunity not found for this owner")
        m = self.create_mission(owner, f"Pursue opportunity: {o['title']}",
                                source="opportunity", source_ref=opp_id)
        self.store.set_opportunity(opp_id, status="converted",
                                   converted_to=m["mission_run_id"])
        return m

    # ── reviews with memory write-back (provenance preserved) ─────────────
    def weekly_review(self, owner: str) -> dict:
        summary = self.portfolio_summary(owner)
        content = {"kind": "weekly", "generated_at": time.time(),
                  "kpis": summary["kpis"], "open_risks": summary["open_risks"],
                  "decisions_awaiting": summary["decisions_awaiting"],
                  "system_health": summary["system_health"]}
        rid = self.store.add_review(owner=owner, kind="weekly", content=content,
                                    provenance={"source": "ceo.service",
                                               "tier": EvidenceTier.CALCULATED.value})
        # write conclusion to memory (no secrets)
        mem = self._mem()
        if mem:
            try:
                mem.remember(namespace=f"business:global",
                            content=f"Weekly review: {summary['open_risks']} open risks, "
                                    f"{summary['decisions_awaiting']} decisions awaiting.",
                            memory_type="business", confidence=0.7,
                            source_type="ceo_review", source_id=rid)
            except Exception:
                pass
        return {"review_id": rid, **content}


_default: CEOService | None = None


def default_service() -> CEOService:
    global _default
    if _default is None:
        _default = CEOService()
    return _default
