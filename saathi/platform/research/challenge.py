"""Deterministic, bounded thesis challenge protocol; research-only."""
from dataclasses import dataclass, field
from enum import Enum
from .evidence import ResearchClaim, StructuredInvestmentThesis, EvidenceReference
class ChallengeType(str,Enum): SUPPORTING_CASE='SUPPORTING_CASE'; OPPOSING_CASE='OPPOSING_CASE'; EVIDENCE_CHALLENGE='EVIDENCE_CHALLENGE'; ASSUMPTION_CHALLENGE='ASSUMPTION_CHALLENGE'; RISK_CHALLENGE='RISK_CHALLENGE'; CATALYST_CHALLENGE='CATALYST_CHALLENGE'; INVALIDATION_CHALLENGE='INVALIDATION_CHALLENGE'; DATA_QUALITY_CHALLENGE='DATA_QUALITY_CHALLENGE'
class Resolution(str,Enum): SUPPORTED_WITH_LIMITATIONS='SUPPORTED_WITH_LIMITATIONS'; CONTESTED='CONTESTED'; INSUFFICIENT_EVIDENCE='INSUFFICIENT_EVIDENCE'; INVALIDATED='INVALIDATED'; READY_FOR_INTENT_PROPOSAL='READY_FOR_INTENT_PROPOSAL'
@dataclass
class ResearchChallenge:
    challenge_id:str; challenge_type:ChallengeType; target_claim_ids:tuple[str,...]; statement:str; evidence_refs:list[EvidenceReference]=field(default_factory=list); severity:str='MEDIUM'; status:str='OPEN'; response_ref:str|None=None
@dataclass
class ChallengeResolution:
    status:Resolution; challenges:list[ResearchChallenge]; unresolved:tuple[str,...]; reason:str
class ChallengeSession:
    def __init__(self,session_id,research_run_id,instrument_id,decision_time,thesis,round_limit=2,max_challenges=16):
        self.session_id=session_id; self.research_run_id=research_run_id; self.instrument_id=instrument_id; self.decision_time=decision_time; self.thesis=thesis; self.round_limit=round_limit; self.max_challenges=max_challenges; self.challenges=[]
    def add(self,typ,target,statement,evidence,severity='MEDIUM'):
        if len(self.challenges)>=self.max_challenges:return 'BUDGET_EXCEEDED'
        if any(e.available_at>self.decision_time for e in evidence): statement='FUTURE_EVIDENCE_REJECTED: '+statement
        if target not in {c.claim_id for c in self.thesis.supporting_claims+self.thesis.contradicting_claims}: return 'INVALID_CLAIM_REF'
        self.challenges.append(ResearchChallenge(f'{self.session_id}:{len(self.challenges)+1}',typ,(target,),statement,evidence,severity)); return 'ACCEPTED'
    def resolve(self):
        if not self.challenges:return ChallengeResolution(Resolution.INSUFFICIENT_EVIDENCE,[],(), 'NO_CHALLENGES')
        high=any(c.severity=='HIGH' or c.status=='OPEN' for c in self.challenges)
        return ChallengeResolution(Resolution.CONTESTED if high else Resolution.SUPPORTED_WITH_LIMITATIONS,self.challenges,tuple(c.challenge_id for c in self.challenges if c.status=='OPEN'),'BOUNDED_ROUNDS')
