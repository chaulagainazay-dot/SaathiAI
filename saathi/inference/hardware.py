"""Local hardware capability profile (Apple Silicon M2 / 8 GB aware).

Never downloads models. Never assumes dedicated GPU VRAM.
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class ModelFitResult:
    model_id: str
    memory_estimate_gb: float
    disk_estimate_gb: float
    fits_memory: bool
    fits_disk: bool
    warnings: tuple[str, ...] = ()
    recommended: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "memory_estimate_gb": self.memory_estimate_gb,
            "disk_estimate_gb": self.disk_estimate_gb,
            "fits_memory": self.fits_memory,
            "fits_disk": self.fits_disk,
            "warnings": list(self.warnings),
            "recommended": self.recommended,
        }


@dataclass
class HardwareProfile:
    architecture: str
    platform_system: str
    cpu_brand: str
    total_memory_gb: float
    available_memory_gb: float
    free_disk_gb: float
    total_disk_gb: float
    supported_runtimes: list[str] = field(default_factory=list)
    recommended_max_model_size_b: float = 3.0  # parameters (billions), Q4-ish
    safe_context_tokens: int = 4096
    memory_safety_margin_gb: float = 2.0
    disk_warning_gb: float = 25.0
    unified_memory: bool = True
    dedicated_vram_gb: Optional[float] = None  # None = none / unknown
    warnings: list[str] = field(default_factory=list)
    source: str = "detected"
    downloads_performed: bool = False  # always False for this profiler

    def to_dict(self) -> dict[str, Any]:
        return {
            "architecture": self.architecture,
            "platform_system": self.platform_system,
            "cpu_brand": self.cpu_brand,
            "total_memory_gb": self.total_memory_gb,
            "available_memory_gb": self.available_memory_gb,
            "free_disk_gb": self.free_disk_gb,
            "total_disk_gb": self.total_disk_gb,
            "supported_runtimes": list(self.supported_runtimes),
            "recommended_max_model_size_b": self.recommended_max_model_size_b,
            "safe_context_tokens": self.safe_context_tokens,
            "memory_safety_margin_gb": self.memory_safety_margin_gb,
            "disk_warning_gb": self.disk_warning_gb,
            "unified_memory": self.unified_memory,
            "dedicated_vram_gb": self.dedicated_vram_gb,
            "warnings": list(self.warnings),
            "source": self.source,
            "downloads_performed": self.downloads_performed,
        }

    def estimate_model_fit(
        self,
        *,
        model_id: str,
        parameter_count_b: float,
        memory_estimate_gb: Optional[float] = None,
        disk_estimate_gb: Optional[float] = None,
        quantization: str = "q4",
    ) -> ModelFitResult:
        """Estimate whether a model is safe on this profile.

        Memory estimate (if missing): rough Q4 ~0.6 GB per billion params + 0.5 OS overhead,
        then caller compares against available memory minus safety margin.
        """
        mem = memory_estimate_gb
        if mem is None:
            q = (quantization or "q4").lower()
            factor = 0.55 if "q4" in q or "int4" in q else 0.9 if "q8" in q or "int8" in q else 1.8
            mem = round(parameter_count_b * factor + 0.5, 2)
        disk = disk_estimate_gb if disk_estimate_gb is not None else round(mem * 1.05, 2)

        budget = max(0.0, self.available_memory_gb - self.memory_safety_margin_gb)
        fits_mem = mem <= budget
        fits_disk = disk + self.disk_warning_gb <= self.free_disk_gb + disk  # download leaves margin
        # clearer: free disk after download should stay above disk_warning_gb
        free_after = self.free_disk_gb - disk
        fits_disk = free_after >= self.disk_warning_gb

        warnings: list[str] = []
        if not fits_mem:
            warnings.append(
                f"memory pressure risk: model needs ~{mem} GB, "
                f"safe budget ~{budget:.1f} GB (available {self.available_memory_gb:.1f} "
                f"minus margin {self.memory_safety_margin_gb})"
            )
        if not fits_disk:
            warnings.append(
                f"disk pressure risk: download ~{disk} GB would leave "
                f"~{free_after:.1f} GB free (warning threshold {self.disk_warning_gb} GB)"
            )
        if parameter_count_b > self.recommended_max_model_size_b:
            warnings.append(
                f"parameter count {parameter_count_b}B exceeds recommended max "
                f"{self.recommended_max_model_size_b}B for this device"
            )
        recommended = fits_mem and fits_disk and parameter_count_b <= self.recommended_max_model_size_b
        return ModelFitResult(
            model_id=model_id,
            memory_estimate_gb=mem,
            disk_estimate_gb=disk,
            fits_memory=fits_mem,
            fits_disk=fits_disk,
            warnings=tuple(warnings),
            recommended=recommended,
        )


def _sysctl(key: str) -> str:
    try:
        out = subprocess.run(
            ["sysctl", "-n", key],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        if out.returncode == 0:
            return (out.stdout or "").strip()
    except Exception:
        pass
    return ""


def _memory_gb() -> tuple[float, float]:
    """Return (total_gb, available_gb). Best-effort; no extra deps."""
    total = 0.0
    available = 0.0
    # macOS
    raw = _sysctl("hw.memsize")
    if raw.isdigit():
        total = int(raw) / (1024 ** 3)
    # page stats for available (approx free+inactive)
    try:
        out = subprocess.run(
            ["vm_stat"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        if out.returncode == 0 and total:
            page_size = 4096
            free = inactive = speculative = 0
            for line in out.stdout.splitlines():
                if "page size of" in line:
                    # e.g. "Mach Virtual Memory Statistics: (page size of 16384 bytes)"
                    parts = line.split()
                    for i, p in enumerate(parts):
                        if p.isdigit() and i > 0:
                            page_size = int(p)
                            break
                if line.startswith("Pages free"):
                    free = int(line.split(":")[1].strip().rstrip(".").replace(".", ""))
                elif line.startswith("Pages inactive"):
                    inactive = int(line.split(":")[1].strip().rstrip(".").replace(".", ""))
                elif line.startswith("Pages speculative"):
                    speculative = int(line.split(":")[1].strip().rstrip(".").replace(".", ""))
            available = (free + inactive + speculative) * page_size / (1024 ** 3)
    except Exception:
        pass
    if total <= 0:
        # Linux fallback
        try:
            with open("/proc/meminfo", encoding="utf-8") as f:
                info = {}
                for line in f:
                    if ":" in line:
                        k, v = line.split(":", 1)
                        info[k.strip()] = v.strip()
                total = int(info.get("MemTotal", "0").split()[0]) / (1024 ** 2)
                available = int(info.get("MemAvailable", "0").split()[0]) / (1024 ** 2)
        except Exception:
            total, available = 8.0, 4.0  # honest default for this product target
    if available <= 0:
        available = max(0.5, total * 0.4)
    return round(total, 2), round(available, 2)


def _disk_gb(path: Optional[str] = None) -> tuple[float, float]:
    target = path or os.path.expanduser("~")
    try:
        usage = shutil.disk_usage(target)
        return round(usage.free / (1024 ** 3), 2), round(usage.total / (1024 ** 3), 2)
    except Exception:
        return 0.0, 0.0


def _detect_runtimes() -> list[str]:
    found: list[str] = []
    for name in ("ollama", "llama-server", "llama-cli"):
        if shutil.which(name):
            found.append(name if name != "llama-server" else "llama.cpp")
    # OpenAI-compatible local endpoints are config-based, not binary-based
    if os.getenv("OLLAMA_HOST") or os.getenv("OLLAMA_URL"):
        if "ollama" not in found:
            found.append("ollama")
    if os.getenv("SHIMMY_URL") or os.getenv("OPENAI_COMPAT_BASE_URL"):
        found.append("openai_compat")
    if os.getenv("MLX_HOST"):
        found.append("mlx")
    return found


def m2_8gb_reference_profile(
    *,
    free_disk_gb: float = 50.0,
    total_disk_gb: float = 228.0,
    available_memory_gb: float = 3.5,
) -> HardwareProfile:
    """Canonical reference profile for the primary SaathiOS device (tests)."""
    warnings = []
    if free_disk_gb < 25:
        warnings.append("disk below 25 GB free — model downloads discouraged")
    if available_memory_gb < 2.5:
        warnings.append("low available memory — prefer ≤3B Q4 models")
    return HardwareProfile(
        architecture="arm64",
        platform_system="Darwin",
        cpu_brand="Apple M2",
        total_memory_gb=8.0,
        available_memory_gb=available_memory_gb,
        free_disk_gb=free_disk_gb,
        total_disk_gb=total_disk_gb,
        supported_runtimes=["ollama", "openai_compat"],
        recommended_max_model_size_b=3.0,
        safe_context_tokens=4096,
        memory_safety_margin_gb=2.0,
        disk_warning_gb=25.0,
        unified_memory=True,
        dedicated_vram_gb=None,
        warnings=warnings,
        source="reference_m2_8gb",
        downloads_performed=False,
    )


def profile_local_hardware(
    *,
    memory_safety_margin_gb: float = 2.0,
    disk_warning_gb: float = 25.0,
    auto_detect: bool = True,
) -> HardwareProfile:
    """Build a live profile. Never downloads models."""
    if not auto_detect:
        return m2_8gb_reference_profile()

    arch = platform.machine() or "unknown"
    system = platform.system() or "unknown"
    brand = _sysctl("machdep.cpu.brand_string") or platform.processor() or "unknown"
    total_mem, avail_mem = _memory_gb()
    free_disk, total_disk = _disk_gb()
    runtimes = _detect_runtimes()

    # Apple Silicon heuristics
    is_apple_silicon = system == "Darwin" and arch in {"arm64", "aarch64"}
    unified = is_apple_silicon
    recommended_max = 3.0 if total_mem <= 8.5 else 7.0 if total_mem <= 16.5 else 14.0
    safe_ctx = 4096 if total_mem <= 8.5 else 8192 if total_mem <= 16.5 else 16384

    warnings: list[str] = []
    if free_disk < disk_warning_gb:
        warnings.append(
            f"disk pressure: only {free_disk} GB free (threshold {disk_warning_gb} GB)"
        )
    if avail_mem < memory_safety_margin_gb + 1.0:
        warnings.append(
            f"memory pressure: available {avail_mem} GB is near safety margin "
            f"{memory_safety_margin_gb} GB"
        )
    if total_mem <= 8.5:
        warnings.append(
            "8 GB class device: prefer ≤3B Q4 local models; avoid concurrent large loads"
        )
    if not runtimes:
        warnings.append("no local LLM runtime binary detected (ollama etc.)")

    return HardwareProfile(
        architecture=arch,
        platform_system=system,
        cpu_brand=brand,
        total_memory_gb=total_mem,
        available_memory_gb=avail_mem,
        free_disk_gb=free_disk,
        total_disk_gb=total_disk,
        supported_runtimes=runtimes,
        recommended_max_model_size_b=recommended_max,
        safe_context_tokens=safe_ctx,
        memory_safety_margin_gb=memory_safety_margin_gb,
        disk_warning_gb=disk_warning_gb,
        unified_memory=unified,
        dedicated_vram_gb=None,
        warnings=warnings,
        source="detected",
        downloads_performed=False,
    )
