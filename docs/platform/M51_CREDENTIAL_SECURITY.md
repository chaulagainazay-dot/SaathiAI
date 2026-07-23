# M51 Credential Security

- Algorithm: **scrypt** (stdlib); PBKDF2 still verifiable for migration.
- Min length 12, complexity rules, trivial denylist.
- Password change revokes other sessions.
- Never store plaintext passwords or raw tokens.
