# M39 — Leak Validation

## Runtime evidence scan

**CLEAN** (offline preparation payloads)

Scanner reports locations + redacted previews only — never matching secret values.

## Repository scan

Evidence generation records deferred full-repo scan note; operator/CI must scan
diff and evidence after any live run.

## Stop condition

Any confirmed plaintext leak → immediate stop; revoke disposable credential;
do not commit until cleaned.
