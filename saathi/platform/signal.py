"""Canonical strategy signal and proposal-only intent contracts."""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from enum import Enum
class Direction(str,Enum): LONG_BIAS='LONG_BIAS'; REDUCE_BIAS='REDUCE_BIAS'; NEUTRAL='NEUTRAL'; EXIT_BIAS='EXIT_BIAS'; NO_SIGNAL='NO_SIGNAL'; INSUFFICIENT_EVIDENCE='INSUFFICIENT_EVIDENCE'
@dataclass(frozen=True)
class TradingSignal:
 signal_id:str; strategy_id:str; strategy_version:str; instrument_id:str; direction:Direction; strength:Decimal; generated_at:datetime; valid_until:datetime; data_mode:str; reason_codes:tuple[str,...]; quality:str='VALID'; venue:str|None=None
 @classmethod
 def create(cls,strategy_id,strategy_version,instrument_id,direction,strength,generated_at,valid_until,data_mode,reason_codes,quality='VALID'):
  try: x=Decimal(strength)
  except (InvalidOperation,ValueError): raise ValueError('invalid strength')
  try: valid=Decimal('0')<=x<=Decimal('1')
  except InvalidOperation: valid=False
  if not valid: raise ValueError('strength out of range')
  if valid_until<generated_at or data_mode not in {'LIVE','DELAYED','HISTORICAL','REPLAY','SYNTHETIC','UNKNOWN'}: raise ValueError('invalid signal window/mode')
  sid=sha256('|'.join(map(str,(strategy_id,strategy_version,instrument_id,generated_at.isoformat(),data_mode))).encode()).hexdigest()[:24]
  return cls(sid,strategy_id,strategy_version,instrument_id,Direction(direction),x,generated_at,valid_until,data_mode,tuple(reason_codes),quality)
 def is_valid(self,at): return at<=self.valid_until and self.quality=='VALID'
@dataclass(frozen=True)
class TradingIntentProposal:
 intent_id:str; signal_refs:tuple[str,...]; instrument_id:str; direction:Direction; valid_until:datetime; quality:str; generated_at:datetime|None=None; data_mode:str='UNKNOWN'; strategy_id:str=''; strategy_version:str=''
 @classmethod
 def from_signal(cls,s): return cls('intent:'+s.signal_id,(s.signal_id,),s.instrument_id,s.direction,s.valid_until,s.quality,s.generated_at,s.data_mode,s.strategy_id,s.strategy_version)
def resolve_conflict(signals):
 ds={s.direction for s in signals}; return 'ALIGNED' if len(ds)<=1 else 'CONFLICTING'
