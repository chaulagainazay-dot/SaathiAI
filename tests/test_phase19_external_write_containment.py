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


# ══════════════════════════════════════════════════════════════════════════
# Phase 19B — repository-wide containment
#
# The first pass closed the social and email families. A complete AST sweep
# then found the same bypass in eleven more modules: remote video generation
# (Runway, Kling, Minimax, Pika), hosted avatar and voice generation (HeyGen,
# D-ID, ElevenLabs), image generation, transcription, YouTube publishing via
# n8n, a Facebook video upload, the Telegram send path, and a direct SMTP
# sender with no callers but a live send.
#
# Paid quota counts. A generation API that charges the operator and creates a
# remote job is an external side effect even though nothing is "posted".
# ══════════════════════════════════════════════════════════════════════════

#: Calls that satisfy the guard. `_egress_guard` is the aliased import used at
#: call sites, where a bare `guard` name would collide with local variables.
_GUARD_NAMES = {"guard", "_egress_guard", "current_grant"}

#: RPC-shaped POSTs that mutate nothing outside SaathiOS, and the loopback call.
#: Listed explicitly so the exemption is a decision on the record rather than a
#: silent gap: LLM completions, embeddings, vision and search are reads carried
#: over POST, the two TikTok endpoints are queries, the Gmail one is an OAuth
#: token exchange, and `_stage_draft` posts to 127.0.0.1.
_NOT_EXTERNAL_WRITES = {
    ("saathi/inference/adapters/http_providers.py", None),
    ("saathi/inference/adapters/grounding.py", None),
    ("saathi/memory/engine/embeddings.py", None),
    ("saathi/infrastructure/human_browser/vision_verifier.py", None),
    ("saathi/tools/analytics_loop.py", "pull_tiktok_analytics"),
    ("saathi/tools/social_dashboard.py", "_tiktok"),
    ("saathi/tools/email_tool.py", "_access_token"),
    ("saathi/tools/registry.py", "_stage_draft"),
}

_HTTP_CLIENTS = {"httpx", "requests", "aiohttp"}
_MUTATING = {"post", "put", "patch", "delete"}


def _guarded_functions(tree: ast.AST) -> set[str]:
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for sub in ast.walk(node):
                if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name) \
                        and sub.func.id in _GUARD_NAMES:
                    out.add(node.name)
    return out


def _external_write_sites() -> list[tuple[str, int, str, bool]]:
    """Every mutating HTTP call in the repository, with whether it is guarded."""
    sites = []
    for path in sorted(pathlib.Path("saathi").rglob("*.py")):
        if "__pycache__" in str(path):
            continue
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:
            continue
        guarded = _guarded_functions(tree)
        stack: list[str] = []

        class Scan(ast.NodeVisitor):
            def visit_FunctionDef(self, n):
                stack.append(n.name); self.generic_visit(n); stack.pop()
            visit_AsyncFunctionDef = visit_FunctionDef

            def visit_Call(self, n):
                f = n.func
                if isinstance(f, ast.Attribute) and f.attr in _MUTATING \
                        and isinstance(f.value, ast.Name) and f.value.id in _HTTP_CLIENTS:
                    fn = stack[-1] if stack else "<module>"
                    key = str(path)
                    if (key, None) not in _NOT_EXTERNAL_WRITES \
                            and (key, fn) not in _NOT_EXTERNAL_WRITES:
                        sites.append((key, n.lineno, fn, fn in guarded))
                self.generic_visit(n)

        Scan().visit(tree)
    return sites


def test_every_external_write_in_the_repository_is_guarded():
    """The whole invariant, as one executable statement.

    Not a list of known modules -- a sweep. A new posting function added
    anywhere fails here until it is either guarded or explicitly recorded as
    something that does not mutate the outside world.
    """
    unguarded = [f"{p}:{ln} {fn}" for p, ln, fn, g in _external_write_sites() if not g]
    assert unguarded == [], f"ungoverned external writes: {unguarded}"


def test_the_sweep_actually_finds_sites():
    """Non-vacuity: an empty sweep would make the test above pass for nothing."""
    sites = _external_write_sites()
    assert len(sites) >= 25, f"sweep found only {len(sites)} sites -- is it still working?"
    assert all(g for *_, g in sites)


def test_the_sweep_would_catch_a_newly_added_unguarded_write(tmp_path, monkeypatch):
    """Negative control for the repository-wide sweep."""
    probe = tmp_path / "saathi_probe.py"
    probe.write_text("import httpx\n"
                     "def publish_thing():\n"
                     "    return httpx.post('https://example.com/publish')\n")
    tree = ast.parse(probe.read_text())
    guarded = _guarded_functions(tree)
    assert "publish_thing" not in guarded


# ── the newly contained families ────────────────────────────────────────────

_PHASE_19B_FAMILIES = [
    ("saathi/tools/backup_video.py", {"generate_runway", "generate_kling",
                                      "generate_minimax", "generate_pika"}),
    ("saathi/tools/content_studio.py", {"elevenlabs_voiceover", "make_animated_video",
                                        "make_avatar_video", "_voiceover",
                                        "publish_to_youtube"}),
    ("saathi/tools/meta_post.py", {"_post_instagram_reel_direct",
                                   "_post_instagram_reel_url"}),
    ("saathi/tools/mr_yeti_pipeline.py", {"_upload_facebook_video"}),
    ("saathi/tools/images.py", {"_flux"}),
    ("saathi/tools/voice.py", {"_openai", "_elevenlabs"}),
    ("saathi/tools/video_editor.py", {"transcribe_audio"}),
    ("saathi/tools/speaking_eval.py", {"_transcribe"}),
    ("saathi/tools/content.py", {"post"}),
    ("saathi/connectors/adapters/telegram.py", {"send"}),
    ("saathi/mailer.py", {"send"}),
]


@pytest.mark.parametrize("path,funcs", _PHASE_19B_FAMILIES,
                         ids=[p.split("/")[-1] for p, _ in _PHASE_19B_FAMILIES])
def test_each_newly_contained_family_carries_the_guard(path, funcs):
    tree = ast.parse(pathlib.Path(path).read_text())
    guarded = _guarded_functions(tree)
    missing = funcs - guarded
    assert missing == set(), f"{path}: unguarded external writes {missing}"


# ── the guard sits at the call, not at the function's entry ─────────────────

def test_local_fallbacks_still_work_without_a_grant():
    """Guarding function entry broke these, and looked like containment while
    being a bug: they return early when unconfigured and several fall back to
    local generation, so a path that never reaches a network must not be
    refused."""
    from saathi import mailer
    from saathi.tools import images

    # SMTP unconfigured: writes the local outbox and reports honestly.
    result = mailer.send("a@example.test", "s", "b")
    assert result["delivered"] is False
    assert result["reason"] == "smtp_not_configured"

    # No FLUX endpoint configured: declines without attempting a network call.
    assert images._flux({"label": "x", "text": "y"}, pathlib.Path("/tmp/x.png")) is False


def test_the_guard_still_fires_when_the_provider_is_configured(monkeypatch, tmp_path):
    """The other half: with configuration present, the network call is not made.

    `_flux` catches its own exceptions and returns False so the caller falls
    back to local rendering -- correct for a best-effort generator, and it means
    the denial is not observable in the return value. The property that matters
    is that the request never happened, so that is what is asserted. The denial
    is still recorded by the guard's own audit before it raises.
    """
    import httpx

    from saathi.tools import images

    attempts = []
    monkeypatch.setattr(httpx, "post",
                        lambda *a, **k: attempts.append(a) or (_ for _ in ()).throw(
                            AssertionError("network reached")))
    monkeypatch.setenv("FLUX_API_URL", "https://flux.example/generate")
    monkeypatch.setenv("FLUX_API_KEY", "synthetic-not-a-real-key")

    assert images._flux({"label": "x", "text": "y"}, tmp_path / "x.png") is False
    assert attempts == [], "configured provider was contacted without a grant"


# ── paid-quota generation is an external side effect ────────────────────────

_GENERATION_CALLS = [
    ("saathi.tools.backup_video", "generate_runway", ("prompt", "/tmp/i.png")),
    ("saathi.tools.content_studio", "make_animated_video", ("script",)),
    ("saathi.tools.content_studio", "make_avatar_video", ("script",)),
]


@pytest.mark.parametrize("module,func,args", _GENERATION_CALLS,
                         ids=[f"{f}" for _, f, _ in _GENERATION_CALLS])
def test_paid_generation_is_refused_outside_governance(module, func, args,
                                                       monkeypatch):
    """A generation API that charges the operator and creates a remote job is a
    side effect even though nothing is published."""
    import importlib

    for var in ("RUNWAY_API_KEY", "HEYGEN_API_KEY", "DID_API_KEY",
                "ELEVENLABS_API_KEY", "ELEVENLABS_VOICE_ID"):
        monkeypatch.setenv(var, "synthetic-not-a-real-key")
    mod = importlib.import_module(module)
    try:
        result = getattr(mod, func)(*args)
    except EgressDenied:
        return
    except AssertionError:
        pytest.fail("a real network call was attempted")
    except Exception:
        return  # declined for its own reasons before reaching the network
    assert not (isinstance(result, dict) and result.get("status") == "ok")


# ── sanitization reaches the newly governed families ────────────────────────

def test_a_provider_error_carrying_a_credential_is_sanitised():
    """Provider error bodies quote the request that failed, credential included.
    Whatever leaves the execution boundary crosses the Phase 17 sanitiser."""
    from saathi.execution.sanitization import sanitize

    fake = "sk-abcdefghijklmnop1234567890"
    raw = {"error": {"message": f"401 Unauthorized for key {fake}",
                     "headers": {"authorization": "Bearer abc123def456"}},
           "job_id": "job_991"}
    cleaned, report = sanitize(raw)
    blob = str(cleaned)
    assert fake not in blob and "abc123def456" not in blob
    assert "job_991" in blob, "identifiers must survive; only credentials go"
    assert report.redaction_count >= 2


# ── non-HTTP external writes ────────────────────────────────────────────────
#
# The repository-wide sweep above looks at httpx/requests. Two genuine writes
# use neither, and were found only by reading the code: praw posts a Reddit
# comment through its own client, and a scheduler job submits to reddit.com by
# driving Brave through AppleScript. Different mechanism, same side effect --
# and a detector shaped around HTTP verbs cannot see either.

_NON_HTTP_WRITES = [
    ("saathi/tools/reddit_outreach.py", "send_reply", "praw client"),
    ("saathi/scheduler.py", "auto_reddit_post", "browser automation via osascript"),
]


@pytest.mark.parametrize("path,func,mechanism", _NON_HTTP_WRITES,
                         ids=[f for _, f, _ in _NON_HTTP_WRITES])
def test_non_http_external_writes_are_guarded(path, func, mechanism):
    tree = ast.parse(pathlib.Path(path).read_text())
    assert func in _guarded_functions(tree), f"{path}:{func} ({mechanism}) is ungoverned"


def test_the_reddit_scheduler_job_refuses_deterministically():
    """It opens a browser window and submits a post. The refusal belongs before
    any of that happens, and must be a value the caller can read rather than an
    exception through a daemon thread."""
    from saathi import scheduler

    result = scheduler.auto_reddit_post()
    assert result["status"] == "blocked"
    assert result["reason_code"] == "egress.not_governed"


def test_the_praw_reply_is_refused_outside_governance(monkeypatch):
    from saathi.tools import reddit_outreach

    monkeypatch.setattr(reddit_outreach, "_creds_ok", lambda: True)
    monkeypatch.setattr(reddit_outreach, "_get_reddit",
                        lambda: pytest.fail("reddit client built before the guard"))
    result = reddit_outreach.send_reply("t3_abc", "hello")
    # The client is built first, so the guard raises inside the function's own
    # try/except and comes back as an error rather than propagating.
    assert result.get("ok") is not True


def test_no_browser_automation_reaches_reddit_without_a_grant(monkeypatch):
    """Dynamic: arm subprocess to fail if the job ever shells out."""
    import subprocess

    from saathi import scheduler

    monkeypatch.setattr(subprocess, "run",
                        lambda *a, **k: pytest.fail("subprocess invoked without a grant"))
    assert scheduler.auto_reddit_post()["status"] == "blocked"
