"""Bounded specialist research; outputs evidence-bound claims, never orders."""
from dataclasses import dataclass
from datetime import datetime
from .evidence import EvidenceReference, ResearchClaim, ResearchEvidenceSnapshot, validate_claim, ClaimStatus, snapshot_checksum

ROLES=('FUNDAMENTAL','TECHNICAL','MARKET_REGIME','NEWS_EVENT','SENTIMENT','RISK','CATALYST','COUNTER_THESIS')
SPECIALISTS={r:{'role':r,'llm':r in {'FUNDAMENTAL','NEWS_EVENT','SENTIMENT','CATALYST','COUNTER_THESIS'},'authority':'RESEARCH_ONLY'} for r in ROLES}
@dataclass(frozen=True)
class ResearchContext:
    instrument_id:str; venue:str; decision_time:datetime; evidence:tuple[EvidenceReference,...]; max_evidence:int=32
    def visible(self): return tuple(e for e in self.evidence[:self.max_evidence] if e.available_at<=self.decision_time)
@dataclass
class SpecialistResult:
    role:str; claims:list[ResearchClaim]; warnings:list[str]; missing_evidence:list[str]
@dataclass
class ResearchBundle:
    run_id:str; instrument_id:str; decision_time:datetime; results:list[SpecialistResult]; claims:list[ResearchClaim]; missing_evidence:list[str]
class SpecialistOrchestrator:
    def run(self, context, roles=None):
        roles=tuple(roles or ROLES)
        if len(roles)>8: raise ValueError('specialist budget exceeded')
        visible=context.visible(); missing=[]; results=[]; claims=[]
        for role in roles:
            if not visible:
                missing.append(f'{role}:INSUFFICIENT_EVIDENCE'); results.append(SpecialistResult(role,[],[],['INSUFFICIENT_EVIDENCE'])); continue
            c=ResearchClaim(f'{role.lower()}:{context.instrument_id}',context.instrument_id,role,'evidence observed',list(visible),confidence='0.5',generated_at=context.decision_time,as_of=context.decision_time)
            validate_claim(c,context.decision_time); claims.append(c); results.append(SpecialistResult(role,[c],[],[]))
        return ResearchBundle('run:'+snapshot_checksum([x.evidence_id for x in visible]),context.instrument_id,context.decision_time,results,claims,missing)
