"""R2.1-S7 — the adversarial security matrix, run against the committed repair.

One test per numbered item, so the file reads as the evidence it produces. The
items are not new claims: they are the questions an attacker would ask, asked
in one place, against the shipped code rather than a description of it.

Handlers are harmless counting mocks. Nothing here performs a real side effect,
and no test needs one — the finding is always "did execution happen where it
must not", which a mock records perfectly.
"""
import ast
import inspect
import io
import pathlib
import subprocess
import tempfile
import time

import numpy as np
import pytest
from fastapi.testclient import TestClient

from saathi import config, server, voice
from saathi.tools import registry
from saathi.tools.registry import execute_tool, recent_governance_decisions


# ── fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_governance():
    registry._governance_harness = None
    registry._governance_audit.clear()
    yield


@pytest.fixture
def client():
    return TestClient(server.app)


@pytest.fixture
def authed():
    return {"x-baadar-session": server._session_token()}


@pytest.fixture
def handlers():
    """Every registered handler replaced by a harmless counting mock."""
    calls: list[str] = []
    original = dict(registry._HANDLERS)

    def make(name):
        def handler(**kwargs):
            calls.append(name)
            return {"ok": True}
        return handler

    for name in list(registry._HANDLERS):
        registry._HANDLERS[name] = make(name)
    for extra in ("__s7_unclassified__", "__s7_readonly__", "__s7_fs__", "__s7_net__"):
        registry._HANDLERS[extra] = make(extra)
    try:
        yield calls
    finally:
        registry._HANDLERS.clear()
        registry._HANDLERS.update(original)


def _upload(content=b"\x1a\x45\xdf\xa3fake", name="speech.webm", mime="audio/webm"):
    return {"file": (name, io.BytesIO(content), mime)}


class Boom:
    """Fails the test if a stage runs that must not."""

    def __init__(self, label):
        self.label = label

    def __call__(self, *a, **kw):
        raise AssertionError(f"{self.label} ran for a rejected request")


# ── 1–2: the doors ───────────────────────────────────────────────────────────


def test_01_anonymous_agent_chat_is_rejected(client):
    assert client.post("/api/v1/agent/chat", json={"text": "hi"}).status_code == 401


def test_02_anonymous_voice_command_is_rejected_before_body_processing(client, monkeypatch):
    for attr in ("_decode", "decode_16k", "transcribe", "transcribe_array",
                 "verify", "verify_array", "synthesize"):
        monkeypatch.setattr(voice, attr, Boom(attr), raising=False)

    class NoBrain:
        def respond(self, *a, **kw):
            raise AssertionError("the agent ran for an anonymous request")

    monkeypatch.setattr(server, "agent", NoBrain())
    r = client.post("/api/v1/voice/command", files=_upload(b"x" * 100_000),
                    data={"session_id": "web"})
    assert r.status_code == 401


# ── 3–8: identity signals grant nothing ──────────────────────────────────────


def test_03_client_supplied_speaker_verified_grants_nothing(client):
    r = client.post("/api/v1/agent/chat",
                    json={"text": "run shell whoami", "speaker_verified": True})
    assert r.status_code == 401
    assert "speaker_verified" not in server.ChatIn.model_fields


def test_04_extra_authority_fields_grant_nothing():
    parsed = server.ChatIn(**{"text": "hi", "is_admin": True, "identity": "ADMIN",
                              "human_approved": True, "code_confirmed": True,
                              "approval_reference": "forged", "role": "owner"})
    assert set(parsed.model_dump()) == {"text", "session_id"}
    for forged in ("is_admin", "identity", "human_approved", "code_confirmed",
                   "approval_reference", "role"):
        assert not hasattr(parsed, forged)


@pytest.mark.parametrize("observed", [True, False, None])
def test_05_voiceprint_match_grants_nothing(handlers, observed):
    out = execute_tool("send_email", {"to": "a@b.c", "subject": "s", "body": "b"},
                       speaker_match_observed=observed)
    assert out["blocked"] is True
    assert handlers == []
    audit = recent_governance_decisions()
    assert audit and audit[0]["who"] == "user"


def test_06_telegram_channel_trust_grants_nothing():
    root = pathlib.Path(server.__file__).resolve().parent
    source = (root / "telegram_bot.py").read_text(encoding="utf-8")
    assert "speaker_verified" not in source
    assert "Identity.ADMIN" not in source


def test_07_default_brain_grants_nothing():
    source = inspect.getsource(server)
    idx = source.find("register_default_brain")
    assert idx > -1
    window = source[idx:idx + 400]
    assert "speaker_verified" not in window
    assert "identity" not in window.lower() or "ADMIN" not in window


@pytest.mark.parametrize("module", ["listener.py", "pushtotalk.py"])
def test_08_listener_and_push_to_talk_voice_match_grants_nothing(module):
    # read from disk: these modules import sounddevice, which is not installed
    # in every environment, and the claim is about their source either way
    root = pathlib.Path(server.__file__).resolve().parent
    source = (root / module).read_text(encoding="utf-8")
    assert "speaker_verified" not in source
    assert "speaker_match_observed" in source


# ── 9–10: RBAC ceilings hold ─────────────────────────────────────────────────


def test_09_viewer_cannot_reach_owner_or_admin_authority():
    from saathi.platform.bindings import ROLE_AUTHORITY_CEILING, authority_allows
    from saathi.platform.models import PlatformRole
    from saathi.tool_runtime.contracts import ToolAuthorityClass

    viewer = ROLE_AUTHORITY_CEILING[PlatformRole.VIEWER.value]
    assert viewer == ToolAuthorityClass.READ_ONLY.value
    for reach in (ToolAuthorityClass.LOCAL_MUTATION, ToolAuthorityClass.EXTERNAL_MUTATION,
                  ToolAuthorityClass.SECURITY_SENSITIVE):
        assert authority_allows(viewer, reach.value) is False


def test_10_operator_cannot_bypass_rbac():
    from saathi.platform.bindings import ROLE_AUTHORITY_CEILING, authority_allows
    from saathi.platform.models import PlatformRole
    from saathi.tool_runtime.contracts import ToolAuthorityClass

    operator = ROLE_AUTHORITY_CEILING[PlatformRole.OPERATOR.value]
    assert authority_allows(operator, ToolAuthorityClass.EXTERNAL_MUTATION.value) is False
    assert authority_allows(operator, ToolAuthorityClass.SECURITY_SENSITIVE.value) is False
    # an unknown ceiling never opens anything
    assert authority_allows("not-a-class", ToolAuthorityClass.READ_ONLY.value) is False


# ── 11–17: nothing executes outside the gateway ──────────────────────────────


@pytest.mark.parametrize("label,tool,args", [
    ("ordinary", "canteen_query", {"topic": "sales_today"}),
    ("read_only", "self_status", {}),
    ("filesystem", "read_project_file", {"name": "x", "path": "y"}),
    ("network", "web_search", {"query": "x"}),
    ("unclassified", "__s7_unclassified__", {"a": 1}),
])
def test_11_to_15_no_tool_class_executes_directly(handlers, label, tool, args):
    out = execute_tool(tool, args, speaker_match_observed=True)
    assert handlers == [], f"{label} executed outside the gateway"
    assert out["blocked"] is True


@pytest.mark.parametrize("bad", [None, [], "text", 42, ("a",)])
def test_16_malformed_arguments_fail_closed(handlers, bad):
    out = execute_tool("canteen_query", bad)
    assert handlers == []
    assert isinstance(out, dict) and out["blocked"] is True


def test_17_unknown_tool_fails_closed(handlers):
    out = execute_tool("__no_such_tool_at_all__", {})
    assert handlers == []
    assert out["blocked"] is True
    assert "unknown tool" in out["error"]


# ── 18–21: approval cannot be manufactured ───────────────────────────────────


def test_18_human_approval_cannot_be_synthesized():
    source = inspect.getsource(execute_tool)
    assert "human_approved=False" in source
    assert "human_approved=speaker" not in source
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.keyword) and node.arg == "human_approved":
            assert isinstance(node.value, ast.Constant) and node.value.value is False


def test_19_code_confirmation_cannot_be_synthesized():
    source = inspect.getsource(execute_tool)
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.keyword) and node.arg == "code_confirmed":
            assert isinstance(node.value, ast.Constant) and node.value.value is False


def test_20_no_approval_reference_is_fabricated(handlers):
    for tool, args in [("send_email", {"to": "a@b.c"}), ("canteen_query", {"topic": "x"}),
                       ("post_social_content", {"platform": "facebook"})]:
        out = execute_tool(tool, args, speaker_match_observed=True)
        blob = repr(out)
        assert "ToolApprovalReference" not in blob
        assert out.get("approval_reference") is None
        assert out.get("approved") is not True
    source = inspect.getsource(registry)
    assert "ToolApprovalReference(" not in source, "the legacy path can mint an approval"


def test_21_invalid_approval_reference_is_rejected():
    from saathi.tool_runtime.contracts import ToolApprovalReference, ToolSideEffectClass

    kwargs = dict(tool_id="m49.connector.gmail.send_message", capability="gmail.send",
                  run_id="run-1", side_effect=ToolSideEffectClass.EXTERNAL_IRREVERSIBLE)
    good = ToolApprovalReference(approval_id="a1", tool_id=kwargs["tool_id"],
                                 capability=kwargs["capability"], run_id="run-1",
                                 expires_at=time.time() + 600)
    # wrong tool, wrong run, expired, revoked, inactive, and empty id all fail
    assert ToolApprovalReference().is_valid_for(**kwargs)[0] is False
    assert good.__class__(**{**good.__dict__, "tool_id": "m49.other"}).is_valid_for(**kwargs)[0] is False
    assert good.__class__(**{**good.__dict__, "run_id": "run-2"}).is_valid_for(**kwargs)[0] is False
    assert good.__class__(**{**good.__dict__, "expires_at": time.time() - 1}).is_valid_for(**kwargs)[0] is False
    assert good.__class__(**{**good.__dict__, "revoked": True}).is_valid_for(**kwargs)[0] is False
    assert good.__class__(**{**good.__dict__, "active": False}).is_valid_for(**kwargs)[0] is False


# ── 22: session scope ────────────────────────────────────────────────────────


@pytest.mark.parametrize("forged", ["voice:s:someone:web", "s:abc", "../../etc/passwd", "a b"])
def test_22_cross_scope_session_identifier_is_rejected(client, authed, forged, monkeypatch):
    for attr in ("_decode", "decode_16k", "transcribe", "transcribe_array"):
        monkeypatch.setattr(voice, attr, Boom(attr), raising=False)
    r = client.post("/api/v1/voice/command", files=_upload(), headers=authed,
                    data={"session_id": forged})
    assert r.status_code == 400
    assert r.json()["error"] == "invalid_session_id"


# ── 23–24: enrollment is inert ───────────────────────────────────────────────


def test_23_retired_enrollment_reads_decodes_uploads_and_overwrites_nothing(
        client, authed, monkeypatch):
    monkeypatch.setattr(voice, "enroll", Boom("voice.enroll"))
    monkeypatch.setattr(voice, "_decode", Boom("audio decode"))
    r = client.post("/api/v1/voice/enroll", files=_upload(b"x" * 50_000), headers=authed)
    assert r.status_code == 410
    assert r.json()["error"] == "voice_enrollment_unavailable"
    assert list(inspect.signature(server.enroll_voice).parameters) == ["request"]


def test_24_existing_voice_profile_hash_is_unchanged(client, authed, tmp_path, monkeypatch):
    import hashlib

    profile = tmp_path / "owner_voice.npy"
    profile.write_bytes(b"an existing enrolled profile")
    before = hashlib.sha256(profile.read_bytes()).hexdigest()
    monkeypatch.setattr(config, "VOICE_PROFILE_PATH", profile)
    client.post("/api/v1/voice/enroll", files=_upload(), headers=authed)
    client.post("/api/v1/voice/command", files=_upload(), headers=authed,
                data={"session_id": "web"})
    assert hashlib.sha256(profile.read_bytes()).hexdigest() == before


# ── 25–26: audio resources ───────────────────────────────────────────────────


@pytest.mark.parametrize("failure", ["ffmpeg_error", "ffmpeg_timeout", "decoder_error", "cancelled"])
def test_25_temporary_files_are_clean_on_every_failure_path(monkeypatch, tmp_path, failure):
    import soundfile as sf
    from pathlib import Path

    sandbox = tmp_path / "tmp"
    sandbox.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(sandbox))
    monkeypatch.setattr(voice, "_ffmpeg", lambda: "ffmpeg")

    def raise_read(*a, **kw):
        raise RuntimeError("not a wav")

    monkeypatch.setattr(sf, "read", raise_read)

    if failure == "ffmpeg_error":
        monkeypatch.setattr(subprocess, "run",
                            _raiser(subprocess.CalledProcessError(1, "ffmpeg")))
    elif failure == "ffmpeg_timeout":
        monkeypatch.setattr(subprocess, "run",
                            _raiser(subprocess.TimeoutExpired("ffmpeg", 60)))
    elif failure == "cancelled":
        import asyncio
        monkeypatch.setattr(subprocess, "run", _raiser(asyncio.CancelledError()))
    else:  # decoder_error — ffmpeg writes its output, reading it fails
        def fake_run(cmd, **kw):
            Path(cmd[-1]).write_bytes(b"converted")
            return subprocess.CompletedProcess(cmd, 0)

        monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(BaseException):
        voice._decode(b"not-audio", "speech.webm")
    assert list(sandbox.iterdir()) == [], f"{failure} left temporary audio behind"


def _raiser(exc):
    def _fn(*a, **kw):
        raise exc
    return _fn


@pytest.mark.parametrize("case", ["unsupported_mime", "oversized", "too_long"])
def test_26_rejected_audio_invokes_no_stt_llm_or_tts(client, authed, monkeypatch, case):
    monkeypatch.setattr(voice, "transcribe_array", Boom("STT"))
    monkeypatch.setattr(voice, "transcribe", Boom("STT"), raising=False)
    monkeypatch.setattr(voice, "synthesize", Boom("TTS"))

    class NoBrain:
        def respond(self, *a, **kw):
            raise AssertionError("the LLM ran for a rejected request")

    monkeypatch.setattr(server, "agent", NoBrain())

    if case == "unsupported_mime":
        monkeypatch.setattr(voice, "decode_16k", Boom("decode"))
        files = _upload(b"x" * 64, "payload.exe", "application/x-msdownload")
        expected = 415
    elif case == "oversized":
        monkeypatch.setattr(voice, "decode_16k", Boom("decode"))
        files = _upload(b"\x00" * (server.VOICE_MAX_UPLOAD_BYTES + 512))
        expected = 413
    else:
        long_wav = np.zeros(int((server.VOICE_MAX_SECONDS + 5) * 16000), dtype=np.float32)
        monkeypatch.setattr(voice, "_decode", lambda *a, **kw: (long_wav, 16000))
        files = _upload()
        expected = 413

    r = client.post("/api/v1/voice/command", files=files, headers=authed,
                    data={"session_id": "web"})
    assert r.status_code == expected


# ── 27–30: the surviving authority architecture ──────────────────────────────


def test_27_gateway_audit_records_proposed_and_denied_attempts(handlers):
    registry._governance_audit.clear()
    execute_tool("canteen_query", {"topic": "sales_today"}, speaker_match_observed=True)
    execute_tool("send_email", {"to": "a@b.c"}, speaker_match_observed=False)
    audit = recent_governance_decisions()
    assert len(audit) >= 2, "denied attempts must still reach the audit"
    assert {a["what"] for a in audit} >= {"canteen_query", "send_email"}


def test_28_exactly_one_execution_gateway():
    root = pathlib.Path(server.__file__).resolve().parent
    definitions = []
    for path in root.rglob("*.py"):
        for num, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            if line.startswith("class ExecutionGateway") and "Exception" not in line:
                definitions.append(f"{path.relative_to(root)}:{num}")
    assert len(definitions) == 1, f"more than one ExecutionGateway: {definitions}"
    from saathi.tool_runtime import compat
    assert "ExecutionGateway" in inspect.getsource(compat.try_canonical_legacy_tool)


def test_29_approval_validation_remains_in_the_execution_service():
    from saathi.tool_runtime import service

    source = inspect.getsource(service)
    assert "_validate_approval" in source
    assert "is_valid_for" in source
    # the legacy dispatcher must not carry a competing validator — the name
    # appears in its docstring as a pointer, so assert on code, not prose
    tree = ast.parse(inspect.getsource(registry))
    defined = {n.name for n in ast.walk(tree)
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    assert "_validate_approval" not in defined
    called = {n.func.id for n in ast.walk(tree)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert "_validate_approval" not in called
    assert "is_valid_for" not in {n.attr for n in ast.walk(tree)
                                  if isinstance(n, ast.Attribute)}


def test_30_trading_guardian_and_deterministic_risk_are_preserved():
    from saathi.platform.tg.service import TradingGuardianService

    posture = TradingGuardianService().posture()
    for key in ("live_trading_authorized", "live_order_capable", "broker_credential_support",
                "leverage_allowed", "margin_allowed"):
        assert posture[key] is False, f"posture.{key} drifted"
    assert posture["paper_only"] is True
    assert posture["require_approval"] is True
    assert "ApprovalCenter" in posture["execution_path"]
    assert "ExecutionGateway" in posture["execution_path"]
