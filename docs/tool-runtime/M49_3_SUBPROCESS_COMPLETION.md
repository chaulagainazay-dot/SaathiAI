# M49.3 Subprocess Completion

States: STARTING → RUNNING → CANCELLATION_REQUESTED → SIGTERM_SENT → GRACE_WAIT → SIGKILL_SENT → EXIT_CONFIRMED / CANCELLATION_UNCONFIRMED / TIMEOUT_CONFIRMED / OUTCOME_UNKNOWN / COMPLETED.

Rules:
- process group owned (`start_new_session=True`)
- termination targets process group where supported
- cancellation success requires confirmed exit
- timeout is distinct from user cancellation
- shell executables rejected
- platform: verified on macOS local + CI Linux where applicable
