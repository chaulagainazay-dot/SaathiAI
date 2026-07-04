"""Re-export shim — canonical home for LLM execution (`generate`).

Implementation currently lives in `saathi.llm`. New code imports from here.
"""
from saathi.llm import *  # noqa: F401,F403
from saathi.llm import generate, LLMResult, env_availability, DEFAULT_CALLERS

__all__ = ["generate", "LLMResult", "env_availability", "DEFAULT_CALLERS"]
