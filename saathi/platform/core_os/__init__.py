"""SaathiOS Core unification layer (M148–M156).

Composes existing certified runtimes — never replaces them.
"""
from .service import SaathiCoreService, default_core_service, reset_core_service_for_tests

__all__ = [
    "SaathiCoreService",
    "default_core_service",
    "reset_core_service_for_tests",
]
