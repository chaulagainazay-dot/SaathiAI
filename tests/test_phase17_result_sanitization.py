"""Phase 17 — execution results are sanitised before they leave the gateway.

Two failure modes, opposite in shape. A sanitiser that misses a credential leaks
it; a sanitiser that redacts everything destroys the result's purpose and gets
switched off. Both are tested here with roughly equal weight, because only one
of them is usually tested and it is not the second one.

Every credential below is synthetic. Nothing here is a real key, and nothing
here contacts anything.
"""
from __future__ import annotations

import time

import pytest

from saathi.execution.errors import ErrorSeverity, ExecutionError
from saathi.execution.gateway import ExecutionGateway
from saathi.execution.results import ExecutionResult, ExecutionStatus
from saathi.execution.sanitization import (
    MAX_TEXT_CHARS,
    SanitizationReport,
    sanitize,
)
from saathi.execution.toolintent import ToolIntent

# Synthetic credentials. Shaped like the real formats, valid as none of them.
FAKE_OPENAI = "sk-abcdefghijklmnop1234567890"
FAKE_GITHUB = "ghp_abcdefghijklmnopqrstuvwxyz012345"
FAKE_AWS = "AKIAIOSFODNN7EXAMPLE"
FAKE_SLACK = "xoxb-000000000000-abcdefghijkl"
FAKE_JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.c2lnbmF0dXJlZmFrZQ"
FAKE_PEM = "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA\n"


def _redacted(obj) -> str:
    import json

    return json.dumps(obj, default=str)


# ── structured redaction ────────────────────────────────────────────────────

@pytest.mark.parametrize("key", [
    "password", "token", "api_key", "apikey", "access_token", "refresh_token",
    "authorization", "cookie", "secret", "client_secret", "private_key",
])
def test_a_credential_key_is_redacted_whatever_its_value_looks_like(key):
    """Key-aware first: a short or oddly-formatted password is still a password,
    and value-shape detection alone would pass it straight through."""
    out, report = sanitize({key: "short"})
    assert out[key] == "***REDACTED***"
    assert report.redaction_count == 1


def test_a_nested_credential_is_found():
    out, report = sanitize({"a": {"b": {"c": {"password": "hunter2"}}}})
    assert "hunter2" not in _redacted(out)
    assert report.redaction_count == 1


def test_credentials_inside_lists_are_found():
    out, _ = sanitize({"items": [{"safe": "ok"}, {"token": "t"}, ["x", {"secret": "s"}]]})
    blob = _redacted(out)
    assert "ok" in blob
    for leaked in ("\"t\"", "\"s\""):
        assert leaked not in blob


def test_multiple_credentials_are_all_removed_and_counted():
    out, report = sanitize({
        "password": "p", "nested": {"api_key": "k"},
        "log": f"token {FAKE_OPENAI} and {FAKE_AWS}",
    })
    assert report.redaction_count >= 4
    for secret in ("\"p\"", "\"k\"", FAKE_OPENAI, FAKE_AWS):
        assert secret not in _redacted(out)


def test_tuples_keep_their_type():
    out, _ = sanitize({"pair": ("safe", {"token": "t"})})
    assert isinstance(out["pair"], tuple)


# ── free-text detection ─────────────────────────────────────────────────────

@pytest.mark.parametrize("secret", [FAKE_OPENAI, FAKE_GITHUB, FAKE_AWS,
                                    FAKE_SLACK, FAKE_JWT])
def test_a_credential_embedded_in_prose_is_removed(secret):
    out, report = sanitize({"message": f"request failed using {secret} retrying"})
    assert secret not in _redacted(out)
    assert report.redaction_count == 1
    # The surrounding message survives: an error that says what failed is worth
    # more than one reduced to a redaction marker.
    assert "request failed" in out["message"] and "retrying" in out["message"]


def test_a_private_key_block_is_removed():
    out, _ = sanitize({"pem": FAKE_PEM})
    assert "BEGIN RSA PRIVATE KEY" not in _redacted(out)


@pytest.mark.parametrize("header", [
    "Authorization: Bearer abc123def456ghi",
    "Cookie: session=abc123def456; Path=/",
    "api_key=abcdef123456",
    "password=correcthorsebattery",
])
def test_a_credential_assignment_in_text_keeps_the_field_name_not_the_value(header):
    """The field name tells an operator which credential was involved; the value
    is the thing that must not survive."""
    out, _ = sanitize({"captured": header})
    cleaned = out["captured"]
    field = header.split(":")[0].split("=")[0]
    assert field in cleaned, "the operator still needs to know what was involved"
    assert "***REDACTED***" in cleaned


# ── ordinary data must survive ──────────────────────────────────────────────

@pytest.mark.parametrize("payload", [
    {"order_id": "ORD-99213", "status": "shipped"},
    {"uuid": "550e8400-e29b-41d4-a716-446655440000"},
    {"summary": "Revenue rose 12% to NPR 4,500 in Q3."},
    {"sha": "a3f5b91c4d2e8f01", "path": "/var/log/app.log"},
    {"count": 42, "ratio": 0.75, "ok": True, "missing": None},
    {"email": "someone@example.com", "url": "https://example.com/orders/12"},
    {"key_findings": ["latency down", "cost flat"]},
])
def test_ordinary_data_is_returned_unchanged(payload):
    """A sanitiser that redacts everything is not acceptable. Ids, hashes, prose,
    numbers and URLs are the substance of a tool result."""
    out, report = sanitize(payload)
    assert out == payload
    assert report.redaction_count == 0
    assert report.categories == set()


def test_a_field_merely_named_key_is_not_treated_as_a_credential():
    """`key_findings` and `monkey` contain "key". Matching on that would eat
    ordinary business fields."""
    out, report = sanitize({"key_findings": ["a"], "monkey": "b", "keyboard": "c"})
    assert report.redaction_count == 0
    assert out["monkey"] == "b"


# ── the input is never mutated ──────────────────────────────────────────────

def test_the_original_payload_is_left_alone():
    """Callers keep raw output for their own bounded purposes; editing it in
    place would silently change what they already hold."""
    original = {"password": "hunter2", "nested": {"list": [1, 2]}}
    out, _ = sanitize(original)
    assert original["password"] == "hunter2"
    assert out["password"] == "***REDACTED***"
    out["nested"]["list"].append(3)
    assert original["nested"]["list"] == [1, 2]


# ── bounds and hostile shapes ───────────────────────────────────────────────

def test_oversized_text_is_truncated_not_passed_through_unscanned():
    out, report = sanitize({"log": "a" * (MAX_TEXT_CHARS + 5000)})
    assert len(out["log"]) <= MAX_TEXT_CHARS + 32
    assert "truncated" in report.categories


def test_bytes_are_withheld_rather_than_guessed_at():
    """A blob that might carry a credential is not returned on the chance it
    does not."""
    out, report = sanitize({"blob": b"\x00\x01binary payload"})
    assert "withheld" in out["blob"]
    assert "uninspectable" in report.categories


def test_a_pathologically_deep_structure_is_bounded():
    payload: dict = {}
    node = payload
    for _ in range(200):
        node["n"] = {}
        node = node["n"]
    node["password"] = "deep"
    out, report = sanitize(payload)
    assert "deep" not in _redacted(out)
    assert "uninspectable" in report.categories


def test_a_self_referential_structure_does_not_hang():
    payload: dict = {"a": 1}
    payload["self"] = payload
    out, report = sanitize(payload)  # deepcopy handles the cycle; depth bounds it
    assert report is not None


# ── fail closed ─────────────────────────────────────────────────────────────

class _Hostile:
    """Raises on deep-copy, which is how sanitisation can fail in practice."""

    def __deepcopy__(self, memo):
        raise RuntimeError("cannot copy")


def test_a_sanitiser_failure_withholds_the_payload_rather_than_returning_it():
    """The one shortcut that would make every other guarantee conditional."""
    out, report = sanitize({"data": _Hostile()})
    assert out is None
    assert report.failed is True
    assert report.clean is False


def test_a_failed_report_says_so_in_its_note_without_naming_anything():
    report = SanitizationReport(failed=True)
    assert "withheld" in report.note()
    assert report.to_dict()["sanitized"] is False


def test_provenance_names_categories_never_values():
    _, report = sanitize({"password": "hunter2", "log": f"x {FAKE_OPENAI}"})
    blob = report.note() + _redacted(report.to_dict())
    assert "hunter2" not in blob and FAKE_OPENAI not in blob
    assert report.to_dict()["redaction_count"] >= 2


# ── the gateway boundary ────────────────────────────────────────────────────

@pytest.fixture
def gw():
    return ExecutionGateway()


def _intent():
    return ToolIntent(intent_id="p17-san", operation="local-llm-inference",
                      actor_id="user:test", parameters={})


def test_the_gateway_sanitises_result_data(gw):
    result = ExecutionResult(status=ExecutionStatus.SUCCESS,
                             data={"text": f"here is {FAKE_OPENAI}",
                                   "api_key": "abc"})
    sanitized = gw.sanitize_result(result, _intent())
    blob = _redacted(sanitized.sanitized_data)
    assert FAKE_OPENAI not in blob and "abc" not in blob
    assert sanitized.is_clean is True
    assert "redactions" in sanitized.sanitization_notes


def test_the_gateway_sanitises_error_messages_and_context(gw):
    """Errors leak as readily as successes: a failure that quotes the request it
    made carries the credential it made it with."""
    result = ExecutionResult(
        status=ExecutionStatus.FAILED,
        error=ExecutionError(code="UPSTREAM", severity=ErrorSeverity.HIGH,
                             message=f"401 from provider, sent {FAKE_GITHUB}",
                             context={"authorization": "Bearer abc123def456"}),
    )
    sanitized = gw.sanitize_result(result, _intent())
    blob = _redacted(sanitized.error.message) + _redacted(sanitized.error.context)
    assert FAKE_GITHUB not in blob and "abc123def456" not in blob
    # Diagnostic value preserved.
    assert sanitized.error.code == "UPSTREAM"
    assert "401 from provider" in sanitized.error.message


def test_a_clean_result_reports_zero_redactions(gw):
    result = ExecutionResult(status=ExecutionStatus.SUCCESS,
                             data={"answer": "42", "order_id": "ORD-1"})
    sanitized = gw.sanitize_result(result, _intent())
    assert sanitized.sanitized_data == {"answer": "42", "order_id": "ORD-1"}
    assert sanitized.sanitization_notes == "sanitized: 0 redactions"


def test_is_clean_reflects_the_sanitiser_rather_than_asserting_it(gw):
    """`is_clean` used to `return True` with the comment "Verified in
    sanitization phase", while that phase was an unimplemented stub."""
    result = ExecutionResult(status=ExecutionStatus.SUCCESS,
                             data={"bad": _Hostile()})
    sanitized = gw.sanitize_result(result, _intent())
    assert sanitized.is_clean is False
    assert sanitized.sanitized_data is None


def test_a_none_result_does_not_crash_the_boundary(gw):
    assert gw.sanitize_result(None, _intent()).sanitized_data is None


# ── the full execution path ─────────────────────────────────────────────────

def test_no_secret_reaches_the_caller_through_execute_intent():
    """The escape path this closed: the sanitised result went to evidence while
    the raw one was returned to the caller."""
    import asyncio
    from datetime import datetime

    from saathi.execution.gateway import ExecutionContext
    from saathi.execution.integration import SaathiExecutionSystem
    from saathi.execution.queue.memory import MemoryQueue

    system = SaathiExecutionSystem(MemoryQueue())

    class _LeakyProvider:
        async def route_and_execute(self, intent, policy):
            return ExecutionResult(
                status=ExecutionStatus.SUCCESS,
                data={"text": f"leaked {FAKE_OPENAI}", "password": "hunter2",
                      "kept": "ordinary value"},
                connector_trace={"authorization": "Bearer abc123def456"},
            )

    system.model_gateway = _LeakyProvider()
    system._get_model_policy = lambda i: {"provider_choice": "x",
                                          "fallback_chain": [],
                                          "data_sensitivity": "internal"}
    now = datetime.now()
    intent = ToolIntent(intent_id="p17-e2e-san", operation="local-llm-inference",
                        actor_id="user:test", parameters={"prompt": "hi"})
    ctx = ExecutionContext(actor_id="user:test", business_unit="t",
                           timestamp=now, current_time=now)

    from saathi.execution.authorization_sources import actor_context

    with actor_context(None):  # system actor: READ_ONLY inference is permitted
        result = asyncio.run(system.execute_intent(intent, ctx))

    # Non-vacuity first. If the provider had not run, or the result had come
    # back empty, every assertion below would pass while proving nothing.
    assert result.status is ExecutionStatus.SUCCESS
    assert result.data and result.data["kept"] == "ordinary value"

    blob = _redacted(result.data) + _redacted(result.connector_trace)
    assert FAKE_OPENAI not in blob
    assert "hunter2" not in blob
    assert "abc123def456" not in blob


def test_evidence_carries_the_sanitised_result_not_the_raw_one(gw):
    from saathi.execution.state import StateHistory

    intent = _intent()
    result = ExecutionResult(status=ExecutionStatus.SUCCESS,
                             data={"password": "hunter2"})
    sanitized = gw.sanitize_result(result, intent)
    evidence = gw.record_evidence(intent, StateHistory(intent_id=intent.intent_id),
                                  sanitized)
    assert "hunter2" not in _redacted(evidence.sanitized_result.sanitized_data)
    assert evidence.execution_result is None, "raw result never enters evidence"


# ── performance ─────────────────────────────────────────────────────────────

def test_sanitisation_is_bounded_on_a_realistic_payload():
    """No catastrophic backtracking, no full-system scan."""
    payload = {
        "rows": [{"id": i, "name": f"item {i}", "note": "ordinary text " * 20}
                 for i in range(200)],
        "log": "GET /x 200 OK\n" * 500,
    }
    start = time.perf_counter()
    _, report = sanitize(payload)
    elapsed = time.perf_counter() - start
    assert elapsed < 2.0, f"sanitisation took {elapsed:.2f}s"
    assert report.redaction_count == 0


def test_a_long_repetitive_string_does_not_blow_up_the_matcher():
    hostile = ("Authorization: " + "a" * 5000) * 20
    start = time.perf_counter()
    sanitize({"log": hostile})
    assert time.perf_counter() - start < 2.0


# ── the sanitisation TODO is resolved; the rest still cannot grant ──────────

def test_sanitize_result_no_longer_carries_a_todo():
    import inspect as _inspect

    assert "TODO" not in _inspect.getsource(ExecutionGateway.sanitize_result)


def test_no_remaining_todo_sits_on_the_output_boundary():
    """Four TODOs remain in the gateway. None of them is the thing that decides
    what leaves it, and none can turn a withheld payload into a returned one."""
    import inspect as _inspect

    for method in (ExecutionGateway.sanitize_result,
                   ExecutionGateway.record_evidence):
        assert "TODO" not in _inspect.getsource(method), method.__name__


def test_sanitisation_does_not_touch_authorization():
    """Output hardening must not become an authority surface. The sanitiser
    reads no decision and grants nothing."""
    import inspect as _inspect

    import saathi.execution.sanitization as sanitization

    source = _inspect.getsource(sanitization)
    for forbidden in ("authorize", "AuthorizationInputs", "Decision",
                      "approval", "kill_switch", "rbac"):
        assert forbidden not in source, forbidden
