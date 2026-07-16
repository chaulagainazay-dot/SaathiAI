"""Legacy ModelGateway adapter name: "OpenJarvis".

M20.1 Slice A: real inference lives in ``saathi.inference`` (SaathiOS-native).
This adapter optionally delegates to OllamaEngine when
``SAATHI_INFERENCE_ENABLED=1``; otherwise it remains a non-production stub.
OpenJarvis the upstream project is **not** started as a runtime.
"""

from typing import Optional, Dict, Any
import logging
import os

from saathi.execution.toolintent import ToolIntent
from saathi.execution.results import ExecutionResult, ExecutionStatus
from saathi.execution.errors import ConnectorException

logger = logging.getLogger(__name__)


class OpenJarvisAdapter:
    """Local LLM adapter behind ModelGateway (name retained for compatibility).

    Authoritative selection remains ModelRouter. This class only executes when
    invoked by ModelGateway / ExecutionGateway paths.
    """

    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = base_url
        self.ollama_engine_url = base_url

    def _inference_enabled(self) -> bool:
        return os.getenv("SAATHI_INFERENCE_ENABLED", "").strip().lower() in {
            "1", "true", "yes", "on"
        }

    async def check_health(self) -> bool:
        """Check local Ollama via saathi.inference when enabled."""
        if not self._inference_enabled():
            logger.info("OpenJarvisAdapter health: inference disabled (stub ok=False)")
            return False
        try:
            from saathi.inference.adapters.ollama import OllamaEngine
            eng = OllamaEngine(host=self.base_url)
            h = await eng.health()
            return bool(h.get("ok"))
        except Exception as e:
            logger.warning("OpenJarvisAdapter health failed: %s", e)
            return False

    async def execute(self, intent: ToolIntent) -> ExecutionResult:
        """Execute local generation when inference is enabled; else stub fail-closed."""
        if not self._inference_enabled():
            logger.info("OpenJarvisAdapter execute stub (inference disabled): %s", intent.intent_id)
            return ExecutionResult(
                status=ExecutionStatus.FAILED,
                data={"output": "", "stub": True, "reason": "SAATHI_INFERENCE_ENABLED not set"},
                cost_usd=0.0,
                duration_sec=0,
                connector_trace={"engine": "stub", "openjarvis_runtime": False},
            )

        try:
            from saathi.inference.adapters.ollama import OllamaEngine
            payload = getattr(intent, "payload", None) or {}
            if not isinstance(payload, dict):
                payload = {}
            prompt = str(payload.get("prompt") or payload.get("input") or "")
            system = str(payload.get("system") or "You are a helpful assistant.")
            model = str(payload.get("model") or os.getenv("OLLAMA_MODEL", "qwen2.5:3b"))
            eng = OllamaEngine(host=self.base_url)
            result = await eng.generate(
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                model=model,
            )
            return ExecutionResult(
                status=ExecutionStatus.SUCCESS,
                data={"output": result.text, "model": result.model},
                cost_usd=0.0,
                duration_sec=result.latency_ms / 1000.0,
                connector_trace={
                    "engine": result.engine_id,
                    "model": result.model,
                    "openjarvis_runtime": False,
                    "saathi_inference": True,
                },
            )
        except Exception as e:
            logger.warning("OpenJarvisAdapter execute failed: %s", e)
            raise ConnectorException(str(e)) from e

    async def list_models(self) -> list[str]:
        if not self._inference_enabled():
            return []
        try:
            from saathi.inference.adapters.ollama import OllamaEngine
            eng = OllamaEngine(host=self.base_url)
            return await eng.list_models()
        except Exception:
            return []

    async def fallback_to_cloud(self, intent: ToolIntent) -> ExecutionResult:
        """Cloud fallback is policy-gated; default denied."""
        if os.getenv("SAATHI_ALLOW_CLOUD_FALLBACK", "").strip().lower() not in {
            "1", "true", "yes", "on"
        }:
            return ExecutionResult(
                status=ExecutionStatus.FAILED,
                data={"output": "", "reason": "cloud fallback disabled"},
                cost_usd=0.0,
                connector_trace={"engine": "none", "fallback_denied": True},
            )
        # Explicit future: route through ModelRouter + cloud InferenceEngine
        return ExecutionResult(
            status=ExecutionStatus.FAILED,
            data={"output": "", "reason": "cloud fallback not wired in Slice A"},
            cost_usd=0.0,
            connector_trace={"engine": "none", "fallback": True},
        )
