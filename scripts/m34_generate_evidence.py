"""M34 — Deterministic live-external-verification evidence generator.

Regenerates docs/evidence/m34/*.json from the live modules. The M34 reliability
harness is exercised OFFLINE against the committed, sanitized github_meta fixture
(no network, no DNS, no TLS, no credentials): the injected transport is
fixture-backed, so ``run_m34_live_verification`` walks the full bounded call loop
(budget 3) without touching the network. This is a fixture-backed SIMULATION of
the operator-only live path — the real live external call remains operator-only
and is recorded here as NOT EXERCISED.

Every payload is leak-scanned before write (fail closed, via M32 write_evidence).

Run:  .venv/bin/python scripts/m34_generate_evidence.py
"""
from __future__ import annotations

from pathlib import Path

from saathi.connectors.providers.evidence import write_evidence
from saathi.connectors.providers.external.m34 import (
    M34_DEFAULT_CALL_BUDGET,
    run_m34_live_verification,
    write_m34_evidence,
)
from saathi.connectors.providers.external.verification import ExternalVerificationStore
from saathi.connectors.providers.external.verify import offline_transport
from saathi.credentials.leakscan import is_clean

ROOT = Path(__file__).resolve().parents[1]
REL = "docs/evidence/m34"          # repo-relative — recorded into evidence, no local paths
EV = ROOT / "docs" / "evidence" / "m34"
FIXED_TS = 1752800000.0  # deterministic clock for stable evidence
PROVIDER = "github_meta"


def _run() -> dict:
    """Drive the bounded M34 harness offline (fixture transport, fixed clock)."""
    store = ExternalVerificationStore(Path(REL) / "external_verification_registry.json", clock=lambda: FIXED_TS)
    return run_m34_live_verification(
        PROVIDER,
        ack_read_only=True,
        ack_network=True,
        ack_non_production=True,
        ack_call_budget=True,
        max_calls=M34_DEFAULT_CALL_BUDGET,
        transport=offline_transport(PROVIDER),
        enabled=True,                 # explicit — never reads the live env opt-in flag
        store=store,
        evidence_dir=REL,
        clock=lambda: FIXED_TS,
        now=str(int(FIXED_TS)),
    )


def _write_pre_live(result: dict) -> list[str]:
    """Evidence unique to the pre-live gate: authorization/plan + not-exercised record."""
    written: list[str] = []

    written.append(write_evidence(
        "live_call_budget",
        {
            "approved_call_budget": result.get("approved_call_budget"),
            "max_call_budget": 5,
            "actual_call_count": result.get("actual_call_count"),
            "retries_consume_budget": True,
            "note": "actual_call_count never exceeds approved_call_budget, retries included",
        },
        evidence_dir=Path(REL), schema="m34.live_call_budget.v1",
    ))

    # The genuine on-network live call is operator-only and was NOT run here.
    written.append(write_evidence(
        "live_external_call_result",
        {
            "provider": PROVIDER,
            "operation": result.get("operation"),
            "mode": "SHADOW",
            "on_network_live_call": False,
            "call_count_on_network": 0,
            "success_or_failure": "not_exercised",
            "harness_exercised": "OFFLINE_FIXTURE_SIMULATION",
            "verification_state_from_simulation": result.get("verification_state"),
            "max_possible_state": "EXTERNAL_READ_ONLY_VERIFIED_WITH_LIMITATIONS",
            "limitations": [
                "on_network_live_call_not_exercised",
                "external_read_only",
                "single_endpoint_only",
                "non_production",
                "no_write_authority",
                "no_account_link",
                "no_credential",
            ],
            "operator_command": (
                "python -m saathi.connectors.providers external-verify github_meta "
                "--ack-read-only --ack-network --ack-non-production --ack-call-budget"
            ),
            "operator_env_flag": "SAATHI_M34_LIVE_VERIFY_ENABLED=1",
        },
        evidence_dir=Path(REL), schema="m34.live_external_call_result.v1",
    ))

    written.append(write_evidence(
        "rollout_state",
        {
            "connector_rollout": "OFF",
            "provider_rollout": "OFF",
            "inference_rollout": "OFF",
            "canary_providers": 0,
            "active_providers": 0,
            "trading_guardian": "UNCHANGED / UNENGAGED",
            "note": "verification and canary assessment never mutate rollout",
        },
        evidence_dir=Path(REL), schema="m34.rollout_state.v1",
    ))
    return written


def main() -> int:
    EV.mkdir(parents=True, exist_ok=True)
    result = _run()

    # fail closed: the whole result must be leak-clean before anything is written
    printable = {k: v for k, v in result.items() if k != "_calls_internal"}
    if not is_clean(printable):
        raise SystemExit("ABORT: M34 result failed leak scan — nothing written")

    written = write_m34_evidence(result, evidence_dir=REL)
    written += _write_pre_live(result)

    print(f"provider              : {result['provider_id']}")
    print(f"operation             : {result['operation']}")
    print(f"actual_call_count     : {result['actual_call_count']} (budget {result['approved_call_budget']})")
    print(f"reliability           : {result['reliability_qualification']}")
    print(f"repeatability         : {result['repeatability']}")
    print(f"canary_readiness      : {result['canary_readiness']}")
    print(f"verification_state    : {result['verification_state']}")
    print(f"leak_clean            : {result['leak_clean']}")
    print(f"rollout_state         : {result['rollout_state']}")
    print(f"evidence files written: {len(written)}")
    for p in sorted(written):
        print(f"  {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
