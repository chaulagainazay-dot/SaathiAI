"""M370 — Operator-side host probes that need a process.

:mod:`saathi.agentdev.resources` reads everything it can without spawning
anything, and that is the right default. Two numbers this milestone depends on
cannot be read that way on Darwin: **swap usage** and **memory pressure**. Both
decide whether a model may be loaded at all on an 8 GB host, so measuring them
is not optional and assuming them would be worse than spawning a reader.

This module is therefore the one place in the package that runs a command, and
it is built so that the fact stays contained:

* every argv is a **frozen constant** in :data:`PROBES` — nothing is
  constructed, formatted or interpolated at call time;
* no probe takes a parameter, so no caller-supplied string can reach argv;
* ``shell=False`` always, and there is no ``shell=True`` anywhere in the file;
* every probe is read-only: ``sysctl -n``, ``vm_stat``, ``df -k``;
* a probe that fails returns ``available: False`` with the reason, and never
  raises into the caller.

**It is not on the model path.** No model output reaches this module, and
nothing here is imported by :mod:`saathi.agentdev.model_adapter`,
:mod:`~saathi.agentdev.model_eval`, :mod:`~saathi.agentdev.adversarial`,
:mod:`~saathi.agentdev.cross_model_eval` or
:mod:`~saathi.agentdev.claim_verification`. The M373 shell-access probe asserts
exactly that separation rather than trusting this sentence.
"""
from __future__ import annotations

import platform
import re
import subprocess
from dataclasses import dataclass
from typing import Any

PROBE_VERSION = "agentdev.host_probe.v1"

#: Every command this module may run, frozen. A probe is selected by name; its
#: argv is never built from an argument.
PROBES: dict[str, tuple[str, ...]] = {
    "swap": ("/usr/sbin/sysctl", "-n", "vm.swapusage"),
    "vm_stat": ("/usr/bin/vm_stat",),
    "memory_pressure": ("/usr/bin/memory_pressure",),
}

PROBE_TIMEOUT_S = 10.0


def _run(name: str) -> tuple[bool, str, str]:
    """Run one frozen probe. Never raises; a failure is a returned reason."""
    argv = PROBES.get(name)
    if argv is None:
        return False, "", f"no such probe: {name}"
    try:
        completed = subprocess.run(  # noqa: S603 — frozen argv, shell=False
            list(argv),
            capture_output=True,
            text=True,
            timeout=PROBE_TIMEOUT_S,
            shell=False,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, "", f"{type(exc).__name__}: {exc}"[:200]
    if completed.returncode != 0:
        return False, completed.stdout, f"exit {completed.returncode}"
    return True, completed.stdout, ""


# --------------------------------------------------------------------------
# Swap
# --------------------------------------------------------------------------

_SWAP_RE = re.compile(
    r"total\s*=\s*([\d.]+)([KMG])\s+used\s*=\s*([\d.]+)([KMG])\s+free\s*=\s*([\d.]+)([KMG])",
    re.IGNORECASE,
)

_UNIT_BYTES = {"K": 1024, "M": 1024 ** 2, "G": 1024 ** 3}


def parse_swapusage(text: str) -> dict[str, Any]:
    """Parse ``vm.swapusage``. Pure; the tests drive it with fixed strings."""
    match = _SWAP_RE.search(text or "")
    if not match:
        return {"available": False, "reason": "vm.swapusage did not match the expected shape"}
    total, tu, used, uu, free, fu = match.groups()
    total_b = int(float(total) * _UNIT_BYTES[tu.upper()])
    used_b = int(float(used) * _UNIT_BYTES[uu.upper()])
    free_b = int(float(free) * _UNIT_BYTES[fu.upper()])
    return {
        "available": True,
        "total_bytes": total_b,
        "used_bytes": used_b,
        "free_bytes": free_b,
        "total_mib": round(total_b / (1024 ** 2), 1),
        "used_mib": round(used_b / (1024 ** 2), 1),
        "free_mib": round(free_b / (1024 ** 2), 1),
        "used_fraction": round(used_b / total_b, 4) if total_b else 0.0,
    }


def swap_usage() -> dict[str, Any]:
    if platform.system() != "Darwin":
        return {"available": False, "reason": f"no swap probe for {platform.system()}"}
    ok, out, reason = _run("swap")
    if not ok:
        return {"available": False, "reason": reason}
    return parse_swapusage(out)


# --------------------------------------------------------------------------
# Page statistics
# --------------------------------------------------------------------------

_PAGESIZE_RE = re.compile(r"page size of (\d+) bytes")
_STAT_RE = re.compile(r"^([A-Za-z][^:]*):\s+(\d+)\.?\s*$")


def parse_vm_stat(text: str) -> dict[str, Any]:
    """Parse ``vm_stat``into byte counts. Pure."""
    lines = (text or "").splitlines()
    if not lines:
        return {"available": False, "reason": "vm_stat produced no output"}
    page_match = _PAGESIZE_RE.search(lines[0])
    page_size = int(page_match.group(1)) if page_match else 4096
    pages: dict[str, int] = {}
    for line in lines[1:]:
        stat = _STAT_RE.match(line.strip())
        if stat:
            key = stat.group(1).strip().lower().replace(" ", "_")
            pages[key] = int(stat.group(2))
    if not pages:
        return {"available": False, "reason": "vm_stat produced no parseable counters"}

    free = pages.get("pages_free", 0)
    inactive = pages.get("pages_inactive", 0)
    speculative = pages.get("pages_speculative", 0)
    wired = pages.get("pages_wired_down", 0)
    active = pages.get("pages_active", 0)
    compressed = pages.get("pages_occupied_by_compressor", 0)
    # Darwin's own definition of "available": free plus what can be reclaimed
    # without paging anything out.
    available_pages = free + inactive + speculative
    return {
        "available": True,
        "page_size_bytes": page_size,
        "pages": pages,
        "free_bytes": free * page_size,
        "available_bytes": available_pages * page_size,
        "available_mib": round(available_pages * page_size / (1024 ** 2), 1),
        "wired_bytes": wired * page_size,
        "active_bytes": active * page_size,
        "compressor_bytes": compressed * page_size,
        "note": (
            "available = free + inactive + speculative, the pages Darwin can "
            "reclaim without paging out. It is an upper bound on what a model "
            "may take, not a promise that it will get it."
        ),
    }


def page_statistics() -> dict[str, Any]:
    if platform.system() != "Darwin":
        return {"available": False, "reason": f"no vm_stat probe for {platform.system()}"}
    ok, out, reason = _run("vm_stat")
    if not ok:
        return {"available": False, "reason": reason}
    return parse_vm_stat(out)


# --------------------------------------------------------------------------
# Memory pressure
# --------------------------------------------------------------------------

_FREE_PCT_RE = re.compile(r"System-wide memory free percentage:\s*(\d+)%")


def parse_memory_pressure(text: str) -> dict[str, Any]:
    """Parse the one line of ``memory_pressure`` this milestone uses. Pure."""
    match = _FREE_PCT_RE.search(text or "")
    if not match:
        return {"available": False, "reason": "no free-percentage line in the output"}
    free_pct = int(match.group(1))
    return {
        "available": True,
        "free_percent": free_pct,
        "used_percent": 100 - free_pct,
        "note": (
            "Darwin's own free percentage. It counts compressible and "
            "reclaimable pages as free, so it reads higher than the memory a "
            "new process will actually be handed."
        ),
    }


def memory_pressure() -> dict[str, Any]:
    if platform.system() != "Darwin":
        return {"available": False, "reason": f"no pressure probe for {platform.system()}"}
    ok, out, reason = _run("memory_pressure")
    if not ok:
        return {"available": False, "reason": reason}
    return parse_memory_pressure(out)


# --------------------------------------------------------------------------
# Combined
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ProbeReport:
    swap: dict[str, Any]
    pages: dict[str, Any]
    pressure: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "probe": PROBE_VERSION,
            "platform": platform.system(),
            "swap": self.swap,
            "pages": self.pages,
            "pressure": self.pressure,
            "commands": {name: list(argv) for name, argv in sorted(PROBES.items())},
            "limitation": (
                "Three read-only commands, run once. Every number is a moment, "
                "not a trend, and none of them predicts what a model will need."
            ),
        }


def probe_host() -> ProbeReport:
    """Every probe once. Each failure is carried, not raised."""
    return ProbeReport(
        swap=swap_usage(), pages=page_statistics(), pressure=memory_pressure()
    )
