"""M353 — Host and process resource measurement.

The development host is a fixed, small machine: Apple Silicon, 8 GB of RAM, a
256 GB SSD. Every ceiling in :mod:`saathi.agentdev.settings` exists because of
those numbers, so the numbers themselves have to be *measured* rather than
assumed — a declared ceiling nobody checks is documentation, not a limit.

Everything here reads. Nothing spawns a process, installs a package or writes a
file, and no third-party dependency is introduced: ``resource``, ``shutil`` and
``os.sysconf`` are enough on both Darwin and Linux.

Two honesty notes carried in the output rather than hidden here:

* ``ru_maxrss`` is the *peak* resident size of this process since it started,
  in bytes on Darwin and in kilobytes on Linux. It is normalised to bytes and
  labelled ``peak``, never ``current``.
* Total system memory is what the kernel reports as physical pages. Memory
  actually available to a new model is smaller and is not predicted here.
"""
from __future__ import annotations

import os
import platform
import resource
import shutil
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterator

#: Darwin reports ``ru_maxrss`` in bytes; Linux reports it in kilobytes.
_MAXRSS_IS_KILOBYTES = platform.system() == "Linux"

BYTES_PER_GIB = 1024 ** 3


def _to_bytes(maxrss: int) -> int:
    return maxrss * 1024 if _MAXRSS_IS_KILOBYTES else maxrss


def total_memory_bytes() -> int:
    """Physical memory as the kernel reports it, or ``0`` if unavailable."""
    try:
        return int(os.sysconf("SC_PHYS_PAGES")) * int(os.sysconf("SC_PAGE_SIZE"))
    except (ValueError, OSError, AttributeError):  # pragma: no cover — exotic host
        return 0


def peak_process_memory_bytes() -> int:
    """Peak resident size of *this* process since it started."""
    return _to_bytes(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)


def load_average() -> tuple[float, float, float]:
    try:
        one, five, fifteen = os.getloadavg()
        return round(one, 2), round(five, 2), round(fifteen, 2)
    except (OSError, AttributeError):  # pragma: no cover — no load average
        return 0.0, 0.0, 0.0


@dataclass
class HostSnapshot:
    """One read of the host. Comparable across runs; never predictive."""

    system: str
    machine: str
    cpu_count: int
    total_memory_bytes: int
    peak_process_memory_bytes: int
    disk_total_bytes: int
    disk_free_bytes: int
    load_average: tuple[float, float, float]
    measured_at: float = field(default_factory=time.time)

    @property
    def total_memory_gib(self) -> float:
        return round(self.total_memory_bytes / BYTES_PER_GIB, 2)

    @property
    def disk_free_gib(self) -> float:
        return round(self.disk_free_bytes / BYTES_PER_GIB, 2)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["load_average"] = list(self.load_average)
        d["total_memory_gib"] = self.total_memory_gib
        d["disk_free_gib"] = self.disk_free_gib
        d["peak_process_memory_mib"] = round(
            self.peak_process_memory_bytes / (1024 ** 2), 1
        )
        d["note"] = (
            "peak_process_memory is this process since start, not current usage; "
            "total_memory is physical, not available."
        )
        return d


def host_snapshot(path: Path | str | None = None) -> HostSnapshot:
    """Read the host once. Pure read: no process is spawned, nothing is written."""
    target = Path(path) if path else Path.home()
    try:
        usage = shutil.disk_usage(str(target))
        disk_total, disk_free = usage.total, usage.free
    except OSError:  # pragma: no cover — unreadable mount
        disk_total = disk_free = 0
    return HostSnapshot(
        system=platform.system(),
        machine=platform.machine(),
        cpu_count=os.cpu_count() or 0,
        total_memory_bytes=total_memory_bytes(),
        peak_process_memory_bytes=peak_process_memory_bytes(),
        disk_total_bytes=disk_total,
        disk_free_bytes=disk_free,
        load_average=load_average(),
    )


@dataclass
class Measurement:
    """What one measured block actually cost."""

    label: str
    duration_ms: float = 0.0
    peak_memory_before_bytes: int = 0
    peak_memory_after_bytes: int = 0

    @property
    def peak_memory_growth_bytes(self) -> int:
        return max(0, self.peak_memory_after_bytes - self.peak_memory_before_bytes)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["peak_memory_growth_bytes"] = self.peak_memory_growth_bytes
        d["peak_memory_growth_mib"] = round(
            self.peak_memory_growth_bytes / (1024 ** 2), 2
        )
        d["limitation"] = (
            "Growth in this process's peak RSS. A model served by a separate "
            "daemon does not appear here; its cost is reported by the adapter."
        )
        return d


@contextmanager
def measure(label: str) -> Iterator[Measurement]:
    """Time a block and record the growth in this process's peak RSS.

    The measurement is filled in on exit, including when the block raises, so a
    failed run still reports what it cost.
    """
    m = Measurement(label=label, peak_memory_before_bytes=peak_process_memory_bytes())
    started = time.perf_counter()
    try:
        yield m
    finally:
        m.duration_ms = round((time.perf_counter() - started) * 1000, 3)
        m.peak_memory_after_bytes = peak_process_memory_bytes()


def ceiling_report(settings: Any = None) -> dict[str, Any]:
    """Declared concurrency ceilings beside the measured host.

    The ceilings are ``schema_validated`` — they are read from settings and
    reported. Nothing in this package spawns agents, so nothing enforces them
    yet; saying otherwise would overstate the control.
    """
    if settings is None:
        from saathi.agentdev.settings import load_settings

        settings = load_settings()
    snapshot = host_snapshot()
    return {
        "host": snapshot.to_dict(),
        "declared_ceilings": {
            "max_reasoning_agents": settings.max_reasoning_agents,
            "max_coding_agents": settings.max_coding_agents,
            "max_testing_agents": settings.max_testing_agents,
            "max_local_model_instances": settings.max_local_model_instances,
        },
        "enforcement": "schema_validated",
        "note": (
            "Ceilings are declared in settings and reported here. No component "
            "in this package spawns agents, so no component enforces them."
        ),
    }
