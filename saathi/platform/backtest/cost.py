"""Versioned deterministic simulation cost policies; no production authority."""
from dataclasses import dataclass
from decimal import Decimal
@dataclass(frozen=True)
class CostEstimate:
 explicit_fee:Decimal; spread_cost:Decimal; slippage_cost:Decimal; total_cost:Decimal; currency:str; status:str; policy_version:str
class CryptoCostModel:
 def __init__(self,fee_bps='10',slippage_bps='5',version='crypto-spot-v1'): self.fee_bps=Decimal(str(fee_bps)); self.slippage_bps=Decimal(str(slippage_bps)); self.version=version
 def stress(self,multiple):
  if Decimal(str(multiple))<0: raise ValueError('invalid stress')
  return CryptoCostModel(self.fee_bps*Decimal(str(multiple)),self.slippage_bps*Decimal(str(multiple)),self.version+':x'+str(multiple))
 def estimate(self,instrument,side,reference,best_price,quantity):
  ref=Decimal(reference); px=Decimal(best_price); qty=Decimal(quantity)
  if min(ref,px,qty)<0 or self.fee_bps<0 or self.slippage_bps<0: raise ValueError('invalid cost input')
  spread=abs(px-ref)*qty; fee=px*qty*self.fee_bps/Decimal('10000'); slip=px*qty*self.slippage_bps/Decimal('10000')
  return CostEstimate(fee,spread,slip,fee+spread+slip,'USDT','CONFIGURED_ASSUMPTION',self.version)
 def fill_price(self,side,ask,bid):
  ask,bid=Decimal(ask),Decimal(bid)
  if bid<=0 or ask<=0 or bid>ask: raise ValueError('invalid quote')
  p=ask if side=='BUY' else bid; adj=p*self.slippage_bps/Decimal('10000'); return p+adj if side=='BUY' else p-adj
class UnverifiedCostModel:
 def estimate(self): return type('Unavailable',(),{'status':'COST_MODEL_UNAVAILABLE'})()
class NepseCostModel:
 def estimate(self): return type('Unavailable',(),{'status':'NEPSE_COST_POLICY_UNVERIFIED'})()
