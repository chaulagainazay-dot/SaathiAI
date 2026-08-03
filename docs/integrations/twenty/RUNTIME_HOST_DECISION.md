# Twenty private runtime-host decision package

No runtime, host, account, subscription, or paid resource was created.

## Decision summary

- Preferred: **Option C — private temporary development host**.
- Fallback: **Option B — owner-approved lightweight local container runtime for
  short bounded sessions only**, after stopping other heavy local workloads.
- Local Docker Desktop: `NOT_RECOMMENDED_FOR_PERSISTENT_USE` on this 8 GB Mac.
- Owner approval required before installing software, creating an account,
  provisioning infrastructure, starting a paid trial, or incurring cost.

Recommended minimum for a temporary host is 4 vCPU, 8 GB RAM, and 40 GB encrypted
SSD. Twenty's audited documentation states a lower 2 GB minimum, but that does not
include a conservative allowance for server, worker, PostgreSQL, Redis, browser
verification, backups, and evidence collection together. Runtime measurements
must replace this planning estimate during M367.

## Option comparison

| Option | Resource/operational assessment | Decision |
| --- | --- | --- |
| A. Local Docker Desktop | Adds a persistent Linux VM, image/cache disk, server+worker+Postgres+Redis memory, and competes with Ollama, SaathiOS, Next.js, and Playwright. Easy UI but highest persistent local overhead. | Not recommended for persistent use; do not install without owner approval. |
| B. Colima, OrbStack, Rancher Desktop, or Podman machine | May reduce idle overhead or improve controls, but still requires a Linux VM and the same application containers/data. Product licensing, compatibility, networking, volume, and Apple Silicon behavior remain untested. | Fallback for a short session only; install none in this milestone. |
| C. Private temporary development host | Isolates workload from the Mac and supports repeatable resource measurement and clean destruction. Requires private networking, host hardening, firewall/TLS, backup handling, and cost control. | Preferred after explicit owner approval. |
| D. Existing private server | Avoids provisioning only if an owner-controlled host actually exists and passes capacity, isolation, patching, backup, and no-conflicting-workload checks. | Viable conditional alternative; existence not assumed. |
| E. Hosted Twenty service | Removes host operations but creates an external account/workspace and introduces vendor, residency, privacy, availability, subscription, and deletion concerns. | Architectural possibility only; not preferred for synthetic contract validation. |

## Preferred-host controls

- Private address or private overlay only; deny public ingress by default.
- Firewall allow only operator access and the minimum private application path.
- TLS for any non-loopback hop; no public DNS required.
- Pinned image digest and configuration, encrypted disk, patched host, separate
  prefixed volumes/network, synthetic data only, and no email/OAuth integrations.
- Secrets created only after authorization, held through references, never Git or
  reports; least-privilege read token only when M363 begins.
- Encrypted backup with checksum and restore test; no dump committed.
- Cost ceiling, expiry date, owner, shutdown procedure, and destroy-after-validation
  checklist established before provisioning.
- Final removal includes containers, prefixed volumes/network, host, tokens, and
  backups according to the approved retention record.

## Unresolved risks

Published image digest/architecture support, actual RAM/disk behavior, generated
workspace schemas, role granularity, outbound dependencies, webhook reachability,
backup/restore reliability, upgrade behavior, and data-deletion completeness remain
unverified. A host decision reduces local pressure; it does not validate Twenty.
