"""M39.2 — Live-test failure-mode simulation (offline; SIMULATED_NOT_LIVE).

Additive extension of M39. Drives the *real* M39 single-session runner through
injected fault transports/backends so every live-only failure mode is exercised
deterministically WITHOUT a live provider. Introduces no new session / lease /
credential / provider subsystem — it composes M39 + M37 transport testkit + the
M38 retry classifier.

Every outcome is stamped ``SIMULATED_NOT_LIVE``. No live network is performed, no
secret value is resolved (offline fixture only), and no authority is granted.

Covered fault modes (single-session transport seam):
  throttle_429, auth_denied_401, auth_denied_403, server_error_500,
  malformed_response, network_timeout, connection_reset, connection_refused,
  dns_resolution_failure, secret_resolution_failure, kill_switch_tripped.

Multi-session partial-failure / retry aggregation is already covered by M38's
failure matrix (``m38-run-failure-matrix``) and is intentionally not duplicated.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Optional

from saathi.connectors.providers.external import testkit as tk
from saathi.credentials.backends import SecretBackend, SecretBackendError
from saathi.credentials.leakscan import is_clean
from saathi.credentials.m38 import classify_retry
from saathi.credentials.m39 import (
    AUTHORITIES,
    NON_PRODUCTION_BANNER,
    LiveKillSwitch,
    M39Error,
    M39_ACK_TOKENS,
    _hmac,
    run_live_single_session,
)

SCHEMA_VERSION = "m39_2.failure_simulation.v1"
_FP_DOMAIN = b"saathi.m39_2.failure_simulation.domain.v1"

SIMULATED = "SIMULATED_NOT_LIVE"

_LOCATOR = "m39/synth"
_SOURCE = "IN_MEMORY_TEST"


class _SecretResolutionFailureBackend(SecretBackend):
    """Test backend that passes existence but fails on retrieval (offline only)."""

    kind = "m39_2_secret_resolution_failure"

    def put(self, locator: str, fields: dict[str, str]) -> None:  # pragma: no cover
        pass

    def exists(self, locator: str) -> bool:
        return True

    def get(self, locator: str, fields: Optional[list[str]] = None) -> dict[str, str]:
        raise SecretBackendError("secret_resolution_failure_sim")

    def delete(self, locator: str) -> None:  # pragma: no cover
        pass


def _run(*, transport=None, backend=None, kill_switch=None) -> dict[str, Any]:
    return run_live_single_session(
        secret_source_kind=_SOURCE,
        secret_locator=_LOCATOR,
        acknowledgements=M39_ACK_TOKENS,
        allow_offline_fixture=True,
        transport=transport,
        backend=backend,
        kill_switch=kill_switch,
        session_id="m39_2_sim",
    )


def _baseline() -> dict[str, Any]:
    return _run()


# Each fault: (mode, factory producing a completed single-session result, expect_retryable)
# expect_retryable is the intended M38 retry classification for the failure reason.
def _throttle() -> dict[str, Any]:
    return _run(transport=tk.make_transport(sender=tk.fixture_sender(status=429)))


def _auth401() -> dict[str, Any]:
    return _run(transport=tk.make_transport(sender=tk.fixture_sender(status=401)))


def _auth403() -> dict[str, Any]:
    return _run(transport=tk.make_transport(sender=tk.fixture_sender(status=403)))


def _server500() -> dict[str, Any]:
    return _run(transport=tk.make_transport(sender=tk.fixture_sender(status=500)))


def _malformed() -> dict[str, Any]:
    return _run(transport=tk.make_transport(
        sender=tk.fixture_sender(status=200, body_bytes=b"not-json{{")))


def _timeout() -> dict[str, Any]:
    return _run(transport=tk.make_transport(sender=tk.raising_sender(TimeoutError())))


def _conn_reset() -> dict[str, Any]:
    return _run(transport=tk.make_transport(sender=tk.raising_sender(ConnectionResetError())))


def _conn_refused() -> dict[str, Any]:
    return _run(transport=tk.make_transport(sender=tk.raising_sender(ConnectionRefusedError())))


def _dns_fail() -> dict[str, Any]:
    return _run(transport=tk.make_transport(
        resolver=tk.failing_resolver(), sender=tk.fixture_sender()))


def _secret_resolution_failure() -> dict[str, Any]:
    return _run(backend=_SecretResolutionFailureBackend())


def _kill_switch() -> dict[str, Any]:
    ks = LiveKillSwitch()
    ks.trip("m39_2_sim_operator_cancel")
    return _run(kill_switch=ks)


# ordered registry: (mode, runner, expected_retryable)
FAULT_MODES: tuple[tuple[str, Callable[[], dict[str, Any]], Optional[bool]], ...] = (
    ("throttle_429", _throttle, True),
    ("auth_denied_401", _auth401, False),
    ("auth_denied_403", _auth403, False),
    ("server_error_500", _server500, True),
    ("malformed_response", _malformed, False),
    ("network_timeout", _timeout, True),
    ("connection_reset", _conn_reset, True),
    ("connection_refused", _conn_refused, True),
    ("dns_resolution_failure", _dns_fail, False),
    ("secret_resolution_failure", _secret_resolution_failure, False),
    ("kill_switch_tripped", _kill_switch, False),
)


def _classify(reason: str) -> str:
    try:
        return classify_retry(reason)
    except Exception:
        return "UNKNOWN"


def simulate_fault(mode: str) -> dict[str, Any]:
    """Run one fault simulation. Extracts only deterministic classification fields."""
    entry = next((e for e in FAULT_MODES if e[0] == mode), None)
    if entry is None:
        raise M39Error("unknown_fault_mode", mode)
    _, runner, expected_retryable = entry
    r = runner()
    reason = str(r.get("reason", ""))
    retry_class = _classify(reason)
    retryable = retry_class == "RETRYABLE"
    fails_closed = (r.get("ok") is False) and bool(reason)
    handle_closed = bool(r.get("handle_closed", True))
    lease_revoked = bool(r.get("lease_revoked", False))
    return {
        "mode": mode,
        "status": SIMULATED,
        "ok": bool(r.get("ok")),
        "reason": reason[:80],
        "retry_classification": retry_class,
        "retryable": retryable,
        "expected_retryable": expected_retryable,
        "retry_matches_expected": (
            expected_retryable is None or retryable == expected_retryable
        ),
        "fails_closed": fails_closed,
        "handle_closed": handle_closed,
        "lease_revoked_or_na": lease_revoked or not r.get("live_network", False),
        "live_network": bool(r.get("live_network", False)),
        "contains_secret_values": False,
    }


def run_simulation_matrix() -> dict[str, Any]:
    """Run every fault mode + baseline. Deterministic; SIMULATED_NOT_LIVE."""
    base = _baseline()
    baseline = {
        "mode": "baseline_fixture",
        "status": SIMULATED,
        "ok": bool(base.get("ok")),
        "reason": str(base.get("reason", ""))[:40],
        "handle_closed": bool(base.get("handle_closed", True)),
        "contains_secret_values": False,
    }
    results = [simulate_fault(m) for (m, _, _) in FAULT_MODES]

    all_fail_closed = all(x["fails_closed"] for x in results)
    all_handles_closed = all(x["handle_closed"] for x in results) and baseline["handle_closed"]
    all_retry_expected = all(x["retry_matches_expected"] for x in results)
    baseline_ok = baseline["ok"] is True
    no_live = all(not x["live_network"] for x in results) and not base.get("live_network", False)

    verdict = (
        "ALL_FAULTS_FAIL_CLOSED"
        if (all_fail_closed and all_handles_closed and all_retry_expected and baseline_ok and no_live)
        else "SIMULATION_DISCREPANCY"
    )
    body = {
        "schema": SCHEMA_VERSION,
        "milestone": "M39.2",
        "status": SIMULATED,
        "verdict": verdict,
        "baseline": baseline,
        "fault_count": len(results),
        "results": results,
        "invariants": {
            "all_faults_fail_closed": all_fail_closed,
            "all_secret_handles_closed": all_handles_closed,
            "all_retry_classifications_match": all_retry_expected,
            "baseline_passes": baseline_ok,
            "no_live_network": no_live,
        },
        "authorities": dict(AUTHORITIES),
        "banner": NON_PRODUCTION_BANNER,
        "trading_guardian": "UNENGAGED",
        "contains_secret_values": False,
    }
    body["fingerprint"] = _hmac(
        _FP_DOMAIN,
        json.dumps(
            {k: body[k] for k in sorted(body) if k != "fingerprint"},
            sort_keys=True, separators=(",", ":"),
        ).encode(),
        length=24,
    )
    return body


def build_m39_2_evidence() -> dict[str, dict[str, Any]]:
    matrix = run_simulation_matrix()
    return {
        "failure_simulation_matrix": matrix,
        "summary": {
            "schema": "m39_2.summary.v1",
            "milestone": "M39.2",
            "verdict": matrix["verdict"],
            "status": SIMULATED,
            "fault_modes": [m for (m, _, _) in FAULT_MODES],
            "authorities": dict(AUTHORITIES),
            "trading_guardian": "UNENGAGED",
            "contains_secret_values": False,
        },
    }


def emit_m39_2_evidence(out_dir: str | Path) -> dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    bodies = build_m39_2_evidence()
    written: list[str] = []
    for name, body in bodies.items():
        assert is_clean(body), f"m39_2 evidence not leak-clean: {name}"
        p = out / f"{name}.json"
        p.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n")
        written.append(str(p))
    return {"written": written, "count": len(written), "dir": str(out)}
