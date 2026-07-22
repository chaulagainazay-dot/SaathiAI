"""M17.4 resource limits for harness subprocesses.

Bounded CPU time, address space (RAM), file size, and wall-clock runtime via
POSIX setrlimit in a preexec hook, plus an artifact-size cap enforced after the
run. Prevents resource-exhaustion / zip-bomb-style attacks from a harness.
"""
from __future__ import annotations

import os
import resource
from dataclasses import dataclass


@dataclass
class ResourceLimits:
    cpu_seconds: int = 60
    address_space_mb: int = 2048        # RLIMIT_AS
    file_size_mb: int = 200             # RLIMIT_FSIZE (caps runaway output files)
    max_runtime_sec: float = 120.0      # wall clock (enforced by adapter timeout)
    max_artifact_bytes: int = 500_000_000

    def preexec(self):
        """Return a callable applied in the child before exec (POSIX only)."""
        cpu = self.cpu_seconds
        addr = self.address_space_mb * 1024 * 1024
        fsize = self.file_size_mb * 1024 * 1024

        def _apply():
            try:
                resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
            except Exception:
                pass
            try:
                resource.setrlimit(resource.RLIMIT_FSIZE, (fsize, fsize))
            except Exception:
                pass
            # RLIMIT_AS is unreliable on macOS; apply best-effort
            try:
                resource.setrlimit(resource.RLIMIT_AS, (addr, addr))
            except Exception:
                pass
        return _apply

    def artifact_within_cap(self, path: str) -> bool:
        try:
            return os.path.getsize(path) <= self.max_artifact_bytes
        except Exception:
            return True


DEFAULT_LIMITS = ResourceLimits()
