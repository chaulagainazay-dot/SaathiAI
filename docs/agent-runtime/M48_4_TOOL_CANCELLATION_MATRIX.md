# M48.4 — Tool Cancellation Matrix

| adapter | class |
|---|---|
| AgentExecutor.run_turn | COOPERATIVE_CANCEL_SUPPORTED (CancellationToken) |
| AgentExecutor.request_tool | COOPERATIVE_CANCEL_SUPPORTED |
| ChatLLMAdapter | TIMEOUT_ONLY / cooperative via run cancel |
| local-llm-inference gateway | TIMEOUT_ONLY |
| video-generation | TIMEOUT_ONLY |
| unknown tools | no-op recorded, not faked |

Uncertain mutations: no blind retry (M48.3 classify_retry).
