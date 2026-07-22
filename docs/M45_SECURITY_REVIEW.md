# M45 — Security Review

## Threat model

Attackers may try to:

- self-assert runtime safety flags (M44 gap);
- replay or forge snapshots;
- claim hardware attestation without hardware;
- smuggle secrets into evidence;
- treat readiness as execution authority.

## Mitigations

| Threat | Control |
|--------|---------|
| Self-asserted gates | Collector + integrity; SELF_REPORTED insufficient |
| Tampering | Canonical fingerprint + HMAC signature |
| Replay | `seen_snapshot_ids` + short TTL |
| Expiry bypass | `expires_at` enforced |
| Secret leakage | collector never reads secrets; leakscan on all outputs |
| Authority escalation | hard-coded `authorizes_execution: false` |
| Hardware pretence | `HARDWARE_ATTESTED` rejected; flag unsupported |
| Parallel auth system | composes M44; does not replace it |

## Invariants

- Deny-by-default empty snapshot
- No execution / write / deploy / production authority
- M32 prohibition unchanged
- Trading Guardian unengaged
- Historical M39–M44 evidence never rewritten

## Residual risks

- Local HMAC is not operator identity and not hardware root of trust.
- Git/process observation can be spoofed on a fully compromised host — future
  hardware attestation would be a separate milestone.
- CLI readiness still requires a separately authorized execution step.
