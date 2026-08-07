# M48.4 — Streaming Contract

Single-agent M8 wrap returns final message (not token deltas). Multi-agent uses run events in RunStore. Cancellation/timeout → non-success terminal states. No stream completion without durable evidence.
