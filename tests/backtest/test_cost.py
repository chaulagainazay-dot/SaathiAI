from decimal import Decimal
from saathi.platform.backtest.cost import *
def test_crypto_cost_and_marketable_prices():
 m=CryptoCostModel(fee_bps=10,slippage_bps=5)
 c=m.estimate('BINANCE:BTC/USDT','BUY',Decimal('100'),Decimal('101'),Decimal('1'))
 assert c.total_cost==Decimal('1.1515') and m.fill_price('BUY',Decimal('101'),Decimal('99'))==Decimal('101.0505')
def test_no_zero_cost_fallback_and_nepse_unverified():
 assert UnverifiedCostModel().estimate().status=='COST_MODEL_UNAVAILABLE'
 assert NepseCostModel().estimate().status=='NEPSE_COST_POLICY_UNVERIFIED'
def test_stress_and_invalid_inputs_fail_closed():
 m=CryptoCostModel(fee_bps=10,slippage_bps=5)
 assert m.stress(2).fee_bps==Decimal('20')
 for kwargs in ({'fee_bps':-1},{'slippage_bps':-1}):
  try: CryptoCostModel(**kwargs).estimate('X','BUY',1,1,1); assert False
  except ValueError: pass
