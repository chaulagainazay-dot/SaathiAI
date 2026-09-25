"""M355 — the isolated local reasoning adapter.

The suite runs with no daemon: every path is exercised through an injected
opener or the scripted adapter. The two tests that need a live provider skip
themselves when one is not reachable, and say so rather than passing silently.

What is asserted, in order of importance:

1. the adapter cannot reach a non-loopback host, a credential or a tool;
2. timeout, cancel and retry behave as documented;
3. metadata is recorded, and a token count says whether it was measured;
4. no automatic fallback exists between adapters.
"""
from __future__ import annotations

import json
import urllib.error
from pathlib import Path

import pytest

from saathi.agentdev import model_adapter as adapter_module
from saathi.agentdev.model_adapter import (
    ADAPTER_VERSION,
    DEFAULT_MODEL,
    FORBIDDEN_OPTION_KEYS,
    LOOPBACK_HOSTS,
    ModelAdapterError,
    ModelRequest,
    ModelResponse,
    OllamaAdapter,
    ScriptedAdapter,
    TokenAccounting,
    assert_loopback,
    assert_no_forbidden_options,
    estimate_tokens,
    verify_adapter,
)


def _opener(payload=None, *, raises=None, record=None):
    """Build a fake transport. Never opens a socket."""
    def opener(url, body, timeout):
        if record is not None:
            record.append({"url": url, "body": body, "timeout": timeout})
        if raises is not None:
            raise raises
        return dict(payload or {"response": "ok", "done_reason": "stop"})

    return opener


def _live_adapter() -> OllamaAdapter | None:
    adapter = OllamaAdapter(DEFAULT_MODEL)
    return adapter if adapter.health().get("healthy") else None


# --------------------------------------------------------------------------
# Isolation — the reason this module exists
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url", ["http://127.0.0.1:11434", "http://localhost:11434", "http://[::1]:11434"]
)
def test_loopback_endpoints_are_accepted(url):
    assert assert_loopback(url).endswith(":11434")


def test_every_declared_loopback_host_is_reachable_through_a_url():
    # urlparse lowercases and unbrackets the authority, so each declared host
    # must be the form that comparison actually sees.
    assert LOOPBACK_HOSTS == {"127.0.0.1", "localhost", "::1"}


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://api.openai.com/v1",
        "http://example.com:11434",
        "http://10.0.0.5:11434",
        "http://169.254.169.254/latest/meta-data",
        "ftp://127.0.0.1/x",
        "file:///etc/passwd",
    ],
)
def test_a_non_loopback_endpoint_is_refused_before_any_socket(endpoint):
    with pytest.raises(ModelAdapterError) as exc:
        assert_loopback(endpoint)
    assert exc.value.code in ("endpoint_not_loopback", "endpoint_scheme_not_allowed")


def test_the_adapter_refuses_a_non_loopback_endpoint_at_construction():
    with pytest.raises(ModelAdapterError) as exc:
        OllamaAdapter("m", endpoint="https://api.anthropic.com")
    assert exc.value.code == "endpoint_not_loopback"


@pytest.mark.parametrize("key", sorted(FORBIDDEN_OPTION_KEYS))
def test_every_forbidden_option_is_refused(key):
    with pytest.raises(ModelAdapterError) as exc:
        assert_no_forbidden_options({key: "anything"})
    assert exc.value.code == "forbidden_option"


def test_the_module_imports_no_shell_or_filesystem_primitive():
    """Checked against the parsed imports, not a substring of the prose."""
    import ast

    source = Path(adapter_module.__file__).read_text(encoding="utf-8")
    imported: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert imported.isdisjoint({
        "subprocess", "os", "shutil", "pathlib", "socket", "ctypes", "pty", "shlex",
    }), sorted(imported)




def test_no_request_carries_an_authorization_header():
    record: list[dict] = []
    adapter = OllamaAdapter("m", opener=_opener(record=record))
    adapter.generate(ModelRequest(prompt="hi"))
    assert record
    for call in record:
        assert "authorization" not in json.dumps(call["body"]).lower()
        assert "api_key" not in json.dumps(call["body"]).lower()


def test_the_request_body_offers_the_model_no_tools():
    record: list[dict] = []
    OllamaAdapter("m", opener=_opener(record=record)).generate(ModelRequest(prompt="hi"))
    body = record[0]["body"]
    assert set(body) <= {"model", "prompt", "stream", "think", "options", "system", "format"}
    assert "tools" not in body


def test_capabilities_name_what_the_adapter_denies():
    denies = set(OllamaAdapter("m", opener=_opener()).capabilities()["denies"])
    assert {
        "shell_access", "filesystem_writes", "tool_invocation",
        "non_loopback_network", "credentials", "provider_fallback",
    } <= denies


def test_capabilities_name_the_nine_required_supports():
    supports = set(OllamaAdapter("m", opener=_opener()).capabilities()["supports"])
    assert supports == {
        "load", "health_check", "send_prompt", "receive_response",
        "record_metadata", "timeout", "cancel", "retry", "resource_measurement",
    }


def test_capabilities_publish_the_determinism_limitation():
    limitation = OllamaAdapter("m", opener=_opener()).capabilities()["limitation"]
    assert "not guaranteed" in limitation


# --------------------------------------------------------------------------
# Request handling
# --------------------------------------------------------------------------


def test_an_empty_model_name_is_refused():
    with pytest.raises(ModelAdapterError) as exc:
        OllamaAdapter("   ")
    assert exc.value.code == "missing_model"


def test_defaults_are_reproducible():
    request = ModelRequest(prompt="x")
    assert request.temperature == 0.0
    assert request.seed == 1


def test_the_request_is_frozen_so_a_retry_cannot_change_it():
    request = ModelRequest(prompt="x")
    with pytest.raises(Exception):
        request.prompt = "y"  # type: ignore[misc]


def test_json_mode_sets_the_provider_format_flag():
    record: list[dict] = []
    adapter = OllamaAdapter("m", opener=_opener(record=record))
    adapter.generate(ModelRequest(prompt="x", json_mode=True))
    assert record[0]["body"]["format"] == "json"


def test_reasoning_traces_are_not_requested():
    record: list[dict] = []
    OllamaAdapter("m", opener=_opener(record=record)).generate(ModelRequest(prompt="x"))
    assert record[0]["body"]["think"] is False


def test_the_declared_timeout_reaches_the_transport():
    record: list[dict] = []
    adapter = OllamaAdapter("m", opener=_opener(record=record))
    adapter.generate(ModelRequest(prompt="x", timeout_s=7.5))
    assert record[0]["timeout"] == 7.5


def test_stop_sequences_are_forwarded():
    record: list[dict] = []
    adapter = OllamaAdapter("m", opener=_opener(record=record))
    adapter.generate(ModelRequest(prompt="x", stop=("###",)))
    assert record[0]["body"]["options"]["stop"] == ["###"]


# --------------------------------------------------------------------------
# Metadata
# --------------------------------------------------------------------------


def test_measured_token_counts_are_used_when_the_provider_reports_them():
    adapter = OllamaAdapter("m", opener=_opener({
        "response": "hello", "done_reason": "stop",
        "prompt_eval_count": 11, "eval_count": 3,
    }))
    response = adapter.generate(ModelRequest(prompt="x"))
    assert response.tokens.source == "measured"
    assert response.tokens.total_tokens == 14


def test_estimated_token_counts_are_labelled_when_the_provider_reports_none():
    adapter = OllamaAdapter("m", opener=_opener({"response": "hello"}))
    response = adapter.generate(ModelRequest(prompt="x" * 40))
    assert response.tokens.source == "estimated"
    assert "divided by four" in response.tokens.to_dict()["note"]


def test_estimate_is_characters_over_four():
    assert estimate_tokens("") == 0
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("abcde") == 2


def test_a_response_records_latency_attempts_and_memory():
    adapter = OllamaAdapter("m", opener=_opener())
    response = adapter.generate(ModelRequest(prompt="x", label="probe"))
    assert response.ok
    assert response.latency_ms >= 0.0
    assert response.attempts == 1
    assert response.request_label == "probe"
    assert response.peak_memory_growth_bytes >= 0


def test_a_response_explains_whose_memory_it_measured():
    response = OllamaAdapter("m", opener=_opener()).generate(ModelRequest(prompt="x"))
    assert "provider daemon" in response.to_dict()["memory_note"]


def test_throughput_is_zero_without_a_measured_response():
    assert ModelResponse(ok=True, model="m", adapter="a").throughput_tokens_per_second == 0.0


def test_throughput_is_derived_from_response_tokens_and_latency():
    response = ModelResponse(
        ok=True, model="m", adapter="a", latency_ms=1000.0,
        tokens=TokenAccounting(prompt_tokens=5, response_tokens=20, source="measured"),
    )
    assert response.throughput_tokens_per_second == 20.0


def test_a_response_is_json_serialisable():
    json.dumps(OllamaAdapter("m", opener=_opener()).generate(ModelRequest(prompt="x")).to_dict())


# --------------------------------------------------------------------------
# Timeout, retry, cancel
# --------------------------------------------------------------------------


def test_a_timeout_is_reported_as_a_timeout_not_a_generic_failure():
    adapter = OllamaAdapter("m", max_attempts=1, opener=_opener(raises=TimeoutError("slow")))
    response = adapter.generate(ModelRequest(prompt="x"))
    assert response.ok is False
    assert response.error_code == "timeout"


def test_a_socket_timeout_wrapped_in_urlerror_is_still_a_timeout():
    adapter = OllamaAdapter(
        "m", max_attempts=1,
        opener=_opener(raises=urllib.error.URLError(TimeoutError("timed out"))),
    )
    assert adapter.generate(ModelRequest(prompt="x")).error_code == "timeout"


def test_an_unreachable_provider_is_reported_as_unreachable():
    adapter = OllamaAdapter(
        "m", max_attempts=1, opener=_opener(raises=urllib.error.URLError("refused"))
    )
    assert adapter.generate(ModelRequest(prompt="x")).error_code == "provider_unreachable"


def test_a_failing_call_retries_up_to_the_declared_maximum():
    calls: list[dict] = []
    adapter = OllamaAdapter(
        "m", max_attempts=3,
        opener=_opener(raises=urllib.error.URLError("refused"), record=calls),
    )
    response = adapter.generate(ModelRequest(prompt="x"))
    assert response.attempts == 3
    assert len(calls) == 3


def test_a_successful_call_does_not_retry():
    calls: list[dict] = []
    adapter = OllamaAdapter("m", max_attempts=3, opener=_opener(record=calls))
    assert adapter.generate(ModelRequest(prompt="x")).attempts == 1
    assert len(calls) == 1


def test_max_attempts_is_never_below_one():
    assert OllamaAdapter("m", max_attempts=0, opener=_opener()).max_attempts == 1


def test_cancel_stops_the_next_attempt_and_is_recorded():
    calls: list[dict] = []
    adapter = OllamaAdapter("m", max_attempts=3, opener=_opener(record=calls))
    adapter.cancel()
    response = adapter.generate(ModelRequest(prompt="x"))
    assert response.cancelled is True
    assert response.ok is False
    assert response.error_code == "cancelled"
    assert calls == []


def test_cancel_can_be_reset():
    adapter = OllamaAdapter("m", opener=_opener())
    adapter.cancel()
    adapter.reset_cancel()
    assert adapter.generate(ModelRequest(prompt="x")).ok is True


def test_a_non_json_provider_reply_is_reported_not_raised():
    adapter = OllamaAdapter(
        "m", max_attempts=1,
        opener=_opener(raises=json.JSONDecodeError("bad", "doc", 0)),
    )
    assert adapter.generate(ModelRequest(prompt="x")).error_code == (
        "provider_response_not_json"
    )


# --------------------------------------------------------------------------
# Health, and no fallback
# --------------------------------------------------------------------------


def test_health_reports_unreachable_without_raising():
    adapter = OllamaAdapter("m", endpoint="http://127.0.0.1:1")
    health = adapter.health()
    assert health["healthy"] is False
    assert health["error_code"] == "provider_unreachable"


def test_health_reports_a_missing_model_distinctly(monkeypatch):
    adapter = OllamaAdapter("absent:1b")
    monkeypatch.setattr(
        adapter, "_get", lambda path, timeout=5.0: {"models": [{"name": "other:1b"}]}
    )
    health = adapter.health()
    assert health["healthy"] is False
    assert health["error_code"] == "model_not_installed"
    assert health["available_models"] == ["other:1b"]


def test_a_failed_call_returns_a_failure_rather_than_another_model_s_answer():
    adapter = OllamaAdapter(
        "configured:1b", max_attempts=1,
        opener=_opener(raises=urllib.error.URLError("refused")),
    )
    response = adapter.generate(ModelRequest(prompt="x"))
    assert response.ok is False
    assert response.text == ""
    assert response.model == "configured:1b"
    assert response.adapter == "ollama"


def test_neither_adapter_can_construct_the_other():
    """Prose may name the sibling; code may not instantiate it."""
    import inspect

    assert "ScriptedAdapter(" not in inspect.getsource(OllamaAdapter)
    assert "OllamaAdapter(" not in inspect.getsource(ScriptedAdapter)


def test_a_response_names_the_adapter_that_produced_it():
    assert OllamaAdapter("m", opener=_opener()).generate(
        ModelRequest(prompt="x")
    ).adapter == "ollama"
    assert ScriptedAdapter().generate(ModelRequest(prompt="x")).adapter == "scripted"


# --------------------------------------------------------------------------
# Scripted adapter
# --------------------------------------------------------------------------


def test_the_scripted_adapter_is_deterministic():
    a = ScriptedAdapter(responses=["one", "two"])
    assert a.generate(ModelRequest(prompt="x")).text == "one"
    assert a.generate(ModelRequest(prompt="x")).text == "two"
    assert a.generate(ModelRequest(prompt="x")).text == ""


def test_the_scripted_adapter_records_what_it_was_asked():
    a = ScriptedAdapter(responses=["r"])
    a.generate(ModelRequest(prompt="the question", label="q1"))
    assert a.calls[0].prompt == "the question"
    assert a.calls[0].label == "q1"


def test_the_scripted_adapter_declares_it_establishes_nothing():
    assert "Establishes nothing" in ScriptedAdapter().capabilities()["limitation"]


def test_the_scripted_adapter_honours_cancel():
    a = ScriptedAdapter(responses=["r"])
    a.cancel()
    assert a.generate(ModelRequest(prompt="x")).cancelled is True


# --------------------------------------------------------------------------
# Verification report
# --------------------------------------------------------------------------


def test_verification_of_an_unreachable_provider_is_a_result_not_an_exception():
    report = verify_adapter(OllamaAdapter("m", endpoint="http://127.0.0.1:1"))
    assert report["verified"] is False
    assert report["reason"] == "provider_unreachable"
    assert report["calls"] == []


def test_verification_report_carries_capabilities_and_host(monkeypatch):
    adapter = ScriptedAdapter(responses=['{"status":"ok","reason":"x"}', "ready", "unknown"])
    monkeypatch.setattr(adapter, "health", lambda: {"healthy": True, "error_code": ""})
    report = verify_adapter(adapter)
    assert report["verified"] is True
    assert report["capabilities"]["adapter_version"] == ADAPTER_VERSION
    assert report["host_before"]["total_memory_bytes"] > 0
    assert len(report["calls"]) == 3
    assert "not what any model will do" in report["limitation"]


def test_verification_records_whether_json_mode_parsed(monkeypatch):
    adapter = ScriptedAdapter(responses=["ready", "not json at all", "unknown"])
    monkeypatch.setattr(adapter, "health", lambda: {"healthy": True, "error_code": ""})
    row = next(c for c in verify_adapter(adapter)["calls"] if c["label"] == "json_object")
    assert row["json_parsed"] is False


# --------------------------------------------------------------------------
# Live provider — skipped when absent, never silently passed
# --------------------------------------------------------------------------


@pytest.mark.parametrize("_", [0])
def test_live_provider_answers_and_reports_measured_tokens(_):
    adapter = _live_adapter()
    if adapter is None:
        pytest.skip(f"no local provider serving {DEFAULT_MODEL}; live path not exercised")
    response = adapter.generate(
        ModelRequest(prompt="Reply with exactly one word: ready", max_tokens=16,
                     label="live")
    )
    assert response.ok, response.error_detail
    assert response.tokens.source == "measured"
    assert response.latency_ms > 0


def test_live_provider_honours_json_mode():
    adapter = _live_adapter()
    if adapter is None:
        pytest.skip(f"no local provider serving {DEFAULT_MODEL}; live path not exercised")
    response = adapter.generate(
        ModelRequest(
            prompt='Return a JSON object with keys "status" and "reason".',
            max_tokens=96, json_mode=True, label="live_json",
        )
    )
    assert response.ok, response.error_detail
    json.loads(response.text)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def test_cli_model_capabilities_lists_the_denials(capsys):
    from saathi.agentdev.cli import main

    assert main(["model", "capabilities"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert "shell_access" in payload["denies"]


def test_cli_model_health_exits_nonzero_when_unreachable(capsys):
    from saathi.agentdev.cli import EXIT_FAIL, main

    code = main(["model", "health", "--endpoint", "http://127.0.0.1:1"])
    assert code == EXIT_FAIL
    assert json.loads(capsys.readouterr().out)["healthy"] is False


def test_cli_model_health_refuses_a_remote_endpoint(capsys):
    from saathi.agentdev.cli import EXIT_REFUSED, main

    code = main(["model", "health", "--endpoint", "https://api.openai.com"])
    assert code == EXIT_REFUSED
    assert json.loads(capsys.readouterr().out)["error"] == "endpoint_not_loopback"
