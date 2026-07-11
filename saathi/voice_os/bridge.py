"""M12 bridge — the ONLY place voice touches ChatEngine / Orchestrator.

Voice never calls a model provider or tool directly. Every turn resolves
through saathi.chat.engine.ChatEngine (Solo) or
ChatEngine.start_orchestration (Team, itself the M10 Orchestrator). Approval
resolution reuses saathi.agent_runtime.orchestrator.Orchestrator.approve — the
exact same ownership/expiry-checked path M10/M11 already enforce.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from saathi.voice_os.models import SessionState, ChatMode
from saathi.voice_os.store import VoiceStore
from saathi.voice_os.transcript import detect_command, detect_agent_switch, CommandMatch
from saathi.voice_os.segmentation import segment_for_speech


@dataclass
class TurnOutcome:
    turn_id: str
    assistant_text: str
    segments: list[str]
    chat_message_id: str = ""
    execution_id: str = ""
    agent_run_id: str = ""
    command: str = ""
    status: str = "ok"


class VoiceBridge:
    """Wires a voice session to the real Chat/Agent-Runtime stack.

    `chat_engine` and `orchestrator` are injected for deterministic testing;
    production defaults are the real singletons.
    """

    def __init__(self, store: VoiceStore | None = None, chat_engine=None,
                 orchestrator=None):
        self.store = store or VoiceStore()
        self._chat = chat_engine
        self._orch = orchestrator

    def _chat_engine(self):
        if self._chat is None:
            from saathi.chat.engine import default_engine
            self._chat = default_engine()
        return self._chat

    def _orchestrator(self):
        if self._orch is None:
            from saathi.agent_runtime.orchestrator import default_orchestrator
            self._orch = default_orchestrator()
        return self._orch

    # ── the canonical voice turn ────────────────────────────────────────────
    def submit_turn(self, session_id: str, transcript: str, *, user_id: str) -> TurnOutcome:
        """Final transcript -> ChatEngine (Solo) or start_orchestration (Team).

        Exactly one final user message per turn (transcript pipeline dedupes
        upstream). Voice commands short-circuit before any Chat call.
        """
        session = self.store.get_session(session_id)
        if not session:
            raise KeyError(session_id)
        if session["user_id"] != user_id:
            raise PermissionError("session does not belong to this user")
        if session["state"] in ("completed", "cancelled", "failed"):
            raise RuntimeError(f"cannot submit turn: session is {session['state']}")

        tid = self.store.create_turn(session_id, conversation_id=session["conversation_id"])
        t0 = time.monotonic()

        cmd = detect_command(transcript)
        if cmd:
            return self._handle_command(session, tid, cmd)

        agent_switch = detect_agent_switch(transcript)

        cid = session["conversation_id"]
        if not cid:
            cid = self._chat_engine().store.create_conversation(
                project_id=session["project_id"])["id"]
            self.store.set_conversation(session_id, cid)

        self.store.update_turn(tid, normalized_text=transcript)

        if session["chat_mode"] == ChatMode.TEAM.value:
            res = self._chat_engine().start_orchestration(
                cid, transcript, strategy=session.get("strategy", ""))
            text = res["outcome"].get("note", "") or \
                f"Team run {res['outcome']['state']}: {res['outcome'].get('tasks_done', 0)} tasks done."
            outcome = TurnOutcome(turn_id=tid, assistant_text=text,
                                  segments=segment_for_speech(text),
                                  agent_run_id=res["run_id"])
        else:
            agent = agent_switch or session.get("agent", "")
            r = self._chat_engine().send(cid, transcript, agent=agent)
            outcome = TurnOutcome(turn_id=tid, assistant_text=r.message["content"],
                                  segments=segment_for_speech(r.message["content"]),
                                  chat_message_id=r.message["id"],
                                  execution_id=r.execution.get("intent_id", ""))

        self.store.update_turn(tid, assistant_text=outcome.assistant_text,
                               chat_message_id=outcome.chat_message_id,
                               execution_id=outcome.execution_id,
                               agent_run_id=outcome.agent_run_id)
        self.store.finish_turn(tid)
        self.store.record_latency(tid, "turn_total_ms", (time.monotonic() - t0) * 1000)
        return outcome

    def _handle_command(self, session: dict, tid: str, cmd: CommandMatch) -> TurnOutcome:
        self.store.update_turn(tid, normalized_text=cmd.matched_phrase,
                               assistant_text=f"[command: {cmd.command}]")
        self.store.finish_turn(tid)
        return TurnOutcome(turn_id=tid, assistant_text="", segments=[],
                           command=cmd.command, status="command")

    # ── approval by voice — reuses the M10 approval store, never a shortcut ─
    def resolve_approval_by_voice(self, session_id: str, *, user_id: str,
                                  run_id: str, approval_id: str,
                                  approved: bool) -> dict:
        """Binds: authenticated user, active session ownership, unexpired
        approval, existing run/conversation — via the SAME Orchestrator.approve
        path the UI's Approve/Deny buttons call. No keyword-only shortcut."""
        session = self.store.get_session(session_id)
        if not session or session["user_id"] != user_id:
            raise PermissionError("session ownership check failed")
        orch = self._orchestrator()
        approval = orch.store.get_approval(approval_id)
        if not approval or approval["run_id"] != run_id:
            raise KeyError("approval not found for this run")
        result = orch.approve(run_id, approval_id, approved=approved,
                              actor=f"user:{user_id}")
        self.store.event(session_id, "voice.approval.resolved",
                         {"approval_id": approval_id, "status": result["status"]})
        return result
