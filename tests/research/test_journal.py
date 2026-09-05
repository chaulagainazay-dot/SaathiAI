from datetime import datetime,timezone,timedelta
from decimal import Decimal
import pytest
from saathi.platform.research.journal import *
T=datetime(2024,1,1,tzinfo=timezone.utc)
def test_decision_outcome_and_revision():
 d=InvestmentDecisionRecord('d','BINANCE:BTC/USDT',T,'t','RESEARCH_ONLY','LONG','1d')
 o=DecisionOutcome('o','d',T,T+timedelta(days=1),Decimal('0.1'),None)
 assert o.benchmark_status=='BENCHMARK_UNAVAILABLE'
 j=DecisionJournal(); j.record(d); assert j.record(d)=='DUPLICATE'; j.add_outcome(o); j.add_outcome(o); assert len(j.outcomes)==1
def test_lessons_need_provenance_and_pti():
 j=InvestmentLesson('l',('d',),'use bounded horizons','TIMING','INSTRUMENT','BINANCE:BTC/USDT',T,T+timedelta(days=1))
 assert j.status==LessonStatus.OBSERVED and lessons_visible([j],T)==[]
 j.status=LessonStatus.PROMOTED; assert lessons_visible([j],T)==[j]
 assert lessons_visible([j],T+timedelta(days=2))==[]
 with pytest.raises(ValueError): InvestmentLesson('x',(), 'bad','RISK','GLOBAL',None,T,None)
def test_promotion_gate_never_self_promotes():
 l=InvestmentLesson('l',('d',),'x','RISK','INSTRUMENT','BTC',T,None)
 assert promote(l, sample_size=1)=='REJECTED'
 assert l.status==LessonStatus.OBSERVED
