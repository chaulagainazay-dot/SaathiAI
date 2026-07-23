# M49.1 Secret Policy

Policies: NO_SECRET, OPTIONAL_SECRET_REFERENCE, REQUIRED_SECRET_REFERENCE, BROKERED_CLIENT_ONLY, PROHIBITED.

Raw secret keys/values rejected in generic request payloads.
Evidence/events redacted via `secrets.redact`.
No Keychain, no env dump, no live credential validation in M49.1.
