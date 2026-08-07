# TRADING_GUARDIAN_COMPOSITION

`compose_guardian_with_risk(guardian, risk_engine, intent, ...)`:

1. TG.evaluate (existing checks)
2. RiskEngine.evaluate_proposed_trade
3. If risk BLOCK or DATA_INSUFFICIENT → allowed=false
4. WARN does not alone deny
5. Never authorizes execution

PaperTradingService may call this later without replacing TG.

