# Model Qualification — Limitations

**Milestones:** M369–M376

What this range does not establish. Read this before quoting any number from it.

## 1. One host

Every measurement describes an Apple M2 with 8 GiB unified memory and a single
SSD, at one commit, on one day.

Eligibility, resource findings and latency are properties of that machine, not
of any model. `qwen3:8b` is `resource_unsuitable_on_current_host`; on a 32 GiB
machine it would be eligible with no change to this repository.

## 2. Not every installed model was measured

Five installed, three evaluated, two excluded by the size ceiling. The two
excluded models have **no behavioural reading at all**. Their absence from the
behavioural results is not evidence about them, and their `RESOURCE_UNSUITABLE`
rows are not a quality judgement.

## 3. Zero qualified pairs is the finding, not a placeholder

No model qualified for any of the ten roles. This is what the published
thresholds returned. It is not a pending state, and it is not a lowered bar
waiting to be raised.

The corollary is that the routing policy has never routed anything. Its refusal
path is exercised; its selection path is exercised only by test.

## 4. Determinism is requested, not guaranteed

Temperature 0 and a fixed seed are provider hints. A provider may vary output
across versions, quantisations and hardware. Runs are repeated rather than
assumed equal, and `scenario_stability` measures agreement across repeats at
*this* temperature and seed — not generality.

## 5. Coverage is what was written down

Twelve behavioural scenarios and eighteen adversarial attacks. A model that
passed here can fail a scenario nobody wrote; a system that held here can fall
to an attack nobody wrote. The suites are a floor.

## 6. Claim verification has a bounded reach

Detection covers the claim families the detector set names — regular expressions
over text, a guard rather than a reading. Verification covers the subjects the
evidence sources cover. Open-domain factual accuracy is out of scope and is
reported `NOT_VERIFIABLE`.

`VERIFIED` means one named deterministic source agreed with one claim. It does
not mean the claim is true in general, and another model agreeing is never
verification.

## 7. The concurrency ceiling is observed, not enforced

One resident model and one concurrent evaluation are `schema_validated` and
operator-observed. No component in this package spawns a model process, so none
enforces a ceiling at the operating-system level. An operator who loads a second
model elsewhere is detected on the next check, not prevented.

## 8. A probe error is not a boundary breach

A probe that raises is conservatively recorded as `SYSTEM_FAILED_OPEN`, because
a harness that cannot measure a control must not report the control as holding.
That conservatism can produce a `BLOCKED` verdict from an evaluation fault
rather than a real breach — a stale scratch directory did exactly this during
this range's repair.

The certificate therefore reports `probe_errors` separately and says so in
`verdict_reasons`. A `BLOCKED` verdict must be read before it is acted on.

## 9. Two readings of qwen3:4b are not a trend

2 of 8 under M356 and 4 of 12 under M372 are not comparable ratios. The suites
differ in size and scenario set; the run counts differ, so a pass under M372
means passed on every run while a pass under M356 does not. Comparison is
directional only. Both readings fall short of every published threshold, and
the role is unchanged.

## 10. The certificate is a derivation, not an endorsement

`CERTIFICATION.json` states what the evidence files say. It certifies that the
apparatus ran and what it found. It does not certify that any model is safe to
use, and it grants no authority — `authority_boundary` is carried in the
certificate precisely so that reading it as an approval is difficult.

## 11. Terminology checking is literal

The phrase guard catches the wordings the owner named and cannot detect an
overstatement phrased in words nobody listed. The coverage check confirms a
pinned term appears on a surface, not that it was used correctly there.
Terminology consistency beyond these two checks is `documentation_only`.

## 12. Nothing here is reachable from the product

No product surface calls this package. No model in this range has tool,
filesystem, shell, implementation, approval, mission-transition or deployment
authority. No Trading Guardian or CRM authority was touched.
