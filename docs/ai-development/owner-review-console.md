# Owner Review and Evidence Console

**Milestone:** M358
**Module:** `saathi/agentdev/review_console.py`
**Commands:** `review packet` · `review render` · `review ledger` ·
`review approve` · `review reject` · `review request-changes` ·
`review needs-research`

The owner-facing surface. It assembles everything needed to judge one mission
into a single packet, and records the owner's decision in an append-only,
hash-chained ledger.

---

## 1. What the packet shows

| Section | Source |
|---|---|
| `mission` | Mission status, state, gates, verdict, participants |
| `agent_outputs` | Every artifact, with author, status, and whether a model produced it |
| `review_comments` | Challenges, responses, code reviews, security reviews, minutes |
| `approval_history` | Every gate decision, plus the owner's own decisions and the state of their chain |
| `artifact_lineage` | Dependency edges between artifacts |
| `tests` | Verification reports, including negative paths and the `not_run` list |
| `behaviour_evaluation` | The M356 report, if one exists for this commit |
| `adversarial_evaluation` | The M357 report, if one exists for this commit |
| `resource_usage` | Measured host, plus the declared ceilings |
| `limitations` | Every limitation any artifact recorded, deduplicated |
| `confidence_signals` | Counts a reader can check — see below |
| `remaining_risks` | Open vetoes, unresolved disagreements, unanswered challenges, risks the decision carried, model substitutions |

## 2. Four actions, and no fifth

| Action | Effect |
|---|---|
| `approve` | Records an owner-authored `owner_approval` artifact and passes the owner-only gate |
| `reject` | Records a failed `owner_approval` gate with the owner's reason |
| `request_changes` | Records the request; no gate changes |
| `needs_research` | Records that the evidence is insufficient to decide; no gate changes |

**Nothing merges, pushes, deploys or contacts a provider.** Those verbs are not
implemented in this module, and a test asserts that no name beginning `merge`,
`push`, `deploy`, `release`, `publish` or `rollout` exists on it. A second test
parses the module's imports and asserts none of `urllib`, `socket`,
`subprocess`, `http` or `requests` is among them.

No action moves the mission's state. Approval satisfies a gate; what happens
outside this system remains the owner's to do.

## 3. Only the owner decides

| Rule | Classification |
|---|---|
| An action recorded by any actor other than `owner` is refused | `technically_enforced` |
| An action without a rationale is refused | `technically_enforced` |
| An action citing an artifact that does not exist is refused | `technically_enforced` |
| Approval over an open security veto is refused | `technically_enforced` |
| Approval must acknowledge every remaining risk by name | `technically_enforced` |
| Only `owner` may author an `owner_approval` artifact | `schema_validated` (M347) |
| Only `owner` may pass the `owner_approval` gate | `technically_enforced` (M349) |

The last rule predates this milestone. What M358 adds is the means for the
owner to exercise it — without giving anyone else the same means.

## 4. Immutable by construction

Each decision appends one line to `<store>/<mission>/owner_review.jsonl`. Every
line carries the SHA-256 hash of the line before it, and its own hash covers
sequence, timestamp, action, mission, actor, rationale, reviewed artifacts,
acknowledged risks and the previous hash.

`OwnerDecisionLedger` has an `append` method and a `verify_chain` method. It has
no update method, no delete method and no truncate method — asserted by test.

Four tampering tests establish what "immutable" means here:

| Tampering | Detected as |
|---|---|
| Editing an earlier decision | `entry content does not match its hash`, at that entry |
| Deleting a decision | `sequence jumped to 2`, at entry 1 |
| Reordering decisions | chain broken at the first mismatch |
| Appending a forged entry | `prev_hash does not match the entry before it` |

A corrupt line raises `ledger_corrupt` rather than being skipped. The rendered
page shows a broken chain in red, at the top of the approval-history card, with
the entry number.

Detection is not prevention: anyone with write access to the file can edit it.
What the chain guarantees is that the edit cannot go unnoticed.

## 5. Confidence, honestly

The packet reports **signals**, not a score:

`gates_passed / gates_total` · `self_approved_gates` · `artifacts` ·
`artifacts_produced_by_model` · `model_substitutions` ·
`unresolved_disagreements` · `open_vetoes` · `verification_reports` ·
`checks_not_run`

Every one is a count the owner can verify against the artifacts in the same
packet. No scalar confidence number is computed, because a number nobody can
derive is worse than no number — and the packet says so in its own `note`.

## 6. The page displays; it does not act

`review render` produces a self-contained HTML page — no script tag, no
external stylesheet, no network reference, everything escaped. It shows the
exact CLI command for each of the four actions and states plainly that it
cannot run them.

A page that could approve would be a page that could be tricked into approving.

Evidence: `docs/evidence/m352_m359/OWNER_REVIEW_CONSOLE.html` and
`OWNER_REVIEW_PACKET.json`.
