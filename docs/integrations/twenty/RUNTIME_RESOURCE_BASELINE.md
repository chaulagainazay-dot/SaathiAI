# Twenty runtime resource baseline

These are conservative planning envelopes, not measured Twenty benchmarks and
not production sizing guidance.

## Workload decomposition

| Component | Planning concern | Validation allowance |
| --- | --- | --- |
| Twenty server/UI | Node process, UI assets, API schema | 1.5–3 GB RAM estimate |
| Worker | background queue processing | 0.5–1.5 GB RAM estimate |
| PostgreSQL | synthetic records, metadata, indexes | 0.5–1.5 GB RAM; 10–15 GB disk allowance |
| Redis | queues/cache only | 0.1–0.5 GB RAM; bounded persistence |
| Operating system/runtime | kernel, container engine, agents | 1–2 GB RAM estimate |
| Logs/evidence | capped logs, schemas, transcripts | 5 GB disk allowance |
| Backup/restore | encrypted backup plus disposable restore | 10–20 GB temporary disk allowance |
| Source build | Yarn/Nx compilation and caches | outside runtime floor; prefer 8 vCPU/16 GB/80 GB if approved |

## Thresholds

| Resource | Minimum viable | Recommended | Abort threshold |
| --- | --- | --- | --- |
| CPU | 4 vCPU | 4–8 vCPU | sustained >90% for 10 minutes or health timeout |
| RAM | 8 GB | 12 GB | sustained >85%, OOM, or growing swap pressure |
| Swap | 0–2 GB available safety margin | no sustained swap | >2 GB used by session or continuous growth |
| Encrypted disk | 40 GB | 60 GB | less than 15 GB free reserve |
| Free-disk reserve | 15 GB | 25 GB | reserve below 15 GB |
| Bandwidth | stable 10 Mbps private path | 25 Mbps | repeated timeout/loss or unexpected external route |
| Session duration | maximum 4 hours initially | maximum 8 hours after stable measurement | expiry or approved maximum reached |

The proposed 4 vCPU, 8 GB RAM, 40 GB encrypted SSD baseline is accepted only as
a safe bounded validation floor for prebuilt pinned images and synthetic data. It
is not proof that Twenty will fit, and it is insufficiently evidenced for a source
build. Record CPU, RSS, swap, disk, network, health latency, and growth at startup,
idle, read load, backup, restart, and restore checkpoints.

The local 8 GB Mac is not a safe persistent host because the OS already reports
substantial encrypted swap use. Local disk availability does not mitigate unified
memory pressure, image architecture uncertainty, or interference with Ollama and
browser workflows.
