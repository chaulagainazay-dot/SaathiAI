# M57 Process Management & Ownership

## Ownership model
- **Recognize** a SaathiOS process by command signature: backend matches
  `uvicorn saathi.server:app` or `-m saathi.server`; frontend matches
  `next-server`/`next dev` **and** a `saathi-os` working directory.
- **Reuse** a backend only after canonical provenance validation: exact
  repository/CWD, package path reported by `/api/v1/platform/provenance`, and
  the canonical security/platform database paths must match. A foreign
  worktree on port 8765 is `provenance-mismatch`, never reusable or killed.
- **Own** (for stopping) only processes recorded in the launcher's PID files
  (`~/.saathi/run/{backend,frontend}.pid`). The launcher reuses only a healthy,
  provenance-matched SaathiOS process and **stops only what it started**.

## Start
Resolves the repo, verifies `curl`, then classifies ports 8765 and 3000. If a
healthy SaathiOS process already serves a port, it is **reused and left as-is**.
If a port is held by an **unrelated** process, the launcher **fails closed** and
never kills it. Otherwise it starts the backend on `127.0.0.1:8765` and the
frontend on `localhost:3000` with the explicit API base, waits for readiness, and
only then reports success. A `launcher.lock` prevents duplicate start storms.

**Build-toolchain checks are role-conditional (M336–M343).** The Python venv is
required only when the launcher must spawn the backend itself, and
`saathi-os/node_modules` only when it must spawn the frontend — those are the
only paths that use them. Each spawn path still aborts non-zero when its
toolchain is missing. A role that is reused rather than spawned needs neither, so
the documented reuse path is no longer gated on developer build artifacts, and a
real blocker (unhealthy or unrelated listener) is reported as itself rather than
being masked behind a generic "environment not ready" message.

## Stop
Graceful `SIGTERM` first, bounded 10 s wait, then `SIGKILL` **only** for
owned processes. Removes stale PID records. Unrelated Node/Python/npm/Next.js/
uvicorn processes are never touched.

## Stale recovery
A PID file pointing at a dead or non-matching PID is treated as **not owned** and
is safe to clean; `status`/`doctor` report it.
