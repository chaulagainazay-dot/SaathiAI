# M46 — Security Review

## Threats mitigated

| Threat | Control |
|--------|---------|
| Unapproved live call | live_flag + SAATHI_M46_LIVE_GATE + preflight |
| Self-asserted runtime | M45 attested snapshot required |
| Write/deploy/production | hard-false flags; fail if true |
| Secret leakage | reference-only; leakscan; no secret in evidence |
| Replay approval/plan | seen_ids + expiry + integrity HMAC |
| Silent phase chaining | commands stop at manual boundaries |
| Authority inflation | hard-coded grants_*=false |

## Residual risks

- Live path depends on operator hygiene for disposable credentials.
- Local HMAC is integrity, not hardware root of trust.
- Host compromise can spoof observation — out of scope for M46 offline.
