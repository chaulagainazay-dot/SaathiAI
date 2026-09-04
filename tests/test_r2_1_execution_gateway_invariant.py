"""R2.1-S2 — the legacy dispatch path never executes a tool itself.

One invariant, stated positively: ``saathi.tools.registry.execute_tool`` may
classify, govern, audit, and route to the canonical ExecutionGateway. It may
not invoke a registered handler. Not for privileged tools, and not for the
ordinary ones either — read-only, local, filesystem, networked, or residual.

Before this repair the dispatcher ended in ``result = handler(**args)`` for
everything classified ``LEGACY_BOUNDED``, which included ~70 named tools *and*
the default classification for any handler registered later. Those calls
executed outside the gateway: no approval contract, no idempotency key, no
gateway audit record. The tests below pin that shut from three directions —
source, dispatcher, and every legacy entry point that reaches it.
"""
import ast
import inspect

import pytest

from saathi import agent as agent_mod
from saathi import server
from saathi.tools import registry
from saathi.tools.registry import execute_tool, recent_governance_decisions
from saathi.tool_runtime import legacy_policy


@pytest.fixture(autouse=True)
def _reset_governance():
    registry._governance_harness = None
    registry._governance_audit.clear()
    yield


@pytest.fixture
def counting_handlers():
    """Replace every registered handler with a counting mock.

    Harmless by construction: a mock records the call and returns a dict. If
    the dispatcher ever executes one, the list is non-empty and the test fails
    — no real side effect is needed to detect the breach.
    """
    calls: list[tuple[str, dict]] = []
    original = dict(registry._HANDLERS)

    def make(name):
        def handler(**kwargs):
            calls.append((name, kwargs))
            return {"ok": True, "handler_ran": name}
        return handler

    for name in list(registry._HANDLERS):
        registry._HANDLERS[name] = make(name)
    # A handler that is in no policy set at all — this is the residual case
    # that classify_legacy_tool() defaults to LEGACY_BOUNDED.
    registry._HANDLERS["__probe_residual_tool__"] = make("__probe_residual_tool__")
    try:
        yield calls
    finally:
        registry._HANDLERS.clear()
        registry._HANDLERS.update(original)


# ── 1. Source invariant ──────────────────────────────────────────────────────


def test_dispatcher_source_contains_no_handler_invocation():
    """The machine invariant: no call expression on the resolved handler.

    A source-level assertion, so the guarantee survives a refactor that keeps
    the tests passing by accident (e.g. a handler invoked behind a helper the
    runtime probe happens not to reach).
    """
    tree = ast.parse(inspect.getsource(execute_tool))
    fn = tree.body[0]
    bound = {"handler"}
    offenders = []
    for node in ast.walk(fn):
        # `h = _HANDLERS.get(x)` / `h = _HANDLERS[x]` binds another alias
        if isinstance(node, ast.Assign):
            src = ast.dump(node.value)
            if "_HANDLERS" in src:
                for tgt in node.targets:
                    if isinstance(tgt, ast.Name):
                        bound.add(tgt.id)
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in bound:
                offenders.append(func.id)
            if isinstance(func, ast.Subscript):
                inner = ast.dump(func.value)
                if "_HANDLERS" in inner:
                    offenders.append("_HANDLERS[...]()")
    assert offenders == [], (
        f"execute_tool invokes a registered handler directly: {offenders}. "
        "All execution must route through ExecutionGateway."
    )


def test_dispatcher_still_looks_handlers_up_for_existence():
    """Guard the guard: the source check above is only meaningful while the
    dispatcher still consults _HANDLERS to reject unknown names."""
    src = inspect.getsource(execute_tool)
    assert "_HANDLERS.get(name)" in src


# ── 2. Dispatcher invariant, per tool class ──────────────────────────────────


TOOL_CLASSES = [
    ("ordinary_non_privileged", "canteen_query", {"topic": "sales_today"}),
    ("read_only", "self_status", {}),
    ("filesystem", "read_project_file", {"name": "x", "path": "y"}),
    ("shell", "run_shell", {"command": "echo hello"}),
    ("email", "send_email", {"to": "a@b.c", "subject": "s", "body": "b"}),
    ("social", "post_social_content", {"platform": "facebook", "content_text": "x"}),
    ("deployment", "deploy_ielts_site", {}),
    ("networked", "web_search", {"query": "x"}),
    ("residual_unclassified", "__probe_residual_tool__", {"a": 1}),
]


@pytest.mark.parametrize("label,tool,args", TOOL_CLASSES, ids=[c[0] for c in TOOL_CLASSES])
def test_no_tool_class_executes_its_handler(counting_handlers, label, tool, args):
    result = execute_tool(tool, args)
    assert counting_handlers == [], f"{label}: handler executed outside the gateway"
    assert result.get("blocked") is True
    assert result.get("outcome_class") in {"BLOCKED", "PROHIBITED"}


def test_unknown_tool_executes_nothing(counting_handlers):
    result = execute_tool("__no_such_tool__", {"a": 1})
    assert counting_handlers == []
    assert result["blocked"] is True
    assert "unknown tool" in result["error"]


def test_malformed_request_executes_nothing(counting_handlers):
    """Malformed args must fail closed, not fall through to a handler."""
    for bad in (None, [], "text", {"unexpected": object()}):
        result = execute_tool("canteen_query", bad)
        assert counting_handlers == []
        assert isinstance(result, dict)
        assert result.get("blocked") is True


def test_every_registered_tool_fails_closed(counting_handlers):
    """Exhaustive sweep: no name in the registry executes its handler."""
    for name in sorted(registry._HANDLERS):
        execute_tool(name, {})
    assert counting_handlers == [], (
        f"{len(counting_handlers)} handler(s) executed outside the gateway: "
        f"{sorted({c[0] for c in counting_handlers})}"
    )


def test_legacy_bounded_tools_are_no_longer_runtime_executable(counting_handlers):
    """The LEGACY_BOUNDED inventory specifically — the class that used to run."""
    for name in sorted(legacy_policy.LEGACY_BOUNDED_TOOLS):
        if name not in registry._HANDLERS:
            continue
        result = execute_tool(name, {})
        assert result.get("blocked") is True, f"{name} was not blocked"
    assert counting_handlers == []


def test_blocked_response_is_truthful_about_what_is_required(counting_handlers):
    result = execute_tool("canteen_query", {"topic": "sales_today"})
    assert result["error"] == "execution_gateway_required"
    assert result["requires"] == "execution_gateway"
    assert "ExecutionGateway" in result["message"]
    assert "no handler was invoked" in result["message"]


def test_no_approval_artefact_is_fabricated(counting_handlers):
    """Nothing on this path may mint or imply an approval."""
    for _, tool, args in TOOL_CLASSES:
        result = execute_tool(tool, args, speaker_match_observed=True)
        blob = repr(result)
        assert "ToolApprovalReference" not in blob
        assert result.get("approval_reference") is None
        assert result.get("human_approved") is not True
        assert result.get("code_confirmed") is not True
        assert result.get("approved") is not True


def test_canonical_mapped_tools_still_route_to_the_gateway(counting_handlers):
    """Fail-closed must not mean fail-everything: the gateway path survives."""
    result = execute_tool("system_health", {})
    assert counting_handlers == []
    assert result.get("error") != "execution_gateway_required"


# ── 3. Every legacy entry point, and the metadata that changes nothing ───────


ENTRY_POINTS = [
    # (label, speaker_match_observed as that entry point supplies it)
    ("agent_chat", None),
    ("voice_command_match", True),
    ("voice_command_no_match", False),
    ("telegram", None),
    ("default_brain", None),
    ("listener_wake_word", True),
    ("push_to_talk", True),
]


@pytest.mark.parametrize("label,observed", ENTRY_POINTS, ids=[e[0] for e in ENTRY_POINTS])
@pytest.mark.parametrize("tool,args", [(t, a) for _, t, a in TOOL_CLASSES])
def test_entry_point_cannot_execute_a_handler(counting_handlers, label, observed, tool, args):
    result = execute_tool(tool, args, speaker_match_observed=observed)
    assert counting_handlers == [], f"{label} executed {tool} outside the gateway"
    assert result.get("blocked") is True


@pytest.mark.parametrize("label,observed", ENTRY_POINTS, ids=[e[0] for e in ENTRY_POINTS])
def test_entry_point_attempt_reaches_the_audit(counting_handlers, label, observed):
    registry._governance_audit.clear()
    execute_tool("canteen_query", {"topic": "sales_today"},
                 speaker_match_observed=observed)
    decisions = recent_governance_decisions()
    assert decisions, f"{label}: the attempt was not audited"


def test_speaker_match_metadata_changes_no_outcome(counting_handlers):
    """True, False, and unknown must produce identical decisions."""
    outcomes = {}
    for observed in (True, False, None):
        for _, tool, args in TOOL_CLASSES:
            result = execute_tool(tool, args, speaker_match_observed=observed)
            outcomes.setdefault(tool, set()).add(
                (result.get("error"), result.get("blocked"), result.get("outcome_class"))
            )
    assert counting_handlers == []
    for tool, seen in outcomes.items():
        assert len(seen) == 1, f"{tool}: speaker match altered the outcome: {seen}"


def test_agent_tool_sink_is_the_shared_dispatcher_only():
    """The agent loop must have exactly one tool sink.

    If a provider branch ever called a handler (or a second dispatcher)
    directly, the dispatcher-level invariant above would not cover it.
    """
    src = inspect.getsource(agent_mod)
    assert "_HANDLERS" not in src
    assert src.count("execute_tool(") >= 3  # one per provider branch
    tree = ast.parse(src)
    sinks = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        and node.func.id.endswith("execute_tool")
    }
    assert sinks == {"execute_tool"}


def test_server_entry_points_do_not_bypass_the_agent():
    """No HTTP entry point may import the legacy handler table."""
    assert "_HANDLERS" not in inspect.getsource(server)
