"""M49.1 Canonical Tool Execution Framework.

Sits beneath ExecutionGateway — does not replace it, Orchestrator, RunStore,
or agent lifecycle. Public entry for tool calls:

    ExecutionGateway.execute_registered_tool(...)
    ToolExecutionService.execute_tool(...)
"""
from saathi.tool_runtime.contracts import (
    ToolApprovalReference,
    ToolAuthorityClass,
    ToolErrorCode,
    ToolExecutionRequest,
    ToolExecutionResult,
    ToolManifest,
    ToolOutcomeClass,
    ToolSideEffectClass,
)
from saathi.tool_runtime.registry import ToolRegistry, default_registry
from saathi.tool_runtime.service import ToolExecutionService, default_tool_service

__all__ = [
    "ToolApprovalReference",
    "ToolAuthorityClass",
    "ToolErrorCode",
    "ToolExecutionRequest",
    "ToolExecutionResult",
    "ToolManifest",
    "ToolOutcomeClass",
    "ToolSideEffectClass",
    "ToolRegistry",
    "default_registry",
    "ToolExecutionService",
    "default_tool_service",
]
