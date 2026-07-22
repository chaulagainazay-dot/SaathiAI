# M17.5 Audit — Second Live Application Harness (SQLite)
Current: harness platform (M17.3/M17.4) with ONE live app (FFmpeg). sqlite3 present
at /usr/bin/sqlite3. Reusable: ApplicationHarnessAdapter (argv-only), service
(ownership/trust/risk/verify), registry, verify.py. Missing: a second live app +
DB-specific verification. Risks: SQL injection (mitigate: argv separation + query
from constants/validated identifiers + -readonly for reads + reject ATTACH/dot-
commands), file-root escape (confine DB path + reject ATTACH), write on read op.
Non-goals: full SQL surface, external DBs, network. Env: fully available (no
install/permission).
