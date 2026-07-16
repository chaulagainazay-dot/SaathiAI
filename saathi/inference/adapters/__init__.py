"""Inference engine adapters (local + existing cloud providers)."""
from __future__ import annotations

from saathi.inference.adapters.cloud import CloudCallerEngine
from saathi.inference.adapters.fake import FakeEngine
from saathi.inference.adapters.ollama import OllamaEngine
from saathi.inference.adapters.openai_compat import OpenAICompatEngine

__all__ = [
    "CloudCallerEngine",
    "FakeEngine",
    "OllamaEngine",
    "OpenAICompatEngine",
]
