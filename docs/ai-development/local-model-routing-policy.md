# Local Model Routing Policy

**Milestone:** M376
**Module:** `saathi/agentdev/model_qualification.py`
**Command:** `qualification route`
**Classification:** `documentation_only` (the policy) · `deterministic` (the decision)

The routing policy records which model an operator may ask for a given role,
under what restrictions. It is a policy over measured qualification, **not a
scheduler**. Nothing in it executes anything.

## 1. What a decision considers

| Input | Effect |
|---|---|
| Requested role | Selects the tier and its thresholds |
| Role qualification | The only thing that can make a model a candidate |
| Model availability | Can remove a candidate; can never add one |
| Resource state | Can veto a qualified model; can never promote one |
| Latency | Tie-break **inside** the qualified set only |
| Contradiction risk | Already disqualifying at the threshold stage |
| Human review | Attached to every qualified decision |
| Fallback eligibility | Off unless every candidate is independently qualified for the same role |

Latency deserves emphasis because it is the easiest thing to get wrong: a fast
unqualified model is still unqualified. Latency orders the qualified set and
touches nothing else.

## 2. The default

```
NO_QUALIFIED_MODEL → a deterministic workflow, or a person
```

A request is never routed to an unqualified model because that model happens to
be installed. On the certifying host all ten roles take this path, because zero
model-role pairs qualified.

## 3. What is prohibited

| Prohibited | Recorded as |
|---|---|
| Automatic fallback between local models | `automatic_fallback: disabled` |
| Cloud fallback | `cloud_fallback: prohibited` |
| Paid provider fallback | `paid_provider_fallback: prohibited` |
| Provider switching | `provider_switching: prohibited` |

Even when several models are qualified for one role, automatic fallback stays
off: a silent switch would make a recorded result unattributable. A fallback is
an operator decision.

## 4. Every decision is an evidence record

Each carries the role, the selected model or `NO_QUALIFIED_MODEL`, the
candidates, every rejected model with its status, the fallback state and the
reason for it, the human-review requirement, the universal prohibitions, the
resource state at decision time, and the qualification evidence behind the
choice.

The reason is written out, not implied. A decision nobody can read back is not
a record.

## 5. Concurrency

One active local model, one simultaneous evaluation. Schema-validated and
operator-observed: no component in this package spawns a model process, so none
enforces the ceiling at the operating-system level. The honest description of
that control is "observed", and that is how it is recorded.

## 6. Certification

`CERTIFICATION.json` is derived from the evidence files, never asserted. Its
verdict is decided worst-first so a blocking finding cannot be masked by a
milder one recorded later:

1. any `SYSTEM_FAILED_OPEN` → `LOCAL_MODEL_QUALIFICATION_BLOCKED`
2. any failing test in the certifying run → `LOCAL_MODEL_QUALIFICATION_BLOCKED`
3. no model completed an evaluation → `LOCAL_MODEL_EVALUATION_INCOMPLETE`
4. otherwise → `LOCAL_MODEL_QUALIFICATION_CERTIFIED_WITH_LIMITATIONS`

`LOCAL_MODEL_QUALIFICATION_CERTIFIED` — clean, no limitations — is reachable
only when every installed model was evaluated and every gate genuinely
qualified. That was not the case here and the certificate says so.

Test counts come from a recorded pytest run supplied by the operator. The
certifier never runs pytest itself: a certificate that measured its own tests
would be exactly the self-report this range exists to distrust.

## 7. The console

`qualification show` renders thirteen read-only panels; `qualification render`
writes the HTML. The console reads evidence files and has no write verb — no
form, no button, no input, no polling, no provider contact, no model start or
stop, no approval control, no mission execution. `capabilities()` returns every
verb it does not have, and a test asserts they are all false.

A panel whose evidence file is absent says so rather than showing an empty
table.

## Evidence

- `docs/evidence/m369_m376/ROUTING_POLICY.json`
- `docs/evidence/m369_m376/CERTIFICATION.json`
- `docs/evidence/m369_m376/console-screenshots/`

## Limitations

- A policy, not a scheduler. Nothing here routes anything; it records what an
  operator may do.
- The routing evidence describes this host at this commit.
