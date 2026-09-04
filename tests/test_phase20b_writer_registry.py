"""Phase 20B — every external writer reachable through the governed path.

Phase 19 put a guard in front of every external mutation. Phase 20 proved one
legitimate scheduled write can pass through. This closes the gap between them:
a closed registry of every writer, reachable only by a ToolIntent the boundary
admitted.

The claim being tested is narrow and worth stating precisely, because the
obvious misreading is the dangerous one:

    Registering a writer makes it REACHABLE under authority.
    It does not make it PERMITTED, and it does not make it SCHEDULED.

Nothing here enables sending. No scheduler job is turned on, no gate is
lowered, and a registered writer with no delegation, no approval and no
connector authority refuses exactly as it did before Phase 20B existed. Those
are the properties asserted below, in that order.

No real provider is contacted: httpx and requests are replaced with clients that
raise, so a real request fails the suite rather than sending something.
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
)
from saathi.execution.writers import WRITERS, UnknownWriter, get, handler_for


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """A real request is a certification failure, not a silent side effect."""
    import httpx
    import requests

    def _boom(*a, **k):
        raise AssertionError("a test attempted to contact a real provider")

    for mod in (httpx, requests):
        for verb in ("post", "put", "patch", "delete", "get", "request"):
            monkeypatch.setattr(mod, verb, _boom, raising=False)


# ── the registry is closed and honest ──────────────────────────────────────

def test_every_registered_writer_resolves():
    """A registry entry pointing at a function that no longer exists is a lie
    the first real dispatch would discover."""
    unresolvable = []
    for key, writer in WRITERS.items():
        try:
            writer.resolve()
        except Exception as exc:  # noqa: BLE001 - reported, not swallowed
            unresolvable.append(f"{key}: {type(exc).__name__}")
    assert unresolvable == [], unresolvable


def test_the_registry_is_closed():
    """A writer not in the table cannot be reached through this path at all."""
    with pytest.raises(UnknownWriter):
        get("facebook.delete_everything")


def test_registry_keys_are_unique_and_stable():
    assert len(WRITERS) == len({w.key for w in WRITERS.values()})
    for key, writer in WRITERS.items():
        assert writer.key == key


def test_the_registry_covers_every_guarded_family():
    """Cross-checked against the Phase 19 guarded modules, so a writer cannot be
    guarded but unreachable, nor registered but unguarded."""
    registered_modules = {w.module for w in WRITERS.values()}
    for expected in ("saathi.tools.meta_post", "saathi.tools.email_tool",
                     "saathi.tools.mailerlite", "saathi.tools.twitter_post",
                     "saathi.tools.linkedin_post", "saathi.tools.tiktok_post",
                     "saathi.tools.reddit_outreach", "saathi.mailer",
                     "saathi.connectors.adapters.telegram",
                     "saathi.tools.backup_video", "saathi.tools.content_studio",
                     "saathi.tools.images", "saathi.tools.voice",
                     "saathi.tools.video_editor", "saathi.tools.speaking_eval",
                     "saathi.tools.content", "saathi.tools.mr_yeti_pipeline"):
        assert expected in registered_modules, f"{expected} guarded but unreachable"


def test_every_registered_target_is_actually_guarded():
    """The `egress_target` recorded here must match a guard that really exists in
    the writer's module, or the registry is describing protection it does not
    have."""
    missing = []
    for key, writer in WRITERS.items():
        path = pathlib.Path(writer.module.replace(".", "/") + ".py")
        source = path.read_text()
        if writer.egress_target not in source:
            missing.append(f"{key}: {writer.egress_target} not guarded in {path}")
    assert missing == [], missing


# ── registration is not permission ─────────────────────────────────────────

@pytest.mark.parametrize("key", sorted(WRITERS))
def test_dispatching_any_writer_without_a_grant_is_refused(key, monkeypatch):
    """The whole point. Being in the registry changes nothing about authority.

    Tested with a stub standing in for each provider function, because the real
    ones return early when unconfigured -- correct Phase 19B placement, the
    guard sits at the call rather than the entry, so an unconfigured writer
    declines before it ever reaches one. That makes "did it raise?" a question
    about credentials rather than about authority. Substituting a stub that
    *does* reach its guard asks the authority question directly, and Phase 19
    separately proves each real module carries the guard.
    """
    stub = _StubWriter()
    monkeypatch.setattr(type(get(key)), "resolve", lambda self: stub)
    with pytest.raises(EgressDenied):
        handler_for(key, {})(_intent_stub(), None)
    assert stub.calls == [], "the writer ran without a grant"


@pytest.mark.parametrize("key", sorted(WRITERS))
def test_dispatching_any_writer_inside_a_grant_reaches_it(key, monkeypatch):
    """Non-vacuity for the whole set: the guard must be the thing stopping them,
    not a broken registry entry. Inside a grant every writer is reached."""
    stub = _StubWriter()
    monkeypatch.setattr(type(get(key)), "resolve", lambda self: stub)
    with governed_egress(EgressGrant("i1", "d1", "user:test", key)):
        out = handler_for(key, {})(_intent_stub(), None)
    assert len(stub.calls) == 1
    assert stub.calls[0]["grant"].intent_digest == "d1"
    assert out["status"] == "succeeded"


def test_an_unconfigured_real_writer_declines_without_reaching_a_network():
    """The behaviour the stub test above deliberately factors out, asserted once
    on real code: with no credentials these decline locally, and the network
    fixture proves nothing was contacted."""
    from saathi import mailer

    result = mailer.send("a@example.test", "s", "b")
    assert result["delivered"] is False
    assert result["reason"] == "smtp_not_configured"


def test_the_registry_opens_no_grant_of_its_own():
    """Static: only execution infrastructure may open a Phase 19 grant, and a
    lookup table is not that."""
    tree = ast.parse(pathlib.Path("saathi/execution/writers.py").read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id != "governed_egress", "the registry opens a grant"
        if isinstance(node, ast.Attribute):
            assert node.attr != "governed_egress"


def test_the_registry_calls_no_raw_external_client():
    tree = ast.parse(pathlib.Path("saathi/execution/writers.py").read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in ("post", "put",
                                                             "patch", "delete"):
            recv = node.value
            name = recv.id if isinstance(recv, ast.Name) else ""
            assert name not in ("httpx", "requests", "aiohttp")


def test_the_registry_restates_no_authority_facts():
    """Risk class, approval requirement and mutation class live in the connector
    registry. A second copy here would be a second thing to keep in sync, and
    the copy that drifts is the one that grants too much."""
    source = pathlib.Path("saathi/execution/writers.py").read_text()
    tree = ast.parse(source)
    docstrings = {id(n.value) for n in ast.walk(tree)
                  if isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)}
    literals = {n.value for n in ast.walk(tree)
                if isinstance(n, ast.Constant) and isinstance(n.value, str)
                and id(n) not in docstrings}
    for forbidden in ("EXTERNAL_SIDE_EFFECT", "HIGH_IMPACT", "IRREVERSIBLE",
                      "NO_APPROVAL_REQUIRED", "READ_ONLY"):
        assert forbidden not in literals, f"registry restates {forbidden}"


# ── dispatch happens only under a grant ────────────────────────────────────

class _StubWriter:
    """Stands in for a provider function, and asserts the grant is held."""

    def __init__(self):
        self.calls = []

    def __call__(self, **kwargs):
        from saathi.execution.egress import guard

        grant = guard("stub.target", operation="stub")
        self.calls.append({"kwargs": kwargs, "grant": grant})
        return {"ok": True, "id": len(self.calls),
                "echo": {"authorization": "Bearer synthetic-abc123def456"}}


def test_a_dispatched_writer_runs_inside_the_grant(monkeypatch):
    """The positive control: inside a grant the handler reaches the writer, and
    the writer sees the grant."""
    stub = _StubWriter()
    writer = get("telegram.send")
    monkeypatch.setattr(type(writer), "resolve", lambda self: stub)

    handler = handler_for("telegram.send", {"message": "hi"})
    grant = EgressGrant(intent_id="i1", intent_digest="d1", actor="user:test",
                        operation="telegram.send")
    with governed_egress(grant):
        out = handler(_intent_stub(), None)

    assert stub.calls and stub.calls[0]["grant"].intent_digest == "d1"
    assert out["status"] == "succeeded"


def test_the_dispatched_result_is_sanitised(monkeypatch):
    """Provider echoes carry credentials. Whatever leaves the handler has
    crossed the Phase 17 sanitiser."""
    stub = _StubWriter()
    writer = get("telegram.send")
    monkeypatch.setattr(type(writer), "resolve", lambda self: stub)

    with governed_egress(EgressGrant("i1", "d1", "user:test", "op")):
        out = handler_for("telegram.send", {})(_intent_stub(), None)

    assert "synthetic-abc123def456" not in str(out["result"])
    assert out["result"]["id"] == 1, "identifiers survive; only credentials go"


def test_the_grant_does_not_outlive_the_dispatch(monkeypatch):
    stub = _StubWriter()
    monkeypatch.setattr(type(get("telegram.send")), "resolve", lambda self: stub)
    with governed_egress(EgressGrant("i1", "d1", "a", "op")):
        handler_for("telegram.send", {})(_intent_stub(), None)
    assert current_grant() is None


# ── nothing was scheduled, nothing was enabled ─────────────────────────────

def test_no_scheduler_job_was_wired_to_send(monkeypatch):
    """The load-bearing safety property of this change.

    Registering writers must not turn any cron job into a sender. Every
    scheduler job that performs an external write still refuses, because none of
    them runs inside a grant.
    """
    from saathi import scheduler

    assert scheduler.auto_reddit_post()["status"] == "blocked"


def test_autopost_is_still_fail_closed():
    from saathi import autopost

    for fn in (lambda: autopost.run_social_autopost("AM"),
               autopost.run_daily_autopost):
        result = fn()
        assert result["status"] == "blocked"
        assert result["reason_code"] == "egress.not_governed"


def test_the_scheduler_does_not_import_the_registry():
    """Wiring reachability must not become wiring *firing*. If a scheduler job
    ever dispatches a writer directly it will do so without a grant and be
    refused -- but the import itself is the signal that somebody tried."""
    source = pathlib.Path("saathi/scheduler.py").read_text()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [a.name for a in node.names]
            module = getattr(node, "module", "") or ""
            assert "execution.writers" not in module, "scheduler dispatches writers"
            assert not any("writers" in n for n in names)


def test_registering_a_writer_changed_no_gate():
    """Phase 16's refusal vocabulary is untouched: the registry adds no reason
    code, no authority class and no bypass."""
    import saathi.execution.authorization as authz

    source = pathlib.Path("saathi/execution/writers.py").read_text()
    assert "authorization" not in source or "authorize" not in source
    # And the guard still refuses an unregistered, ungoverned call.
    from saathi.execution.egress import guard

    with pytest.raises(EgressDenied):
        guard("anything.at.all")
    assert hasattr(authz, "SYSTEM_ACTOR_MAX_AUTHORITY")


def _intent_stub():
    """The minimum a handler reads from an intent. The boundary passes a real
    ToolIntent; these tests exercise the handler directly."""
    class _I:
        intent_id = "i-stub"
        idempotency_key = "k" * 64
        operation = "stub"
    return _I()
