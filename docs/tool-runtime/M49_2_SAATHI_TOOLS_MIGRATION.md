# M49.2 saathi.tools Migration

| Legacy | Canonical | Status |
|---|---|---|
| system_health | m49.system_health | MIGRATED |
| my_files (list) | m49.my_files_list | WRAPPED list-only |
| manage_tasks (list) | m49.list_open_tasks | WRAPPED list-only |
| run_shell freeform | — | BLOCKED (use subprocess_diag allowlist) |
| send_email | m49.connector.gmail.send_message stub | STUB / not live |
| Others | — | DEFERRED |
