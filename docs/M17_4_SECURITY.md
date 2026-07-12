# M17.4 Harness Security
Install: path-hijack rejection (binary must be system/brew/Applications), arbitrary
URL + embedded-command refusal, unknown-method + unpinned-source refusal, real
smoke test + sha256. Update: trust RESET to source_pinned (never auto-trusted),
rollback backup. Revocation: disable/quarantine/revoke/uninstall block execution +
preserve evidence. Adapter: argv-only, sanitized env, minimal PATH, file-root
confinement, RLIMIT CPU/AS/FSIZE + wall-clock + artifact cap. Verifiers: ZIP-slip,
zip-bomb (ratio + uncompressed cap), XXE, oversize/secret-pattern rejection.
Red-team 75/75 incl. path-hijack, install-URL, update-hijack, revoke, zip-bomb,
dep-blocked, resource-limits.
