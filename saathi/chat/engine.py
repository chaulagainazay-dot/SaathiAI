"""Saathi Chat engine — the send pipeline and every chat capability (M8).

Pipeline for one message:
  user text → memory retrieval (Layer 5) → knowledge/RAG (Layer 6)
  → context assembly (project-aware, Layer 8) → ToolIntent
  → ExecutionGateway (validate/authorize/risk/approve/queue — Layer 3)
  → ChatLLMAdapter (real multi-provider llm.generate) → sanitize → evidence
  → persist message + execution record + citations + auto-summary (Layer 4)

Models are NEVER called directly by the API layer: every inference travels
through the ExecutionGateway pipeline and is recorded as an execution row.
Tool calls (Layer 7) are ToolIntents through the same gateway. Agents
(Layer 9) are role-prompted runs that can delegate to each other, each run
recorded in agent_run.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Optional

from saathi.chat.store import ChatStore, default_store

logger = logging.getLogger(__name__)

# ── LLM bridge ──────────────────────────────────────────────────────────────
LLMFn = Callable[[str, str], dict]
# signature: (prompt, system) -> {"text": str, "provider": str, "tokens": int}


def _default_llm(prompt: str, system: str) -> dict:
    """Real multi-provider call via the Model Router (Anthropic/OpenAI/DeepSeek/
    Qwen/GLM/Groq/Gemini/Ollama…). Raises if no provider is available — the
    engine converts that into an honest error message, never a fabricated reply."""
    from saathi import llm as llm_mod
    from saathi.model_router import ModelLabel
    res = llm_mod.generate(ModelLabel.STANDARD, prompt, system=system)
    return {"text": res.text, "provider": res.provider,
            "tokens": getattr(res, "tokens", 0) or 0}


class ChatLLMAdapter:
    """ExecutionGateway adapter wrapping the Model Router for chat inference."""

    def __init__(self, llm_fn: LLMFn):
        self.llm_fn = llm_fn

    async def execute(self, intent) -> "Any":
        from saathi.execution.results import ExecutionResult, ExecutionStatus
        import time as _t
        t0 = _t.monotonic()
        p = intent.parameters
        out = self.llm_fn(p.get("prompt", ""), p.get("system", ""))
        return ExecutionResult(
            status=ExecutionStatus.SUCCESS,
            data={"text": out.get("text", ""), "provider": out.get("provider", ""),
                  "tokens": out.get("tokens", 0)},
            cost_usd=0.0, duration_sec=round(_t.monotonic() - t0, 3),
            connector_trace=[f"chat-llm:{out.get('provider', 'unknown')}"])


AGENT_ROLES: dict[str, str] = {
    "planner": "You are the Planner. Break the objective into a short, ordered, actionable plan.",
    "researcher": "You are the Researcher. Gather and synthesize the relevant facts, citing sources you were given.",
    "coder": "You are the Coder. Produce minimal, correct, well-tested code for the task.",
    "reviewer": "You are the Reviewer. Critically review the given work; list defects and concrete fixes.",
    "architect": "You are the Architect. Design the structure: components, boundaries, data flow, trade-offs.",
    "writer": "You are the Writer. Produce clear, concise prose for the requested audience.",
    "ceo": "You are the CEO advisor. Prioritize by business impact for Ajay's dream target and current missions.",
}


@dataclass
class SendResult:
    message: dict
    execution: dict
    memory_links: list
    citations: list


class ChatEngine:
    """All chat operations over a ChatStore + the ExecutionGateway."""

    def __init__(self, store: ChatStore | None = None,
                 llm_fn: LLMFn | None = None):
        self.store = store or default_store()
        self.llm_fn = llm_fn or _default_llm
        self._system = None  # lazy SaathiExecutionSystem

    # ── gateway wiring (Layer 3) ──────────────────────────────────────────
    def _execution_system(self):
        if self._system is None:
            from saathi.execution.integration import SaathiExecutionSystem
            from saathi.execution.queue.memory import MemoryQueue
            self._system = SaathiExecutionSystem(MemoryQueue())
            # register the chat adapter as a ModelGateway provider so chat
            # inference is a first-class, gateway-audited path
            self._system.model_gateway.providers["chat-llm"] = ChatLLMAdapter(self.llm_fn)
        return self._system

    def _run_gateway(self, cid: str, prompt: str, system: str) -> tuple[dict, dict]:
        """Run one inference through the full gateway pipeline.

        Returns (result_data, execution_meta). Raises nothing — failures come
        back as honest error results.
        """
        import uuid
        from saathi.execution import ToolIntent, ExecutionContext
        sysm = self._execution_system()
        intent = ToolIntent(
            intent_id=f"chat-{uuid.uuid4().hex[:12]}",
            operation="local-llm-inference",
            business_unit="saathi-chat",
            actor_id="user:ajay",
            parameters={"prompt": prompt, "system": system, "model": "auto"},
            metadata={"data_sensitivity": "internal", "conversation": cid},
        )
        ctx = ExecutionContext(actor_id="user:ajay", business_unit="saathi-chat",
                               timestamp=datetime.utcnow(),
                               current_time=datetime.utcnow())
        # route to the chat adapter
        policy = {"provider_choice": "chat-llm", "fallback_chain": [],
                  "data_sensitivity": "internal"}
        orig = sysm._get_model_policy
        sysm._get_model_policy = lambda i: policy
        try:
            result = asyncio.run(sysm.execute_intent(intent, ctx))
        finally:
            sysm._get_model_policy = orig
        data = result.data or {}
        meta = {"intent_id": intent.intent_id,
                "status": getattr(result.status, "value", str(result.status)),
                "provider": data.get("provider", ""),
                "cost_usd": result.cost_usd or 0.0,
                "duration_sec": result.duration_sec or 0.0,
                "error": result.error or ""}
        return data, meta

    # ── Layer 5: memory retrieval ─────────────────────────────────────────
    def _retrieve_memory(self, cid: str, text: str) -> list[dict]:
        """Automatic pre-execution memory retrieval: related conversations +
        mission knowledge. Failures degrade to empty — never block the send."""
        links: list[dict] = []
        try:  # related conversations (semantic-lite: keyword content search)
            import re
            terms = sorted({w.lower() for w in re.findall(r"\w{5,}", text)},
                           key=len, reverse=True)[:3]
            seen: set[str] = set()
            for term in terms:
                for conv in self.store.search(term, limit=3):
                    if conv["id"] != cid and conv["id"] not in seen:
                        seen.add(conv["id"])
                        links.append(self.store.add_memory_link(
                            cid, memory_kind="conversation",
                            memory_ref=conv["id"], relevance=0.5))
        except Exception:
            pass
        try:  # mission/business knowledge nodes
            from saathi.missions.store import default_store as m_store
            from saathi.missions.knowledge import default_graph
            g = default_graph()
            for m in m_store().list(status="active")[:2]:
                for n in (g.nodes(m["id"]) or [])[:2]:
                    links.append(self.store.add_memory_link(
                        cid, memory_kind="business",
                        memory_ref=f"mission:{m['id']}:node:{n.get('id', '')}",
                        relevance=0.4))
        except Exception:
            pass
        return links

    # ── Layer 6: knowledge / RAG over attachments ─────────────────────────
    def _retrieve_knowledge(self, cid: str, text: str) -> tuple[str, list[dict]]:
        """Naive-but-real RAG: score attachment text chunks by term overlap,
        return context block + citation records."""
        import re
        from pathlib import Path
        terms = {w.lower() for w in re.findall(r"\w{4,}", text)}
        chunks: list[tuple[float, str, str, str]] = []  # (score, source, ref, chunk)
        for att in self.store.list_attachments(cid):
            p = Path(att["path"])
            if not p.exists() or att["kind"] not in ("text", "markdown", "code", "pdf-text"):
                continue
            try:
                body = p.read_text(errors="replace")[:200_000]
            except Exception:
                continue
            for i in range(0, len(body), 1200):
                chunk = body[i:i + 1200]
                words = {w.lower() for w in re.findall(r"\w{4,}", chunk)}
                score = len(terms & words) / (len(terms) or 1)
                if score > 0.08:
                    chunks.append((score, att["name"], f"{att['id']}#c{i // 1200}", chunk))
        chunks.sort(reverse=True)
        top = chunks[:4]
        context = "\n\n".join(f"[{ref}] from {src}:\n{ch}" for _, src, ref, ch in top)
        citations = [{"source": src, "chunk_ref": ref, "quote": ch[:160]}
                     for _, src, ref, ch in top]
        return context, citations

    # ── Layer 8: project context ──────────────────────────────────────────
    def _project_context(self, conv: dict) -> str:
        pid = conv.get("project_id") or ""
        if not pid:
            return ""
        refs = self.store.list_project_refs(pid)
        if not refs:
            return f"Active project: {pid}."
        lines = [f"- {r['kind']}: {r['ref']}" for r in refs[:10]]
        return f"Active project: {pid}. Project resources:\n" + "\n".join(lines)

    # ── the send pipeline ─────────────────────────────────────────────────
    def send(self, cid: str, text: str, *, system: str = "",
             agent: str = "") -> SendResult:
        conv = self.store.get_conversation(cid)
        if not conv or conv["deleted"]:
            raise KeyError(f"conversation not found: {cid}")

        user_msg = self.store.add_message(cid, "user", text)

        # Layers 5+6+8 — automatic pre-execution context
        links = self._retrieve_memory(cid, text)
        knowledge, citation_specs = self._retrieve_knowledge(cid, text)
        project = self._project_context(conv)

        history = self.store.list_messages(cid, limit=20)
        convo = "\n".join(f"{m['role']}: {m['content'][:500]}"
                          for m in history[-12:-1])
        base_system = (AGENT_ROLES.get(agent, "") or system
                       or "You are Saathi, Ajay's AI operating system. Be direct and useful.")
        parts = [base_system]
        if project:
            parts.append(project)
        if conv.get("summary"):
            parts.append(f"Conversation summary so far: {conv['summary']}")
        if knowledge:
            parts.append("Relevant knowledge (cite [chunk refs] you use):\n" + knowledge)
        full_system = "\n\n".join(parts)
        prompt = (convo + "\nuser: " + text) if convo else text

        # Layer 3 — through the gateway, never direct
        data, meta = self._run_gateway(cid, prompt, full_system)
        if meta["status"] != "success" or not data.get("text"):
            err = meta.get("error") or "no provider available"
            reply = self.store.add_message(
                cid, "assistant",
                f"The task was not executed — model inference failed: {err}",
                status="error", parent_id=user_msg["id"])
        else:
            reply = self.store.add_message(
                cid, "assistant", data["text"], model=data.get("provider", ""),
                tokens=data.get("tokens", 0), parent_id=user_msg["id"])
            self.store.add_tokens(cid, tokens_in=len(prompt) // 4,
                                  tokens_out=data.get("tokens", 0) or len(data["text"]) // 4)

        execution = self.store.record_execution(
            reply["id"], intent_id=meta["intent_id"], provider=meta["provider"],
            status=meta["status"], cost_usd=meta["cost_usd"],
            duration_sec=meta["duration_sec"])
        citations = [self.store.add_citation(reply["id"], **spec)
                     for spec in citation_specs]

        # Layer 4 — rolling auto-summary + periodic checkpoint
        msgs = self.store.list_messages(cid)
        if len(msgs) % 8 == 0:
            self.store.create_checkpoint(cid, label=f"auto@{len(msgs)}msgs")
        first_user = next((m for m in msgs if m["role"] == "user"), None)
        if first_user and not conv.get("title"):
            self.store.rename(cid, first_user["content"][:60])
        self.store.add_summary(
            cid, f"{len(msgs)} messages; last topic: {text[:120]}",
            upto_message_id=reply["id"])

        return SendResult(message=reply, execution=execution,
                          memory_links=links, citations=citations)

    # ── Layer 2 extras ────────────────────────────────────────────────────
    def regenerate(self, cid: str, message_id: str) -> SendResult:
        """Re-run the assistant turn for the user message that produced it."""
        msg = self.store.get_message(message_id)
        if not msg:
            raise KeyError(message_id)
        parent = self.store.get_message(msg["parent_id"]) if msg["parent_id"] else None
        source = parent if (parent and parent["role"] == "user") else msg
        result = self.send(cid, f"(regenerate) {source['content']}")
        return result

    def edit_and_resend(self, cid: str, message_id: str, new_text: str) -> SendResult:
        self.store.edit_message(message_id, new_text)
        return self.send(cid, new_text)

    # ── Layer 7: tool calling through the gateway ─────────────────────────
    def call_tool(self, cid: str, message_id: str, tool: str,
                  args: dict | None = None) -> dict:
        """Execute a tool as a ToolIntent through the ExecutionGateway.

        Only tools with a registered gateway operation run; everything else is
        recorded as blocked — never silently faked.
        """
        import uuid
        from saathi.execution import ToolIntent, ExecutionContext
        args = args or {}
        rec = self.store.record_tool(message_id, tool=tool, args=args)
        known = {"video-generation", "local-llm-inference"}
        if tool not in known:
            self.store.finish_tool(rec["id"], status="blocked",
                                   result=f"tool '{tool}' has no gateway operation; not executed")
            return {**rec, "status": "blocked"}
        sysm = self._execution_system()
        intent = ToolIntent(intent_id=f"tool-{uuid.uuid4().hex[:12]}", operation=tool,
                            business_unit="saathi-chat", actor_id="user:ajay",
                            parameters=args, metadata={"conversation": cid})
        ctx = ExecutionContext(actor_id="user:ajay", business_unit="saathi-chat",
                               timestamp=datetime.utcnow(), current_time=datetime.utcnow())
        try:
            result = asyncio.run(sysm.execute_intent(intent, ctx))
            status = getattr(result.status, "value", "failed")
            self.store.finish_tool(rec["id"], status=status,
                                   result=str(result.data or "")[:2000])
            return {**rec, "status": status, "intent_id": intent.intent_id}
        except Exception as exc:
            self.store.finish_tool(rec["id"], status="failed", result=repr(exc)[:500])
            return {**rec, "status": "failed"}

    # ── Layer 9: agent collaboration ──────────────────────────────────────
    def run_agent(self, cid: str, agent: str, task: str, *,
                  delegated_by: str = "") -> dict:
        if agent not in AGENT_ROLES:
            raise ValueError(f"unknown agent: {agent}")
        run = self.store.record_agent_run(cid, agent=agent, task=task,
                                          delegated_by=delegated_by)
        try:
            result = self.send(cid, task, agent=agent)
            ok = result.message["status"] != "error"
            self.store.finish_agent_run(run["id"],
                                        status="done" if ok else "failed",
                                        result_message_id=result.message["id"])
            return {**run, "status": "done" if ok else "failed",
                    "message": result.message}
        except Exception as exc:
            self.store.finish_agent_run(run["id"], status="failed")
            return {**run, "status": "failed", "error": repr(exc)[:300]}

    def delegate(self, cid: str, from_agent: str, to_agent: str, task: str) -> dict:
        """One agent hands a subtask to another; both runs are recorded."""
        return self.run_agent(cid, to_agent, task, delegated_by=from_agent)


_default_engine: ChatEngine | None = None


def default_engine() -> ChatEngine:
    global _default_engine
    if _default_engine is None:
        _default_engine = ChatEngine()
    return _default_engine
