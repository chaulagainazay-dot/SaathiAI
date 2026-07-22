"""ModelGateway: Multi-provider LLM orchestrator.

M20.2: when SAATHI_INFERENCE_ENABLED and SAATHI_INFERENCE_GATEWAY_ENABLED are set,
``local-llm-inference`` executes via the governed path:

  ToolIntent → ModelRouter (authoritative) → saathi.inference → Ollama

OpenJarvis is not a runtime. Chat adapters registered under other provider keys
are unchanged.
"""
from __future__ import annotations

from typing import Optional, Dict, Any
from enum import Enum
import logging

from saathi.execution.toolintent import ToolIntent
from saathi.execution.results import ExecutionResult, ExecutionStatus
from saathi.execution.adapters.openjarvis_adapter import OpenJarvisAdapter

logger = logging.getLogger(__name__)


class LLMProvider(Enum):
    """LLM provider options."""
    OLLAMA = "ollama"
    OPENJARVIS = "openjarvis"  # legacy name; not an OpenJarvis process
    CLAUDE = "claude"
    OPENAI = "openai"
    GEMINI = "gemini"
    GROQ = "groq"
    GOVERNED_LOCAL = "governed-local"


class ModelGateway:
    """Routes LLM inference to adapters / governed local path.

    Selection policy for the governed path is owned by ModelRouter inside
    ``saathi.inference.gateway_path``. This class does not re-route models.
    """

    def __init__(self):
        self.openjarvis = OpenJarvisAdapter()
        self.providers: Dict[str, Any] = {
            "ollama": self.openjarvis,
            "openjarvis": self.openjarvis,
            "governed-local": self,  # self-handle
        }

    def _gateway_path_enabled(self) -> bool:
        try:
            from saathi.inference.config import load_inference_settings

            s = load_inference_settings()
            return bool(s.enabled and s.gateway_enabled)
        except Exception:
            return False

    async def route_and_execute(
        self, intent: ToolIntent, policy_decision: Dict[str, Any]
    ) -> ExecutionResult:
        """Execute LLM inference per policy decision + optional governed path."""
        provider = policy_decision.get("provider_choice", "openjarvis")
        fallback_chain = list(policy_decision.get("fallback_chain") or [])
        data_sensitivity = policy_decision.get("data_sensitivity", "public")

        logger.info("ModelGateway routing: %s → %s", intent.intent_id, provider)

        # Confidential → force local keys only (no cloud provider adapters)
        if data_sensitivity == "confidential" and provider not in (
            "ollama",
            "openjarvis",
            "governed-local",
            "chat-llm",  # existing chat path may stay
        ):
            logger.warning("Confidential data cannot use cloud provider, forcing local")
            provider = "governed-local" if self._gateway_path_enabled() else "openjarvis"

        # M20.2 governed path for local operations (not chat-llm override)
        if provider in ("ollama", "openjarvis", "governed-local") and self._gateway_path_enabled():
            return await self._execute_governed(intent, policy_decision)

        try:
            adapter = self.providers.get(provider)
            if adapter is self:
                return await self._execute_governed(intent, policy_decision)
            if adapter is not None:
                return await adapter.execute(intent)
            return await self.execute_fallback(intent, fallback_chain)
        except Exception as e:
            logger.warning("Provider failed: %s, trying fallback: %s", provider, e)
            return await self.execute_fallback(intent, fallback_chain)

    async def _execute_governed(
        self, intent: ToolIntent, policy_decision: Dict[str, Any]
    ) -> ExecutionResult:
        from saathi.inference.gateway_path import execute_governed_local_inference
        from saathi.inference.request import request_from_toolintent_parameters

        params = dict(intent.parameters or {})
        meta = dict(intent.metadata or {})
        if "data_sensitivity" not in meta and policy_decision.get("data_sensitivity"):
            meta["data_sensitivity"] = policy_decision["data_sensitivity"]
        # Pilot is local-first; policy cloud fallback must still pass settings
        req = request_from_toolintent_parameters(
            params,
            metadata=meta,
            mission_id=getattr(intent, "mission_id", "") or "",
            actor_id=getattr(intent, "actor_id", "") or "",
            intent_id=getattr(intent, "intent_id", "") or "",
            timeout=getattr(intent, "timeout", None),
        )
        structured = await execute_governed_local_inference(req)
        if structured.ok:
            return ExecutionResult(
                status=ExecutionStatus.SUCCESS,
                data=structured.to_dict(),
                cost_usd=0.0,
                duration_sec=(structured.latency_ms or 0.0) / 1000.0,
                connector_trace={
                    "engine": structured.selected_engine,
                    "model": structured.selected_model,
                    "provider": structured.selected_provider,
                    "governed_path": True,
                    "openjarvis_runtime": False,
                    "result_fingerprint": structured.result_fingerprint,
                },
            )
        return ExecutionResult(
            status=ExecutionStatus.FAILED,
            data=structured.to_dict(),
            cost_usd=0.0,
            duration_sec=(structured.latency_ms or 0.0) / 1000.0,
            connector_trace={
                "governed_path": True,
                "error_category": structured.error_category,
                "openjarvis_runtime": False,
            },
        )

    async def execute_fallback(
        self, intent: ToolIntent, fallback_chain: list[str]
    ) -> ExecutionResult:
        """Execute via fallback chain. Does not invent cloud routes when disabled."""
        for fallback_provider in fallback_chain:
            logger.info("Trying fallback: %s", fallback_provider)
            if fallback_provider in ("ollama", "openjarvis", "governed-local") and self._gateway_path_enabled():
                try:
                    return await self._execute_governed(
                        intent, {"provider_choice": fallback_provider}
                    )
                except Exception as e:
                    logger.warning("Governed fallback failed: %s", e)
                    continue
            try:
                adapter = self.providers.get(fallback_provider)
                if adapter is not None and adapter is not self:
                    return await adapter.execute(intent)
            except Exception as e:
                logger.warning("Fallback %s failed: %s", fallback_provider, e)
                continue

        if self._gateway_path_enabled():
            return await self._execute_governed(intent, {"provider_choice": "governed-local"})

        logger.info("Falling back to legacy OpenJarvisAdapter stub")
        return await self.openjarvis.execute(intent)
