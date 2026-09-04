"""Kimi K3 / NVIDIA provider — contract qualification (K3-01 … K3-25).

The integration point is an ordinary `InferenceEngine`, so most of what matters
is that it behaves like one: it executes and reports, and owns no routing, no
policy and no authority. The tests that matter most are the ones proving what it
*cannot* do -- reach ExecutionGateway, bypass Trading Guardian, leak a
credential, or surface a model's private reasoning into a conversation.

Everything here is offline. `httpx` is replaced with a client that raises, so a
real NVIDIA request is a test failure rather than a silent charge against
someone's quota. Nothing in this file constitutes live certification.
"""
from __future__ import annotations

import ast
import json
import pathlib

import pytest

from saathi.inference.adapters.nvidia import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_REASONING,
    KIMI_K3,
    MAX_ALLOWED_TOKENS,
    NVIDIA_API_KEY_ENV,
    NVIDIA_CHAT_COMPLETIONS_URL,
    NvidiaConfigError,
    NvidiaEngine,
    REASONING_EFFORT,
    api_key_present,
    build_payload,
    chunk_from_delta,
    parse_completion,
    parse_sse_line,
    to_provider_messages,
    validate_image_url,
)
from saathi.inference.errors import (
    EngineError,
    EngineTimeoutError,
    EngineUnhealthyError,
)

#: Deliberately not shaped like a real NVIDIA key. Using the vendor's `nvapi-`
#: prefix here would make this line trip every secret scanner that looks for
#: one -- including the repository's own -- for a value that is not a secret.
SYNTHETIC_KEY = "TEST-FIXTURE-NOT-A-CREDENTIAL"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """A real provider request is a certification failure, not a side effect."""
    import httpx

    def _boom(*a, **k):
        raise AssertionError("a test attempted a real NVIDIA request")

    for verb in ("post", "get", "put", "patch", "delete", "request", "stream"):
        monkeypatch.setattr(httpx, verb, _boom, raising=False)


@pytest.fixture()
def keyed(monkeypatch):
    monkeypatch.setenv(NVIDIA_API_KEY_ENV, SYNTHETIC_KEY)
    return SYNTHETIC_KEY


def _resolver(_host):
    """Deterministic DNS: a public address, so tests never touch a resolver."""
    return ["93.184.216.34"]


# ── K3-01 model registration ───────────────────────────────────────────────

def test_k3_01_model_is_registered():
    engine = NvidiaEngine()
    assert KIMI_K3 == "moonshotai/kimi-k3"
    assert engine.can_serve(KIMI_K3)


def test_k3_01b_the_engine_is_a_closed_model_list():
    """An engine that serves any string a caller passes is an open proxy to a
    paid API."""
    engine = NvidiaEngine()
    for other in ("gpt-4o", "claude-sonnet-5", "../../etc/passwd", ""):
        assert not engine.can_serve(other)


def test_k3_01c_the_path_is_declared_like_every_other_engine():
    from saathi.inference.path_inventory import CALL_PATH_INVENTORY

    paths = {p.path_id: p for p in CALL_PATH_INVENTORY}
    nvidia = paths.get("engine_nvidia")
    assert nvidia is not None, "engine not declared in the path inventory"
    assert nvidia.can_reach_cloud is True
    assert nvidia.default_enabled is False, "a remote tier must be off by default"


# ── K3-02 / K3-03 endpoint and identifier ──────────────────────────────────

def test_k3_02_endpoint_is_the_supplied_one():
    assert NVIDIA_CHAT_COMPLETIONS_URL == \
        "https://integrate.api.nvidia.com/v1/chat/completions"


def test_k3_02b_the_endpoint_is_not_caller_supplied():
    """An engine whose destination can be set per request is an SSRF primitive."""
    import inspect

    from saathi.inference.adapters import nvidia

    for name in ("generate", "stream"):
        sig = inspect.signature(getattr(nvidia.NvidiaEngine, name))
        assert "url" not in sig.parameters


def test_k3_03_payload_carries_the_canonical_identifier():
    payload = build_payload([{"role": "user", "content": "hi"}], model=KIMI_K3)
    assert payload["model"] == "moonshotai/kimi-k3"


# ── K3-04 / K3-05 secret handling ──────────────────────────────────────────

def test_k3_04_authorization_comes_from_configuration(keyed):
    assert api_key_present() is True


def test_k3_04b_a_placeholder_is_not_a_key(monkeypatch):
    """The convention the other cloud transports use: `YOUR...` is a template
    somebody has not filled in."""
    monkeypatch.setenv(NVIDIA_API_KEY_ENV, "YOUR_NVIDIA_API_KEY")
    assert api_key_present() is False


def test_k3_05_no_credential_appears_in_source():
    """No key, and no shell placeholder pasted in as a literal header either --
    `"Bearer $NVIDIA_API_KEY"` in Python sends the string, not the secret."""
    source = pathlib.Path("saathi/inference/adapters/nvidia.py").read_text()
    assert "$NVIDIA_API_KEY" not in source
    assert "nvapi-" not in source
    for marker in ("sk-", "Bearer nv", "api_key = \""):
        assert marker not in source


def test_k3_05b_the_key_is_never_in_an_error_message(monkeypatch):
    monkeypatch.delenv(NVIDIA_API_KEY_ENV, raising=False)
    from saathi.inference.adapters.nvidia import _api_key

    with pytest.raises(NvidiaConfigError) as excinfo:
        _api_key()
    message = str(excinfo.value)
    assert NVIDIA_API_KEY_ENV in message, "the variable is named, which is useful"
    assert SYNTHETIC_KEY not in message


def test_k3_05c_health_reports_availability_without_the_value(keyed):
    import asyncio

    health = asyncio.run(NvidiaEngine().health())
    assert health["ok"] is True
    assert SYNTHETIC_KEY not in json.dumps(health)


def test_k3_05d_no_credential_reaches_the_frontend_bundle():
    """A key that reaches JavaScript is a published key."""
    frontend = pathlib.Path("saathi-os")
    if not frontend.exists():
        pytest.skip("frontend not present")
    hits = []
    for path in list(frontend.rglob("*.js")) + list(frontend.rglob("*.jsx")):
        if "node_modules" in str(path) or ".next" in str(path):
            continue
        if "NVIDIA_API_KEY" in path.read_text(errors="ignore"):
            hits.append(str(path))
    assert hits == [], hits


# ── K3-06 / K3-07 serialization ────────────────────────────────────────────

def test_k3_06_text_request_serialization():
    payload = build_payload([{"role": "user", "content": "What is 2+2?"}],
                            model=KIMI_K3, temperature=0.2, max_tokens=64)
    assert payload["messages"] == [{"role": "user", "content": "What is 2+2?"}]
    assert payload["max_tokens"] == 64 and payload["temperature"] == 0.2
    assert payload["stream"] is False


def test_k3_07_image_and_text_serialization():
    """The multimodal shape from the supplied contract, with the URL validated
    before it leaves the process."""
    messages = [{"role": "user", "content": [
        {"type": "text", "text": "What is in this image?"},
        {"type": "image_url", "image_url": {"url": "https://example.com/a.jpg"}},
    ]}]
    payload = build_payload(messages, model=KIMI_K3, resolver=_resolver)
    parts = payload["messages"][0]["content"]
    assert parts[0] == {"type": "text", "text": "What is in this image?"}
    assert parts[1]["type"] == "image_url"
    assert parts[1]["image_url"]["url"] == "https://example.com/a.jpg"


def test_k3_07b_bounded_defaults_are_not_the_reference_maximums():
    """The supplied example uses `max_tokens=16384` and `reasoning_effort=max`.
    Those are the ceiling, not a sensible default for every call."""
    payload = build_payload([{"role": "user", "content": "hi"}], model=KIMI_K3)
    assert payload["max_tokens"] == DEFAULT_MAX_TOKENS < MAX_ALLOWED_TOKENS
    assert payload["reasoning_effort"] == REASONING_EFFORT[DEFAULT_REASONING]
    assert payload["reasoning_effort"] != "max"


def test_k3_07c_max_tokens_is_clamped_not_trusted():
    payload = build_payload([{"role": "user", "content": "x"}], model=KIMI_K3,
                            max_tokens=10**9)
    assert payload["max_tokens"] == MAX_ALLOWED_TOKENS


def test_k3_07d_arbitrary_provider_parameters_are_not_forwarded():
    """An engine that forwards an unfiltered dict has its behaviour defined by
    whoever calls it."""
    payload = build_payload([{"role": "user", "content": "x"}], model=KIMI_K3)
    assert set(payload) <= {"model", "messages", "max_tokens", "temperature",
                            "stream", "reasoning_effort", "seed", "tools"}


# ── image security (§8) ────────────────────────────────────────────────────

@pytest.mark.parametrize("url,expected", [
    ("file:///etc/passwd", "scheme_not_http"),
    ("data:image/png;base64,AAAA", "scheme_not_http"),
    ("gopher://example.com/x", "scheme_not_http"),
    ("https://user:pw@example.com/a.jpg", "userinfo_forbidden"),
    ("", "empty_url"),
    ("https:///a.jpg", "missing_host"),
])
def test_unsafe_image_urls_are_refused(url, expected):
    ok, reason = validate_image_url(url, resolver=_resolver)
    assert ok is False and reason == expected


@pytest.mark.parametrize("address,category", [
    ("127.0.0.1", "loopback"), ("10.0.0.5", "private"),
    ("192.168.1.10", "private"), ("169.254.169.254", "metadata"),
    ("0.0.0.0", "unspecified"),
])
def test_image_urls_resolving_to_internal_addresses_are_refused(address, category):
    """The provider fetches whatever URL we send, so an unvalidated one aims a
    request at someone else's network from NVIDIA's."""
    ok, reason = validate_image_url("https://internal.example/a.jpg",
                                    resolver=lambda h: [address])
    assert ok is False and reason == f"blocked_{category}"


def test_a_name_resolving_to_both_public_and_private_is_refused():
    """One private answer is enough; that split is the interesting attack."""
    ok, reason = validate_image_url(
        "https://split.example/a.jpg",
        resolver=lambda h: ["93.184.216.34", "10.0.0.1"])
    assert ok is False and reason == "blocked_private"


def test_a_refused_image_does_not_lose_the_whole_turn():
    """Dropping the attachment is the point; failing the conversation is not."""
    messages = [{"role": "user", "content": [
        {"type": "text", "text": "describe"},
        {"type": "image_url", "image_url": {"url": "file:///etc/passwd"}},
    ]}]
    parts = to_provider_messages(messages, resolver=_resolver)[0]["content"]
    assert parts[0]["text"] == "describe"
    assert parts[1]["type"] == "text" and "omitted" in parts[1]["text"]
    assert "etc/passwd" not in json.dumps(parts)


def test_unknown_content_parts_are_described_not_forwarded():
    messages = [{"role": "user", "content": [{"type": "video_url", "url": "x"}]}]
    parts = to_provider_messages(messages, resolver=_resolver)[0]["content"]
    assert parts[0]["type"] == "text" and "unsupported" in parts[0]["text"]


# ── K3-08 streaming ────────────────────────────────────────────────────────

def test_k3_08_sse_parsing():
    event = parse_sse_line('data: {"choices":[{"delta":{"content":"hi"}}]}')
    chunk = chunk_from_delta(event)
    assert chunk.content == "hi"


@pytest.mark.parametrize("line", ["", "   ", ": keep-alive", "data: [DONE]",
                                  "data: {not json", "garbage"])
def test_k3_08b_malformed_sse_frames_are_skipped_not_raised(line):
    """A stream that dies on one bad frame is worse than one that drops it."""
    assert parse_sse_line(line) is None


def test_k3_08c_a_finish_reason_is_emitted():
    event = parse_sse_line('data: {"choices":[{"delta":{},"finish_reason":"stop"}]}')
    assert chunk_from_delta(event).finish_reason == "stop"


def test_k3_08d_usage_only_events_are_emitted():
    event = parse_sse_line('data: {"usage":{"total_tokens":12}}')
    assert chunk_from_delta(event).usage == {"total_tokens": 12}


def test_k3_08e_empty_deltas_yield_nothing():
    assert chunk_from_delta({"choices": [{"delta": {}}]}) is None


# ── K3-09 non-stream parsing ───────────────────────────────────────────────

def test_k3_09_non_stream_response_parsing():
    body = {"choices": [{"message": {"content": "SAATHIOS_KIMI_K3_TEXT_OK"},
                         "finish_reason": "stop"}],
            "usage": {"total_tokens": 9}}
    text, finish, usage, tools = parse_completion(body)
    assert text == "SAATHIOS_KIMI_K3_TEXT_OK"
    assert finish == "stop" and usage["total_tokens"] == 9 and tools == []


def test_k3_09b_an_empty_choice_list_is_not_a_crash():
    text, finish, _, _ = parse_completion({})
    assert text == "" and finish == "error"


# ── K3-10 reasoning configuration ──────────────────────────────────────────

@pytest.mark.parametrize("level,wire", sorted(REASONING_EFFORT.items()))
def test_k3_10_reasoning_levels_map_to_provider_vocabulary(level, wire):
    payload = build_payload([{"role": "user", "content": "x"}], model=KIMI_K3,
                            reasoning=level)
    assert payload["reasoning_effort"] == wire


def test_k3_10b_an_unknown_reasoning_level_is_refused():
    with pytest.raises(NvidiaConfigError):
        build_payload([{"role": "user", "content": "x"}], model=KIMI_K3,
                      reasoning="TURBO")


# ── K3-11 / K3-24 reasoning content is not user-visible ────────────────────

def test_k3_11_reasoning_content_is_not_part_of_the_visible_text():
    """Private working, not an assistant message. Putting it in `text` would
    surface chain-of-thought in chat, logs and audit."""
    body = {"choices": [{"message": {
        "content": "The answer is 4.",
        "reasoning_content": "Let me think step by step: 2+2 ... internal."}}]}
    text, _, _, _ = parse_completion(body)
    assert text == "The answer is 4."
    assert "internal" not in text and "step by step" not in text


def test_k3_24_reasoning_deltas_are_not_streamed_as_content():
    event = parse_sse_line(
        'data: {"choices":[{"delta":{"reasoning_content":"hidden thinking"}}]}')
    assert chunk_from_delta(event) is None


def test_k3_24b_the_result_reports_reasoning_presence_not_its_text(keyed, monkeypatch):
    """A caller that needs to know reasoning happened can; nobody gets to read
    it out of a normal result."""
    import asyncio

    body = {"choices": [{"message": {"content": "ok",
                                     "reasoning_content": "secret chain"}}]}
    _install_fake_post(monkeypatch, 200, body)
    result = asyncio.run(NvidiaEngine().generate(
        [{"role": "user", "content": "x"}], model=KIMI_K3))
    assert result.text == "ok"
    assert result.raw["reasoning_present"] is True
    assert "secret chain" not in json.dumps(result.raw)


# ── K3-12 / K3-13 tool calls are untrusted proposals ───────────────────────

def test_k3_12_tool_calls_are_normalized_onto_the_result_not_executed():
    body = {"choices": [{"message": {
        "content": "", "tool_calls": [
            {"id": "c1", "function": {"name": "send_email",
                                      "arguments": '{"to":"x"}'}}]}}]}
    text, _, _, tool_calls = parse_completion(body)
    assert text == ""
    assert tool_calls[0]["function"]["name"] == "send_email"


def test_k3_13_the_engine_cannot_execute_a_proposed_tool():
    """A model-proposed tool call is untrusted input. This engine has no path to
    execution at all -- it cannot import one."""
    source = pathlib.Path("saathi/inference/adapters/nvidia.py").read_text()
    tree = ast.parse(source)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
        elif isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
    for forbidden in ("saathi.execution.gateway", "saathi.execution.egress",
                      "saathi.agent_runtime.gateway_exec",
                      "saathi.execution.delegation", "saathi.platform.tg"):
        assert not any(m.startswith(forbidden) for m in imported), forbidden


def test_k3_12b_capabilities_do_not_claim_unproven_tool_calling():
    """Claiming a capability the router may act on, without evidence, is how a
    request is sent somewhere it cannot be served."""
    import asyncio

    caps = asyncio.run(NvidiaEngine().capabilities())
    assert caps.streaming is True and caps.vision is True
    assert caps.tool_calling is False and caps.structured_output is False
    assert caps.local is False


# ── K3-14 … K3-19 failure behaviour ────────────────────────────────────────

class _FakeResponse:
    def __init__(self, status, body=None, lines=None):
        self.status_code = status
        self._body = body or {}
        self._lines = lines or []

    def json(self):
        return self._body

    def iter_lines(self):
        return iter(self._lines)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _install_fake_post(monkeypatch, status, body=None):
    import httpx

    monkeypatch.setattr(httpx, "post",
                        lambda *a, **k: _FakeResponse(status, body), raising=False)


def test_k3_14_missing_api_key_fails_safely(monkeypatch):
    import asyncio

    monkeypatch.delenv(NVIDIA_API_KEY_ENV, raising=False)
    with pytest.raises(NvidiaConfigError):
        asyncio.run(NvidiaEngine().generate([{"role": "user", "content": "x"}],
                                            model=KIMI_K3))


@pytest.mark.parametrize("status,expected", [
    (401, EngineUnhealthyError), (403, EngineUnhealthyError),
    (404, EngineError), (429, EngineUnhealthyError),
    (500, EngineUnhealthyError), (503, EngineUnhealthyError),
    (400, EngineError),
])
def test_k3_15_to_17_provider_status_codes_are_normalized(keyed, monkeypatch,
                                                          status, expected):
    import asyncio

    _install_fake_post(monkeypatch, status)
    with pytest.raises(expected):
        asyncio.run(NvidiaEngine().generate([{"role": "user", "content": "x"}],
                                            model=KIMI_K3))


def test_k3_18_timeout_is_normalized(keyed, monkeypatch):
    import asyncio

    import httpx

    def _timeout(*a, **k):
        raise TimeoutError("request timed out")

    monkeypatch.setattr(httpx, "post", _timeout, raising=False)
    with pytest.raises(EngineTimeoutError):
        asyncio.run(NvidiaEngine().generate([{"role": "user", "content": "x"}],
                                            model=KIMI_K3))


def test_k3_18b_connection_failure_is_normalized(keyed, monkeypatch):
    import asyncio

    import httpx

    def _refused(*a, **k):
        raise ConnectionError("connection refused")

    monkeypatch.setattr(httpx, "post", _refused, raising=False)
    with pytest.raises(EngineUnhealthyError):
        asyncio.run(NvidiaEngine().generate([{"role": "user", "content": "x"}],
                                            model=KIMI_K3))


def test_k3_18c_a_non_json_body_is_an_engine_error(keyed, monkeypatch):
    import asyncio

    import httpx

    class _Bad(_FakeResponse):
        def json(self):
            raise ValueError("not json")

    monkeypatch.setattr(httpx, "post", lambda *a, **k: _Bad(200), raising=False)
    with pytest.raises(EngineError):
        asyncio.run(NvidiaEngine().generate([{"role": "user", "content": "x"}],
                                            model=KIMI_K3))


def test_k3_19_stream_interruption_surfaces_as_an_engine_error(keyed, monkeypatch):
    import asyncio

    import httpx

    class _Broken(_FakeResponse):
        def iter_lines(self):
            yield 'data: {"choices":[{"delta":{"content":"par"}}]}'
            raise ConnectionError("stream reset")

    monkeypatch.setattr(httpx, "stream", lambda *a, **k: _Broken(200), raising=False)

    async def _drain():
        got = []
        async for chunk in NvidiaEngine().stream(
                [{"role": "user", "content": "x"}], model=KIMI_K3):
            got.append(chunk)
        return got

    with pytest.raises((EngineUnhealthyError, EngineError)):
        asyncio.run(_drain())


def test_k3_19b_a_clean_stream_yields_content_then_finish(keyed, monkeypatch):
    import asyncio

    import httpx

    lines = ['data: {"choices":[{"delta":{"content":"SAATHIOS_"}}]}',
             ': keep-alive',
             'data: {"choices":[{"delta":{"content":"KIMI_K3_STREAM_OK"}}]}',
             'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}',
             'data: [DONE]']
    monkeypatch.setattr(httpx, "stream",
                        lambda *a, **k: _FakeResponse(200, lines=lines), raising=False)

    async def _drain():
        return [c async for c in NvidiaEngine().stream(
            [{"role": "user", "content": "x"}], model=KIMI_K3)]

    chunks = asyncio.run(_drain())
    assert "".join(c.content or "" for c in chunks) == "SAATHIOS_KIMI_K3_STREAM_OK"
    assert chunks[-1].finish_reason == "stop"


# ── K3-20 optionality ──────────────────────────────────────────────────────

def test_k3_20_the_engine_is_unavailable_not_broken_without_a_key(monkeypatch):
    """An optional remote tier that throws on a health probe has made itself a
    startup dependency."""
    import asyncio

    monkeypatch.delenv(NVIDIA_API_KEY_ENV, raising=False)
    health = asyncio.run(NvidiaEngine().health())
    assert health["ok"] is False
    assert health["reason"] == f"{NVIDIA_API_KEY_ENV}_missing"


def test_k3_20b_importing_the_engine_touches_no_network_and_no_credential():
    """No import-time side effects -- the discipline Phase 15 spent a milestone
    establishing."""
    source = pathlib.Path("saathi/inference/adapters/nvidia.py").read_text()
    tree = ast.parse(source)
    for node in tree.body:
        assert not isinstance(node, (ast.Expr, ast.If)) or not _calls_out(node)


def _calls_out(node) -> bool:
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute):
            if sub.func.attr in ("post", "get", "getenv", "environ"):
                return True
    return False


def test_k3_20c_saathios_core_does_not_depend_on_this_engine():
    """Nothing outside the inference layer imports it, so its absence cannot
    stop SaathiOS starting."""
    importers = []
    for path in pathlib.Path("saathi").rglob("*.py"):
        if "__pycache__" in str(path) or "adapters/nvidia.py" in str(path):
            continue
        text = path.read_text(errors="ignore")
        if "adapters.nvidia" in text or "adapters import nvidia" in text:
            importers.append(str(path))
    assert all("inference" in i for i in importers), importers


# ── K3-21 … K3-23 authority boundaries preserved ───────────────────────────

def test_k3_21_trading_guardian_is_untouched():
    """The engine cannot reach Guardian, and Guardian's semantics are unchanged
    by this integration."""
    from saathi.execution.authorization import (
        AuthorizationInputs, Decision, ResolvedAction, authorize_intent)
    from saathi.agent_runtime.contracts import AuthorityClass
    from saathi.agent_runtime.models import RiskClass
    from saathi.execution.record import tool_intent_digest
    from saathi.execution.toolintent import ToolIntent

    intent = ToolIntent(intent_id="k3", operation="advice", actor_id="user:a",
                        parameters={"from": "kimi-k3"})
    action = ResolvedAction(AuthorityClass.FINANCIAL_ADVISORY,
                            RiskClass.EXTERNAL_SIDE_EFFECT, "test_fixture")
    approval = {"approval_id": "a1", "tool_intent_digest": tool_intent_digest(intent),
                "status": "approved", "used": 0, "max_uses": 1}
    decision = authorize_intent(intent, AuthorizationInputs(
        actor_user_id="a", has_permission=True, kill_switch_blocked=False,
        connector_action=action, approvals=[approval], now=1_000_000.0))
    assert decision.decision is not Decision.AUTHORIZED
    assert decision.reason_code == "guardian.missing"


def test_k3_22_execution_gateway_cannot_be_reached_from_the_engine():
    """Asserted over the parsed tree, not the text.

    The module docstring explains at length that it cannot reach
    ExecutionGateway -- so a substring search flags the explanation rather than
    any code. Names, attributes and non-docstring literals are what matter.
    """
    tree = ast.parse(pathlib.Path("saathi/inference/adapters/nvidia.py").read_text())
    docstrings = {id(n.value) for n in ast.walk(tree)
                  if isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)}
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    literals = {n.value for n in ast.walk(tree)
                if isinstance(n, ast.Constant) and isinstance(n.value, str)
                and id(n) not in docstrings}
    reachable = names | attrs | literals
    for forbidden in ("ExecutionGateway", "gateway_exec", "governed_egress",
                      "execute_delegated", "submit", "guard"):
        assert forbidden not in reachable, forbidden


def test_k3_23_approval_boundary_is_preserved():
    from saathi.execution.authorization import (
        AuthorizationInputs, Decision, authorize_intent)
    from saathi.execution.toolintent import ToolIntent

    intent = ToolIntent(intent_id="k3-a", operation="video-generation",
                        actor_id="user:a", parameters={"prompt": "from k3"})
    decision = authorize_intent(intent, AuthorizationInputs(
        actor_user_id="a", has_permission=True, kill_switch_blocked=False,
        approvals=[], now=1_000_000.0))
    assert decision.decision is Decision.DENIED
    assert decision.reason_code == "approval.missing"


def test_k3_23b_a_model_proposed_write_still_meets_the_egress_guard():
    """The end of the line for anything K3 suggests: the side effect is guarded
    regardless of which model proposed it."""
    from saathi.execution.egress import EgressDenied, guard

    with pytest.raises(EgressDenied):
        guard("telegram.send_message", operation="proposed_by_kimi_k3")


# ── K3-25 existing providers unaffected ────────────────────────────────────

def test_k3_25_existing_provider_availability_is_unchanged(monkeypatch):
    from saathi.inference.adapters.http_providers import env_availability

    for name in ("anthropic/x", "openai/x", "groq/x", "gemini/x", "ollama/x"):
        monkeypatch.delenv(NVIDIA_API_KEY_ENV, raising=False)
        before = env_availability(name)
        monkeypatch.setenv(NVIDIA_API_KEY_ENV, SYNTHETIC_KEY)
        assert env_availability(name) == before, f"{name} availability changed"


def test_k3_25b_nvidia_availability_follows_its_own_key(monkeypatch):
    from saathi.inference.adapters.http_providers import env_availability

    monkeypatch.delenv(NVIDIA_API_KEY_ENV, raising=False)
    assert env_availability("moonshotai/kimi-k3") is False
    monkeypatch.setenv(NVIDIA_API_KEY_ENV, SYNTHETIC_KEY)
    assert env_availability("moonshotai/kimi-k3") is True


def test_k3_25c_the_loopback_only_adapter_was_not_widened():
    """The reason this is a separate engine: `openai_compat` speaks the same
    dialect, and pointing it at a remote host would have meant admitting one
    into an allowlist that exists to keep traffic local."""
    from saathi.inference.adapters.openai_compat import allowed_openai_compat_hosts

    hosts = allowed_openai_compat_hosts()
    assert "integrate.api.nvidia.com" not in hosts
    assert hosts <= {"127.0.0.1", "localhost", "::1", "0.0.0.0"}
