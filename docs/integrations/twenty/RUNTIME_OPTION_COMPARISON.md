# Twenty runtime option comparison

No provider, product, account, or operator is selected by this document.

| Criterion | Private temporary development host | Lightweight local runtime | No runtime |
| --- | --- | --- | --- |
| Current decision | Preferred future option; not approved | Fallback only; not installed | Safest present state |
| CPU/RAM | Select at or above validated baseline | Competes for 8 GB unified memory | No added load |
| Storage | Dedicated encrypted volume; explicit deletion | Consumes local image/volume space | No added footprint |
| Architecture | Prefer a native architecture with verified image manifests | ARM64 compatibility and emulation remain unproven | Not applicable |
| Network | Private subnet/VPN, deny-by-default firewall | Loopback/private container network | No exposure |
| Access | Named operator through MFA-protected private access | Local owner session only | No operator required |
| Billing | Hourly/ephemeral with cap, alerts, expiry | No host bill; local resource cost | None |
| Snapshot/restore | Encrypted disposable snapshot and restore target | Local encrypted archive; resource pressure risk | Not applicable |
| Reproducibility | Pinned image/config manifest | Same pins required; host contention reduces repeatability | Evidence-only remains reproducible |
| Cleanup | Delete host, volumes, snapshots, rules, DNS, credentials | Remove VM/images/volumes/config and verify disk recovery | Nothing to remove |
| Main risk | Provider/cost/operator not selected | High swap, thermal, disk, and tooling contention | Runtime questions stay unanswered |

## Option A — Private temporary development host

Minimum decision inputs are provider/operator, architecture, region, private
network, encrypted storage, cost ceiling, payer, start/expiry/removal dates, and
named operator. The host must support snapshot/restore, auditable firewall rules,
MFA-protected operator access, and verified deletion. Expected cost remains a
provider-dependent estimate until selection. This is the recommended future path.

## Option B — Lightweight local container runtime

The owner Mac is ARM64 with 8 GB RAM and currently has about 5.3 GB of 6 GB swap
in use. The source clone alone is about 468 MB; image and volume footprints have
not been measured. Any runtime would compete with SaathiOS, Ollama, browsers, and
development tools. Emulation could amplify CPU, memory, thermal, and session-time
risk. Persistent use is not recommended. No Docker, Colima, Podman, Lima,
OrbStack, or Rancher Desktop installation is authorized.

## Option C — No runtime

Postponement preserves the certified offline boundary at zero runtime, network,
credential, and cost risk. It is safer than either unapproved option while CI,
image digests, operator, billing, webhook routing, and host controls remain open.
It leaves live API, schema, persistence, and resource behavior unvalidated.

## Decision

`PRIVATE_TEMPORARY_DEVELOPMENT_HOST_RECOMMENDED`, subject to every M361 entry row
becoming `PASS`. Until then, the effective option is no runtime.
