# M43.1 — Environment Diagnosis (read-only)

Starting commit: `57ad589`. No source changed while producing this diagnosis; all
findings come from read-only inspection. No secret value was read, printed, or stored.

## Executive finding

The M43 live prerequisites are **absent**, not **inaccessible**. The prior M43 outcome
attributed the block to artifacts "not visible to the execution environment." Direct
inspection shows the opposite: the execution environment can reach the login Keychain and
the operator-local filesystem fully. Both prerequisites simply **do not exist yet** — they
were never provisioned.

There is **no** sandbox boundary, user mismatch, session boundary, lock state, stale
environment, or Full-Disk-Access problem blocking access. Once the operator provisions the
two artifacts in this same login session, the existing M43 CLI reaches them with **zero
code changes**.

## Execution-environment context (evidence)

| Property | Value |
|---|---|
| user / euid | `macbookpro` / `501` (operator's own account) |
| group membership | `staff`, `admin`, `_developer`, `access_ssh` |
| shell / HOME / cwd | `/bin/zsh` / `/Users/macbookpro` / `/Users/macbookpro` |
| terminal | `Apple_Terminal` (`com.apple.Terminal`), **not** SSH |
| launchd session owner uid | `501` (GUI login session, matches operator) |
| sandboxed | no (`APP_SANDBOX_CONTAINER_ID` unset, no seatbelt) |
| repo root / HEAD | `/Users/macbookpro/SaathiAI` @ `57ad589` |

The Claude Code tool environment runs as the operator, in the operator's GUI login
session — the same security context that can mint and store the credential.

## Keychain accessibility (evidence)

* `security list-keychains` → login keychain present in search list.
* `security show-keychain-info login.keychain-db` → **`no-timeout` (unlocked)**.
* Capability round-trip with a **non-secret dummy value** on a throwaway probe service
  (`saathi_m43_probe`): `add` → `find` (metadata) → `find -w` (read-back matched) →
  `delete` → confirmed absent. **The environment can add, find, read, and delete generic
  passwords in the login Keychain.**
* Target item lookup — `security find-generic-password -s saathi_m43 -a github_meta`
  (metadata only, no `-w`, no secret printed) → **rc=44 `errSecItemNotFound`**.

Conclusion: the Keychain is reachable and writable/readable by this environment; the
target item `saathi_m43:github_meta` **has never been created**.

## Approval-record accessibility (evidence)

* Only the template exists: `docs/m41/operator_canary_approval.template.json`.
* No filled operator record anywhere: no `docs/m41/operator_canary_approval.local.json`,
  no `*.local.json` operator approval under the repo or `~/.claude`.
* `.gitignore` had **no** rule protecting an operator-local approval record from
  accidental commit (previously flagged risk).

Conclusion: the approval record was never authored. The path is fully readable by the
environment; the file is simply absent.

## Credential wiring is correct (no fix needed)

`saathi/credentials/m39.py::MacOSKeychainReferenceBackend` parses the operator locator
`saathi_m43:github_meta` into service `saathi_m43` / account `github_meta` and reads it
with `security find-generic-password -s saathi_m43 -a github_meta -w` — exactly the item
the operator guide instructs the operator to create. It never writes/deletes the item
(fail-closed: `keychain_put/delete_not_supported_in_m39`) and never logs the value. The
M43 validation phase's other input, `docs/evidence/m40/live_certification_record.json`,
**is present**.

## Root cause

The disposable read-only GitHub PAT (Keychain `saathi_m43:github_meta`) and the filled +
validated M39.3 approval record were **never provisioned** in any environment. The M43
milestone closed BLOCKED and no one created them afterward. The block is provisioning
absence, not an execution-environment isolation defect.

## Why no code remediation can "reach" them

The two missing artifacts require **operator-only actions that the execution environment
must not perform**:

1. Minting a real disposable read-only PAT is an action at github.com. Fabricating a token
   would violate the M43.1 prohibitions (`NO persistent raw secret`, `NO fabricated
   machine evidence`).
2. Storing it in the Keychain must happen at the operator TTY (`security … -w`, value
   entered at the prompt) so the secret never transits chat, args, or history.
3. The approval record encodes **operator attestation** (decision + five acknowledgement
   tokens); the operator must author and sign it.
4. The revocation phase requires the operator to revoke the PAT **externally at GitHub** —
   also not performable by the environment.

## Secure remediation options

* **(chosen) Provisioning + ignore-hardening.** Add a `.gitignore` rule so the
  operator-local approval record can never be committed, then have the operator provision
  both artifacts in *this* login session using the existing operator guide commands. No new
  credential path, approval path, evidence model, or runner. Once present, the unchanged
  M43 CLI runs.
* Relaunch / re-user the environment — **not applicable**: already running as the owning
  operator in the owning GUI login session with an unlocked keychain.
* Artifact-discovery option / secure wrapper — **not needed**: the existing
  `--approval-file <path>` + `--locator saathi_m43:github_meta` inputs already resolve
  correctly from this environment.

## Rejected unsafe workarounds

* Fabricating or hard-coding a PAT, or writing one to a plaintext/`.env`/temp/JSON file.
* Copying or exporting the token into an environment variable or command-line argument.
* Weakening M39.3 validation or the Keychain-only credential isolation.
* Generating a machine record without a real live 200→revoke→401 chain.
* Reclassifying the offline rehearsal (`SIMULATED_REHEARSAL`) as a live run.

## Verdict

**Environment: READY. Prerequisites: ABSENT (operator provisioning required).** The
correct next step is operator provisioning in this session, not a code change. If the
operator provisions the two artifacts here, the diagnosis predicts the existing M43 live
phases will reach them unchanged.
