"""SaathiOS Spec Kit wrapper — offline, native spec-driven delivery governance.

This is NOT a vendored copy of GitHub Spec Kit. It is a small native wrapper
implementing the same discipline (constitution -> spec -> plan -> tasks ->
traceability -> convergence) against SaathiOS's own repo layout, so no external
Next.js/SaaS scaffolding (e.g. garrytan/gstack) is dragged into this Python
monorepo. The convergence gate enforces the Delivery Constitution.
"""
from saathi.specs.traceability import (
    load_traceability, validate_traceability, converge,
)

__all__ = ["load_traceability", "validate_traceability", "converge"]
