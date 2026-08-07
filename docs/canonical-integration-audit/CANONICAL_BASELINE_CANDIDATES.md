# CANONICAL_BASELINE_CANDIDATES

Scoring dimensions (0–100 composite with explicit subscores).  
**Merge authorized: false** for all candidates until owner runs `SAATHIOS_CANONICAL_BASELINE_INTEGRATION`.

## Candidate A — RECOMMENDED

| Field | Value |
| --- | --- |
| Branch | `hardening/fm-i6.2-macos-memory-gate-fix` |
| SHA | `e1738d7deec5f44600fbf0d99e2b8f74a4bc83d0` |
| Subject | docs(agent-runtime): record FM-I6.2-LIVE memory-gate denial |
| Ahead of master | 331 commits |

### Contains

- Full linear product chain: M48–M53, M54–M61, TG M166–M343, UI recovery, full E2E recovery, private-alpha excellence (voice settings), M344–M359 agentdev, M369–M376 qualification
- Full AgentHarness design + FM-I1–I6.2 implementation and evidence
- Architecture freeze FM-C1/C2

### Excludes

- M17 scheduled-graph concurrency fix (8 commits on divergent merge tip)
- Twenty CRM evaluation branch
- Uncommitted original-worktree Baadar/evaluation WIP

### Scores

| Dimension | Score | Reasoning |
| --- | --- | --- |
| Architecture consistency | 88 | Gateway/harness/platform layered; residual multi-runtime debt documented |
| Security correctness | 86 | Financial exec prohibited; residual subprocess tools; memory gate fail-closed |
| Test completeness | 84 | Large suites claimed historically; M17 race tests missing on this tip |
| UI completeness | 85 | Private-alpha + UI recovery + command surfaces |
| Voice readiness | 72 | Settings + half-duplex interrupt; no full duplex/VAD; multi-owner residual |
| Trading research readiness | 80 | Deep TG paper/research; no live; fund ledger incomplete |
| Agent-runtime maturity | 90 | Strongest harness stack |
| Model-runtime maturity | 78 | Qualification + LocalModelHarness; live cert denied on memory |
| Documentation accuracy | 82 | Roadmap current for FM; BUILD_STATUS stale globally |
| Branch ancestry cleanliness | 92 | Linear from master through product to harness |
| Ease of future integration | 88 | Only need m17 cherry-pick + optional twenty |
| Rollback safety | 90 | Clear tip; no force history rewrite needed |
| **Composite** | **85** | |

### Can become canonical without rewriting history?

**YES** — declare tip as integration HEAD; cherry-pick m17; leave original branches intact.

### Limitations

- Live local model cert denied (`MODEL_HEADROOM_LOW`)
- M17 not present
- master still stale until stack or tip publish
- Multi-runtime coexistence remains

---

## Candidate B — Published multi-agent merge tip

| Field | Value |
| --- | --- |
| Branch | `origin/milestone/m344-m351-multi-agent-development-foundation` |
| SHA | `48510a9570d4f009848a4f12be4edaadbd7555e1` |
| Ahead of master | 320 |

### Contains

- Same product chain through m344-local features
- Merged #16 (m369) and #17 (m17 concurrency)

### Excludes

- Entire FM-C / FM-I harness implementation chain (19 commits)

### Scores

| Dimension | Score | Reasoning |
| --- | --- | --- |
| Architecture consistency | 75 | Missing harness consolidation layer |
| Security correctness | 84 | Includes M17 recovery hardening |
| Test completeness | 82 | M17 tests present; harness suite absent |
| UI completeness | 84 | Same pre-harness UI |
| Voice readiness | 70 | Same private-alpha voice, no later changes expected |
| Trading research readiness | 80 | Same TG depth |
| Agent-runtime maturity | 70 | Agentdev strong; AgentHarness missing |
| Model-runtime maturity | 74 | M369 present; LocalModelHarness missing |
| Documentation accuracy | 78 | Lacks FM architecture freeze on tip |
| Branch ancestry cleanliness | 80 | Merge commits; diverges from harness |
| Ease of future integration | 70 | Must merge/replay 19 harness commits (large) |
| Rollback safety | 85 | Good publish point but incomplete |
| **Composite** | **78** | |

### Why not preferred

Integrating harness onto B is a large forward merge; integrating m17 onto A is a **bounded cherry-pick**. Prefer smaller missing piece.

---

## Candidate C — Private-alpha product excellence

| Field | Value |
| --- | --- |
| Branch | `improve/saathios-private-alpha-product-excellence` |
| SHA | `53b9b20736d5acf4a7ca3a9bd25b68d01e666a5d` |
| Ahead of master | 290 |

### Contains

- Product + TG + E2E + voice settings diagnostics

### Excludes

- M344–M359 agentdev, M369+, entire harness chain, M17

### Scores

| Dimension | Score | Reasoning |
| --- | --- | --- |
| Architecture consistency | 72 | Pre-agentdev/harness |
| Security correctness | 83 | E2E security recovery included |
| Test completeness | 80 | Strong E2E era |
| UI completeness | 86 | Voice settings focus |
| Voice readiness | 74 | Best pure voice surface focus |
| Trading research readiness | 78 | TG present |
| Agent-runtime maturity | 60 | No harness / limited agentdev |
| Model-runtime maturity | 55 | Pre-qualification apparatus tip |
| Documentation accuracy | 75 | E2E docs strong; later architecture missing |
| Branch ancestry cleanliness | 88 | Linear ancestor of both A and B |
| Ease of future integration | 65 | Must still absorb agentdev+harness+m17 |
| Rollback safety | 88 | Stable product point |
| **Composite** | **75** | |

Useful as **rollback waypoint**, not forward baseline.

---

## Comparison summary

| Candidate | Composite | Prefer when |
| --- | --- | --- |
| **A harness tip** | **85** | Default — max certified ancestry + runtime maturity |
| B m344-remote | 78 | If M17 must be merge-commit preserved literally and harness deferred |
| C private-alpha | 75 | Emergency product-only rollback |

## Required predecessor action for A

1. Cherry-pick or merge `4197c9b..8577f2f` (m17 fix + tests + docs) onto A  
2. Resolve any conflicts in `application_harness/*` only  
3. Re-run scheduler concurrency tests  
4. Do **not** reverse-merge B into A (would not add harness; only m17 + merges)
