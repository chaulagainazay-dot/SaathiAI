"""M62.3 — ResearchService: server-authoritative orchestration.

Ties the research pipeline together: permission-gated, audited, tenant-scoped,
optimistic-concurrency on the project version, fail-closed publication. Research
agents have NO trading/approval/broker/execution authority — this service never
imports or touches the runtime, gateway, or approval-consumption path.
"""
from __future__ import annotations

import time as _time
from typing import Any

from saathi.platform.context import PlatformContextError, PlatformExecutionContext
from saathi.platform.models import PlatformPermission, new_id
from saathi.platform.research.models import (
    ResearchState, can_research_transition, ResearchSource, Claim, Citation, Contradiction,
    SourceType, TrustClass, SourceQuality, InjectionState, FactClass, Verification, ContradictionType,
    content_hash,
)
from saathi.platform.research import analysis
from saathi.platform.research.store import ResearchStore

MAX_SOURCE_BYTES = 200_000  # bounded source ingestion


class ResearchService:
    def __init__(self, store: ResearchStore | None = None):
        self.store = store or ResearchStore()
        self._audit_sink = None  # optional: platform store.append_audit

    def bind_audit(self, platform_store):
        self._audit_sink = platform_store
        return self

    def _audit(self, ctx, event, pid, **extra):
        if not self._audit_sink:
            return
        try:
            self._audit_sink.append_audit(event, org_id=ctx.org_id, workspace_id=ctx.workspace_id,
                                          user_id=ctx.user_id, role=ctx.role, outcome=extra.pop("outcome", "ok"),
                                          detail={"research_project_id": pid, **extra})
        except Exception:
            pass

    def _project(self, ctx, pid) -> dict:
        p = self.store.get_project(ctx.org_id, pid)
        if not p:
            raise PlatformContextError("NOT_FOUND", "research project not found for tenant")
        return p

    def _advance(self, ctx, pid, target: ResearchState, expected_version) -> dict:
        p = self._project(ctx, pid)
        cur = ResearchState(p["state"])
        if cur != target and not can_research_transition(cur, target):
            raise PlatformContextError("VALIDATION_FAILED", f"illegal research transition {cur.value} -> {target.value}")
        kind, rec = self.store.update_project(ctx.org_id, pid, expected_version=expected_version, state=target.value)
        if kind == "conflict":
            raise PlatformContextError("STALE_STATE", "project version conflict — reload")
        if kind == "not_found":
            raise PlatformContextError("NOT_FOUND", "project not found")
        return rec

    # ── projects / plan ──────────────────────────────────────────────────
    def create_project(self, ctx, *, title, question, scope="", mission_id="") -> dict:
        ctx.require_permission(PlatformPermission.RESEARCH_CREATE)
        p = self.store.create_project(org_id=ctx.org_id, workspace_id=ctx.workspace_id, mission_id=mission_id,
                                      title=title, question=question, scope=scope, created_by=ctx.user_id)
        self._audit(ctx, "research.project.created", p["project_id"], title=title)
        return p

    def list_projects(self, ctx) -> list[dict]:
        ctx.require_permission(PlatformPermission.RESEARCH_READ)
        return self.store.list_projects(ctx.org_id)

    def get_project(self, ctx, pid) -> dict:
        ctx.require_permission(PlatformPermission.RESEARCH_READ)
        return self._project(ctx, pid)

    def set_plan(self, ctx, pid, *, plan: dict, expected_version) -> dict:
        ctx.require_permission(PlatformPermission.RESEARCH_EDIT)
        p = self._project(ctx, pid)
        if not can_research_transition(ResearchState(p["state"]), ResearchState.PLANNED) and p["state"] != "PLANNED":
            raise PlatformContextError("VALIDATION_FAILED", "plan only from DRAFT")
        kind, rec = self.store.update_project(ctx.org_id, pid, expected_version=expected_version, state="PLANNED", plan=plan)
        if kind == "conflict":
            raise PlatformContextError("STALE_STATE", "version conflict")
        self._audit(ctx, "research.plan.created", pid)
        return rec

    # ── sources ──────────────────────────────────────────────────────────
    def add_source(self, ctx, pid, *, source_type, title, content, locator="", author="", publisher="",
                   published_at=0.0, trust="UNVERIFIED", now=None) -> dict:
        ctx.require_permission(PlatformPermission.RESEARCH_EDIT)
        p = self._project(ctx, pid)
        if len(content.encode("utf-8")) > MAX_SOURCE_BYTES:
            raise PlatformContextError("VALIDATION_FAILED", "source exceeds size limit")
        now = now if now is not None else _time.time()
        s = ResearchSource(
            source_id=new_id("rsrc_"), project_id=pid, org_id=ctx.org_id, workspace_id=ctx.workspace_id,
            source_type=SourceType(source_type), title=title, locator=locator, content=content, author=author,
            publisher=publisher, published_at=float(published_at), retrieved_at=now, effective_at=float(published_at),
            trust=TrustClass(trust) if trust in TrustClass._value2member_map_ else TrustClass.UNVERIFIED,
        )
        s.compute_hash()
        s.quality = analysis.classify_source_quality(s, now=now)
        self.store.add_source(ctx.org_id, s)
        # advance DRAFT/PLANNED -> COLLECTING_SOURCES on first source
        if p["state"] in ("PLANNED",):
            self.store.update_project(ctx.org_id, pid, expected_version=p["version"], state="COLLECTING_SOURCES")
        self._audit(ctx, "research.source.added", pid, source_id=s.source_id, quality=s.quality.value, injection=s.injection.value)
        if s.injection == InjectionState.BLOCKED:
            self._audit(ctx, "research.source.rejected", pid, source_id=s.source_id, reason="prompt_injection")
        return s.to_public()

    def list_sources(self, ctx, pid) -> list[dict]:
        ctx.require_permission(PlatformPermission.RESEARCH_READ)
        self._project(ctx, pid)
        return self.store.list_sources(ctx.org_id, pid)

    def validate_sources(self, ctx, pid, *, expected_version, now=None) -> dict:
        ctx.require_permission(PlatformPermission.RESEARCH_EDIT)
        self._advance(ctx, pid, ResearchState.VALIDATING_SOURCES, expected_version)
        srcs = self.store.list_sources(ctx.org_id, pid)
        blocked = sum(1 for s in srcs if s["injection"] == "BLOCKED")
        self._audit(ctx, "research.sources.validated", pid, count=len(srcs), blocked=blocked)
        return {"validated": len(srcs), "blocked_injection": blocked}

    # ── claims / citations / contradictions ──────────────────────────────
    def extract_claims(self, ctx, pid, *, expected_version) -> dict:
        ctx.require_permission(PlatformPermission.RESEARCH_EDIT)
        self._advance(ctx, pid, ResearchState.EXTRACTING_CLAIMS, expected_version)
        self.store.clear_derived(ctx.org_id, pid)  # idempotent re-extraction
        n = 0
        for srow in self.store.list_sources(ctx.org_id, pid):
            full = self.store.get_source_row(ctx.org_id, srow["source_id"])
            if not full or full["injection"] == "BLOCKED":
                continue  # never extract from prompt-injection-blocked sources
            src = ResearchSource(source_id=full["source_id"], project_id=pid, org_id=ctx.org_id,
                                 workspace_id=full["workspace_id"], source_type=SourceType(full["source_type"]),
                                 title=full["title"], locator=full["locator"], content=full["content"],
                                 published_at=full["published_at"], effective_at=full["effective_at"], hash=full["hash"])
            for cd in analysis.extract_claims(src):
                c = Claim(claim_id=new_id("rclm_"), project_id=pid, source_id=src.source_id,
                          statement=cd["statement"], fact_class=cd["fact_class"], locator=cd["locator"],
                          materiality="high" if cd["numeric"] is not None else "medium",
                          agent_role=cd["agent_role"], excerpt=cd["excerpt"])
                self.store.add_claim(ctx.org_id, c, {"topic": cd["topic"], "numeric": cd["numeric"]})
                n += 1
        self._audit(ctx, "research.claims.extracted", pid, claims=n)
        return {"claims": n}

    def list_claims(self, ctx, pid) -> list[dict]:
        ctx.require_permission(PlatformPermission.RESEARCH_READ)
        self._project(ctx, pid)
        return self.store.list_claims(ctx.org_id, pid)

    def verify_citations(self, ctx, pid, *, expected_version) -> dict:
        ctx.require_permission(PlatformPermission.RESEARCH_EDIT)
        self._advance(ctx, pid, ResearchState.VERIFYING_CITATIONS, expected_version)
        verified = failed = 0
        for cl in self.store.list_claims(ctx.org_id, pid):
            full = self.store.get_source_row(ctx.org_id, cl["source_id"])
            src = None
            if full:
                src = ResearchSource(source_id=full["source_id"], project_id=pid, org_id=ctx.org_id,
                                     workspace_id=full["workspace_id"], source_type=SourceType(full["source_type"]),
                                     title=full["title"], content=full["content"], hash=full["hash"])
            cit = Citation(citation_id=new_id("rcit_"), claim_id=cl["claim_id"], source_id=cl["source_id"],
                           locator=cl["locator"], source_hash=(full["hash"] if full else ""))
            analysis.verify_citation(cit, src)
            self.store.add_citation(ctx.org_id, pid, cit)
            self.store.set_claim_verification(ctx.org_id, cl["claim_id"],
                                              Verification.VERIFIED.value if cit.verification == Verification.VERIFIED else Verification.FAILED.value)
            verified += cit.verification == Verification.VERIFIED
            failed += cit.verification == Verification.FAILED
        self._audit(ctx, "research.citations.verified", pid, verified=verified, failed=failed)
        return {"verified": verified, "failed": failed}

    def search_contradictions(self, ctx, pid, *, expected_version) -> dict:
        ctx.require_permission(PlatformPermission.RESEARCH_EDIT)
        self._advance(ctx, pid, ResearchState.SEARCHING_CONTRADICTIONS, expected_version)
        rows = self.store.list_claims(ctx.org_id, pid)
        claims = [Claim(claim_id=r["claim_id"], project_id=pid, source_id=r["source_id"], statement=r["statement"],
                        fact_class=FactClass(r["fact_class"]), locator=r["locator"], materiality=r["materiality"]) for r in rows]
        meta = {r["claim_id"]: r["meta"] for r in rows}
        srcs = {}
        for sr in self.store.list_sources(ctx.org_id, pid):
            full = self.store.get_source_row(ctx.org_id, sr["source_id"])
            if full:
                srcs[full["source_id"]] = ResearchSource(source_id=full["source_id"], project_id=pid, org_id=ctx.org_id,
                    workspace_id=full["workspace_id"], source_type=SourceType(full["source_type"]), title=full["title"],
                    content=full["content"], published_at=full["published_at"], effective_at=full["effective_at"])
        found = analysis.find_contradictions(claims, srcs, meta)
        for f in found:
            con = Contradiction(contradiction_id=new_id("rcon_"), project_id=pid, claim_a=f["claim_a"],
                                claim_b=f["claim_b"], kind=f["kind"], severity=f["severity"])
            self.store.add_contradiction(ctx.org_id, pid, con)
        self._audit(ctx, "research.contradictions.found", pid, count=len(found))
        return {"contradictions": len(found)}

    def list_contradictions(self, ctx, pid) -> list[dict]:
        ctx.require_permission(PlatformPermission.RESEARCH_READ)
        self._project(ctx, pid)
        return self.store.list_contradictions(ctx.org_id, pid)

    # ── synthesize / challenge / revise / publish ────────────────────────
    def _gather(self, ctx, pid):
        srcs = [self._mk_source(ctx, r) for r in self.store.list_sources(ctx.org_id, pid)]
        crows = self.store.list_claims(ctx.org_id, pid)
        claims = [Claim(claim_id=r["claim_id"], project_id=pid, source_id=r["source_id"], statement=r["statement"],
                        fact_class=FactClass(r["fact_class"]), locator=r["locator"], materiality=r["materiality"],
                        confidence=r["confidence"], verification=Verification(r["verification"])) for r in crows]
        cits = [Citation(citation_id=r["citation_id"], claim_id=r["claim_id"], source_id=r["source_id"],
                         locator=r["locator"], source_hash=r["source_hash"], verification=Verification(r["verification"]))
                for r in self.store.list_citations(ctx.org_id, pid)]
        cons = [Contradiction(contradiction_id=r["contradiction_id"], project_id=pid, claim_a=r["claim_a"],
                              claim_b=r["claim_b"], kind=ContradictionType(r["kind"]), severity=r["severity"],
                              resolution=r["resolution"]) for r in self.store.list_contradictions(ctx.org_id, pid)]
        return srcs, claims, cits, cons

    def _mk_source(self, ctx, r):
        return ResearchSource(source_id=r["source_id"], project_id=r["project_id"], org_id=ctx.org_id,
                              workspace_id=r.get("workspace_id", ctx.workspace_id),
                              source_type=SourceType(r["source_type"]), title=r["title"],
                              trust=TrustClass(r["trust"]), quality=SourceQuality(r["quality"]),
                              published_at=r.get("published_at", 0), effective_at=r.get("effective_at", 0))

    def synthesize(self, ctx, pid, *, expected_version, scenarios=None) -> dict:
        ctx.require_permission(PlatformPermission.RESEARCH_EDIT)
        self._advance(ctx, pid, ResearchState.SYNTHESIZING, expected_version)
        srcs, claims, cits, cons = self._gather(ctx, pid)
        scenarios = scenarios or [{"name": "Base"}, {"name": "Downside"}]
        conf = analysis.confidence_components(sources=srcs, claims=claims, citations=cits, contradictions=cons)
        body = {"summary": self._project(ctx, pid)["question"], "n_claims": len(claims), "n_sources": len(srcs),
                "scenarios": scenarios, "supporting_claims": [c.claim_id for c in claims if c.verification == Verification.VERIFIED],
                "contradicting": [con.contradiction_id for con in cons]}
        thesis = self.store.new_thesis_version(ctx.org_id, ctx.workspace_id, pid, state="DRAFT", body=body,
                                               confidence=conf, challenge={}, author=f"user:{ctx.user_id}")
        p = self.store.get_project(ctx.org_id, pid)
        self.store.update_project(ctx.org_id, pid, expected_version=p["version"], state="CHALLENGE_REQUIRED")
        self._audit(ctx, "research.thesis.synthesized", pid, thesis_version=thesis["version"], confidence=conf["score"])
        return {"thesis": thesis}

    def challenge(self, ctx, pid, *, expected_version) -> dict:
        ctx.require_permission(PlatformPermission.RESEARCH_CHALLENGE)
        self._advance(ctx, pid, ResearchState.UNDER_CHALLENGE, expected_version)
        srcs, claims, cits, cons = self._gather(ctx, pid)
        thesis = self.store.latest_thesis(ctx.org_id, pid)
        scenarios = (thesis or {}).get("body", {}).get("scenarios", [])
        result = analysis.challenge_thesis(sources=srcs, claims=claims, citations=cits, contradictions=cons, scenarios=scenarios)
        no_critical = result["critical_count"] == 0
        # persist challenge onto the thesis version
        self.store.set_thesis_state(ctx.org_id, pid, thesis["version"],
                                    state=("REVIEW_READY" if no_critical else "REVISION_REQUIRED"), challenge=result)
        p = self.store.get_project(ctx.org_id, pid)
        # fail-closed: critical findings keep the project UNDER_CHALLENGE (needs revise)
        target = "HUMAN_REVIEW_REQUIRED" if no_critical else "UNDER_CHALLENGE"
        if target != p["state"]:
            self.store.update_project(ctx.org_id, pid, expected_version=p["version"], state=target)
        self._audit(ctx, "research.challenge.completed", pid, critical=result["critical_count"], disposition=result["recommended_disposition"])
        return {"challenge": result, "review_ready": no_critical}

    def revise(self, ctx, pid, *, expected_version, rationale="") -> dict:
        ctx.require_permission(PlatformPermission.RESEARCH_EDIT)
        self._advance(ctx, pid, ResearchState.SYNTHESIZING, expected_version)
        srcs, claims, cits, cons = self._gather(ctx, pid)
        conf = analysis.confidence_components(sources=srcs, claims=claims, citations=cits, contradictions=cons)
        prev = self.store.latest_thesis(ctx.org_id, pid)
        body = dict(prev.get("body", {})) if prev else {}
        thesis = self.store.new_thesis_version(ctx.org_id, ctx.workspace_id, pid, state="DRAFT", body=body,
                                               confidence=conf, challenge={}, author=f"user:{ctx.user_id}", rationale=rationale)
        p = self.store.get_project(ctx.org_id, pid)
        self.store.update_project(ctx.org_id, pid, expected_version=p["version"], state="CHALLENGE_REQUIRED")
        self._audit(ctx, "research.thesis.revised", pid, thesis_version=thesis["version"])
        return {"thesis": thesis}

    def publish(self, ctx, pid, *, expected_version) -> dict:
        ctx.require_permission(PlatformPermission.RESEARCH_PUBLISH)  # owner+ only
        p = self._project(ctx, pid)
        if p["state"] != "HUMAN_REVIEW_REQUIRED":
            raise PlatformContextError("VALIDATION_FAILED", "publish only from HUMAN_REVIEW_REQUIRED")
        thesis = self.store.latest_thesis(ctx.org_id, pid)
        if not thesis or thesis.get("challenge", {}).get("critical_count", 1) != 0:
            raise PlatformContextError("VALIDATION_FAILED", "unresolved critical challenge findings block publication")
        # unresolved critical contradictions also block
        if any(c["severity"] == "critical" and c["resolution"] == "UNRESOLVED" for c in self.store.list_contradictions(ctx.org_id, pid)):
            raise PlatformContextError("VALIDATION_FAILED", "unresolved critical contradiction blocks publication")
        self.store.update_project(ctx.org_id, pid, expected_version=expected_version, state="APPROVED_FOR_PUBLICATION")
        p2 = self.store.get_project(ctx.org_id, pid)
        self.store.set_thesis_state(ctx.org_id, pid, thesis["version"], state="PUBLISHED", published=True)
        self.store.update_project(ctx.org_id, pid, expected_version=p2["version"], state="PUBLISHED")
        self._audit(ctx, "research.thesis.published", pid, thesis_version=thesis["version"])
        return {"published": True, "thesis_version": thesis["version"]}

    def get_thesis(self, ctx, pid) -> dict | None:
        ctx.require_permission(PlatformPermission.RESEARCH_READ)
        self._project(ctx, pid)
        return self.store.latest_thesis(ctx.org_id, pid)

    def thesis_versions(self, ctx, pid) -> list[dict]:
        ctx.require_permission(PlatformPermission.RESEARCH_READ)
        self._project(ctx, pid)
        return self.store.list_thesis_versions(ctx.org_id, pid)
