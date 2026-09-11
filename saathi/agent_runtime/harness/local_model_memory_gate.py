"""FM-I6.2-MG-FIX — Combined macOS local-model memory admission gate.

Fail-closed, dependency-injected, deterministic under injected samples.
Does not invoke inference, start/stop Ollama, or grant tool/execution authority.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Callable, List, Mapping, Optional, Sequence, Tuple
import platform
import re
import subprocess
import time
import uuid

from saathi.agent_runtime.harness.local_model_types import (
    PINNED_MODEL,
    PINNED_MODEL_DIGEST,
)

# ── Policy version ──────────────────────────────────────────────────────────

MEMORY_GATE_POLICY_VERSION = "fm_i6_2_mg_fix.combined_macos.v1"

# ── Fixed subprocess allowlist (read-only Darwin probes only) ───────────────

_PROBE_TIMEOUT_S = 5.0
_PROBES: dict[str, tuple[str, ...]] = {
    "memsize": ("/usr/sbin/sysctl", "-n", "hw.memsize"),
    "vm_stat": ("/usr/bin/vm_stat",),
    "swap": ("/usr/sbin/sysctl", "-n", "vm.swapusage"),
    "memory_pressure": ("/usr/bin/memory_pressure",),
}

# ── Approved thresholds (do not relax to pass a host) ───────────────────────

DARWIN_FREE_PERCENT_MIN = 20
ABSOLUTE_RECLAIMABLE_MIB_FLOOR = 2048.0
SWAP_USED_MIB_MAX = 512.0
COMPRESSOR_SOFT_FRACTION = 0.50
COMPRESSOR_HARD_FRACTION = 0.70
SAMPLE_COUNT = 2
SAMPLE_WINDOW_SECONDS = 5.0
MAX_ADMISSION_RETRIES = 2
RETRY_INTERVAL_SECONDS = 15.0
HYSTERESIS_MIB = 256.0
SAMPLE_MAX_AGE_SECONDS = 30.0

# ── Pinned model budget (estimate; not a measured peak) ─────────────────────

PINNED_WEIGHT_BYTES = 986_061_892
PINNED_WEIGHT_MIB = PINNED_WEIGHT_BYTES / (1024 ** 2)  # ≈ 940.4
PINNED_ESTIMATED_PEAK_MIB = 2681.0  # estimate only
PINNED_SAFETY_FACTOR = 1.5
PINNED_REQUIRED_HEADROOM_MIB = max(
    ABSOLUTE_RECLAIMABLE_MIB_FLOOR,
    PINNED_ESTIMATED_PEAK_MIB * PINNED_SAFETY_FACTOR,
)  # ≈ 4021.5 → 4022 for display


class MemoryGateReason(str, Enum):
    DARWIN_FREE_PERCENT_LOW = "DARWIN_FREE_PERCENT_LOW"
    ABSOLUTE_RECLAIMABLE_LOW = "ABSOLUTE_RECLAIMABLE_LOW"
    MODEL_HEADROOM_LOW = "MODEL_HEADROOM_LOW"
    SWAP_LIMIT_EXCEEDED = "SWAP_LIMIT_EXCEEDED"
    SWAP_RISING = "SWAP_RISING"
    COMPRESSOR_SOFT_LIMIT = "COMPRESSOR_SOFT_LIMIT"
    COMPRESSOR_HARD_LIMIT = "COMPRESSOR_HARD_LIMIT"
    WRONG_MODEL_LOADED = "WRONG_MODEL_LOADED"
    MULTIPLE_MODELS_LOADED = "MULTIPLE_MODELS_LOADED"
    CONCURRENCY_LIMIT = "CONCURRENCY_LIMIT"
    PROBE_FAILED = "PROBE_FAILED"
    SAMPLE_STALE = "SAMPLE_STALE"
    INVALID_METRICS = "INVALID_METRICS"
    HYSTERESIS_NOT_SATISFIED = "HYSTERESIS_NOT_SATISFIED"
    PHYSICAL_RAM_MISMATCH = "PHYSICAL_RAM_MISMATCH"


@dataclass(frozen=True)
class LocalModelMemoryBudget:
    """Pinned model memory budget. estimated_peak_mib is an estimate, not measured."""

    model_name: str = PINNED_MODEL
    model_digest: str = PINNED_MODEL_DIGEST
    weight_mib: float = PINNED_WEIGHT_MIB
    estimated_peak_mib: float = PINNED_ESTIMATED_PEAK_MIB
    safety_factor: float = PINNED_SAFETY_FACTOR
    absolute_floor_mib: float = ABSOLUTE_RECLAIMABLE_MIB_FLOOR
    context_tokens: int = 2048
    max_output_tokens: int = 512
    max_concurrency: int = 1
    peak_is_estimate: bool = True

    @property
    def required_headroom_mib(self) -> float:
        return max(
            self.absolute_floor_mib,
            float(self.estimated_peak_mib) * float(self.safety_factor),
        )


DEFAULT_PINNED_BUDGET = LocalModelMemoryBudget()


@dataclass(frozen=True)
class MacOSMemorySample:
    """One read-only macOS memory observation."""

    physical_memory_bytes: int
    darwin_free_percent: float
    free_bytes: int
    inactive_bytes: int
    speculative_bytes: int
    purgeable_bytes: int
    compressor_bytes: int
    swap_used_bytes: int
    swap_total_bytes: int
    swapins: int
    swapouts: int
    sampled_at: float
    probe_valid: bool
    probe_errors: Tuple[str, ...] = ()
    pure_free_bytes: int = 0  # diagnostic only — never admission-primary
    page_size_bytes: int = 16384

    @property
    def reclaimable_bytes(self) -> int:
        return int(self.free_bytes) + int(self.inactive_bytes) + int(self.speculative_bytes)

    @property
    def reclaimable_mib(self) -> float:
        return self.reclaimable_bytes / (1024 ** 2)

    @property
    def pure_free_mib(self) -> float:
        return self.pure_free_bytes / (1024 ** 2)

    @property
    def compressor_percent(self) -> float:
        if self.physical_memory_bytes <= 0:
            return 0.0
        return 100.0 * float(self.compressor_bytes) / float(self.physical_memory_bytes)

    @property
    def swap_used_mib(self) -> float:
        return self.swap_used_bytes / (1024 ** 2)

    def to_audit_dict(self) -> dict[str, Any]:
        return {
            "physical_memory_bytes": self.physical_memory_bytes,
            "darwin_free_percent": self.darwin_free_percent,
            "reclaimable_mib": round(self.reclaimable_mib, 2),
            "pure_free_mib": round(self.pure_free_mib, 2),
            "compressor_percent": round(self.compressor_percent, 2),
            "swap_used_mib": round(self.swap_used_mib, 2),
            "swapins": self.swapins,
            "sampled_at": self.sampled_at,
            "probe_valid": self.probe_valid,
            "probe_errors": list(self.probe_errors),
        }


@dataclass(frozen=True)
class MemoryGateDecision:
    allowed: bool
    health_state: str  # MODEL_READY | RESOURCE_PRESSURE | DEGRADED
    denial_reasons: Tuple[MemoryGateReason, ...]
    current_sample: Optional[MacOSMemorySample]
    previous_sample: Optional[MacOSMemorySample]
    required_headroom_mib: float
    available_reclaimable_mib: float
    headroom_deficit_mib: float
    retry_allowed: bool
    next_retry_after: float
    hysteresis_required: bool
    policy_version: str
    correlation_id: str
    detail: str = ""

    def to_audit_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "health_state": self.health_state,
            "denial_reasons": [r.value for r in self.denial_reasons],
            "required_headroom_mib": round(self.required_headroom_mib, 2),
            "available_reclaimable_mib": round(self.available_reclaimable_mib, 2),
            "headroom_deficit_mib": round(self.headroom_deficit_mib, 2),
            "retry_allowed": self.retry_allowed,
            "next_retry_after": self.next_retry_after,
            "hysteresis_required": self.hysteresis_required,
            "policy_version": self.policy_version,
            "correlation_id": self.correlation_id,
            "detail": self.detail,
            "current_sample": self.current_sample.to_audit_dict() if self.current_sample else None,
            "previous_sample": (
                self.previous_sample.to_audit_dict() if self.previous_sample else None
            ),
        }


# ── Pure parsers (no subprocess) ────────────────────────────────────────────

_SWAP_RE = re.compile(
    r"total\s*=\s*([\d.]+)([KMG])\s+used\s*=\s*([\d.]+)([KMG])\s+free\s*=\s*([\d.]+)([KMG])",
    re.IGNORECASE,
)
_UNIT = {"K": 1024, "M": 1024 ** 2, "G": 1024 ** 3}
_PAGESIZE_RE = re.compile(r"page size of (\d+) bytes")
_STAT_RE = re.compile(r"^([A-Za-z][^:]*):\s+(\d+)\.?\s*$")
_FREE_PCT_RE = re.compile(r"System-wide memory free percentage:\s*(\d+)%")


def _parse_swap(text: str) -> Tuple[int, int, Optional[str]]:
    m = _SWAP_RE.search(text or "")
    if not m:
        return 0, 0, "vm.swapusage parse failed"
    total, tu, used, uu, _free, _fu = m.groups()
    total_b = int(float(total) * _UNIT[tu.upper()])
    used_b = int(float(used) * _UNIT[uu.upper()])
    return total_b, used_b, None


def _parse_vm_pages(text: str) -> Tuple[dict[str, int], int, Optional[str]]:
    lines = (text or "").splitlines()
    if not lines:
        return {}, 4096, "empty vm_stat"
    pm = _PAGESIZE_RE.search(lines[0])
    page_size = int(pm.group(1)) if pm else 4096
    pages: dict[str, int] = {}
    for line in lines[1:]:
        sm = _STAT_RE.match(line.strip())
        if sm:
            key = sm.group(1).strip().lower().replace(" ", "_")
            pages[key] = int(sm.group(2))
    if not pages:
        return {}, page_size, "no vm_stat counters"
    return pages, page_size, None


def _parse_darwin_free_percent(text: str) -> Tuple[Optional[float], Optional[str]]:
    m = _FREE_PCT_RE.search(text or "")
    if not m:
        return None, "memory_pressure free% missing"
    return float(m.group(1)), None


def build_sample_from_raw(
    *,
    memsize_text: str,
    vm_stat_text: str,
    swap_text: str,
    pressure_text: str,
    sampled_at: float,
) -> MacOSMemorySample:
    """Build a sample from raw command outputs (test-friendly pure path)."""
    errors: List[str] = []
    try:
        physical = int((memsize_text or "").strip())
    except ValueError:
        physical = 0
        errors.append("hw.memsize invalid")

    pages, page_size, verr = _parse_vm_pages(vm_stat_text)
    if verr:
        errors.append(verr)
    free_p = pages.get("pages_free", 0)
    inactive_p = pages.get("pages_inactive", 0)
    spec_p = pages.get("pages_speculative", 0)
    purge_p = pages.get("pages_purgeable", 0)
    # "pages_wired_down" key from normalize; compressor:
    comp_p = pages.get("pages_occupied_by_compressor", 0)
    swapins = pages.get("swapins", 0)
    swapouts = pages.get("swapouts", 0)

    swap_total, swap_used, serr = _parse_swap(swap_text)
    # Zero swap pool is valid on some hosts; only parse failure is an error.
    if serr and (swap_text or "").strip() and "0.00M" not in (swap_text or ""):
        # Still accept "total = 0.00M used = 0.00M free = 0.00M"
        if not _SWAP_RE.search(swap_text or ""):
            errors.append(serr)

    darwin_pct, perr = _parse_darwin_free_percent(pressure_text)
    if perr:
        errors.append(perr)
        darwin_pct = -1.0

    valid = not errors and physical > 0 and page_size > 0
    return MacOSMemorySample(
        physical_memory_bytes=physical,
        darwin_free_percent=float(darwin_pct if darwin_pct is not None else -1.0),
        free_bytes=free_p * page_size,
        inactive_bytes=inactive_p * page_size,
        speculative_bytes=spec_p * page_size,
        purgeable_bytes=purge_p * page_size,
        compressor_bytes=comp_p * page_size,
        swap_used_bytes=swap_used,
        swap_total_bytes=swap_total,
        swapins=swapins,
        swapouts=swapouts,
        sampled_at=sampled_at,
        probe_valid=valid,
        probe_errors=tuple(errors),
        pure_free_bytes=free_p * page_size,
        page_size_bytes=page_size,
    )


def make_sample(
    *,
    physical_memory_bytes: int = 8 * 1024 ** 3,
    darwin_free_percent: float = 50.0,
    free_mib: float = 100.0,
    inactive_mib: float = 4000.0,
    speculative_mib: float = 50.0,
    purgeable_mib: float = 0.0,
    compressor_mib: float = 500.0,
    swap_used_mib: float = 0.0,
    swap_total_mib: float = 0.0,
    swapins: int = 0,
    swapouts: int = 0,
    sampled_at: Optional[float] = None,
    probe_valid: bool = True,
    probe_errors: Sequence[str] = (),
) -> MacOSMemorySample:
    """Construct a sample in MiB units for tests."""
    mib = 1024 ** 2
    free_b = int(free_mib * mib)
    return MacOSMemorySample(
        physical_memory_bytes=physical_memory_bytes,
        darwin_free_percent=darwin_free_percent,
        free_bytes=free_b,
        inactive_bytes=int(inactive_mib * mib),
        speculative_bytes=int(speculative_mib * mib),
        purgeable_bytes=int(purgeable_mib * mib),
        compressor_bytes=int(compressor_mib * mib),
        swap_used_bytes=int(swap_used_mib * mib),
        swap_total_bytes=int(swap_total_mib * mib),
        swapins=swapins,
        swapouts=swapouts,
        sampled_at=float(sampled_at if sampled_at is not None else time.time()),
        probe_valid=probe_valid,
        probe_errors=tuple(probe_errors),
        pure_free_bytes=free_b,
    )


# ── Sample validation + evaluation ──────────────────────────────────────────


def _invalid_reasons(s: MacOSMemorySample, *, now: float, expected_physical: Optional[int]) -> List[MemoryGateReason]:
    reasons: List[MemoryGateReason] = []
    if not s.probe_valid:
        reasons.append(MemoryGateReason.PROBE_FAILED)
    if s.physical_memory_bytes <= 0:
        reasons.append(MemoryGateReason.INVALID_METRICS)
    if s.darwin_free_percent < 0 or s.darwin_free_percent > 100:
        reasons.append(MemoryGateReason.INVALID_METRICS)
    if s.free_bytes < 0 or s.inactive_bytes < 0 or s.speculative_bytes < 0:
        reasons.append(MemoryGateReason.INVALID_METRICS)
    if s.compressor_bytes < 0 or s.swap_used_bytes < 0:
        reasons.append(MemoryGateReason.INVALID_METRICS)
    if now - s.sampled_at > SAMPLE_MAX_AGE_SECONDS:
        reasons.append(MemoryGateReason.SAMPLE_STALE)
    if s.sampled_at > now + 5.0:
        reasons.append(MemoryGateReason.INVALID_METRICS)
    if expected_physical is not None and s.physical_memory_bytes != expected_physical:
        # Allow only exact match when expected is asserted (tests / consistency).
        if abs(s.physical_memory_bytes - expected_physical) > 0:
            reasons.append(MemoryGateReason.PHYSICAL_RAM_MISMATCH)
    return reasons


def evaluate_memory_samples(
    sample1: MacOSMemorySample,
    sample2: MacOSMemorySample,
    *,
    budget: LocalModelMemoryBudget = DEFAULT_PINNED_BUDGET,
    loaded_models: Sequence[str] = (),
    active_local_sessions: int = 0,
    prior_denial: bool = False,
    correlation_id: str = "",
    now: Optional[float] = None,
    expected_physical_bytes: Optional[int] = None,
    retry_count: int = 0,
) -> MemoryGateDecision:
    """Pure evaluation of two samples against the combined gate. Fail closed."""
    tnow = float(now if now is not None else time.time())
    reasons: List[MemoryGateReason] = []
    required = float(budget.required_headroom_mib)
    if prior_denial:
        required = required + HYSTERESIS_MIB

    # Both samples must be valid
    for s in (sample1, sample2):
        reasons.extend(_invalid_reasons(s, now=tnow, expected_physical=expected_physical_bytes))

    # Sample order / window
    if sample2.sampled_at < sample1.sampled_at:
        reasons.append(MemoryGateReason.INVALID_METRICS)
    if (sample2.sampled_at - sample1.sampled_at) > SAMPLE_WINDOW_SECONDS + 2.0:
        # Too far apart → treat as stale pair
        reasons.append(MemoryGateReason.SAMPLE_STALE)

    # Physical RAM consistency between samples
    if sample1.physical_memory_bytes != sample2.physical_memory_bytes:
        reasons.append(MemoryGateReason.PHYSICAL_RAM_MISMATCH)

    def _check_one(s: MacOSMemorySample) -> None:
        if s.darwin_free_percent < DARWIN_FREE_PERCENT_MIN:
            reasons.append(MemoryGateReason.DARWIN_FREE_PERCENT_LOW)
        if s.reclaimable_mib < ABSOLUTE_RECLAIMABLE_MIB_FLOOR:
            reasons.append(MemoryGateReason.ABSOLUTE_RECLAIMABLE_LOW)
        if s.reclaimable_mib < required:
            if prior_denial and s.reclaimable_mib >= float(budget.required_headroom_mib):
                reasons.append(MemoryGateReason.HYSTERESIS_NOT_SATISFIED)
            else:
                reasons.append(MemoryGateReason.MODEL_HEADROOM_LOW)
        if s.swap_used_mib > SWAP_USED_MIB_MAX:
            reasons.append(MemoryGateReason.SWAP_LIMIT_EXCEEDED)
        frac = (s.compressor_bytes / s.physical_memory_bytes) if s.physical_memory_bytes else 1.0
        if frac >= COMPRESSOR_HARD_FRACTION:
            reasons.append(MemoryGateReason.COMPRESSOR_HARD_LIMIT)
        elif frac >= COMPRESSOR_SOFT_FRACTION:
            reasons.append(MemoryGateReason.COMPRESSOR_SOFT_LIMIT)

    _check_one(sample1)
    _check_one(sample2)

    # Swap rising across window (swapins delta or used bytes delta)
    if sample2.swap_used_bytes > sample1.swap_used_bytes:
        reasons.append(MemoryGateReason.SWAP_RISING)
    if sample2.swapins > sample1.swapins:
        reasons.append(MemoryGateReason.SWAP_RISING)

    # Models — empty is OK before load; wrong or multiple is not.
    names = [str(n) for n in loaded_models]
    if len(names) > 1:
        reasons.append(MemoryGateReason.MULTIPLE_MODELS_LOADED)
    elif len(names) == 1:
        n = names[0]
        pin = budget.model_name
        # Exact pin tag only (e.g. qwen2.5:1.5b).
        if n != pin:
            reasons.append(MemoryGateReason.WRONG_MODEL_LOADED)

    # Concurrency: for new-session admission, active_local_sessions is the count
    # of already-open sessions (must be 0 when max_concurrency == 1).
    if active_local_sessions >= budget.max_concurrency:
        reasons.append(MemoryGateReason.CONCURRENCY_LIMIT)

    # Dedupe reasons preserving order
    seen = set()
    uniq: List[MemoryGateReason] = []
    for r in reasons:
        if r not in seen:
            seen.add(r)
            uniq.append(r)

    avail = min(sample1.reclaimable_mib, sample2.reclaimable_mib)
    deficit = max(0.0, required - avail)
    allowed = len(uniq) == 0
    retries_left = retry_count < MAX_ADMISSION_RETRIES
    next_retry = tnow + RETRY_INTERVAL_SECONDS if (not allowed and retries_left) else 0.0

    if allowed:
        health = "MODEL_READY"
    elif MemoryGateReason.PROBE_FAILED in uniq or MemoryGateReason.INVALID_METRICS in uniq:
        health = "DEGRADED"
    else:
        health = "RESOURCE_PRESSURE"

    return MemoryGateDecision(
        allowed=allowed,
        health_state=health,
        denial_reasons=tuple(uniq),
        current_sample=sample2,
        previous_sample=sample1,
        required_headroom_mib=required,
        available_reclaimable_mib=avail,
        headroom_deficit_mib=deficit,
        retry_allowed=(not allowed) and retries_left,
        next_retry_after=next_retry,
        hysteresis_required=prior_denial and not allowed,
        policy_version=MEMORY_GATE_POLICY_VERSION,
        correlation_id=correlation_id or "",
        detail=(
            "allowed"
            if allowed
            else ",".join(r.value for r in uniq)
        ),
    )


# ── Probe + gate object ─────────────────────────────────────────────────────


def _run_probe(name: str) -> Tuple[bool, str, str]:
    argv = _PROBES.get(name)
    if argv is None:
        return False, "", f"unknown probe {name}"
    try:
        completed = subprocess.run(  # noqa: S603 — frozen argv, shell=False
            list(argv),
            capture_output=True,
            text=True,
            timeout=_PROBE_TIMEOUT_S,
            shell=False,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, "", f"{type(exc).__name__}:{exc}"[:200]
    if completed.returncode != 0:
        return False, completed.stdout or "", f"exit {completed.returncode}"
    return True, completed.stdout or "", ""


def default_darwin_sample(clock: Optional[Callable[[], float]] = None) -> MacOSMemorySample:
    """Live Darwin sample via fixed allowlist. Fail closed on non-Darwin or errors."""
    now = float(clock() if clock else time.time())
    if platform.system() != "Darwin":
        return MacOSMemorySample(
            physical_memory_bytes=0,
            darwin_free_percent=-1.0,
            free_bytes=0,
            inactive_bytes=0,
            speculative_bytes=0,
            purgeable_bytes=0,
            compressor_bytes=0,
            swap_used_bytes=0,
            swap_total_bytes=0,
            swapins=0,
            swapouts=0,
            sampled_at=now,
            probe_valid=False,
            probe_errors=(f"unsupported_platform:{platform.system()}",),
        )
    errors: List[str] = []
    ok_m, out_m, er_m = _run_probe("memsize")
    if not ok_m:
        errors.append(f"memsize:{er_m}")
    ok_v, out_v, er_v = _run_probe("vm_stat")
    if not ok_v:
        errors.append(f"vm_stat:{er_v}")
    ok_s, out_s, er_s = _run_probe("swap")
    if not ok_s:
        errors.append(f"swap:{er_s}")
        out_s = "total = 0.00M  used = 0.00M  free = 0.00M"
    ok_p, out_p, er_p = _run_probe("memory_pressure")
    if not ok_p:
        errors.append(f"memory_pressure:{er_p}")
        out_p = ""

    sample = build_sample_from_raw(
        memsize_text=out_m,
        vm_stat_text=out_v,
        swap_text=out_s,
        pressure_text=out_p,
        sampled_at=now,
    )
    if errors:
        return replace(
            sample,
            probe_valid=False,
            probe_errors=tuple(list(sample.probe_errors) + errors),
        )
    return sample


@dataclass
class CombinedMacOSMemoryGate:
    """Injectable combined gate. Side-effect free except optional read-only probes."""

    budget: LocalModelMemoryBudget = field(default_factory=LocalModelMemoryBudget)
    sampler: Optional[Callable[[], MacOSMemorySample]] = None
    clock: Optional[Callable[[], float]] = None
    sleeper: Optional[Callable[[float], None]] = None
    sample_interval_seconds: float = SAMPLE_WINDOW_SECONDS / max(1, SAMPLE_COUNT - 1)
    # When set, skip live sampling (tests).
    fixed_samples: Optional[Tuple[MacOSMemorySample, MacOSMemorySample]] = None

    def _now(self) -> float:
        return float(self.clock() if self.clock else time.time())

    def _sleep(self, seconds: float) -> None:
        if self.sleeper is not None:
            self.sleeper(seconds)
        elif seconds > 0:
            time.sleep(seconds)

    def _sample(self) -> MacOSMemorySample:
        if self.sampler is not None:
            return self.sampler()
        return default_darwin_sample(clock=self.clock)

    def evaluate(
        self,
        *,
        loaded_models: Sequence[str] = (),
        active_local_sessions: int = 0,
        prior_denial: bool = False,
        correlation_id: str = "",
        retry_count: int = 0,
        samples: Optional[Tuple[MacOSMemorySample, MacOSMemorySample]] = None,
    ) -> MemoryGateDecision:
        pair = samples or self.fixed_samples
        if pair is not None:
            s1, s2 = pair
            # Use sample clock for injected pairs so tests are not wall-time stale.
            now = max(s1.sampled_at, s2.sampled_at) + 0.1
        else:
            s1 = self._sample()
            self._sleep(self.sample_interval_seconds)
            s2 = self._sample()
            now = self._now()
        return evaluate_memory_samples(
            s1,
            s2,
            budget=self.budget,
            loaded_models=loaded_models,
            active_local_sessions=active_local_sessions,
            prior_denial=prior_denial,
            correlation_id=correlation_id or str(uuid.uuid4()),
            now=now,
            retry_count=retry_count,
        )


def legacy_snapshot_from_decision(decision: MemoryGateDecision) -> "Any":
    """Map decision to MemorySnapshot shape for transitional callers."""
    from saathi.agent_runtime.harness.local_model_types import MemorySnapshot

    s = decision.current_sample
    total = s.physical_memory_bytes if s else 0
    # Diagnostic: reclaimable % of RAM (not pure free)
    free_pct = (
        (s.reclaimable_bytes / total * 100.0) if s and total else 0.0
    )
    avail_mib = decision.available_reclaimable_mib
    return MemorySnapshot(
        total_bytes=total,
        free_percent=free_pct,
        available_mib=avail_mib,
        ok=decision.allowed,
        detail=decision.detail or decision.health_state,
    )
