"""Saathi Chat (M8) test suite — store, engine pipeline, gateway integration,
memory/RAG, tools, agents, checkpoints/recovery, search, API, streaming,
performance. LLM is injected (no network); the gateway path is the REAL
ExecutionGateway pipeline."""
import json
import time

import pytest

from saathi.chat.store import ChatStore
from saathi.chat.engine import ChatEngine, AGENT_ROLES


@pytest.fixture
def store(tmp_path):
    return ChatStore(tmp_path / "chat.db")


@pytest.fixture
def engine(store):
    return ChatEngine(store, llm_fn=lambda p, s: {
        "text": f"reply({p[-40:]})", "provider": "test-llm", "tokens": 7})


@pytest.fixture
def conv(store):
    return store.create_conversation(title="t")


# ── Layer 1: conversation engine ───────────────────────────────────────────
def test_conversation_lifecycle(store):
    c = store.create_conversation(title="alpha", folder="work", tags=["x"])
    assert c["id"] and c["title"] == "alpha" and c["tags"] == ["x"]
    store.rename(c["id"], "beta")
    store.pin(c["id"])
    store.archive(c["id"])
    got = store.get_conversation(c["id"])
    assert got["title"] == "beta" and got["pinned"] and got["archived"]
    store.delete(c["id"])
    assert store.get_conversation(c["id"])["deleted"]
    assert not store.list_conversations()  # hidden when deleted
    store.restore(c["id"])
    restored = store.get_conversation(c["id"])
    assert not restored["deleted"] and not restored["archived"]


def test_folders_favorites_and_filters(store):
    a = store.create_conversation(title="a", folder="f1")
    store.create_conversation(title="b", folder="f2")
    store.update_conversation(a["id"], favorite=True)
    assert [c["title"] for c in store.list_conversations(folder="f1")] == ["a"]
    assert store.get_conversation(a["id"])["favorite"] is True


def test_search_titles_and_content(store, engine):
    c = store.create_conversation(title="quarterly revenue planning")
    engine.send(c["id"], "discuss the yeti mascot budget")
    assert any(r["id"] == c["id"] for r in store.search("quarterly"))
    assert any(r["id"] == c["id"] for r in store.search("mascot"))
    assert store.search("nonexistentterm_zz") == []


# ── Layer 2: message engine ────────────────────────────────────────────────
def test_edit_keeps_version_history(store, conv):
    m = store.add_message(conv["id"], "user", "v1")
    m2 = store.edit_message(m["id"], "v2")
    versions = store.message_versions(m2["id"])
    assert [v["content"] for v in versions] == ["v1", "v2"]
    visible = store.list_messages(conv["id"])
    assert [v["content"] for v in visible] == ["v2"]  # superseded hidden


def test_regenerate_produces_new_assistant_message(engine, store, conv):
    r1 = engine.send(conv["id"], "first question")
    r2 = engine.regenerate(conv["id"], r1.message["id"])
    assert r2.message["id"] != r1.message["id"]
    assert r2.message["role"] == "assistant"


# ── Layer 3: gateway integration ───────────────────────────────────────────
def test_send_routes_through_execution_gateway(engine, store, conv):
    r = engine.send(conv["id"], "hello world")
    assert r.execution["status"] == "success"
    assert r.execution["intent_id"].startswith("chat-")
    assert r.execution["provider"] == "test-llm"
    # execution row persisted + joined to conversation
    execs = store.list_executions(conv["id"])
    assert len(execs) == 1 and execs[0]["intent_id"] == r.execution["intent_id"]


def test_llm_failure_yields_honest_error_not_fabrication(store, conv):
    def boom(p, s):
        raise RuntimeError("provider down")
    eng = ChatEngine(store, llm_fn=boom)
    r = eng.send(conv["id"], "hi")
    assert r.message["status"] == "error"
    assert "not executed" in r.message["content"]


# ── Layer 4: persistence / crash recovery / checkpoints ────────────────────
def test_persistence_survives_reopen(tmp_path, conv=None):
    p = tmp_path / "c.db"
    st1 = ChatStore(p)
    c = st1.create_conversation(title="durable")
    st1.add_message(c["id"], "user", "survive me")
    st2 = ChatStore(p)  # simulated restart
    assert st2.get_conversation(c["id"])["title"] == "durable"
    assert st2.list_messages(c["id"])[0]["content"] == "survive me"


def test_checkpoint_restore_previous_state(store, conv):
    store.add_message(conv["id"], "user", "keep")
    ck = store.create_checkpoint(conv["id"], "before-mess")
    store.add_message(conv["id"], "user", "discard-1")
    store.add_message(conv["id"], "user", "discard-2")
    out = store.restore_checkpoint(ck["id"])
    assert out["restored"]
    assert [m["content"] for m in store.list_messages(conv["id"])] == ["keep"]


def test_auto_checkpoint_every_eight_messages(engine, store, conv):
    for i in range(4):  # 4 sends = 8 messages
        engine.send(conv["id"], f"msg {i}")
    assert len(store.list_checkpoints(conv["id"])) >= 1


def test_auto_title_and_summary(engine, store):
    c = store.create_conversation()
    engine.send(c["id"], "Plan the pielts launch for next month please")
    got = store.get_conversation(c["id"])
    assert got["title"].startswith("Plan the pielts launch")
    assert got["summary"]


# ── Layer 5: memory retrieval ──────────────────────────────────────────────
def test_memory_links_related_conversations(engine, store):
    old = store.create_conversation(title="pielts marketing strategy")
    store.add_message(old["id"], "user", "pielts marketing strategy details")
    new = store.create_conversation(title="n")
    engine.send(new["id"], "what was the pielts marketing strategy?")
    links = store.list_memory_links(new["id"])
    assert any(l["memory_kind"] == "conversation" and l["memory_ref"] == old["id"]
               for l in links)


# ── Layer 6: knowledge / RAG / citations ───────────────────────────────────
def test_rag_over_attachment_with_citations(engine, store, conv, tmp_path):
    doc = tmp_path / "notes.md"
    doc.write_text("The cafeteria margin target is thirty percent. "
                   "Momentum trading remains the primary strategy. " * 20)
    store.add_attachment(conv["id"], kind="markdown", name="notes.md",
                         path=str(doc))
    r = engine.send(conv["id"], "what is the cafeteria margin target strategy?")
    assert r.citations, "expected chunk citations from the attachment"
    assert r.citations[0]["source"] == "notes.md"
    saved = store.list_citations(r.message["id"])
    assert saved and saved[0]["chunk_ref"]


def test_rag_ignores_missing_files(engine, store, conv):
    store.add_attachment(conv["id"], kind="text", name="ghost.txt",
                         path="/nonexistent/ghost.txt")
    r = engine.send(conv["id"], "anything about ghosts?")
    assert r.message["role"] == "assistant"  # degraded, not crashed


# ── Layer 7: tools through the gateway ─────────────────────────────────────
def test_tool_call_via_gateway(engine, store, conv):
    m = store.add_message(conv["id"], "assistant", "using tool")
    out = engine.call_tool(conv["id"], m["id"], "local-llm-inference",
                           {"prompt": "hi", "model": "auto"})
    assert out["status"] == "success"
    tools = store.list_tools(m["id"])
    assert tools[0]["status"] == "success" and tools[0]["tool"] == "local-llm-inference"


def test_unknown_tool_blocked_not_faked(engine, store, conv):
    m = store.add_message(conv["id"], "assistant", "x")
    out = engine.call_tool(conv["id"], m["id"], "gmail-send", {"to": "ram"})
    assert out["status"] == "blocked"
    rec = store.list_tools(m["id"])[0]
    assert rec["status"] == "blocked" and "not executed" in rec["result"]


# ── Layer 8: projects ──────────────────────────────────────────────────────
def test_project_context_included(store, tmp_path):
    seen = {}
    def spy(p, s):
        seen["system"] = s
        return {"text": "ok", "provider": "t", "tokens": 1}
    eng = ChatEngine(store, llm_fn=spy)
    store.add_project_ref("proj-pielts", kind="repository", ref="~/Saathi/apps/pielts")
    c = store.create_conversation(project_id="proj-pielts")
    eng.send(c["id"], "status?")
    assert "proj-pielts" in seen["system"]
    assert "repository" in seen["system"]


def test_project_switch_changes_context(store):
    seen = {}
    def spy(p, s):
        seen["system"] = s
        return {"text": "ok", "provider": "t", "tokens": 1}
    eng = ChatEngine(store, llm_fn=spy)
    c = store.create_conversation(project_id="proj-a")
    eng.send(c["id"], "x")
    assert "proj-a" in seen["system"]
    store.update_conversation(c["id"], project_id="proj-b")
    eng.send(c["id"], "y")
    assert "proj-b" in seen["system"]


# ── Layer 9: agents ────────────────────────────────────────────────────────
def test_agent_roles_available():
    assert {"planner", "researcher", "coder", "reviewer",
            "architect", "writer", "ceo"} <= set(AGENT_ROLES)


def test_agent_run_recorded(engine, store, conv):
    out = engine.run_agent(conv["id"], "planner", "plan the week")
    assert out["status"] == "done"
    runs = store.list_agent_runs(conv["id"])
    assert runs[0]["agent"] == "planner" and runs[0]["status"] == "done"


def test_agent_delegation_chain(engine, store, conv):
    engine.run_agent(conv["id"], "planner", "plan it")
    engine.delegate(conv["id"], "planner", "coder", "implement step 1")
    runs = store.list_agent_runs(conv["id"])
    coder = [r for r in runs if r["agent"] == "coder"][0]
    assert coder["delegated_by"] == "planner"


def test_agent_uses_role_system_prompt(store, conv):
    seen = {}
    def spy(p, s):
        seen["system"] = s
        return {"text": "ok", "provider": "t", "tokens": 1}
    ChatEngine(store, llm_fn=spy).send(conv["id"], "review this", agent="reviewer")
    assert "Reviewer" in seen["system"]


# ── Layer 10: performance ──────────────────────────────────────────────────
def test_large_history_pagination_fast(store):
    c = store.create_conversation(title="big")
    for i in range(300):
        store.add_message(c["id"], "user", f"m{i}")
    t0 = time.monotonic()
    page = store.list_messages(c["id"], limit=50, offset=200)
    dt = time.monotonic() - t0
    assert len(page) == 50 and page[0]["content"] == "m200"
    assert dt < 0.5, f"pagination too slow: {dt:.3f}s"


def test_token_accounting_accumulates(engine, store, conv):
    engine.send(conv["id"], "one")
    engine.send(conv["id"], "two")
    got = store.get_conversation(conv["id"])
    assert got["tokens_out"] > 0 and got["tokens_in"] > 0


# ── API layer ──────────────────────────────────────────────────────────────
def test_api_requires_auth():
    from fastapi.testclient import TestClient
    from saathi.server import app
    c = TestClient(app)
    assert c.get("/api/v1/chat/conversations").status_code == 401


def test_api_handlers_direct(store, monkeypatch):
    """Exercise route handlers with the engine/store injected."""
    from saathi.chat import api as chat_api
    eng = ChatEngine(store, llm_fn=lambda p, s: {"text": "api reply",
                                                 "provider": "t", "tokens": 1})
    monkeypatch.setattr(chat_api, "default_store", lambda: store)
    monkeypatch.setattr(chat_api, "default_engine", lambda: eng)

    conv = chat_api.create_conversation(chat_api.CreateConversation(title="api"))
    out = chat_api.send_message(conv["id"], chat_api.SendMessage(text="hello"))
    assert out["message"]["content"] == "api reply"
    got = chat_api.get_conversation(conv["id"])
    assert len(got["messages"]) == 2 and got["executions"]
    assert chat_api.search("hello")["results"]
    ck = chat_api.create_checkpoint(conv["id"], label="L")
    assert chat_api.restore_checkpoint(ck["id"])["restored"]
    agents = chat_api.agents()["agents"]
    assert any(a["name"] == "planner" for a in agents)


def test_api_streaming_sse(store, monkeypatch):
    from saathi.chat import api as chat_api
    eng = ChatEngine(store, llm_fn=lambda p, s: {
        "text": "streamed words arrive in order here", "provider": "t", "tokens": 1})
    monkeypatch.setattr(chat_api, "default_store", lambda: store)
    monkeypatch.setattr(chat_api, "default_engine", lambda: eng)
    conv = chat_api.create_conversation(chat_api.CreateConversation(title="s"))
    resp = chat_api.send_message(conv["id"],
                                 chat_api.SendMessage(text="go", stream=True))

    async def _drain(r):
        chunks = []
        async for chunk in r.body_iterator:
            chunks.append(chunk if isinstance(chunk, str) else chunk.decode())
        return "".join(chunks)

    import asyncio
    body = asyncio.run(_drain(resp))
    frames = [json.loads(l.removeprefix("data: "))
              for l in body.splitlines() if l.startswith("data: ")]
    events = [f["event"] for f in frames]
    assert events[0] == "start" and events[-1] == "done"
    text = "".join(f.get("text", "") for f in frames if f["event"] == "delta")
    assert "streamed words" in text
