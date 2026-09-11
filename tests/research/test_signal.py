from datetime import datetime,timezone,timedelta
from decimal import Decimal
import pytest
from saathi.platform.signal import *
T=datetime(2024,1,1,tzinfo=timezone.utc)
def test_signal_and_intent_are_bounded_and_idempotent():
 s=TradingSignal.create('strat','1','BINANCE:BTC/USDT','LONG_BIAS',Decimal('.7'),T,T+timedelta(hours=1),'REPLAY',['THESIS_SUPPORTED'])
 assert s.signal_id==TradingSignal.create('strat','1','BINANCE:BTC/USDT','LONG_BIAS',Decimal('.7'),T,T+timedelta(hours=1),'REPLAY',['THESIS_SUPPORTED']).signal_id
 i=TradingIntentProposal.from_signal(s); assert i.intent_id and not hasattr(i,'quantity')
def test_invalid_and_stale_signal_rejected():
 with pytest.raises(ValueError): TradingSignal.create('s','1','NEPSE:NABIL','LONG_BIAS',Decimal('NaN'),T,T,'LIVE',[])
 s=TradingSignal.create('s','1','NEPSE:NABIL','LONG_BIAS',Decimal('.5'),T,T+timedelta(hours=1),'HISTORICAL',[])
 assert s.is_valid(T+timedelta(hours=2)) is False
def test_conflicting_signals_preserved():
 a=TradingSignal.create('a','1','NEPSE:NABIL','LONG_BIAS',Decimal('.5'),T,T+timedelta(1),'HISTORICAL',[])
 b=TradingSignal.create('b','1','NEPSE:NABIL','REDUCE_BIAS',Decimal('.5'),T,T+timedelta(1),'HISTORICAL',[])
 assert resolve_conflict([a,b])=='CONFLICTING'
