"""Small canonical, proposal-only backtest boundary."""
from dataclasses import dataclass,field
from datetime import datetime
from decimal import Decimal
@dataclass(frozen=True)
class MarketObservation: instrument_id:str; as_of:datetime; available_at:datetime; price:Decimal
@dataclass
class BacktestResult: status:str; signals:list=field(default_factory=list); fills:list=field(default_factory=list); limitations:list=field(default_factory=list)
@dataclass(frozen=True)
class SimFill: instrument_id:str; price:Decimal
class CanonicalBacktest:
 def __init__(self,strategy_id,strategy_version,dataset_id,dataset_version,data_mode,commission_bps=0):
  if data_mode not in {'HISTORICAL','REPLAY','SYNTHETIC'}: raise ValueError('invalid backtest data mode')
  self.strategy_id=strategy_id; self.strategy_version=strategy_version; self.dataset_id=dataset_id; self.dataset_version=dataset_version; self.mode=data_mode; self.commission_bps=Decimal(str(commission_bps))
 def run(self,observations,strategy):
  obs=sorted(observations,key=lambda x:(x.available_at,x.as_of,x.instrument_id)); signals=[]; fills=[]
  for i,o in enumerate(obs):
   if o.available_at>o.as_of: continue
   d=strategy(o)
   if d in {'LONG_BIAS','REDUCE_BIAS','EXIT_BIAS'}:
    signals.append((o.instrument_id,d,o.as_of));
    if i+1<len(obs): fills.append(SimFill(o.instrument_id,obs[i+1].price))
  return BacktestResult('RESEARCH_ONLY',signals,fills,['COST_MODEL_LIMITED'] if self.commission_bps==0 else [])
