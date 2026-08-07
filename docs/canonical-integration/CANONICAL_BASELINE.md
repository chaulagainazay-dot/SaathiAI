# CANONICAL_BASELINE — SaathiOS

| Field | Value |
| --- | --- |
| **Canonical branch** | `integration/saathios-canonical-baseline` |
| **Final tip SHA** | tip of `integration/saathios-canonical-baseline` (publish-time: see git / PR) |
| **M17 integrated tip (pre final docs)** | `6d72f00b76e902bc957263f05f1d6c11229a88a1` |
| **Source baseline branch** | `hardening/fm-i6.2-macos-memory-gate-fix` |
| **Source baseline SHA** | `6d72f00b76e902bc957263f05f1d6c11229a88a1` |
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

Linear ancestry from master through:

- M47 UI/UX foundation (on master)
- M48 agent runtime baseline
- M49.1–M49.4 tool runtime / gateway
- M50–M53 platform foundation / agent runtime / ops
- M54–M61 private-alpha product / spatial / workflows
- Trading Guardian M166–M343
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
| Twenty CRM (evaluation/twenty-readonly-sandbox) | KEEP_SEPARATE — diverged from m312 |
| Dirty Baadar/evaluation WIP on original m312 worktree | NOT integrated |
| Live provider/broker credentials | Forbidden |
| Uncommitted original worktree changes | Preserved outside this branch |

## Known limitations

1. Full backend suite not fully re-run (architecture-critical + M17 + samples run).
2. Browser smoke requires live platform server — environment-limited this mission.
3. Multi-runtime coexistence remains intentional debt.
4. Residual legacy subprocess tools outside gateway classified, not deleted.
5. Historical M17 evidence JSON pins original repair SHAs (immutable provenance).
6. FM-I6.2 live inference still memory-gated on certifying hosts.
7. master still lags this tip until a separate publish mission.

## Authority invariants (non-negotiable)

- ExecutionGateway = sole external tool-execution authority
- Trading Guardian independent and fail-closed
- Approval does not equal activation
- Model output does not equal authority
- Financial execution prohibited
- Voice activation does not grant execution authority

## Publication pin

- Final tip: resolve with `git rev-parse origin/integration/saathios-canonical-baseline`
- Branch: `integration/saathios-canonical-baseline`
- Remote: origin/integration/saathios-canonical-baseline

M17 code tip (cherry-pick complete): `272dbd5d0b9495d9682955074a76b4931e440daf`
