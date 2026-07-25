# M57 Process Management & Ownership

## Ownership model
- **Recognize** a SaathiOS process by command signature: backend matches
  `uvicorn saathi.server:app` or `-m saathi.server`; frontend matches
  `next-server`/`next dev` **and** a `saathi-os` working directory.
- **Own** (for stopping) only processes recorded in the launcher's PID files
  (`~/.saathi/run/{backend,frontend}.pid`). The launcher **reuses** any healthy
  SaathiOS process it finds, but **stops only what it started**.

## Start
Resolves the repo, verifies the Python venv + frontend deps, checks ports 8765
and 3000. If a healthy SaathiOS process already serves a port, it is **reused and
left as-is**. If a port is held by an **unrelated** process, the launcher **fails
closed** and never kills it. Otherwise it starts the backend on `127.0.0.1:8765`
and the frontend on `localhost:3000` with the explicit API base, waits for
readiness, and only then reports success. A `launcher.lock` prevents duplicate
start storms.

## Stop
Graceful `SIGTERM` first, bounded 10 s wait, then `SIGKILL` **only** for
owned processes. Removes stale PID records. Unrelated Node/Python/npm/Next.js/
uvicorn processes are never touched.

## Stale recovery
A PID file pointing at a dead or non-matching PID is treated as **not owned** and
is safe to clean; `status`/`doctor` report it.
