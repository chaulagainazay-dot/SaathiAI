# CANONICAL_BASELINE — SaathiOS

| Field | Value |
| --- | --- |
| **Canonical branch** | `integration/saathios-canonical-baseline` |
| **Canonical SHA (pre-docs tip after M17)** | `272dbd5d0b9495d9682955074a76b4931e440daf` |
| **Source baseline branch** | `hardening/fm-i6.2-macos-memory-gate-fix` |
| **Source baseline SHA** | `e1738d7deec5f44600fbf0d99e2b8f74a4bc83d0` |
| **Worktree** | `/Users/macbookpro/SaathiAI-canonical-baseline` |
| **Established** | 2026-08-07 |
| **Production status** | **NOT production certified** — private-alpha / integration baseline |
| **Live trading authority** | **false** |
| **Broker connectivity** | **false** |
| **Provider connectivity** | **false** (mock/governance only) |
| **Order / withdrawal / leverage authority** | **false** |
| **Local model live certification** | Unchanged — FM-I6.2 LIVE memory-gate **DENIED** on prior cert host |
| **Memory thresholds** | **Unchanged** (combined macOS gate; no lowering) |

## Contained milestone families

Linear ancestry from `master` through:

- M47 UI/UX foundation (on master)
- M48 agent runtime baseline
- M49.1–M49.4 tool runtime / gateway
- M50–M53 platform foundation / agent runtime / ops
- M54–M61 private-alpha product / spatial / workflows
- Trading Guardian M166–M343 (paper, research, observation, connectivity governance, provider contracts, production readiness, private-alpha readiness)
- UI recovery + full E2E functional/security recovery
- Private-alpha product excellence (voice settings)
- M344–M359 multi-agent development foundation
- M369–M376 local model qualification
- M377–M385 AgentHarness design
- FM-C1 / FM-C2 architecture freeze
- FM-I1–FM-I6.2 AgentHarness + LocalModelHarness + memory gate
- **M17 scheduled-graph concurrent recovery fix (this integration)**

## Known excluded experiments

| Item | Status |
| --- | --- |
| Twenty CRM (`evaluation/twenty-readonly-sandbox`) | KEEP_SEPARATE — diverged from m312 |
| Dirty Baadar/evaluation WIP on original m312 worktree | NOT integrated |
| Live provider/broker credentials | Forbidden |
| Uncommitted original worktree changes | Preserved outside this branch |

## Known limitations

1. Full backend suite (~6000 tests) not fully re-run in this mission (architecture-critical + M17 + samples run).
2. Browser smoke requires running platform server — may be environment-limited.
3. Multi-runtime coexistence (M48 / M52 / harness / engineering) remains intentional debt.
4. Residual legacy `subprocess` tools outside gateway remain classified, not deleted.
5. Historical M17 evidence JSON pins original repair SHAs (immutable provenance), not this tip.
6. FM-I6.2 live inference still memory-gated on certifying hosts.
7. `master` still lags this tip until a separate publish mission.

## Authority invariants (non-negotiable)

- ExecutionGateway = sole external tool-execution authority
- Trading Guardian independent and fail-closed
- Approval ≠ activation
- Model output ≠ authority
- Financial execution prohibited
- Voice activation does not grant execution authority
