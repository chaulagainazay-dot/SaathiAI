"""Saathi Chat — the central intelligence interface of SaathiOS (M8).

Layers: conversation engine, message engine, ExecutionGateway-routed
inference, durable persistence with checkpoints, automatic memory retrieval,
attachment RAG with citations, gateway tool calling, project context, and
multi-agent collaboration.
"""
from saathi.chat.store import ChatStore, default_store
from saathi.chat.engine import ChatEngine, default_engine, AGENT_ROLES, SendResult

__all__ = ["ChatStore", "default_store", "ChatEngine", "default_engine",
           "AGENT_ROLES", "SendResult"]
