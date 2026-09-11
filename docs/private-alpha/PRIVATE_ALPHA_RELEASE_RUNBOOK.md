# Private Alpha — Release Runbook

**Scope** A bounded, local, invite-only private-alpha release on a single machine.
This runbook does **not** cover public deployment, and following it does not
authorize one.

**Rule** A private-alpha release is never automatic. Automation prepares
evidence; a human owner decides. `OWNER_REVIEW_REQUIRED`.

---

## 0. Prerequisites

| Requirement | Check |
| --- | --- |
| Owner is present and will personally review | ask |
| macOS on arm64, Python 3.11/3.12, Node ≥ 18 | `bin/saathi-alpha prepare` |
| ≥ 5 GB free disk | `bin/saathi-alpha prepare` |
| 8 GB memory recommended | `bin/saathi-alpha prepare` |
| No public exposure intended | confirm with owner |
| Testers identified, invitations not yet sent | list them |

If `prepare` reports `install_complete: false`, that is an un-run install step,
not a failed host. Complete step 3 and re-run.

## 1. Fix the approved SHA

```bash
git -C <repo> rev-parse HEAD          # record the FULL sha, not the abbreviation
git -C <repo> status --short          # must be empty
git -C <repo> log -1 --format='%H %s'
```

Record the full SHA in the release evidence. Every later step — and the whole
rollback runbook — refers to this value. Never rely on the abbreviated form.

## 2. Environment preflight

```bash
bin/saathi-alpha prepare
bin/saathi-alpha doctor
```

`doctor` must report `public_listener_regression: false`. If any SaathiOS process
is listening on `0.0.0.0` or `*:`, **stop** and remediate; a private alpha may
never be publicly reachable.

## 3. Dependencies

```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
cd saathi-os && npm install && cd -
```

Re-run `bin/saathi-alpha prepare` and confirm `install_complete: true`.

## 4. Database migration

```bash
.venv/bin/python -m saathi.ops db          # integrity + schema check
```

The private-alpha database is `data/platform/platform.db`. Take a backup
**before** any migration (step 5) — never migrate an unbacked database.

## 5. Configuration and secret validation

```bash
.venv/bin/python -m saathi.ops config
.venv/bin/python -m saathi.ops release-gate
```

The release gate must exit `0` (READY) or `1` (WARN). Any other exit code blocks
the release. Exit `3` means the secret scan found credential-bearing material —
**stop**, and do not attempt to work around it.

Confirm no real credential is present:

- no broker or exchange API key,
- no OAuth client secret,
- no paid-provider key enabled at first run.

Private alpha requests none of these. If any is present, remove it before
releasing.

## 6. Build

```bash
cd saathi-os && npm run build && cd -
```

The production build must complete with no error.

## 7. Start and smoke test

```bash
bin/saathi-local start
bin/saathi-local status
```

`start` must report `SaathiOS localhost is ready`. If a port is held by an
unrelated process, the launcher refuses to kill it and fails closed — resolve
that process manually and retry. The launcher never kills a process it does not
own.

## 8. Health validation

```bash
curl -s http://127.0.0.1:8765/api/v1/platform/health
.venv/bin/python -m saathi.platform.tg operations control-center
```

All seven health domains must report. Any domain in a failed state blocks the
release.

## 9. End-to-end journey

```bash
.venv/bin/python -c "from saathi.platform.private_alpha.journey import run_private_alpha_journey as j; print(j()['verdict'])"
```

Must print `PRIVATE_ALPHA_E2E_JOURNEY_PASSED`.

## 10. Browser validation

```bash
cd saathi-os && npm run cert:m343 && cd -
```

Must reach
`PRIVATE_ALPHA_LAUNCH_READINESS_BROWSER_CERT_PASSED_WITH_LIMITATIONS`.

## 11. Owner approval — human gate

Open `/operations/private-alpha-readiness` and review, in person:

- the verdict and the maximum state,
- the regression-debt closure evidence,
- the user-journey result,
- reliability, soak and recovery results,
- the security section and the authority locks,
- the known limitations.

**The owner records the decision outside this tooling.** No automation may set
owner approval to passed. It stays `OWNER_REVIEW_REQUIRED` until a human says
otherwise.

## 12. Invite the testers

Only after step 11.

```bash
# owner session required
.venv/bin/python -m saathi.platform invite --email <tester@example.com> --role viewer
```

Send each tester:

- the invitation link,
- `docs/private-alpha/PRIVATE_ALPHA_TESTER_GUIDE.md`,
- `docs/private-alpha/PRIVATE_ALPHA_SCOPE.md` (so expectations are set before
  they start).

One invitation per tester. Invitations are single-use.

## 13. Release evidence

Record in `docs/private-alpha/m336_m343_evidence/`:

- the full approved SHA,
- the release-gate output,
- the backend and frontend suite results,
- the production build log,
- the browser certification report,
- the journey report,
- the launch checklist,
- the owner-review status (which remains `OWNER_REVIEW_REQUIRED` until the owner
  personally records otherwise).

## 14. Post-release monitoring

For the first week of the alpha, daily:

```bash
bin/saathi-local status
.venv/bin/python -m saathi.ops storage
.venv/bin/python -c "from saathi.platform.private_alpha.prepare import doctor; import json; print(json.dumps(doctor()['ok']))"
```

Watch for: database growth, log growth, unresolved alerts, failed missions,
and any listener that is not bound to localhost.

---

## Stop conditions

Stop the release immediately, and do not proceed, if any of these is true:

- the release gate exits with anything other than 0 or 1,
- `doctor` reports a public listener,
- the end-to-end journey does not pass,
- browser certification does not pass,
- a real credential is found anywhere in the tree,
- the working tree is dirty at the approved SHA,
- the owner has not personally reviewed.

See [`PRIVATE_ALPHA_ROLLBACK_RUNBOOK.md`](PRIVATE_ALPHA_ROLLBACK_RUNBOOK.md).
