# M49.4 Freeform Shell Closure Proof

## Required state

`FREEFORM_SHELL_BLOCKED`

## Blocked entrypoints

| Entry | Proof |
|---|---|
| `system.run_shell` | returns freeform_shell_blocked; shell=False |
| `projects.project_run` | always freeform_shell_blocked (M49.4: before project resolve) |
| `system.applescript` | freeform_shell_blocked |
| `execute_tool` for run_shell/project_run/applescript | PROHIBITED disposition |
| `run_bounded(shell=True)` | ValueError |
| shell executables in command_manifest | SHELL_EXECUTABLE_PROHIBITED / SHELL_C_PROHIBITED |

## Allowlisted subprocess

7 code-owned command manifests: `uname`, `python_version`, `echo_ok`, `pwd`, `git_status`, `git_rev_parse_head`, `ls_data_files`.

All use fixed executable + argv, shell=False, timeout, output limits.

## Static markers

`validate_tool_gateway_coverage` freeform scan: only INFO FREEFORM_SHELL_BLOCKED findings; no FREEFORM_SHELL_ACTIVE.

## State

`FREEFORM_SHELL_BLOCKED`
