# Limitations

Stated plainly. Everything here is a real boundary of what was certified, not a
hedge.

## Scope actually certified

This mission certifies the **PAPER** execution integrity chain. It does not
certify shadow execution, and it certainly does not certify live execution.

## What was pre-existing vs added

Most of the chain — durable OMS, ledger, posting, gateway path, guardian, risk,
construction, reconciliation reporting — was built by T-NEXT-1 through T-NEXT-3
and was **audited**, not written, by this mission. What this mission added is the
ambiguity layer (`execution_integrity.py`), the failure-injection and authority
test suites, and two defect fixes. `ARCHITECTURE.md` gives the exact split. The
certification below should be read as "the chain as a whole now passes these
tests", not "this mission built the chain".

## Failure scenarios not reachable by injection

F15 (guardian flips allow→block mid-flight) and F16 (risk budget breach
mid-flight) are **not reachable in the current design**, because guardian
evaluation and risk reservation happen server-side inside the same transaction
as the order write. There is no window. They are therefore argued structurally,
not tested.

This is a real limitation with a real trigger: the moment guardian evaluation is
cached, moved out of the write transaction, or made asynchronous, both scenarios
become reachable and must be tested before that change ships.

Likewise, "fill during cancel" is covered at the state-machine level
(`CANCEL_PENDING → FILLED` is deliberately legal) but not as a concurrent race,
because the paper venue is single-threaded and deterministic.

## Reconciliation authority is not yet wired into the submission path

`ReconciliationAuthority` is implemented, tested, and deterministic. It is **not
yet called by `submit_order`**. Today it is a library that answers the readiness
question correctly; making it a mandatory pre-submission gate is a separate,
deliberate change, because it needs a decision about where the external snapshot
comes from in each deployment and what the operator experience is when readiness
is denied.

Certification therefore covers the authority's correctness, not its enforcement
in the live submission path. That wiring is the first task of any shadow
execution mission.

## Submission attempt store is not yet wired into the submission path

Same situation as above. `SubmissionAttemptStore` correctly gates
retry decisions; it is not yet consulted by `submit_order`. The existing
gateway-digest and intent→order idempotency layers are what protect the live
path today, and they are tested (`F1`, `F1b`, `F4`).

## No startup sweep for unresolved ambiguity

Blocks on ambiguous submissions are enforced lazily — when someone tries to
submit that key again. There is no boot-time sweep that enumerates unresolved
`RECONCILE_FIRST` attempts and raises them proactively. Fail-closed, therefore
safe, but not proactive.

## Fill ordering

Fills are deduplicated by market-event hash, which is correct for a
deterministic paper venue. A real venue with a monotonic sequence number should
additionally reject a fill whose sequence precedes the highest applied sequence
for that order. Not implemented, because the paper venue has no such sequence.

## Point-in-time / market realism

PAPER mode simulates fills from supplied market events with versioned fee and
slippage models. It does not model queue position, partial-venue liquidity,
auction phases, halts, or exchange-specific order types beyond MARKET and LIMIT.
Corporate actions are handled by a separate module
(`paper_simulation/corporate_actions.py`) and were not exercised by this mission.

## Cancel / replace

Cancel is implemented and idempotent. **Replace is not implemented** in the paper
contract — only MARKET and LIMIT order types are supported and there is no
replace verb. The brief's Phase 10 replace semantics (replace quantity, replace
price, replace racing a fill, duplicate replace, ancestry traceability) are
therefore **not certified**. Cancel-before-submit, cancel-after-submit,
cancel-after-partial-fill, cancel-after-full-fill, and duplicate cancel are
covered by the state machine and the pre-existing cancel suite.

## Kill switch

Account-level halt is implemented and blocks new orders (`F17`).
`tg/kill_switch.py` provides scoped blocking with an audit log. The brief's
distinction between `BLOCK_NEW_ORDERS` and `BLOCK_ALL_EXECUTION_ACTIONS` exists
in the kill-switch scopes but was **not separately certified** by this mission,
and cancel-open-orders behaviour was not simulated.

## Test suite scope

The full repository suite did not complete. Three attempts: two stalled at ~0.1%
CPU (network- or IO-bound test), one bounded run reached **84% of collected
tests with zero failure or error markers** before hitting a 900 s deadline.

Reported numbers are for the targeted suites that did complete, and they are
real. The remaining 16% is unverified. See `TEST_REPORT.md`.

Separately: a test that hangs on network access is an environment defect worth
fixing on its own merits, independent of this mission.

## Not done, deliberately

No live broker connectivity. No real orders. No production capital. No leverage.
No short selling. No withdrawal path. No LLM anywhere in the execution plane. No
TradingAgents code or dependency. No TA-1 work.
