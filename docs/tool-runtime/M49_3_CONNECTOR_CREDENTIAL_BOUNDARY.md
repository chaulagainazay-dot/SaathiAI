# M49.3 Connector Credential Boundary

Connector tools receive brokered client / session reference / credential handle only.

They must not receive: access token, refresh token, password, cookie, authorization header, private key, raw API key.

Enforced via:
- secret policy BROKERED_CLIENT_ONLY / NO_SECRET
- `find_secret_violations` on arguments
- redaction of evidence/events/results
- dry-run previews strip secret keys
