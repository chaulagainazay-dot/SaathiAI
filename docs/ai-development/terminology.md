# Owner Terminology Decision Record

**Milestone:** M352
**Status:** Accepted by the owner
**Machine-readable source of truth:** `saathi/agentdev/terminology.py`
**Check it:** `python -m saathi.agentdev terminology audit`

M344–M351 ended with one question referred upward, recorded in
`docs/evidence/m344_m351/CERTIFICATION.md` §10 and in the simulated mission's
own executive decision:

> May the first suite claim behaviour evaluation before any model participates?

This record is the answer, plus the review of every other term that carried more
weight than the system could support. It is written before a real model
participates, deliberately: once model output enters the loop, an ambiguous word
stops being a documentation problem and becomes a governance one.

---

## 1. The classification vocabulary

Six classifications, fixed. Every reviewed term gets exactly one.

| Classification | What a reader may conclude | How it fails |
|---|---|---|
| `technically_enforced` | A code path raises or exits non-zero | Removing the control breaks a test |
| `schema_validated` | Malformed input is refused at construction or load | A malformed record is accepted |
| `deterministic` | Same input, same output; no model, no network | Output varies between runs |
| `model_evaluated` | A local model produced it and a documented rubric scored it | The rubric is undocumented or the run is unrecorded |
| `advisory_only` | Guidance an agent may ignore; detectable afterwards | Treated as prevention |
| `documentation_only` | A human statement with no runtime effect | Cited as a control |

A seventh value, `rejected`, marks wording the owner removed. It names a
replacement rather than a meaning.

---

## 2. The reviewed terms

| Term | Classification | Now means | Explicitly does **not** mean |
|---|---|---|---|
| behaviour coverage | **rejected** | — → use *behaviour scenario suite* | A measured proportion of a known behaviour space |
| behaviour scenario suite | `deterministic` | A counted set of offline scenarios, each asserting one governance property against the real modules | That the scenarios bound what an agent can do |
| behaviour evaluation | `model_evaluated` | A local model produced output and a documented rubric scored it, recorded with model, prompt and seed | That the model will repeat it, that another model would match it, or that the behaviour is enforced |
| governance evaluation | **rejected** | — → use *governance refusal scenario* or *behaviour evaluation* | It was used for two different claims |
| simulation | `deterministic` | A scripted mission run end to end with no model, no network, no provider | That an agent's reasoning was reproduced |
| certification | `documentation_only` | An owner-reviewed statement about one commit, naming one verdict token, its evidence and its limitations | Production fitness, external audit, or any claim about a model |
| enforcement | `technically_enforced` | The code path cannot proceed — always written with its tier attached | That an instruction in a prompt was obeyed |
| orchestration | `deterministic` | Scripted sequencing of participants and stages, fixed in code, taking no model input | That an agent decides what happens next; where the workflow refuses to advance, say *orchestration-checked* |
| autonomy | **rejected** | — → use *operator-initiated execution* | Anything this system does |
| runtime | `documentation_only` | The SaathiOS product runtime, or the adverb sense "at execution time" | Any component of this package — the engine here is the *deterministic runner* |
| approval | `technically_enforced` | A gate record naming an approver who is not the subject author, bound to evidence artifact ids | Owner approval, which is a distinct owner-only gate |
| authority | `schema_validated` | A `saathi.safety.SafetyLevel` ceiling declared in a role contract, checked at registry load | A capability granted to a running process |

Twelve entries for eleven reviewed words: *behaviour coverage* was split from its
replacement so both the rejection and the successor are addressable.

---

## 3. The referred question, answered

**Question.** May the first suite claim behaviour evaluation before any model
participates?

**Answer: no.** The M351 suite is a **behaviour scenario suite** — ten
deterministic governance-refusal scenarios. It is reported as a count, never as
a percentage, and it makes no claim about model behaviour because no model runs
in it.

**Consequence.** The term *behaviour evaluation* is reserved for M356 onward,
where a local model produces output that a documented rubric scores. Until that
point the phrase does not appear on this surface, and the audit refuses it.

---

## 4. Banned phrasings

Twenty-two literal phrases, listed in `terminology.py` with a reason and a
replacement for each. They fall into five groups:

1. **Rejected terms** — `behaviour coverage`, `behavior coverage`,
   `governance evaluation`.
2. **Overstated autonomy** — `fully autonomous`, `autonomous agent`.
3. **Name collisions** — `agent runtime`, `agentdev runtime`, `simulated agent`,
   `agent simulation`.
4. **Prompt text described as a control** — `prompt enforcement`,
   `enforced by prompt`.
5. **Unfalsifiable or absolute claims** — `cannot be bypassed`,
   `impossible to bypass`, `guarantees compliance`, `guaranteed safe`,
   `certifies the model`, `model is certified`, `production ready`,
   `production certified`, `self-approve`, `auto-approve`, `100% coverage`.

Four files may quote a banned phrase because they exist to list or test it:
this record, `terminology.py`, `tests/test_m352_agentdev_terminology.py` and the
generated audit JSON. `limitations.md` may quote `behaviour coverage` in the one
sentence that records its rejection. Every allowance is declared in
`QUOTED_FOR_REJECTION` and reviewed with the lexicon.

---

## 5. What the audit is, and is not

The audit is a **literal-phrase guard**. It scans 35 files across
`docs/ai-development/`, `saathi/agentdev/`, `docs/evidence/m352_m359/` and the
`agentdev` test files, and reports every occurrence of a listed phrase with its
file, line and replacement.

It cannot detect an overstatement phrased in words nobody listed. Terminology
consistency beyond these twenty-two phrases is `documentation_only` and depends
on owner review. Saying otherwise would be the exact failure this record exists
to prevent.

| Property | Classification |
|---|---|
| The twenty-two banned phrases are absent from the reviewed surface | `technically_enforced` — a test fails otherwise |
| Every reviewed term carries exactly one classification | `schema_validated` — the lexicon is typed data |
| The audit is reproducible | `deterministic` — no model, no network |
| Wording beyond the listed phrases is honest | `documentation_only` |

---

## 6. Changes made under this record

| File | Change |
|---|---|
| `saathi/agentdev/__init__.py` | Removed the claim that the package "reuses" four `saathi.engineering` modules; the actual import surface is `saathi.safety` and `saathi.config` only |
| `saathi/agentdev/simulation.py` | Eight occurrences of the rejected term replaced; the disputed question preserved and restated in pinned wording |
| `tests/test_m348_agentdev_meetings.py` | One fixture string restated |
| `saathi/agentdev/cli.py` | Added `terminology lexicon`, `terminology audit`, `terminology classify` |

The M344–M351 evidence package is **not** rewritten. It is the record of what
was true at that commit, including the open question this record closes.
