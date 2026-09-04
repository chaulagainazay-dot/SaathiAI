# D14 — First-owner bootstrap and operator recovery

This is the operator-facing half of the D14 repair. It describes how an
installation acquires its first owner, and what to do when one is in a state
where it cannot.

Nothing here generates a token. Generating one is a deliberate act performed at
the moment of setup, by a person, on the machine being set up.

## The authentication state machine

| State | Meaning | What is allowed |
|---|---|---|
| `UNINITIALIZED` | No owner, no credential, no bootstrap marker, no sessions/tokens/passkeys. | Bounded health, `GET /api/v1/auth/bootstrap/status`, and nothing else. Every protected route answers 401; every credential-minting route answers 409. |
| `BOOTSTRAP_ARMED` | As above, plus `SAATHI_BOOTSTRAP_ENABLED=true`. | Additionally `POST /api/v1/auth/bootstrap`, which still has to satisfy every condition below. There is still no authenticated owner. |
| `ACTIVE` | Exactly one owner, a scrypt credential in the security store, bootstrap marker written. | Normal login, sessions, API tokens, passkeys. Bootstrap is permanently closed, including across restarts — the marker is in the database, not in a process variable. |
| `CONTAMINATED_UNINITIALIZED` | No bootstrap marker, but the store already holds a user, credential, session, API token or passkey. | Nothing. Bootstrap is refused with `BOOTSTRAP_CONTAMINATED_STATE`, and the planted material is left exactly as found. |

The state is derived from the database on every check. It is not cached in a
process-global boolean, so a second process, a restart, or a worker cannot
disagree with the first about whether the system is owned.

## Creating the first owner

1. **Arm the installation.** `SAATHI_BOOTSTRAP_ENABLED=true` in the environment
   of the backend process. Off by default; leave it off outside setup.

2. **Write an operator token file.** Somewhere outside the git checkout and
   outside any state database — `~/.config/saathi/bootstrap.token` is a
   reasonable choice:

   ```sh
   umask 077
   python3 -c 'import secrets; print(secrets.token_urlsafe(32))' > "$TOKEN_FILE"
   chmod 600 "$TOKEN_FILE"
   ```

   The file must be a regular file (not a symlink — it is opened `O_NOFOLLOW`),
   mode exactly `0600`, owned by the user the backend runs as, containing at
   least 32 characters, and modified within `SAATHI_BOOTSTRAP_TOKEN_MAX_AGE`
   seconds (default 900). Point the backend at it with
   `SAATHI_BOOTSTRAP_TOKEN_FILE=/absolute/path`.

3. **Open `/unlock` on the machine itself** and complete the setup form: the
   token, and the owner password. The request must arrive from a loopback peer
   carrying no forwarding headers, from an allowed Origin.

4. **The token is spent.** On success it is renamed to `<name>.used` (mode
   `0600`) so the same value cannot be presented again, and the marker closes
   bootstrap permanently regardless. Disarm by removing
   `SAATHI_BOOTSTRAP_ENABLED` from the environment.

The password is stored only as a scrypt hash in the security store. It is never
written to `.env`, never held in a process global as authority, and never
logged. The operator token is never persisted, logged, or returned.

### Why the token, and not loopback

Loopback is a transport condition. Anything that can reach the port — another
process, a browser on the machine, a container sharing a network namespace, a
misconfigured proxy — arrives as a loopback peer. The token proves that the
person driving the request could read a file only the operator account can read.
That is an identity claim; "connected from 127.0.0.1" is not.

## Recovering a `CONTAMINATED_UNINITIALIZED` installation

Contamination means the store holds authentication material that no bootstrap
created. On a system that ran a vulnerable build, the likeliest explanation is
that something used the old unauthenticated paths. It is refused rather than
repaired automatically, and nothing is deleted: the rows are the evidence.

Recovery is deliberately manual and deliberately not implemented as an endpoint.

1. Stop the backend.
2. Copy the security database somewhere safe before touching anything.
3. Inspect what is there and when it arrived:
   `users`, `passwords`, `sessions`, `api_tokens`, `passkeys`, `user_roles`, and
   the `audit_log` around those timestamps.
4. Decide, as a person, whether any of it is legitimate.
   - **Nothing legitimate** — the fastest safe path is a new state root: leave
     the contaminated database in place as evidence and bootstrap a clean one.
   - **Something legitimate** (a real owner from an older build, whose marker
     simply predates D14) — this is the case for an explicit, audited marker
     write, performed against a backup, by an operator who can say what each row
     is. It is not a normal operation and has no supported tooling here.
5. Rotate anything the contaminated window could have exposed: the owner
   password, every API token, and any credential stored in connectors.

## Notes for already-`ACTIVE` systems

Existing legitimate sessions, API tokens and passkeys keep working under their
own contracts. There is no mass revocation, because there is no evidence that
would justify one on a system whose bootstrap completed correctly. Bootstrap
stays closed. If you have specific reason to believe a credential was minted
during a vulnerable window, revoke that credential.

## Deferred: D11 shell presentation

D14 changed the unlock screen only where authentication semantics forced it —
the setup form, the retired recovery screens, and the `signed_in` flag, which
the backend used to report `true` to any loopback caller and the shell used to
render an owned UI to a caller who had never signed in.

The wider D11 presentation work is deliberately untouched and still outstanding:

- the shell's own signed-in/signed-out treatment beyond `/unlock`, now that
  `signed_in` reflects an actual session rather than a network position;
- surfacing `CONTAMINATED_UNINITIALIZED` somewhere an operator will see it
  outside the setup panel;
- the Security settings password flow against `POST /api/v1/auth/password`;
- removing the remaining `has_password` shell reads, which describe an
  environment variable rather than the canonical credential.
