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
