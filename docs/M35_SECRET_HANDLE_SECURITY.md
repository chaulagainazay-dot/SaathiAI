# M35 — Secret Handle Security

`SecretHandle` (`saathi/credentials/m35.py`) is the only boundary in which secret
material may exist during a session. It wraps the fields returned by the M31
broker's `inject_secrets`; it never fetches secrets itself.

## Guarantees (all test-covered)

| Property | Mechanism |
|----------|-----------|
| Non-printable | `__repr__`/`__str__` return `<SecretHandle … REDACTED>` |
| Non-serializable | `__reduce__`/`__getstate__`/`to_json` raise; `json.dumps` raises `TypeError` |
| No pickling | `__reduce__` raises `handle_not_serializable` |
| Log/traceback-safe | no secret in any string form the object can produce |
| Zeroized on close | mutable `bytearray` buffers overwritten with `0`, then cleared |
| Use-after-close rejected | `handle_closed` |
| Session-bound | `use`/`matches_fingerprint` require the correct `session_id` |
| Lease/provider/account-bound | recorded at construction, checked on use |
| Equality-safe | `__eq__` is identity-only; never compares against arbitrary strings |
| Context-managed | `__enter__/__exit__` close and zeroize on scope exit |

## Access pattern

The secret value is exposed only through `use(field, consumer, session_id=…)`,
which passes the value to a caller-supplied callable inside the session. The raw
value never becomes a return value of the handle and is never written to evidence,
events, or logs. `matches_fingerprint` allows a constant-time comparison against a
non-reversible fingerprint without exposing the secret.
