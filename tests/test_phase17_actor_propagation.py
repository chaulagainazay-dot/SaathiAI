"""Phase 17 — authenticated identity survives the execution path.

Phase 16 capped unattributed callers at READ_ONLY because several authenticated
boundaries never carried the session to the gateway. The cause turned out to be
one thing rather than several: the auth middleware answered *whether* a request
was authenticated and discarded *who*, so `request.state.user_id` was read in
multiple places and assigned in none, and every consumer fell through to a
hardcoded owner.

Two properties are tested here, and they pull in opposite directions:

  * identity must **survive** the path -- through middleware, sync and async
    handlers, nested tasks, and into the gateway's decision; and
  * identity must **not survive** into anything else -- another user's
    concurrent request, the next request after an exception, or a background
    thread that outlives the caller.

The second is the one that fails silently, so most of what follows attacks it.
"""
from __future__ import annotations

import asyncio
import concurrent.futures

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from saathi.execution.authorization import SYSTEM_ACTOR
from saathi.execution.authorization_sources import (
    actor_context,
    current_actor,
    current_actor_id,
)


# ── the canonical resolver ──────────────────────────────────────────────────

def test_a_bound_session_resolves_to_that_user():
    with actor_context("ajay"):
        assert current_actor_id() == "user:ajay"


def test_no_bound_session_resolves_to_the_system_actor_never_a_person():
    assert current_actor_id() == SYSTEM_ACTOR
    assert not SYSTEM_ACTOR.startswith("user:")


def test_the_resolver_never_invents_a_user():
    """Every spelling of "nobody" must be the system actor, not a human name."""
    for value in (None, ""):
        with actor_context(value):
            assert current_actor_id() == SYSTEM_ACTOR


# ── propagation through a real ASGI stack ───────────────────────────────────

def _probe_app() -> FastAPI:
    """A stack shaped like the real one: bind in middleware, observe downstream."""
    app = FastAPI()

    @app.middleware("http")
    async def bind(request, call_next):
        with actor_context(request.headers.get("x-who") or None):
            return await call_next(request)

    @app.get("/sync")          # def handler -> runs in the threadpool
    def sync_handler():
        return {"actor": current_actor()}

    @app.get("/async")
    async def async_handler():
        return {"actor": current_actor()}

    @app.get("/task")
    async def task_handler():
        async def inner():
            return current_actor()
        return {"actor": await asyncio.create_task(inner())}

    @app.get("/nested-await")
    async def nested_await():
        before = current_actor()
        await asyncio.sleep(0)
        return {"actor": current_actor(), "before": before}

    @app.get("/thread")
    async def thread_handler():
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return {"actor": pool.submit(current_actor).result()}

    @app.get("/boom")
    async def boom():
        raise RuntimeError("downstream failure")

    @app.get("/cancelled")
    async def cancelled():
        task = asyncio.create_task(asyncio.sleep(10))
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        return {"actor": current_actor()}

    return app


@pytest.fixture
def probe():
    return TestClient(_probe_app(), raise_server_exceptions=False)


@pytest.mark.parametrize("path", ["/sync", "/async", "/task", "/nested-await"])
def test_the_bound_actor_reaches_every_handler_shape(probe, path):
    """Sync handlers run in a threadpool and async ones in the task tree. Both
    copy the context, but they are different mechanisms, so both are checked."""
    assert probe.get(path, headers={"x-who": "ajay"}).json()["actor"] == "ajay"


def test_the_actor_survives_an_await_boundary(probe):
    body = probe.get("/nested-await", headers={"x-who": "ajay"}).json()
    assert body["before"] == body["actor"] == "ajay"


def test_a_raw_thread_loses_the_actor_rather_than_inheriting_it(probe):
    """Handing work to a bare thread drops the context. That must reduce
    authority to the capped system actor, never carry the caller's rights into
    something they no longer control."""
    assert probe.get("/thread", headers={"x-who": "ajay"}).json()["actor"] is None


# ── isolation: identity must not survive into anything else ─────────────────

def test_concurrent_requests_do_not_bleed_actors(probe):
    """The failure that would never show up in a single-user test: two users in
    flight at once, each seeing the other's identity."""
    def call(who):
        return probe.get("/async", headers={"x-who": who}).json()["actor"]

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        wanted = [f"user{i}" for i in range(16)]
        got = list(pool.map(call, wanted))
    assert got == wanted


def test_an_unauthenticated_request_between_two_users_sees_nobody(probe):
    assert probe.get("/async", headers={"x-who": "a"}).json()["actor"] == "a"
    assert probe.get("/async").json()["actor"] is None
    assert probe.get("/async", headers={"x-who": "b"}).json()["actor"] == "b"


def test_an_exception_does_not_strand_the_actor(probe):
    """Mandatory: a handler that raises must still unwind the binding, or the
    next caller inherits the previous one's identity."""
    probe.get("/boom", headers={"x-who": "victim"})
    assert probe.get("/async").json()["actor"] is None


def test_cancellation_does_not_strand_the_actor(probe):
    assert probe.get("/cancelled", headers={"x-who": "ajay"}).json()["actor"] == "ajay"
    assert probe.get("/async").json()["actor"] is None


def test_the_binding_does_not_outlive_the_request(probe):
    probe.get("/async", headers={"x-who": "ajay"})
    assert current_actor() is None


# ── nesting and restoration ─────────────────────────────────────────────────

def test_a_nested_binding_restores_the_outer_actor():
    with actor_context("outer"):
        with actor_context("inner"):
            assert current_actor() == "inner"
        assert current_actor() == "outer"
    assert current_actor() is None


def test_a_nested_binding_restores_even_when_the_inner_block_raises():
    with actor_context("outer"):
        with pytest.raises(ValueError):
            with actor_context("inner"):
                raise ValueError("boom")
        assert current_actor() == "outer"


def test_binding_nobody_inside_a_session_drops_authority_not_keeps_it():
    """A bounded internal operation inside a user's request must not run as the
    user by accident."""
    with actor_context("ajay"):
        with actor_context(None):
            assert current_actor() is None
            assert current_actor_id() == SYSTEM_ACTOR
        assert current_actor() == "ajay"


# ── the real server middleware ──────────────────────────────────────────────

def test_the_server_resolves_identity_separately_from_authentication():
    """`_is_authed` answers whether; `_authenticated_user_id` answers who. They
    were the same question, which is how the identity half got lost."""
    import saathi.server as server

    assert hasattr(server, "_authenticated_user_id")
    assert hasattr(server, "_with_actor")


def test_an_api_token_authenticates_a_program_and_names_no_person():
    """A token is not a person. Resolving one to a human identity would attribute
    automated actions to somebody who did not take them."""
    import saathi.server as server

    class _Req:
        cookies: dict = {}
        headers = {"x-saathi-token": "some-token"}

    assert server._authenticated_user_id(_Req()) is None


def test_identity_is_never_taken_from_the_request_body_or_a_query_string():
    """Only the session cookie/header is consulted -- a caller-supplied field
    would be a claim about identity, not identity."""
    import inspect as _inspect

    import saathi.server as server

    source = _inspect.getsource(server._authenticated_user_id)
    assert "baadar_session" in source
    for forbidden in ("body", "query_params", "json(", "actor_id"):
        assert forbidden not in source, forbidden


# ── no hardcoded human identity remains on an execution path ────────────────

_EXECUTION_PATH_FILES = (
    "saathi/execution/gateway.py",
    "saathi/execution/authorization.py",
    "saathi/execution/authorization_sources.py",
    "saathi/tool_runtime/contracts.py",
    "saathi/chat/engine.py",
    "saathi/connectors/platform/api.py",
    "saathi/control_center/api.py",
)


#: Keyword positions that carry authority. A hardcoded identity in one of these
#: decides who an action is attributed to and authorized as. Elsewhere -- a
#: docstring, a display string -- the same characters decide nothing.
_AUTHORITY_KEYWORDS = ("actor", "actor_id", "requested_by", "owner", "user_id",
                       "requested_by=", "actor=")


def _authority_assignments(path: str) -> list[tuple[int, str]]:
    """Lines assigning a string literal into an authority-bearing keyword.

    Parsed rather than grepped. A substring search over the whole file flags
    comments explaining the very defect being fixed, which is the Phase 15
    lesson about detectors that match words instead of meaning.
    """
    import ast
    import pathlib as _p

    tree = ast.parse(_p.Path(path).read_text())
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.keyword) and node.arg in _AUTHORITY_KEYWORDS:
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                found.append((node.lineno, node.value.value))
        elif isinstance(node, ast.arg):
            continue
    # default values on function signatures carry the same weight
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = node.args
            defaults = list(args.defaults) + [d for d in args.kw_defaults if d]
            names = ([a.arg for a in args.args][len(args.args) - len(args.defaults):]
                     + [a.arg for a in args.kwonlyargs])
            for name, default in zip(names, defaults):
                if name in _AUTHORITY_KEYWORDS and isinstance(default, ast.Constant) \
                        and isinstance(default.value, str):
                    found.append((node.lineno, default.value))
    return found


@pytest.mark.parametrize("path", _EXECUTION_PATH_FILES)
def test_no_hardcoded_human_identity_in_an_authority_position(path):
    """A hardcoded owner was not a default -- `request.state.user_id` was never
    assigned, so the fallback was the only branch and every authenticated caller
    became the same person."""
    offenders = [(line, value) for line, value in _authority_assignments(path)
                 if "ajay" in value.lower()]
    assert offenders == [], f"{path}: hardcoded identity in an authority position"


def test_the_detector_would_catch_a_reintroduced_hardcoded_actor(tmp_path):
    """Negative control. A detector that never fires proves nothing, and this
    one deliberately ignores comments, so its blind spot must be bounded."""
    probe = tmp_path / "probe.py"
    probe.write_text('# actor="user:ajay" in a comment is not authority\n'
                     'run(actor="user:ajay")\n')
    found = [v for _, v in _authority_assignments(str(probe))]
    assert found == ["user:ajay"], "must catch the call, and only the call"


def test_the_owner_helpers_refuse_rather_than_inventing_a_user():
    from fastapi import HTTPException

    import saathi.connectors.platform.api as capi
    import saathi.control_center.api as ccapi

    class _Req:
        class state:
            pass

    for module in (capi, ccapi):
        with pytest.raises(HTTPException) as excinfo:
            module._user(_Req())
        assert excinfo.value.status_code == 401


# ── end to end: a real session reaches a real gateway decision ──────────────

@pytest.fixture()
def sec(tmp_path):
    from saathi.security.store import SecurityStore
    from tests.support.auth_state import make_active

    store = SecurityStore(db_path=tmp_path / "security.db")
    make_active(store)
    return store


@pytest.fixture()
def runs(tmp_path):
    from saathi.agent_runtime.store import RunStore

    return RunStore(db_path=tmp_path / "runs.db")


@pytest.fixture()
def bound_store(monkeypatch, sec):
    """Point session resolution *and* RBAC at the same store.

    Without this the session resolves in the fixture's database while
    permissions are answered from the process-wide one, and every decision is
    `rbac.denied` for a reason that has nothing to do with the code under test.
    """
    import saathi.security.store as secstore
    from saathi import sessions

    monkeypatch.setattr(secstore, "get_store", lambda: sec)
    monkeypatch.setattr(sessions, "_store", lambda: sec)
    return sec


@pytest.fixture()
def app_client(bound_store):
    import saathi.server as server

    return TestClient(server.app)


def _session_for(sec, role_id="role-owner") -> tuple[str, str]:
    """Returns (token, user_id) for a real session in the real security store."""
    from saathi import sessions

    uid = sec.owner_id()
    with sec.db as db:
        db.execute("DELETE FROM user_roles WHERE user_id=?", (uid,))
        db.execute(
            "INSERT INTO user_roles (user_id, role_id, assigned_at) VALUES (?,?,?)",
            (uid, role_id, 0))
    return sessions.create(ua="test", ip="127.0.0.1"), uid


def test_the_server_binds_the_real_session_user_for_the_whole_request(
        app_client, sec, monkeypatch):
    """The end-to-end claim: an authenticated HTTP request reaches backend code
    with that user bound -- not nobody, and not a hardcoded owner.

    Observed through a real route rather than one added for the test, so what
    passes is the stack the product actually serves.
    """
    import saathi.agent_runtime.api as agents_api

    seen = {}
    real = agents_api.registry.all_agents

    def _observing():
        seen["actor"] = current_actor()
        seen["actor_id"] = current_actor_id()
        return real()

    monkeypatch.setattr(agents_api.registry, "all_agents", _observing)

    token, uid = _session_for(sec)
    app_client.headers.update({"x-baadar-session": token})
    assert app_client.get("/api/v1/agents/definitions").status_code == 200
    assert seen["actor"] == uid, "the real session must reach the handler"
    assert seen["actor_id"] == f"user:{uid}"


def test_an_unauthenticated_request_never_reaches_a_bound_actor(app_client):
    """Refused before any handler, so there is nothing to attribute."""
    assert app_client.get("/api/v1/agents/definitions").status_code == 401
    assert current_actor() is None


def test_a_real_session_produces_a_gateway_decision_attributed_to_that_user(
        bound_store, sec):
    """Identity does not merely reach the backend -- it reaches the decision."""
    from datetime import datetime

    from saathi.execution.gateway import ExecutionContext, ExecutionGateway
    from saathi.execution.state import StateHistory
    from saathi.execution.toolintent import ToolIntent

    _, uid = _session_for(sec)
    gw = ExecutionGateway()
    now = datetime.now()
    intent = ToolIntent(intent_id="p17-e2e", operation="local-llm-inference",
                        actor_id=f"user:{uid}", parameters={"prompt": "hi"})
    ctx = ExecutionContext(actor_id="ignored-by-design", business_unit="test",
                           timestamp=now, current_time=now)
    with actor_context(uid):
        gw.authorize(intent, ctx, StateHistory(intent_id=intent.intent_id))
    assert gw._last_decision.actor_user_id == uid


def test_the_execution_context_actor_is_not_trusted_as_identity(bound_store, sec):
    """`ExecutionContext.actor_id` is caller-supplied. Naming someone else in it
    must not make the decision theirs."""
    from datetime import datetime

    from saathi.execution.gateway import ExecutionContext, ExecutionGateway
    from saathi.execution.state import StateHistory
    from saathi.execution.toolintent import ToolIntent

    _, uid = _session_for(sec)
    gw = ExecutionGateway()
    now = datetime.now()
    intent = ToolIntent(intent_id="p17-spoof", operation="local-llm-inference",
                        actor_id=f"user:{uid}", parameters={"p": 1})
    ctx = ExecutionContext(actor_id="user:someone-important", business_unit="t",
                           timestamp=now, current_time=now)
    with actor_context(uid):
        gw.authorize(intent, ctx, StateHistory(intent_id=intent.intent_id))
    assert gw._last_decision.actor_user_id == uid


# ── run creator propagation and cross-user isolation ────────────────────────

def test_a_run_carries_its_creator_and_the_tool_path_can_read_it(runs):
    from saathi.agent_runtime.gateway_exec import run_actor

    rid = runs.create_run(objective="x", strategy="c", actor="user:alice")
    assert run_actor(runs, rid) == "user:alice"


def test_an_unknown_run_yields_no_creator_rather_than_a_guess(runs):
    from saathi.agent_runtime.gateway_exec import run_actor

    assert run_actor(runs, "no-such-run") == ""


def test_one_users_session_cannot_drive_another_users_run(runs, monkeypatch):
    """Holding `write` authorises acting on your own runs, not on everyone's."""
    from saathi.agent_runtime.gateway_exec import _execution_time_block
    import saathi.platform.tg.kill_switch as ks

    monkeypatch.setattr(ks.KillSwitchStore, "is_blocked",
                        lambda self, **kw: {"blocked": False})
    rid = runs.create_run(objective="x", strategy="c", actor="user:alice")

    with actor_context("bob"):
        assert _execution_time_block(runs, rid) == "RUN_NOT_OWNED"
    with actor_context("alice"):
        assert _execution_time_block(runs, rid) is None


def test_a_run_with_no_recorded_creator_is_not_owned_by_everyone(runs, monkeypatch):
    import saathi.platform.tg.kill_switch as ks

    from saathi.agent_runtime.gateway_exec import _execution_time_block

    monkeypatch.setattr(ks.KillSwitchStore, "is_blocked",
                        lambda self, **kw: {"blocked": False})
    rid = runs.create_run(objective="x", strategy="c", actor="")
    with actor_context("alice"):
        assert _execution_time_block(runs, rid) == "RUN_NOT_OWNED"


# ── actor is part of the action's identity ──────────────────────────────────

def test_the_same_action_by_a_different_actor_is_a_different_action():
    """Phase 16 binds decisions to the intent digest. If the actor were not in
    it, one user's authorization would carry to another's identical request."""
    from saathi.execution.record import tool_intent_digest
    from saathi.execution.toolintent import ToolIntent

    def mk(actor):
        return ToolIntent(intent_id="same", operation="local-llm-inference",
                          actor_id=actor, parameters={"prompt": "identical"})

    assert tool_intent_digest(mk("user:alice")) != tool_intent_digest(mk("user:bob"))


def test_an_authorization_for_one_user_does_not_transfer_to_another():
    from saathi.execution.authorization import (
        AuthorizationInputs, Decision, authorize_intent)
    from saathi.execution.record import tool_intent_digest
    from saathi.execution.toolintent import ToolIntent

    alice_intent = ToolIntent(intent_id="i", operation="video-generation",
                              actor_id="user:alice", parameters={"x": 1})
    approval = {"approval_id": "a1",
                "tool_intent_digest": tool_intent_digest(alice_intent),
                "status": "approved", "used": 0, "max_uses": 1}
    bob_intent = ToolIntent(intent_id="i", operation="video-generation",
                            actor_id="user:bob", parameters={"x": 1})
    inputs = AuthorizationInputs(actor_user_id="bob", has_permission=True,
                                 kill_switch_blocked=False, approvals=[approval],
                                 now=1_000_000.0)
    assert authorize_intent(bob_intent, inputs).decision is not Decision.AUTHORIZED


# ── no route accepts actor authority from a request body ───────────────────

def test_the_governed_browser_route_ignores_a_body_supplied_actor():
    """It read `body.get("actor") or "user:api"`, and that value reached
    `bind_approval(..., actor=...)` and the denied-actor permission check -- so a
    caller could have an approval bound to someone else, or step around a denial
    by picking a different name."""
    import inspect as _inspect

    import saathi.server as server

    source = _inspect.getsource(server.human_test)
    # Code only. The comment above the fix quotes the old expression, and a
    # substring match would flag the explanation rather than the defect.
    code = "\n".join(line for line in source.splitlines()
                     if not line.lstrip().startswith("#"))
    assert 'body.get("actor")' not in code
    assert "current_actor_id()" in code


def test_no_execution_route_reads_an_actor_out_of_a_request_body():
    """Repository-wide: an authority-bearing actor must not come from a payload."""
    import pathlib
    import re

    offenders = []
    for path in pathlib.Path("saathi").rglob("*.py"):
        if "__pycache__" in str(path):
            continue
        for lineno, line in enumerate(path.read_text().splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue
            # `actor` / `actor_id` only. `actor_role=body.actor_role` is a role
            # label that travels beside an authoritative actor resolved
            # elsewhere -- matching it would flag correct code.
            if re.search(r"\bactor(_id)?\s*=\s*(body|payload|req\.json"
                         r"|request\.json)[\.\[]", line):
                offenders.append(f"{path}:{lineno}")
    assert offenders == [], f"actor taken from a request payload: {offenders}"
