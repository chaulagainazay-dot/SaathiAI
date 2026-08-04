# Operating Limits

**Milestone:** M359
**Applies to:** `saathi/agentdev/` at the M352–M359 head
**Measured on:** Apple Silicon, 8 GB RAM, 256 GB SSD, macOS 25.5

Every number here was measured on the development host or read from a declared
constant. Nothing is estimated unless the row says so.

---

## 1. Concurrency

| Limit | Value | Where it lives | Classification |
|---|---|---|---|
| Maximum reasoning agents | 2 | `AgentDevSettings.max_reasoning_agents` | `schema_validated` |
| Maximum coding agents | 1 | `AgentDevSettings.max_coding_agents` | `schema_validated` |
| Maximum testing agents | 1 | `AgentDevSettings.max_testing_agents` | `schema_validated` |
| Maximum resident local models | 1 | `AgentDevSettings.max_local_model_instances` | `schema_validated` |

**These ceilings are declared and reported, not enforced.** Nothing in this
package spawns an agent or a model process, so nothing counts them. `doctor`,
the operations console and the review packet all display them; none of them
stops you exceeding them by hand. Saying otherwise would be the overstatement
M352 exists to prevent.

## 2. Providers

| | |
|---|---|
| Supported | Ollama, over loopback only (`127.0.0.1`, `localhost`, `::1`) |
| Evaluated model | `qwen3:4b` |
| Also installed on this host | `qwen2.5-coder:3b`, `gemma4:e2b`, `qwen3:8b`, `qwen2.5:1.5b` — present, **not evaluated** |
| Unsupported | Every cloud provider. Any non-loopback endpoint is refused at adapter construction, before a socket exists |
| Fallback between providers | None, deliberately. A failed call returns a failure naming the configured model |
| Credentials | None. The only header ever constructed is `Content-Type` |

## 3. Memory

| | |
|---|---|
| Host physical memory | 8.0 GiB |
| `qwen3:4b` resident | 2.95 GiB, 100% GPU |
| Adapter process peak RSS | 29 MiB |
| Console / runner / review process peak RSS | 19–29 MiB |
| Headroom with one model resident | ~5 GiB, unmeasured against other applications |

Running a second model concurrently was **not tested** and is outside the
declared ceiling.

## 4. Disk

| | |
|---|---|
| Free at certification | 62 GiB |
| `qwen3:4b` on disk | 2.5 GB |
| All five installed models | ~17.8 GB |
| One mission store (30-step reference mission) | ~120 KB |
| No new virtual environment | The shared `~/SaathiAI/.venv` is reused |
| No new package installed | Standard library only |

## 5. Latency

Measured, warm, on this host.

| Operation | Time |
|---|---|
| `console show` / `console render` | < 1 s |
| Deterministic reference mission, 30 steps | ~20 ms |
| Terminology audit, 44 files | < 1 s |
| Model load (already resident) | ~300 ms |
| Model call, 8-token reply | ~1.1 s |
| Model call, 96-token JSON reply | ~5.6 s |
| Model call, 800-token evaluation scenario | 12–20 s |
| M356 behaviour suite, 8 scenarios | ~120 s |
| M357 adversarial suite, 9 attacks | ~125 s |
| Full `agentdev` test suite (724 tests) | ~106 s |

Budget **four to five minutes** for a full model-in-loop run of both
evaluation suites.

## 6. Data limits

| | |
|---|---|
| Model context | 4096 tokens, as the provider reports it |
| Evaluation `max_tokens` | 800 per call |
| Adapter default timeout | 120 s |
| Adapter default attempts | 2 |
| Temperature / seed | 0 / 1 — reproducibility requested, not guaranteed |

## 7. Known risks

| Risk | Consequence | Mitigation in place |
|---|---|---|
| **No filesystem sandbox** | A process handed a shell can write anywhere the OS user can | `agentdev` never grants one; no role declares a writable scope outside `mission:`/`worktree:`; contamination is detected, not prevented |
| **The evaluated model failed 6 of 8 behaviour scenarios** | Model output cannot be trusted on its face | Every gate is enforced independently of who authored an artifact; the M357 result is that the system held 9 of 9 |
| **Ceilings are unenforced** | An operator can start more agents than declared | Reported everywhere; nothing spawns processes today |
| **Ledger detection, not prevention** | Anyone with write access can edit the owner ledger | The hash chain makes any edit detectable and locates it |
| **The gate engine trusts authorship** | It verifies that `authoring_agent` matches the expected party; it cannot verify who produced the content | Envelope is set by the runner, never by a handler |
| **One host, one day** | Every number here is a single observation | Stated on every report that carries a measurement |
| **Attack coverage is a list** | An attack nobody wrote down is untested | Published in the M357 report's own `limitation` |
| **102 stale worktrees remain** | Disk and confusion | Reported by the census; removing another milestone's leftovers is not this milestone's authority |

## 8. What is forbidden, permanently

Twelve denial flags are re-applied after every settings load and cannot be
turned on by environment variable or keyword:

`push` · `merge` · `deploy` · `force_push` · `branch_delete` ·
`destructive_git` · `force_worktree_removal` · `global_config_writes` ·
`credential_access` · `trading` · `external_paid_calls` ·
`unrestricted_shell`

## 9. Disabling everything

```
unset SAATHI_AGENTDEV_ENABLED
unset SAATHI_AGENTDEV_WORKTREES
python -m saathi.agentdev doctor      # confirms both are false
```

Both default to false. Unsetting is sufficient; there is nothing to uninstall,
no daemon to stop and no global configuration to restore.
