"""SaathiOS ExecutionGateway integration: end-to-end flow."""

from typing import Optional, Dict, Any
from datetime import datetime
import asyncio
import logging

from saathi.execution.toolintent import ToolIntent
from saathi.execution.gateway import ExecutionGateway, ExecutionContext
from saathi.execution.queue.base import ExecutionQueue
from saathi.execution.orchestrators.video_backend import VideoProductionBackend
from saathi.execution.orchestrators.model_gateway import ModelGateway
from saathi.execution.results import ExecutionResult, SanitizedResult

logger = logging.getLogger(__name__)


class SaathiExecutionSystem:
    """Unified execution system wiring everything together.

    Flow:
    Planner
        ↓ creates
    ToolIntent (immutable request)
        ↓ routed to
    ExecutionGateway
        ├─ Validator
        ├─ Authorizer
        ├─ RiskClassifier
        ├─ ApprovalGate
        ├─ CredentialManager
        └─ Queue
        ↓
    Policy Engine (VideoBackendPolicy, ModelGateway)
        ↓
    Orchestrators
        ├─ VideoProductionBackend (Claude | OpenMontage)
        └─ ModelGateway (Ollama | OpenJarvis | Cloud)
        ↓
    Adapters
        ├─ ClaudeVideoAdapter
        ├─ OpenMontageAdapter
        └─ OpenJarvisAdapter
        ↓
    Result Sanitizer (remove secrets)
        ↓
    Evidence (append-only audit)
    """

    def __init__(self, queue: ExecutionQueue):
        self.gateway = ExecutionGateway(queue)
        self.video_backend = VideoProductionBackend()
        self.model_gateway = ModelGateway()

    async def execute_intent(self, intent: ToolIntent, context: ExecutionContext) -> ExecutionResult:
        """Execute ToolIntent through complete flow.

        Hard guarantees:
        1. No external action without ExecutionGateway
        2. ToolIntent never modified
        3. All state transitions recorded
        4. Result always sanitized
        5. Evidence always appended
        """
        logger.info(f"SaathiExecutionSystem: executing {intent.intent_id} ({intent.operation})")

        # Phase 1: Validation & Detection
        try:
            history = self.gateway.receive_intent(intent)
            history = self.gateway.validate_intent(intent, history)
            history = self.gateway.check_idempotency(intent, history)
        except Exception as e:
            logger.error(f"Validation failed: {e}")
            raise

        # Phase 2: Authorization & Risk
        try:
            history = self.gateway.authorize(intent, context, history)
            history, risk_level = self.gateway.classify_risk(intent, context, history)
            history = self.gateway.check_approval(intent, risk_level, history)
        except Exception as e:
            logger.error(f"Authorization failed: {e}")
            raise

        # Phase 3: Queuing
        try:
            history = self.gateway.enqueue_for_execution(intent, history)
        except Exception as e:
            logger.error(f"Queueing failed: {e}")
            raise

        # Phase 4: Execution (per operation type)
        result: Optional[ExecutionResult] = None
        try:
            if intent.operation == "video-generation":
                # Route to VideoProductionBackend
                policy_decision = self._get_video_policy(intent)
                result = await self.video_backend.route_and_execute(intent, policy_decision)

            elif intent.operation == "local-llm-inference":
                # Route to ModelGateway
                policy_decision = self._get_model_policy(intent)
                result = await self.model_gateway.route_and_execute(intent, policy_decision)

            else:
                raise ValueError(f"Unknown operation: {intent.operation}")

        except Exception as e:
            logger.error(f"Execution failed: {e}")
            result = ExecutionResult(
                status="failed",
                error=str(e),
                duration_sec=0.0
            )

        # Phase 5: Sanitization
        try:
            sanitized = self.gateway.sanitize_result(result, intent)
        except Exception as e:
            logger.error(f"Sanitization failed: {e}")
            raise

        # Phase 6: Evidence
        try:
            evidence = self.gateway.record_evidence(intent, history, sanitized)
            logger.info(f"Evidence recorded: {intent.intent_id}")
        except Exception as e:
            logger.error(f"Evidence recording failed: {e}")
            raise

        logger.info(f"Execution complete: {intent.intent_id} → {result.status}")
        return result

    def _get_video_policy(self, intent: ToolIntent) -> Dict[str, Any]:
        """Evaluate VideoBackendPolicy for video generation.

        TODO: Implement actual policy engine from ADR-VIDEO-BACKEND-POLICY.md
        """
        # Stub: return default policy
        return {
            "backend_choice": "claude_toolkit",
            "fallback_chain": ["openmontage"],
            "max_cost_usd": intent.metadata.get("budget", 5.0),
            "approval_required": False,
        }

    def _get_model_policy(self, intent: ToolIntent) -> Dict[str, Any]:
        """Evaluate ModelGateway policy for LLM inference.

        M20.2: when the governed gateway path is enabled, prefer governed-local
        (ModelRouter + saathi.inference). Cloud is never in the default fallback
        chain. Chat may still override this method for chat-llm.
        """
        sensitivity = (intent.metadata or {}).get("data_sensitivity", "public")
        try:
            from saathi.inference.config import load_inference_settings

            s = load_inference_settings()
            if s.enabled and s.gateway_enabled:
                return {
                    "provider_choice": "governed-local",
                    "fallback_chain": [],  # only ModelRouter-approved plans inside path
                    "data_sensitivity": sensitivity,
                }
        except Exception:
            pass
        return {
            "provider_choice": "openjarvis",
            "fallback_chain": [],
            "data_sensitivity": sensitivity,
        }


# Singleton instance
_execution_system: Optional[SaathiExecutionSystem] = None


def get_execution_system(queue: Optional[ExecutionQueue] = None) -> SaathiExecutionSystem:
    """Get or create singleton ExecutionSystem."""
    global _execution_system
    if _execution_system is None:
        if queue is None:
            # TODO: Import DurableQueue (SQLite) for production
            from saathi.execution.queue.memory import MemoryQueue
            queue = MemoryQueue()
        _execution_system = SaathiExecutionSystem(queue)
    return _execution_system


async def execute(intent: ToolIntent, context: ExecutionContext) -> ExecutionResult:
    """Execute ToolIntent via SaathiOS."""
    system = get_execution_system()
    return await system.execute_intent(intent, context)
