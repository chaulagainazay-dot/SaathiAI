from datetime import datetime, timezone, timedelta
from saathi.platform.research.evidence import EvidenceReference
from saathi.platform.research.specialists import *
U=timezone.utc; T=datetime(2024,1,2,tzinfo=U)
def e(i='e',quality='VALID',at=T): return EvidenceReference(i,'market','src',T,at,T,instrument_id='BINANCE:BTC/USDT',quality=quality)
def test_registry_and_context_are_bounded():
    c=ResearchContext('BINANCE:BTC/USDT','BINANCE',T,(e(),),max_evidence=2)
    assert len(SPECIALISTS)==8 and c.visible()[0].evidence_id=='e'
def test_specialists_propagate_missing_and_point_in_time():
    c=ResearchContext('BINANCE:BTC/USDT','BINANCE',T,(e(at=T+timedelta(days=1)),))
    r=SpecialistOrchestrator().run(c,roles=['FUNDAMENTAL','TECHNICAL'])
    assert r.missing_evidence and not r.claims
def test_deterministic_roles_emit_typed_claims_only():
    r=SpecialistOrchestrator().run(ResearchContext('BINANCE:BTC/USDT','BINANCE',T,(e(),)),roles=['TECHNICAL','RISK','COUNTER_THESIS'])
    assert len(r.claims)==3 and all(x.instrument_id=='BINANCE:BTC/USDT' for x in r.claims)
