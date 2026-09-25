# Certification Guide

**Milestone:** M359
**Purpose:** what "certified" means here, what it does not, and how to redo it.

`certification` is `documentation_only` — an owner-reviewed statement about one
commit, naming one verdict token, its evidence and its limitations. It is not
production fitness, not an external audit, and never a claim about a model. See
[terminology.md](terminology.md).

---

## 1. The four tiers, applied

Every claim in this environment sits in exactly one tier. A certification that
blurs them is worthless, so the tier travels with the claim everywhere.

| Tier | What it means | How to break it |
|---|---|---|
| `technically_enforced` | A code path raises or exits non-zero | Remove the control; a test fails |
| `schema_validated` | Malformed input is refused at construction or load | Accept a malformed record |
| `deterministic` | Same input, same output; no model, no network | Output varies between runs |
| `model_evaluated` | A local model produced it and a documented rubric scored it | The rubric is undocumented or the run unrecorded |
| `advisory_only` | Guidance an agent may ignore | Treat it as prevention |
| `documentation_only` | A human statement with no runtime effect | Cite it as a control |

## 2. What is certified at this commit

| Capability | Tier | Evidence |
|---|---|---|
| Pinned terminology; twenty-two banned phrasings absent from the reviewed surface | `technically_enforced` | `TERMINOLOGY_AUDIT.json`, 84 tests |
| Read-only operations console; fifteen panels; no write verb, no store mutation, no external reference | `technically_enforced` | `AGENT_OPERATIONS_CONSOLE.html`, four screenshots, 48 tests |
| Deterministic runner; seven-phase contract; byte-identical artifacts across runs | `deterministic` | `DETERMINISTIC_RUNNER_TRACE.json`, 39 tests |
| Gate enforcement — no self-approval, no missing evidence, no gate skipping | `technically_enforced` | M349 + M354 + M357 tests |
| Local adapter isolation — loopback only, no credentials, no tools, no shell imports | `technically_enforced` | `ADAPTER_VERIFICATION.json`, 67 tests |
| Owner-only decisions, recorded in a hash-chained ledger | `technically_enforced` | `OWNER_REVIEW_PACKET.json`, 52 tests |
| Adversarial resilience against the nine listed attacks | `technically_enforced` | `ADVERSARIAL_EVALUATION.json`, 44 tests |
| One-way dependency: nothing under `engineering/`, `missions/` or `platform/` imports `agentdev` | `technically_enforced` | Verified at certification: zero reverse imports |

## 3. What is still experimental

| Capability | Why it is not certified |
|---|---|
| Model participation in a mission | One model, one seat, one host. The evaluated model failed 6 of 8 behaviour scenarios |
| Any model other than `qwen3:4b` | Four others are installed; none was evaluated |
| Concurrency ceilings | Declared and reported; nothing spawns agents, so nothing enforces them |
| Filesystem confinement | Detection only. There is no sandbox |
| More than one model-backed seat | Never run |

## 4. What requires the owner

- Passing the `owner_approval` gate — no agent may, by construction
- Any change to protected configuration
- Any push, merge or deploy — none of which this package can perform at all
- Enabling `SAATHI_AGENTDEV_ENABLED` and `SAATHI_AGENTDEV_WORKTREES`
- Authorising the next milestone

## 5. What requires deterministic validation

Before any claim about the orchestration path:

```
python -m saathi.agentdev terminology audit          # must be clean
python -m saathi.agentdev runner run                 # 30 steps, 9 gates
python -m saathi.agentdev console show               # no blockers
python -m pytest tests/test_m3*_agentdev*.py         # must be green
```

## 6. What requires model validation

Before any claim about behaviour:

```
python -m saathi.agentdev model health               # provider up, model present
python -m saathi.agentdev model verify               # three measured calls
python -m saathi.agentdev eval run                   # eight scenarios
python -m saathi.agentdev adversarial run            # nine attacks
```

A model-evaluated claim must name the model, the host, the date and the rubric.
Without all four it is not a measurement, it is an impression.

## 7. Reproducing this certification

1. Check out the milestone branch in its own worktree; confirm the tree is clean.
2. Reuse the existing `~/SaathiAI/.venv`; install nothing.
3. Run the deterministic gate (§5). All four must pass.
4. Run the regression suites: `-k "engineering or agent_registry or safety"` and `-k "governance or approval or security or trading"`.
5. Start Ollama, confirm `qwen3:4b` is present, run the model gate (§6). Budget five minutes.
6. Regenerate every artifact in `docs/evidence/m352_m359/`.
7. Compare against the recorded numbers. **Model numbers will differ** — that is expected and is why they are recorded per run rather than asserted by a test.

## 8. The five verdict tokens

| Token | When it applies |
|---|---|
| `AGENT_OPERATIONS_CERTIFIED` | The operations layer is validated with no material limitation |
| `AGENT_OPERATIONS_CERTIFIED_WITH_LIMITATIONS` | The operations layer is validated and the limitations are documented |
| `MODEL_EVALUATION_FOUNDATION_CERTIFIED` | Only the evaluation apparatus is validated |
| `FOUNDATION_VALIDATION_PENDING` | Validation has not completed |
| `BLOCKED` | A gate failed and work stopped |

Exactly one token is used per milestone. The one issued for M352–M359 is in
[the final certification report](../evidence/m352_m359/CERTIFICATION.md).
