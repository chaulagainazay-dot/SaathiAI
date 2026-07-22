# M36 — Sandbox Account Qualification

## Classifications

| Class | Meaning |
|-------|---------|
| `DISPOSABLE_SANDBOX` | Operator-attested disposable sandbox identity |
| `NON_PRODUCTION_TEST` | Non-production test identity |
| `REJECTED` | Fail closed |
| `UNKNOWN` | Insufficient evidence |

## Checks

Provider, safe alias (no email), environment (non-production), declared purpose,
absence of production usage / important data (declared), revocation plan,
expiration/deletion plan, operator disposable acknowledgement.

## Honesty

SaathiOS **cannot independently guarantee** an external account is disposable.
Operator acknowledgement is combined with available declared evidence.

## Rejects

Production, personal, financial, trading, payment, cloud-admin, email/calendar
business-critical identities; missing revocation/deletion plans; personal email aliases.
