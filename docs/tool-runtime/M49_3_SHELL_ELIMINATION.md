# M49.3 Shell Elimination

Freeform `run_shell` / `project_run` / `applescript` are **PROHIBITED** at runtime.

`run_bounded` refuses `shell=True` and shell executables.

## Allowlisted commands

- `echo_ok`: Deterministic echo for cancel/timeout tests (timeout=10.0s)
- `git_rev_parse_head`: Git HEAD SHA (timeout=10.0s)
- `git_status`: Git status short (repo root only) (timeout=15.0s)
- `ls_data_files`: List data/files directory (timeout=10.0s)
- `pwd`: Print working directory (timeout=10.0s)
- `python_version`: Local python version string (timeout=10.0s)
- `uname`: Kernel/OS identity (read-only) (timeout=10.0s)

Rules: code-owned executable, shell=False, cwd roots validated, env keys bounded, process group owned, cancellation truthful.
