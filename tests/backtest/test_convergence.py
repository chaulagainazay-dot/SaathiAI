from datetime import datetime,timezone,timedelta
from decimal import Decimal
import pytest
from saathi.platform.backtest.convergence import *
T=datetime(2024,1,1,tzinfo=timezone.utc)
def test_pti_and_next_bar_fill():
 ev=[MarketObservation('BINANCE:BTC/USDT',T,T,Decimal('100')),MarketObservation('BINANCE:BTC/USDT',T+timedelta(days=1),T+timedelta(days=1),Decimal('110'))]
 r=CanonicalBacktest('s','1','d','v1','REPLAY',commission_bps=10).run(ev,lambda x: 'LONG_BIAS' if x.price==100 else 'NO_SIGNAL')
 assert r.status=='RESEARCH_ONLY' and r.fills[0].price==Decimal('110')
def test_future_observation_rejected_and_mode_bounded():
 with pytest.raises(ValueError): CanonicalBacktest('s','1','d','v1','LIVE')
 ev=[MarketObservation('X',T,T+timedelta(days=1),Decimal('1'))]
 assert CanonicalBacktest('s','1','d','v1','HISTORICAL').run(ev,lambda x:'LONG_BIAS').signals==[]

def test_result_preserves_strategy_dataset_mode_and_future_lessons():
 ev=[MarketObservation('X',T,T,Decimal('1')),MarketObservation('X',T+timedelta(1),T+timedelta(1),Decimal('2'))]
 r=CanonicalBacktest('strat','v2','ds','dv','SYNTHETIC').run(ev,lambda x:'NO_SIGNAL')
 assert (r.strategy_id,r.strategy_version,r.dataset_id,r.dataset_version,r.data_mode)==('strat','v2','ds','dv','SYNTHETIC')
 assert lessons_visible_at([type('L',(),{'available_at':T+timedelta(1)})()],T)==[]

def test_oos_plan_is_chronological_and_config_locks():
 p=StrategyEvaluationPlan('e','s','1','d','1','CRYPTO','BINANCE',T,T+timedelta(days=1),T+timedelta(days=1),T+timedelta(days=2),T+timedelta(days=2),T+timedelta(days=3),'crypto-v1','next-v1',trial_count=2)
 c=LockedStrategyConfiguration.lock('s','1',{'window':5},T+timedelta(days=2),'train','val',2,'max_return','crypto-v1','next-v1')
 assert p.test_start>=p.validation_end and len(c.config_hash)==64
 with pytest.raises(ValueError):
  StrategyEvaluationPlan('e','s','1','d','1','C','V',T,T+timedelta(days=2),T+timedelta(days=1),T+timedelta(days=3),T+timedelta(days=3),T+timedelta(days=4),'c','f')

def test_future_lesson_is_rejected_at_oos_time():
 class A: available_at=T+timedelta(days=1)
 with pytest.raises(ValueError): validate_oos_visibility(decision_time=T, lessons=[A()])
