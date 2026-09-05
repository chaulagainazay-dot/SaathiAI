# Bypass Audit

The mutation path is `ExecutionGateway → registered paper tool →
PaperTradingService`. Direct service calls still enforce the same gate.
Research, construction, and UI read paths do not submit orders.
