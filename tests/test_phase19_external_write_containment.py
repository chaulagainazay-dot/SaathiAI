"""Phase 19 — no external write outside the authority gateway.

Phase 18's inventory surfaced a larger gap than it set out to close. Scheduler
jobs reach Facebook, Instagram, Gmail and MailerLite through direct `httpx.post`
calls in `saathi/tools/*`, and not one of those modules mentions
`ExecutionGateway`. Every gate built in Phases 16-18 sat *beside* that path
rather than in front of it.

It was inert in one checkout because `data/connections.json` happened to be
missing. That is a property of the data, not the architecture: the code posts the
moment credentials appear. These tests assert containment that does not depend on
a file being absent.

Nothing here contacts the network. Every test that exercises a posting function
first replaces the HTTP client with one that raises, so a real request is a test
failure rather than an unnoticed side effect.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

from saathi.execution.egress import (
    EgressDenied,
    EgressGrant,
    current_grant,
    governed_egress,
    guard,
)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Any real request is a failure, not a silent side effect.

    Deliberately not relying on the network being unavailable: a machine with
    connectivity must fail these tests the same way a machine without it does.
    """
    import httpx
    import requests

    def _boom(*a, **k):
        raise AssertionError("a test attempted a real network call")

    for mod in (httpx, requests):
        for verb in ("post", "put", "patch", "delete", "get", "request"):
            monkeypatch.setattr(mod, verb, _boom, raising=False)


def _grant() -> EgressGrant:
    return EgressGrant(intent_id="i1", intent_digest="d1", actor="user:test",
                       operation="test.op")


# ── the guard itself ────────────────────────────────────────────────────────

def test_an_ungoverned_external_write_is_refused():
    with pytest.raises(EgressDenied) as excinfo:
        guard("facebook.page.feed", operation="post_facebook")
    assert excinfo.value.reason_code == "egress.not_governed"


def test_a_governed_external_write_is_permitted():
    """The positive case, so the refusals above are not passing because the
    guard refuses everything."""
    with governed_egress(_grant()):
        assert guard("facebook.page.feed", operation="post_facebook").intent_id == "i1"


def test_the_grant_does_not_survive_the_block():
    with governed_egress(_grant()):
        assert current_grant() is not None
    assert current_grant() is None
    with pytest.raises(EgressDenied):
        guard("facebook.page.feed")


def test_the_grant_is_released_even_when_the_operation_raises():
    with pytest.raises(RuntimeError):
        with governed_egress(_grant()):
            raise RuntimeError("handler failed")
    assert current_grant() is None


def test_a_denial_raises_rather_than_returning_a_status():
    """These posting functions all return dicts nobody inspects for authority.
    A refusal that came back as another dict would be ignored exactly like the
    "not configured" errors already are."""
    with pytest.raises(EgressDenied):
        guard("gmail.send")


def test_the_grant_carries_the_authorized_actions_digest():
    """Correlation: a mutation performed under a grant is tied to the intent
    that was authorized, not merely to the fact that something was."""
    with governed_egress(_grant()):
        got = current_grant()
    assert got.intent_digest == "d1" and got.actor == "user:test"


# ── the real posting functions ──────────────────────────────────────────────

#: Every genuine external mutation reachable from the scheduler, and the target
#: it changes. RPC-shaped POSTs that mutate nothing outside -- LLM completions,
#: embeddings, search -- are deliberately not here: the boundary is an
#: observable mutation outside SaathiOS, not the HTTP verb.
_WRITE_ENTRY_POINTS = [
    ("saathi.tools.meta_post", "post_facebook", ("hello",)),
    ("saathi.tools.meta_post", "post_instagram_text", ("hello",)),
    ("saathi.tools.meta_post", "post_instagram_image", ("http://x/i.png", "c")),
    ("saathi.tools.meta_post", "post_instagram_reel", ("http://x/v.mp4", "c")),
    ("saathi.tools.email_tool", "send_email", ("a@example.com", "s", "b")),
    ("saathi.tools.mailerlite", "add_subscriber", ("a@example.com",)),
    ("saathi.tools.mailerlite", "create_group", ("g",)),
    ("saathi.tools.twitter_post", "tweet", ("hello",)),
    ("saathi.tools.linkedin_post", "post_text", ("hello",)),
]


@pytest.mark.parametrize("module,func,args", _WRITE_ENTRY_POINTS,
                         ids=[f"{m.split('.')[-1]}.{f}" for m, f, _ in _WRITE_ENTRY_POINTS])
def test_every_external_write_entry_point_refuses_outside_governance(module, func, args):
    """This is the bypass Phase 18 found, closed at the side effect itself."""
    import importlib

    mod = importlib.import_module(module)
    with pytest.raises(EgressDenied):
        getattr(mod, func)(*args)


@pytest.mark.parametrize("module,func,args", _WRITE_ENTRY_POINTS,
                         ids=[f"{m.split('.')[-1]}.{f}" for m, f, _ in _WRITE_ENTRY_POINTS])
def test_every_entry_point_gets_past_the_guard_when_governed(module, func, args):
    """Negative control for the whole set: the guard must be the thing stopping
    them, not a broken import or a missing argument. Inside a grant they proceed
    to their own credential check and fail there instead."""
    import importlib

    mod = importlib.import_module(module)
    with governed_egress(_grant()):
        try:
            result = getattr(mod, func)(*args)
        except EgressDenied:
            pytest.fail("governed call was refused by the egress guard")
        except AssertionError:
            pytest.fail("governed call reached the network")
        except Exception:
            return  # reached its own credential/config failure: past the guard
    assert isinstance(result, dict)
    assert "egress" not in str(result.get("reason_code", ""))


# ── autopost fails fast and leaves the queue alone ──────────────────────────

def test_autopost_refuses_before_doing_any_work():
    """It marked the queue item posted unconditionally at the end, so a refused
    write consumed the slot and the post was silently never made."""
    from saathi import autopost

    for fn in (lambda: autopost.run_social_autopost("AM"),
               autopost.run_daily_autopost):
        result = fn()
        assert result["status"] == "blocked"
        assert result["reason_code"] == "egress.not_governed"


def test_a_refused_autopost_consumes_nothing(tmp_path, monkeypatch):
    """The queue must be untouched by a refusal -- otherwise the containment
    fix would silently destroy scheduled work."""
    from saathi import autopost

    seen = {"saved": False}
    monkeypatch.setattr(autopost, "_save", lambda *a, **k: seen.update(saved=True),
                        raising=False)
    monkeypatch.setattr(autopost, "_mark_posted", lambda *a, **k: seen.update(saved=True),
                        raising=False)
    autopost.run_daily_autopost()
    autopost.run_social_autopost("AM")
    assert seen["saved"] is False


# ── static bypass detector ──────────────────────────────────────────────────

#: Modules whose public write functions must carry the guard. Named explicitly
#: rather than discovered, so adding a new posting module is a deliberate act
#: that updates this list.
_GUARDED_MODULES = {
    "saathi/tools/meta_post.py": {"post_facebook", "post_instagram_text",
                                  "post_instagram_image", "post_instagram_reel",
                                  "post_instagram_image_local", "upload_image_public"},
    "saathi/tools/email_tool.py": {"send_email"},
    "saathi/tools/mailerlite.py": {"add_subscriber", "create_group", "create_campaign"},
    "saathi/tools/twitter_post.py": {"tweet", "tweet_with_image"},
    "saathi/tools/linkedin_post.py": {"post_text"},
}


def _calls_guard(fn: ast.FunctionDef) -> bool:
    """Whether this function body calls `guard(...)`.

    Parsed, not grepped: the comment above each call quotes the mechanism, and
    prior milestones repeatedly showed substring detectors flagging the prose
    that explains a fix rather than the code that is the fix.
    """
    for node in ast.walk(fn):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id == "guard":
            return True
    return False


@pytest.mark.parametrize("path,funcs", sorted(_GUARDED_MODULES.items()))
def test_every_declared_write_function_calls_the_guard(path, funcs):
    tree = ast.parse(pathlib.Path(path).read_text())
    found = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    for name in funcs:
        assert name in found, f"{path}: {name} disappeared -- update the detector"
        assert _calls_guard(found[name]), f"{path}:{name} performs an ungoverned write"


def test_the_static_detector_would_catch_an_unguarded_write(tmp_path):
    """Negative control. A detector that cannot fail proves nothing."""
    probe = tmp_path / "probe.py"
    probe.write_text(
        "import httpx\n"
        "def post_thing():\n"
        "    # guard('x') in a comment is not a call\n"
        "    return httpx.post('https://example.com/x')\n"
        "def post_guarded():\n"
        "    guard('x')\n"
        "    return httpx.post('https://example.com/x')\n")
    tree = ast.parse(probe.read_text())
    fns = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    assert _calls_guard(fns["post_thing"]) is False
    assert _calls_guard(fns["post_guarded"]) is True


def test_no_guarded_module_reaches_the_gateway_by_importing_it():
    """The guard is the boundary; these modules must not acquire gateway logic
    of their own. Authorization deciding in one place and executing in another
    is the anti-pattern this milestone exists to prevent."""
    for path in _GUARDED_MODULES:
        tree = ast.parse(pathlib.Path(path).read_text())
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for a in node.names:
                    imported.add(a.name)
        assert "ExecutionGateway" not in imported, path


# ── dynamic bypass detector ─────────────────────────────────────────────────

def test_a_scheduler_job_cannot_produce_an_external_mutation(monkeypatch):
    """Runs the real job function with the network armed to raise. Catches
    indirection the static detector cannot see."""
    from saathi import scheduler

    calls = []
    monkeypatch.setattr("saathi.autopost.run_social_autopost",
                        lambda slot: calls.append(("social", slot)) or {"status": "blocked"})
    scheduler.social_autopost_am()
    assert calls == [("social", "AM")], "the job ran"
    # The autouse no_network fixture would have raised on any real request.


def test_the_scheduler_module_performs_no_external_mutation_itself():
    tree = ast.parse(pathlib.Path("saathi/scheduler.py").read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in {"post", "put", "patch", "delete"} \
                    and isinstance(node.func.value, ast.Name) \
                    and node.func.value.id in {"httpx", "requests"}:
                pytest.fail(f"scheduler.py mutates externally at line {node.lineno}")


# ── the governed path opens the grant, and only there ───────────────────────

def test_the_universal_boundary_opens_the_grant_at_handler_dispatch():
    """The grant must open around the handler and nothing wider: earlier would
    cover code that was never authorized."""
    import inspect

    from saathi.execution.universal import UniversalBoundary

    source = inspect.getsource(UniversalBoundary._run_handler)
    assert "governed_egress" in source
    assert "tool_intent_digest" in source, "the grant must carry the action's digest"


def test_the_tool_runtime_opens_the_grant_around_the_adapter():
    import inspect

    from saathi.tool_runtime.service import ToolExecutionService

    source = inspect.getsource(ToolExecutionService)
    assert "governed_egress" in source


def test_no_module_outside_the_execution_layer_opens_a_grant():
    """A module that could open its own grant could authorize itself."""
    offenders = []
    for path in pathlib.Path("saathi").rglob("*.py"):
        if "__pycache__" in str(path):
            continue
        rel = str(path)
        if rel.startswith(("saathi/execution/", "saathi/tool_runtime/")):
            continue
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                    and node.func.id == "governed_egress":
                offenders.append(f"{rel}:{node.lineno}")
    assert offenders == [], offenders


# ── the security invariants, stated as properties ───────────────────────────

def test_unknown_origin_cannot_write():
    """No delegation, no session, no grant: the system-actor case."""
    from saathi.execution.authorization_sources import actor_context

    with actor_context(None):
        with pytest.raises(EgressDenied):
            guard("facebook.page.feed")


def test_a_bound_user_alone_does_not_authorize_an_external_write():
    """Identity is not authorization. Being signed in does not open the grant --
    only the gateway's execution path does."""
    from saathi.execution.authorization_sources import actor_context

    with actor_context("ajay"):
        with pytest.raises(EgressDenied):
            guard("facebook.page.feed")


def test_a_valid_delegation_alone_does_not_authorize_an_external_write():
    """Delegation establishes origin and scope. It does not execute anything,
    and it does not stand in for the gateway."""
    from saathi.execution.delegation import DelegationDecision, delegated_actor

    decision = DelegationDecision(True, "delegation.valid", user_id="u1",
                                  authority_ceiling="READ_ONLY", delegation_id="d1")
    with delegated_actor(decision):
        with pytest.raises(EgressDenied):
            guard("facebook.page.feed")
