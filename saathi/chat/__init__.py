"""Saathi Chat — the central intelligence interface of SaathiOS (M8 + M23).

Layers: conversation engine, message engine, ExecutionGateway-routed
inference, durable persistence with checkpoints, automatic memory retrieval,
attachment RAG with citations, gateway tool calling, project context, and
multi-agent collaboration.

M23: production chat inference uses the canonical governed chat runtime
(``saathi.chat.runtime``) exclusively — no legacy provider sink.
"""
from saathi.chat.store import ChatStore, default_store
from saathi.chat.engine import ChatEngine, default_engine, AGENT_ROLES, SendResult

__all__ = ["ChatStore", "default_store", "ChatEngine", "default_engine",
           "AGENT_ROLES", "SendResult"]
