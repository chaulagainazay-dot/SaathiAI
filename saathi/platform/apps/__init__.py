"""SaathiOS Universal Application Runtime (M121–M129).

Extends ModuleRegistry. Applications consume platform services; they never
bypass ExecutionGateway, Approval Center, Skills, Conversation, or Knowledge.
"""
from saathi.platform.apps.models import AppLifecycleState, AppManifest, AppTrustState
from saathi.platform.apps.service import (
    AppRuntime,
    default_app_runtime,
    reset_app_runtime_for_tests,
)

__all__ = [
    "AppLifecycleState",
    "AppManifest",
    "AppRuntime",
    "AppTrustState",
    "default_app_runtime",
    "reset_app_runtime_for_tests",
]
