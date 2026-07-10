"""ModelGateway: Multi-provider LLM orchestrator."""

from typing import Optional, Dict, Any
from enum import Enum
import logging

from saathi.execution.toolintent import ToolIntent
from saathi.execution.results import ExecutionResult
from saathi.execution.adapters.openjarvis_adapter import OpenJarvisAdapter

logger = logging.getLogger(__name__)


class LLMProvider(Enum):
    """LLM provider options."""
    OLLAMA = "ollama"           # Local Ollama (free, private, offline)
    OPENJARVIS = "openjarvis"   # OpenJarvis wrapper (local + cloud fallback)
    CLAUDE = "claude"           # Claude API (high quality)
    OPENAI = "openai"           # OpenAI API
    GEMINI = "gemini"           # Google Gemini
    GROQ = "groq"              # Groq (fast, cheap)


class ModelGateway:
    """Routes LLM inference to best provider based on policy.

    Policy engine decides based on:
    - Data sensitivity (private → local)
    - Latency requirement (sub-second → Groq/Ollama)
    - Cost constraint (budget → Ollama/Groq)
    - Quality (high → Claude)
    - Cloud availability (offline → Ollama only)
    - Provider health
    """

    def __init__(self):
        self.openjarvis = OpenJarvisAdapter()
        self.providers = {
            "ollama": self.openjarvis,  # Local via OpenJarvis
            "openjarvis": self.openjarvis,
            # TODO: Initialize other providers
        }

    async def route_and_execute(self, intent: ToolIntent, policy_decision: Dict[str, Any]) -> ExecutionResult:
        """Execute LLM inference per policy decision.

        policy_decision contains:
        - provider_choice: 'ollama' | 'openjarvis' | 'claude' | 'groq' | etc.
        - fallback_chain: list of fallback providers
        - max_latency_sec: deadline
        - data_sensitivity: 'public' | 'internal' | 'confidential'
        """
        provider = policy_decision.get("provider_choice", "openjarvis")
        fallback_chain = policy_decision.get("fallback_chain", [])
        data_sensitivity = policy_decision.get("data_sensitivity", "public")

        logger.info(f"ModelGateway routing: {intent.intent_id} → {provider}")

        # Privacy constraint: confidential data cannot use cloud
        if data_sensitivity == "confidential" and provider not in ("ollama", "openjarvis"):
            logger.warning("Confidential data cannot use cloud provider, forcing local")
            provider = "openjarvis"

        try:
            adapter = self.providers.get(provider)
            if adapter:
                return await adapter.execute(intent)
            else:
                # Unknown provider, try fallback
                return await self.execute_fallback(intent, fallback_chain)

        except Exception as e:
            logger.warning(f"Provider failed: {provider}, trying fallback: {e}")
            return await self.execute_fallback(intent, fallback_chain)

    async def execute_fallback(self, intent: ToolIntent, fallback_chain: list[str]) -> ExecutionResult:
        """Execute via fallback chain."""
        for fallback_provider in fallback_chain:
            logger.info(f"Trying fallback: {fallback_provider}")
            try:
                adapter = self.providers.get(fallback_provider)
                if adapter:
                    return await adapter.execute(intent)
            except Exception as e:
                logger.warning(f"Fallback {fallback_provider} failed: {e}")
                continue

        # Fallback to OpenJarvis (always available as last resort)
        logger.info("Falling back to OpenJarvis")
        return await self.openjarvis.execute(intent)
