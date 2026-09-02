"""Canonical, proposal-only backtest and OOS evaluation boundaries."""
from dataclasses import dataclass,field
from datetime import datetime
from decimal import Decimal
import hashlib,json
@dataclass(frozen=True)
class MarketObservation: instrument_id:str; as_of:datetime; available_at:datetime; price:Decimal
@dataclass
class BacktestResult:
 status:str; signals:list=field(default_factory=list); fills:list=field(default_factory=list); limitations:list=field(default_factory=list)
 strategy_id:str=''; strategy_version:str=''; dataset_id:str=''; dataset_version:str=''; data_mode:str=''
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
  return BacktestResult('RESEARCH_ONLY',signals,fills,['COST_MODEL_LIMITED'] if self.commission_bps==0 else [],self.strategy_id,self.strategy_version,self.dataset_id,self.dataset_version,self.mode)
def lessons_visible_at(lessons, decision_time):
 return [l for l in lessons if l.available_at<=decision_time]

@dataclass(frozen=True)
class StrategyEvaluationPlan:
 """Immutable chronology/configuration contract for strategy evaluation."""
 evaluation_id:str; strategy_id:str; strategy_version:str; dataset_id:str; dataset_version:str
 market:str; venue:str; train_start:datetime; train_end:datetime; validation_start:datetime; validation_end:datetime
 test_start:datetime; test_end:datetime; cost_model_version:str; fill_model_version:str
 trial_count:int=1; seed:int=0; walk_forward_policy:str='EXPANDING'; engine_version:str='backtest-v1'
 def __post_init__(self):
  if not (self.train_start < self.train_end <= self.validation_start < self.validation_end <= self.test_start < self.test_end):
   raise ValueError('evaluation windows must be chronological and non-overlapping')
  if self.trial_count < 1: raise ValueError('trial_count must be positive')
  if self.walk_forward_policy not in {'EXPANDING','ROLLING'}: raise ValueError('invalid walk-forward policy')

@dataclass(frozen=True)
class LockedStrategyConfiguration:
 strategy_id:str; strategy_version:str; parameters:dict; config_hash:str; selected_at:datetime
 training_dataset_ref:str; validation_dataset_ref:str; trial_count:int; selection_rule:str
 cost_model_version:str; fill_model_version:str
 @classmethod
 def lock(cls, strategy_id, strategy_version, parameters, selected_at, training_dataset_ref,
          validation_dataset_ref, trial_count, selection_rule, cost_model_version, fill_model_version):
  if trial_count < 1: raise ValueError('trial_count must be positive')
  payload=json.dumps(parameters,sort_keys=True,separators=(',',':'),default=str)
  digest=hashlib.sha256(payload.encode()).hexdigest()
  return cls(strategy_id,strategy_version,dict(parameters),digest,selected_at,training_dataset_ref,
             validation_dataset_ref,trial_count,selection_rule,cost_model_version,fill_model_version)

@dataclass(frozen=True)
class WalkForwardResult:
 run_id:str; strategy_id:str; strategy_version:str; dataset_id:str; dataset_version:str
 segments:tuple; trial_count:int; cost_model_version:str; fill_model_version:str
 status:str='OOS_VALIDATED_WITH_LIMITATIONS'; limitations:tuple=()
 def __post_init__(self):
  if self.trial_count < 1: raise ValueError('trial_count must be positive')
  if any(self.segments[i].get('test_start', '') > self.segments[i+1].get('test_start', '') for i in range(len(self.segments)-1)):
   raise ValueError('walk-forward segments must be chronological')
 def to_public(self):
  return {'run_id':self.run_id,'strategy_id':self.strategy_id,'strategy_version':self.strategy_version,
          'dataset_id':self.dataset_id,'dataset_version':self.dataset_version,'segments':list(self.segments),
          'trial_count':self.trial_count,'cost_model_version':self.cost_model_version,
          'fill_model_version':self.fill_model_version,'status':self.status,'limitations':list(self.limitations)}

def validate_oos_visibility(*, decision_time, evidence=(), lessons=(), signals=()):
 """Reject any artifact unavailable at the simulated decision time."""
 for item in (*evidence,*lessons,*signals):
  available=getattr(item,'available_at',None)
  if available is not None and available > decision_time:
   raise ValueError('future evidence is unavailable at decision time')
 return True
