"""Typed, point-in-time research evidence; no execution authority."""
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from enum import Enum
from hashlib import sha256

class EvidenceTrustClass(str, Enum): UNTRUSTED_EXTERNAL_DATA="UNTRUSTED_EXTERNAL_DATA"; INTERNAL="INTERNAL"
class ClaimStatus(str, Enum): DRAFT="DRAFT"; SUPPORTED="SUPPORTED"; CONTESTED="CONTESTED"; INSUFFICIENT_EVIDENCE="INSUFFICIENT_EVIDENCE"; STALE="STALE"; EXPIRED="EXPIRED"
@dataclass(frozen=True)
class UntrustedData:
    text:str; is_instruction:bool=False; trust_class:EvidenceTrustClass=EvidenceTrustClass.UNTRUSTED_EXTERNAL_DATA
@dataclass(frozen=True)
class EvidenceReference:
    evidence_id:str; evidence_type:str; source_name:str; as_of:datetime; available_at:datetime; received_at:datetime
    instrument_id:str|None=None; source_uri:str|None=None; provider:str|None=None; content_hash:str|None=None; dataset_id:str|None=None; revision_id:str|None=None; quality:str="UNVERIFIED"; trust_class:EvidenceTrustClass=EvidenceTrustClass.UNTRUSTED_EXTERNAL_DATA; raw_ref:str|None=None
@dataclass
class ResearchClaim:
    claim_id:str; instrument_id:str; claim_type:str; statement:str; evidence_refs:list[EvidenceReference]=field(default_factory=list); contradicting_evidence_refs:list[EvidenceReference]=field(default_factory=list); confidence:Decimal=Decimal("0"); generated_at:datetime|None=None; as_of:datetime|None=None; valid_until:datetime|None=None; model_ref:str|None=None; model_version:str|None=None; prompt_version:str|None=None; status:ClaimStatus=ClaimStatus.DRAFT
    def __post_init__(self):
        self.confidence=Decimal(self.confidence)
        try: valid=Decimal("0")<=self.confidence<=Decimal("1")
        except InvalidOperation: valid=False
        if not valid: raise ValueError("confidence must be between 0 and 1")
        for e in self.evidence_refs+self.contradicting_evidence_refs:
            if e.instrument_id and e.instrument_id!=self.instrument_id: raise ValueError("evidence instrument mismatch")
@dataclass
class StructuredInvestmentThesis:
    thesis_id:str; instrument_id:str; supporting_claims:list[ResearchClaim]=field(default_factory=list); contradicting_claims:list[ResearchClaim]=field(default_factory=list); valid_until:datetime|None=None; stance:str="UNSPECIFIED"; confidence:Decimal=Decimal("0")
    def __post_init__(self):
        if any(c.instrument_id!=self.instrument_id for c in self.supporting_claims+self.contradicting_claims): raise ValueError("claim instrument mismatch")
    def is_active(self, at): return self.valid_until is None or at<=self.valid_until
@dataclass(frozen=True)
class ResearchCheckpoint:
    workflow_type:str; workflow_version:str; schema_version:str; shape_signature:str
    def assert_compatible(self, schema_version, shape_signature):
        if self.schema_version!=schema_version or self.shape_signature!=shape_signature: raise ValueError("CHECKPOINT_INCOMPATIBLE")
@dataclass(frozen=True)
class ResearchEvidenceSnapshot:
    snapshot_id:str; decision_time:datetime; evidence_ids:tuple[str,...]; checksum:str
def visible_at(evidence:EvidenceReference, decision_time:datetime)->bool: return evidence.available_at<=decision_time
def validate_claim(claim:ResearchClaim, decision_time:datetime)->ResearchClaim:
    valid=[e for e in claim.evidence_refs if visible_at(e,decision_time) and e.quality not in {"INVALID","STALE"}]
    claim.status=ClaimStatus.SUPPORTED if valid else ClaimStatus.INSUFFICIENT_EVIDENCE
    if claim.valid_until and decision_time>claim.valid_until: claim.status=ClaimStatus.EXPIRED
    return claim
def snapshot_checksum(ids): return sha256("|".join(sorted(ids)).encode()).hexdigest()
