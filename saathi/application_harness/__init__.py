"""M17.3 Agent-Native Application Harness Platform.

Lets SaathiOS agents operate applications through structured, verified, gateway-
governed CLI harnesses BEFORE falling back to browser/visual control. Design
informed by HKUDS/CLI-Anything (Apache-2.0) — no code copied; see
THIRD_PARTY_NOTICES.md. The ApplicationHarnessAdapter is the sole subprocess
boundary (argv-only, env-sanitized, file-root confined); every execution is
trust-gated, risk/approval-bound, and INDEPENDENTLY verified (a process's own
`status:success` is never trusted). Imported external harnesses stay untrusted
until human review; agents may discover but never self-promote to trusted.
"""
from saathi.application_harness import models, trust, registry, resolver, importer, verify, service
from saathi.application_harness.models import (
    HarnessDefinition, HarnessOperation, HarnessActionIntent, TrustStatus,
)

__all__ = ["models", "trust", "registry", "resolver", "importer", "verify",
           "service", "HarnessDefinition", "HarnessOperation",
           "HarnessActionIntent", "TrustStatus"]
