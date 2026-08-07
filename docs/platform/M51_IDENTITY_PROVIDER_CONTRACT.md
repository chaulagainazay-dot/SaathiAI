# M51 Identity Provider Contract

## Types

- `IdentityProvider` (ABC)
- `IdentityAssertion`
- `AuthenticationMethod`
- `AuthenticationResult`
- `CredentialVerificationResult`
- `ExternalIdentityLink` (table reserved)

## Local-alpha methods

- `LOCAL_PASSWORD` (scrypt hashes)
- `LOCAL_MAGIC_CODE_FIXTURE`
- `DEVELOPMENT_BOOTSTRAP`

## Replacement property

A production OIDC provider can implement `IdentityProvider.authenticate` and
map external subject → platform user without replacing memberships, RBAC,
sessions, approvals, or audit.
