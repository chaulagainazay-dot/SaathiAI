"""VideoProductionBackend: Dual-backend orchestrator for video generation."""

from typing import Optional, Dict, Any
from enum import Enum
import logging

from saathi.execution.toolintent import ToolIntent
from saathi.execution.results import ExecutionResult
from saathi.execution.adapters.claude_video_adapter import ClaudeVideoAdapter
from saathi.execution.adapters.openmontage_adapter import OpenMontageAdapter

logger = logging.getLogger(__name__)


class VideoBackend(Enum):
    """Video generation backend choice."""
    CLAUDE_TOOLKIT = "claude_toolkit"  # Fast, cheap, social
    OPENMONTAGE = "openmontage"        # Slow, expensive, production-quality


class VideoProductionBackend:
    """Routes video generation to best backend based on policy.

    Policy engine decides:
    - Urgency (critical → fast)
    - Budget (limited → cheap)
    - Quality (broadcast → production)
    - Character (yeti → animation)
    - Provider health

    Dual routing:
    - Claude Toolkit: 15-45 min, $0.01-0.30 (Baadar daily automation)
    - OpenMontage: 2-4 hours, $0.50-2.00 (Mr. Yeti campaigns)
    """

    def __init__(self):
        self.claude = ClaudeVideoAdapter()
        self.openmontage = OpenMontageAdapter()

    async def route_and_execute(self, intent: ToolIntent, policy_decision: Dict[str, Any]) -> ExecutionResult:
        """Execute video generation per policy decision.

        policy_decision contains:
        - backend_choice: 'claude_toolkit' | 'openmontage'
        - fallback_chain: list of fallback backends
        - max_cost_usd: budget constraint
        - approval_required: bool
        """
        backend = policy_decision.get("backend_choice", "claude_toolkit")
        fallback_chain = policy_decision.get("fallback_chain", [])

        logger.info(f"VideoProductionBackend routing: {intent.intent_id} → {backend}")

        try:
            if backend == VideoBackend.CLAUDE_TOOLKIT.value:
                return await self.claude.execute(intent)
            elif backend == VideoBackend.OPENMONTAGE.value:
                return await self.openmontage.execute(intent)
            else:
                # Unknown backend, try fallback
                return await self.execute_fallback(intent, fallback_chain)

        except Exception as e:
            logger.warning(f"Backend failed: {backend}, trying fallback: {e}")
            return await self.execute_fallback(intent, fallback_chain)

    async def execute_fallback(self, intent: ToolIntent, fallback_chain: list[str]) -> ExecutionResult:
        """Execute via fallback chain."""
        for fallback_backend in fallback_chain:
            logger.info(f"Trying fallback: {fallback_backend}")
            try:
                if fallback_backend == "claude_toolkit":
                    return await self.claude.execute(intent)
                elif fallback_backend == "openmontage":
                    return await self.openmontage.execute(intent)
            except Exception as e:
                logger.warning(f"Fallback {fallback_backend} failed: {e}")
                continue

        # All fallbacks exhausted
        raise Exception("All video backends exhausted")
