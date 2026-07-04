"""Re-export shim — canonical home for the Model Router.

Implementation currently lives in `saathi.model_router`; this re-exports it so
`saathi.infrastructure.model_router` resolves to the SAME objects. New code
should import from here. See infrastructure/README.md.
"""
from saathi.model_router import *  # noqa: F401,F403
from saathi.model_router import (  # explicit for editors/type-checkers
    ModelRouter, ModelLabel, Privacy, Prefer, ProviderSpec,
    DEFAULT_PROVIDERS, router,
)

__all__ = ["ModelRouter", "ModelLabel", "Privacy", "Prefer", "ProviderSpec",
           "DEFAULT_PROVIDERS", "router"]
