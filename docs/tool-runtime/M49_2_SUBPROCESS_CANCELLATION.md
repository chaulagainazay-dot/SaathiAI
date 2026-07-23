# M49.2 Subprocess Cancellation

`saathi.tool_runtime.subprocess_exec.run_bounded`:
- no shell=True
- argv only
- bounded env
- process group / start_new_session
- SIGTERM → grace → SIGKILL optional
- states: CANCELLATION_REQUESTED, TERMINATION_SENT, KILL_SENT, PROCESS_EXIT_CONFIRMED, ...

CANCELLED only when process exit confirmed.
