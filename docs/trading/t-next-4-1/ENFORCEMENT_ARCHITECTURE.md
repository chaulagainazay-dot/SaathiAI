# T-NEXT-4.1 Enforcement Architecture

Every paper submission enters through `ExecutionGateway`, the registered paper
tool, and `PaperTradingService.submit_order`. The service checks startup
recovery, `ReconciliationAuthority`, and `SubmissionAttemptStore` before
Guardian, approval consumption, reservation, or durable order creation.

No live broker or network path exists.
