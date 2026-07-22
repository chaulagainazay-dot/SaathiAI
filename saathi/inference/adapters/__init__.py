"""Inference engine adapters (local + existing cloud providers)."""
from __future__ import annotations

from saathi.inference.adapters.cloud import CloudCallerEngine
from saathi.inference.adapters.fake import FakeEngine
from saathi.inference.adapters.ollama import OllamaEngine
from saathi.inference.adapters.openai_compat import OpenAICompatEngine

# M22 transport modules are importable but intentionally not re-exported as
# public product APIs — use llm.generate / chat_adapter / research tools.

__all__ = [
    "CloudCallerEngine",
    "FakeEngine",
    "OllamaEngine",
    "OpenAICompatEngine",
]
