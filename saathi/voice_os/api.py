"""M12 Voice OS API — /api/v1/voice/* (auth inherited from /api/v1 middleware).

HTTP/SSE chosen over WebSocket: the browser does STT/TTS client-side
(SpeechRecognition/SpeechSynthesis or MediaRecorder chunks), so the server
only needs request/response + one SSE stream for live session events —
no bidirectional low-latency channel is actually needed, per the audit.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from saathi.voice_os.store import default_store
from saathi.voice_os.bridge import VoiceBridge
from saathi.voice_os.models import SessionState
from saathi.voice_os import stt as stt_mod
from saathi.voice_os import tts as tts_mod

router = APIRouter(prefix="/api/v1/voice", tags=["voice"])


def _user(request: Request) -> str:
    # Mirrors the session-based identity already used elsewhere; voice has no
    # separate identity system. Falls back to a stable local dev identity.
    return getattr(request.state, "user_id", None) or "ajay"


class CreateSession(BaseModel):
    conversation_id: str = ""
    project_id: str = ""
    chat_mode: str = "solo"
    agent: str = ""
    strategy: str = ""
    settings: dict = {}


class SubmitTranscript(BaseModel):
    text: str


class ApprovalVoice(BaseModel):
    run_id: str
    approval_id: str
    approved: bool


class Preferences(BaseModel):
    settings: dict


@router.get("/providers")
def providers():
    return {"stt": stt_mod.provider_status(), "tts": tts_mod.provider_status()}


@router.get("/voices")
def voices():
    # Real local voices available via macOS `say -v ?` when present; degrade
    # honestly to a minimal default list otherwise (never fabricate a catalog).
    import shutil, subprocess
    if shutil.which("say"):
        try:
            out = subprocess.run(["say", "-v", "?"], capture_output=True, text=True,
                                 timeout=5).stdout
            names = [ln.split()[0] for ln in out.splitlines() if ln.strip()]
            return {"voices": names[:40], "source": "say"}
        except Exception:
            pass
    return {"voices": ["default"], "source": "fallback"}


@router.post("/sessions")
def create_session(req: CreateSession, request: Request):
    sid = default_store().create_session(
        user_id=_user(request), conversation_id=req.conversation_id,
        project_id=req.project_id, chat_mode=req.chat_mode, agent=req.agent,
        strategy=req.strategy, settings=req.settings)
    return {"session_id": sid}


@router.get("/sessions/{sid}")
def get_session(sid: str, request: Request):
    st = default_store()
    s = st.get_session(sid)
    if not s or s["user_id"] != _user(request):
        return {"error": "not found"}
    return {"session": s, "turns": st.list_turns(sid),
            "interruptions": st.interruptions(sid),
            "provider_events": st.provider_events(sid)}


@router.post("/sessions/{sid}/transition")
def transition(sid: str, state: str, request: Request):
    st = default_store()
    if not st.owns(sid, _user(request)):
        return {"error": "not found"}
    try:
        st.transition(sid, SessionState(state), actor=f"user:{_user(request)}")
        return {"session_id": sid, "state": state}
    except Exception as exc:
        return {"error": str(exc)}


@router.post("/sessions/{sid}/end")
def end_session(sid: str, request: Request):
    st = default_store()
    if not st.owns(sid, _user(request)):
        return {"error": "not found"}
    st.end_session(sid)
    return {"session_id": sid, "ended": True}


@router.post("/sessions/{sid}/turns")
def submit_turn(sid: str, req: SubmitTranscript, request: Request):
    """Final transcript in -> ChatEngine/Orchestrator out. Real execution."""
    st = default_store()
    if not st.owns(sid, _user(request)):
        return {"error": "not found"}
    bridge = VoiceBridge(st)
    try:
        out = bridge.submit_turn(sid, req.text, user_id=_user(request))
        return {"turn_id": out.turn_id, "status": out.status, "command": out.command,
                "assistant_text": out.assistant_text, "segments": out.segments,
                "chat_message_id": out.chat_message_id,
                "execution_id": out.execution_id, "agent_run_id": out.agent_run_id}
    except PermissionError:
        return {"error": "forbidden"}
    except (KeyError, RuntimeError) as exc:
        return {"error": str(exc)}


@router.post("/sessions/{sid}/interrupt")
def interrupt(sid: str, stop_latency_ms: float, request: Request):
    st = default_store()
    if not st.owns(sid, _user(request)):
        return {"error": "not found"}
    session = st.get_session(sid)
    st.record_interruption(sid, session.get("active_turn_id", ""), stop_latency_ms)
    return {"session_id": sid, "recorded": True}


@router.post("/sessions/{sid}/approve")
def approve_by_voice(sid: str, req: ApprovalVoice, request: Request):
    bridge = VoiceBridge(default_store())
    try:
        return bridge.resolve_approval_by_voice(
            sid, user_id=_user(request), run_id=req.run_id,
            approval_id=req.approval_id, approved=req.approved)
    except (PermissionError, KeyError) as exc:
        return {"error": str(exc)}


@router.get("/preferences")
def get_preferences(request: Request):
    return {"settings": default_store().get_preferences(_user(request))}


@router.put("/preferences")
def set_preferences(req: Preferences, request: Request):
    default_store().set_preferences(_user(request), req.settings)
    return {"saved": True}


@router.get("/sessions/{sid}/latency")
def latency(sid: str, request: Request):
    st = default_store()
    if not st.owns(sid, _user(request)):
        return {"error": "not found"}
    out = {}
    for t in st.list_turns(sid):
        out[t["id"]] = st.latencies(t["id"])
    return {"latency": out}


@router.get("/sessions/{sid}/events")
def events_stream(sid: str, request: Request):
    """SSE tail of session events — the one place bidirectional-feeling
    server->client push is genuinely needed; a plain GET stream suffices."""
    st = default_store()
    if not st.owns(sid, _user(request)):
        return {"error": "not found"}

    def _gen():
        session = st.get_session(sid)
        yield f"data: {json.dumps({'event': 'snapshot', 'state': session['state']})}\n\n"
    return StreamingResponse(_gen(), media_type="text/event-stream")
