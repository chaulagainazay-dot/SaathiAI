"""R2.1 — a stopped or abandoned voice session must stop counting as active.

Reproduced on a throwaway database before anything changed: `POST /stop` moves
only `input_state` and leaves the conversation in LISTENING, while route
change, unmount, hard reset, logout and recognition errors sent the backend
nothing at all. Every abandoned session stayed active, each talk cycle opened
another, and at MAX_SESSIONS_PER_USER the budget answered
RESOURCE_BUDGET_EXHAUSTED — voice stopped working.

The client half is `POST /finish` on every teardown path (covered by
saathi-os/lib/voice-session/session-finalizer.test.js). This is the backend
half: a client cannot always send that request — a closed tab or a hard
navigation kills it in flight — so the server reconciles what was abandoned.

The budget itself is unchanged, nothing is deleted, and reconciliation is
scoped to the caller.
"""
from __future__ import annotations

import pytest

from saathi.platform.context import PlatformContextError
from saathi.platform.service import reset_platform_for_tests
from saathi.platform.voice.runtime import (
    ConversationState,
    VoiceSessionManager,
    reset_voice_runtime_for_tests,
)
from saathi.platform.voice.runtime.models import (
    ABANDONED_SESSION_IDLE_SECONDS,
    MAX_SESSIONS_PER_USER,
)
from saathi.platform.conversation import make_test_conversation_service
from saathi.platform.voice.service import SpeechService, reset_speech_service_for_tests
from test_m74_voice_foundation import FakeProvider


@pytest.fixture()
def platform(tmp_path):
    service = reset_platform_for_tests(tmp_path / "r21-lifecycle.db")
    boot = service.bootstrap_owner_secure(
        email="r21-owner@local", name="R21 Owner", password="R21OwnerPass1!"
    )
    ctx = service.require_context(boot["token"])
    speech = SpeechService(
        service.store,
        providers=[FakeProvider(provider_id="macos_system")],
        artifact_root=tmp_path / "voice-artifacts",
        start_workers=False,
    )
    service._speech_service = speech
    conv = make_test_conversation_service(service.store, reply_fn=lambda messages: "ok")
    service._conversation_service = conv
    runtime = VoiceSessionManager(
        service.store, speech_service=speech, conversation_service=conv
    )
    service._voice_runtime = runtime
    yield service, ctx, runtime
    speech.shutdown()
    reset_speech_service_for_tests(service)
    reset_voice_runtime_for_tests(service)
    reset_platform_for_tests()


def _open(runtime, ctx):
    session = runtime.create_session(ctx, {"input_mode": "toggle"})
    sid = session["session_id"]
    runtime.start_listening(ctx, sid, mode="toggle", permission_granted=True)
    return sid


def _active(runtime, ctx):
    return runtime.repo.count_active_for_user(
        org_id=ctx.org_id, workspace_id=ctx.workspace_id, user_id=ctx.user_id
    )


def _state(runtime, ctx, sid):
    return runtime.get_session(ctx, sid)["state"]


def _age(runtime, ctx, sid, seconds):
    """Backdate a session's activity, the way an abandoned tab would."""
    session = runtime.repo.get_session(
        sid, org_id=ctx.org_id, workspace_id=ctx.workspace_id
    )
    session.last_activity_at = runtime.store._now() - seconds
    runtime.repo.save_session(session)
    # save_session refreshes last_activity_at, so write it again directly.
    runtime.store._conn.execute(
        "UPDATE voice_runtime_sessions SET last_activity_at=?, updated_at=? WHERE session_id=?",
        (runtime.store._now() - seconds, runtime.store._now() - seconds, sid),
    )


class TestStopIsNotTermination:
    def test_stop_alone_leaves_the_session_listening(self, platform):
        _, ctx, runtime = platform
        sid = _open(runtime, ctx)
        runtime.stop_listening(ctx, sid)
        # Pinned deliberately: /stop ends capture, not the conversation. This
        # is why the client has to send the terminal request.
        assert _state(runtime, ctx, sid) == ConversationState.LISTENING.value
        assert _active(runtime, ctx) == 1

    def test_finish_transitions_out_of_listening(self, platform):
        _, ctx, runtime = platform
        sid = _open(runtime, ctx)
        runtime.stop_listening(ctx, sid)
        runtime.finish_session(ctx, sid)
        assert _state(runtime, ctx, sid) == ConversationState.FINISHED.value
        assert _active(runtime, ctx) == 0

    def test_finish_is_idempotent(self, platform):
        _, ctx, runtime = platform
        sid = _open(runtime, ctx)
        runtime.finish_session(ctx, sid)
        runtime.finish_session(ctx, sid)
        runtime.finish_session(ctx, sid)
        assert _state(runtime, ctx, sid) == ConversationState.FINISHED.value
        assert _active(runtime, ctx) == 0

    def test_history_survives_termination(self, platform):
        _, ctx, runtime = platform
        sid = _open(runtime, ctx)
        runtime.finish_session(ctx, sid)
        listed = runtime.list_sessions(ctx)
        assert any(s["session_id"] == sid for s in listed), "the record must remain"


class TestCyclesStayUnderTheCap:
    @pytest.mark.parametrize("cycles", [5, 10, MAX_SESSIONS_PER_USER * 2])
    def test_terminated_cycles_never_accumulate(self, platform, cycles):
        _, ctx, runtime = platform
        peak = 0
        for _ in range(cycles):
            sid = _open(runtime, ctx)
            peak = max(peak, _active(runtime, ctx))
            runtime.stop_listening(ctx, sid)
            runtime.finish_session(ctx, sid)
            assert _active(runtime, ctx) == 0
        assert peak == 1

    def test_without_termination_the_budget_is_exhausted(self, platform):
        _, ctx, runtime = platform
        for _ in range(MAX_SESSIONS_PER_USER):
            runtime.stop_listening(ctx, _open(runtime, ctx))
        assert _active(runtime, ctx) == MAX_SESSIONS_PER_USER
        with pytest.raises(PlatformContextError) as excinfo:
            runtime.create_session(ctx, {"input_mode": "toggle"})
        assert excinfo.value.code == "RESOURCE_BUDGET_EXHAUSTED"


class TestAbandonedSessionsAreReconciled:
    def test_an_idle_session_stops_counting_as_active(self, platform):
        _, ctx, runtime = platform
        sid = _open(runtime, ctx)
        _age(runtime, ctx, sid, ABANDONED_SESSION_IDLE_SECONDS + 60)

        # Reconciliation runs where it matters: when the budget is consulted.
        new_sid = _open(runtime, ctx)

        assert _state(runtime, ctx, sid) == ConversationState.FINISHED.value
        assert _state(runtime, ctx, new_sid) == ConversationState.LISTENING.value
        assert _active(runtime, ctx) == 1

    def test_a_recently_active_session_is_left_alone(self, platform):
        _, ctx, runtime = platform
        sid = _open(runtime, ctx)
        _age(runtime, ctx, sid, ABANDONED_SESSION_IDLE_SECONDS // 2)
        _open(runtime, ctx)
        assert _state(runtime, ctx, sid) == ConversationState.LISTENING.value

    def test_abandoned_sessions_cannot_lock_a_user_out(self, platform):
        _, ctx, runtime = platform
        # Every slot filled by tabs that were closed without cleanup.
        stranded = []
        for _ in range(MAX_SESSIONS_PER_USER):
            sid = _open(runtime, ctx)
            stranded.append(sid)
        for sid in stranded:
            _age(runtime, ctx, sid, ABANDONED_SESSION_IDLE_SECONDS + 60)

        fresh = _open(runtime, ctx)

        assert _state(runtime, ctx, fresh) == ConversationState.LISTENING.value
        assert _active(runtime, ctx) == 1
        for sid in stranded:
            assert _state(runtime, ctx, sid) == ConversationState.FINISHED.value

    def test_reconciliation_preserves_every_record(self, platform):
        _, ctx, runtime = platform
        stranded = [_open(runtime, ctx) for _ in range(3)]
        for sid in stranded:
            _age(runtime, ctx, sid, ABANDONED_SESSION_IDLE_SECONDS + 60)
        _open(runtime, ctx)
        listed = {s["session_id"] for s in runtime.list_sessions(ctx)}
        for sid in stranded:
            assert sid in listed, "reconciliation must not delete audit history"


class TestCleanupIsScopedAndAuthenticated:
    """Isolation follows the repo's existing tenant pattern: a second platform
    on its own store, exactly as test_m79_voice_runtime::test_tenant_isolation
    does. The point is that neither the terminal call nor reconciliation can
    reach across that boundary."""

    @staticmethod
    def _other_tenant(tmp_path):
        other = reset_platform_for_tests(tmp_path / "r21-other.db")
        boot = other.bootstrap_owner_secure(
            email="r21-other@local", name="Other", password="R21OtherPass1!"
        )
        other_ctx = other.require_context(boot["token"])
        return other, other_ctx, VoiceSessionManager(other.store, speech_service=None)

    def test_one_user_cannot_finish_another_users_session(self, platform, tmp_path):
        _, ctx, runtime = platform
        sid = _open(runtime, ctx)
        _other, other_ctx, other_runtime = self._other_tenant(tmp_path)
        with pytest.raises(PlatformContextError) as excinfo:
            other_runtime.finish_session(other_ctx, sid)
        assert excinfo.value.code == "NOT_FOUND"
        assert _state(runtime, ctx, sid) == ConversationState.LISTENING.value

    def test_reconciliation_never_touches_another_users_session(self, platform, tmp_path):
        _, ctx, runtime = platform
        victim = _open(runtime, ctx)
        _age(runtime, ctx, victim, ABANDONED_SESSION_IDLE_SECONDS + 60)

        _other, other_ctx, other_runtime = self._other_tenant(tmp_path)
        # Opening a session there runs reconciliation for that caller only.
        other_runtime.create_session(other_ctx, {"input_mode": "toggle"})

        assert _state(runtime, ctx, victim) == ConversationState.LISTENING.value

    def test_finishing_an_unknown_session_is_refused(self, platform):
        _, ctx, runtime = platform
        with pytest.raises(PlatformContextError) as excinfo:
            runtime.finish_session(ctx, "vses_does_not_exist")
        assert excinfo.value.code == "NOT_FOUND"


class TestNoAuthorityChange:
    def test_the_per_user_budget_is_unchanged(self):
        assert MAX_SESSIONS_PER_USER == 8, "R2.1 must not raise or remove the cap"

    def test_reconciliation_only_moves_sessions_to_finished(self, platform):
        _, ctx, runtime = platform
        sid = _open(runtime, ctx)
        _age(runtime, ctx, sid, ABANDONED_SESSION_IDLE_SECONDS + 60)
        before = len(runtime.list_sessions(ctx))
        _open(runtime, ctx)
        after = len(runtime.list_sessions(ctx))
        assert after == before + 1, "reconciliation adds no rows and removes none"
        assert _state(runtime, ctx, sid) == ConversationState.FINISHED.value
