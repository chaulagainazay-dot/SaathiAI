# M49.1 Timeout Contract

Layers: run deadline, tool deadline, adapter timeout, grace.

Child timeout cannot exceed parent remaining deadline.
timeout≤0 rejects. Timeout emits tool.timeout_detected.
Timeout does not claim adapter hard-stopped for non-cooperative tools.
Uncertain mutation after timeout → SIDE_EFFECT_UNKNOWN, not retryable.
