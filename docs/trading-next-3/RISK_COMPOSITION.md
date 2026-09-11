# RISK_COMPOSITION

Construction does **not** reimplement hard risk.

Flow: candidate target → projected trades → PortfolioRiskEngine.evaluate_proposed_trade → ALLOW / WARN / BLOCK.

- BLOCK → proposal status RISK_BLOCKED (cannot READY_FOR_APPROVAL)
- WARN → may elevate to READY_FOR_APPROVAL with RISK_WARN warning
- TG composition is additive via `tg_compose.compose_proposal_with_tg` (optional intent_factory)

