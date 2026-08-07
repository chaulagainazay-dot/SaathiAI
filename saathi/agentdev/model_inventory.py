"""M370 — Installed-model inventory and the resource baseline that bounds it.

Which local models exist, what each one costs, and which of them this host can
actually evaluate without destabilising itself.

**Read-only by construction.** The inventory is collected over the same
loopback HTTP surface :mod:`saathi.agentdev.model_adapter` uses — ``/api/tags``,
``/api/ps``, ``/api/show`` — all of them GET-or-describe endpoints. Nothing here
pulls, updates, deletes or runs a model. There is no code path in this module
that could: the three endpoint constants are frozen and no other path is
constructed.

**Eligibility is a host finding, not a verdict on the model.** A model that
will not fit in this machine's memory is recorded
``resource_unsuitable_on_current_host``. That says something about an 8 GB
laptop with its swap nearly full; it says nothing about the model. The two are
kept in separate fields precisely so a reader cannot conflate them.

**Thresholds are declared before they are applied.** :data:`THRESHOLDS` is data,
published in the report, and every exclusion names the threshold it tripped and
the measured value that tripped it.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from typing import Any

from saathi.agentdev.model_adapter import DEFAULT_ENDPOINT, assert_loopback
from saathi.agentdev.resources import BYTES_PER_GIB, HostSnapshot, host_snapshot

INVENTORY_VERSION = "agentdev.model_inventory.v1"

#: The only paths this module reads. Frozen: nothing is appended or formatted.
TAGS_PATH = "/api/tags"
PS_PATH = "/api/ps"
SHOW_PATH = "/api/show"

MIB = 1024 ** 2


# --------------------------------------------------------------------------
# Thresholds
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ResourceThresholds:
    """The exact limits this host runs under, chosen before any model was run.

    They are deliberately conservative. The development machine is an Apple M2
    with 8 GiB of unified memory and a swap file that is routinely most of the
    way full; a model that pushes it over starts paging the editor, the test
    runner and the provider daemon against each other, and every latency number
    measured in that state is noise.
    """

    #: A model whose on-disk size exceeds this fraction of physical memory is
    #: not loaded. Unified memory means weights, KV cache and every other
    #: process share one pool, so half is already generous.
    max_model_size_fraction_of_ram: float = 0.5

    #: Swap below this is the strongest signal on this host that the machine is
    #: already paging. Measured before every model run.
    min_free_swap_mib: float = 512.0

    #: Reclaimable memory below this and the load will come straight out of
    #: swap.
    min_available_memory_mib: float = 1024.0

    #: Never fill the disk. Model weights are already on it; this is headroom
    #: for evidence, traces and the system itself.
    min_free_disk_gib: float = 10.0

    #: Darwin's own free percentage, below which a run is deferred.
    min_free_memory_percent: int = 20

    #: One model resident at a time, one evaluation at a time.
    max_resident_models: int = 1
    max_concurrent_evaluations: int = 1

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["rationale"] = (
            "Apple M2, 8 GiB unified memory, single SSD. Unified memory means a "
            "model competes with every other process for one pool, so the size "
            "ceiling is a fraction of physical RAM rather than of free RAM."
        )
        return d


THRESHOLDS = ResourceThresholds()


class Eligibility(str):
    """Why a model is or is not evaluated. Strings, so they survive JSON."""

    ELIGIBLE = "eligible"
    RESOURCE_UNSUITABLE = "resource_unsuitable_on_current_host"
    ADAPTER_INCOMPATIBLE = "adapter_incompatible"
    NOT_INSTALLED = "not_installed"


#: Capabilities the adapter requires. The adapter posts to ``/api/generate``
#: with ``format: json``; a model that cannot complete text cannot be driven.
REQUIRED_CAPABILITIES = frozenset({"completion"})


# --------------------------------------------------------------------------
# Transport
# --------------------------------------------------------------------------


def _get(endpoint: str, path: str, timeout: float = 10.0) -> dict[str, Any]:
    request = urllib.request.Request(f"{endpoint}{path}", method="GET")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _post(endpoint: str, path: str, payload: dict[str, Any], timeout: float = 20.0) -> dict[str, Any]:
    """``/api/show`` is a POST that describes a model. It loads nothing."""
    request = urllib.request.Request(
        f"{endpoint}{path}",
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


# --------------------------------------------------------------------------
# One model
# --------------------------------------------------------------------------


@dataclass
class InstalledModel:
    """One locally installed model, as the provider describes it."""

    name: str
    tag: str = ""
    digest: str = ""
    size_bytes: int = 0
    quantization: str = ""
    family: str = ""
    parameter_size: str = ""
    context_length: int = 0
    capabilities: list[str] = field(default_factory=list)
    installed: bool = True
    running: bool = False
    resident_size_bytes: int = 0
    eligibility: str = Eligibility.ELIGIBLE
    exclusion_reason: str = ""
    expected_memory_bytes: int = 0

    @property
    def size_gib(self) -> float:
        return round(self.size_bytes / BYTES_PER_GIB, 2)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["size_gib"] = self.size_gib
        d["expected_memory_gib"] = round(self.expected_memory_bytes / BYTES_PER_GIB, 2)
        d["digest_short"] = self.digest[:12] if self.digest else ""
        d["memory_note"] = (
            "expected_memory is the on-disk size plus a flat allowance for the "
            "KV cache and provider overhead. It is an estimate stated as one, "
            "not a measurement."
        )
        return d


#: Flat allowance added to on-disk size to estimate resident demand. Ollama's
#: own reported resident sizes on this host ran roughly 0.6–0.8 GiB above the
#: file size for the 1.5B–4B models, so this is rounded up from measurement
#: rather than guessed.
KV_CACHE_ALLOWANCE_BYTES = int(0.8 * BYTES_PER_GIB)


def _split_tag(name: str) -> tuple[str, str]:
    base, _, tag = name.partition(":")
    return base, tag or "latest"


def parse_tags(payload: dict[str, Any]) -> list[InstalledModel]:
    """Build the inventory from ``/api/tags``. Pure; tests drive it directly."""
    models: list[InstalledModel] = []
    for entry in payload.get("models") or []:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or entry.get("model") or "").strip()
        if not name:
            continue
        details = entry.get("details") if isinstance(entry.get("details"), dict) else {}
        _, tag = _split_tag(name)
        models.append(InstalledModel(
            name=name,
            tag=tag,
            digest=str(entry.get("digest") or ""),
            size_bytes=int(entry.get("size") or 0),
            quantization=str(details.get("quantization_level") or ""),
            family=str(details.get("family") or ""),
            parameter_size=str(details.get("parameter_size") or ""),
        ))
    return sorted(models, key=lambda m: m.name)


def parse_ps(payload: dict[str, Any]) -> dict[str, int]:
    """Resident models and their reported sizes, keyed by name. Pure."""
    resident: dict[str, int] = {}
    for entry in payload.get("models") or []:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or entry.get("model") or "").strip()
        if name:
            resident[name] = int(entry.get("size") or 0)
    return resident


def enrich_from_show(model: InstalledModel, payload: dict[str, Any]) -> InstalledModel:
    """Fold ``/api/show`` detail into one model. Pure."""
    info = payload.get("model_info") if isinstance(payload.get("model_info"), dict) else {}
    details = payload.get("details") if isinstance(payload.get("details"), dict) else {}
    caps = payload.get("capabilities")
    if isinstance(caps, list):
        model.capabilities = sorted(str(c) for c in caps)
    if not model.quantization:
        model.quantization = str(details.get("quantization_level") or "")
    if not model.family:
        model.family = str(details.get("family") or "")
    if not model.parameter_size:
        model.parameter_size = str(details.get("parameter_size") or "")
    for key, value in info.items():
        if key.endswith(".context_length") and isinstance(value, int):
            model.context_length = value
            break
    return model


def find_duplicate_digests(models: list[InstalledModel]) -> dict[str, list[str]]:
    """Two names for one set of weights. Recorded, never silently merged."""
    by_digest: dict[str, list[str]] = {}
    for model in models:
        if model.digest:
            by_digest.setdefault(model.digest, []).append(model.name)
    return {d: sorted(n) for d, n in by_digest.items() if len(n) > 1}


# --------------------------------------------------------------------------
# Eligibility
# --------------------------------------------------------------------------


def classify_eligibility(
    model: InstalledModel,
    *,
    total_memory_bytes: int,
    thresholds: ResourceThresholds = THRESHOLDS,
) -> InstalledModel:
    """Decide whether this host may load this model, and say why."""
    model.expected_memory_bytes = model.size_bytes + KV_CACHE_ALLOWANCE_BYTES

    if not model.installed:
        model.eligibility = Eligibility.NOT_INSTALLED
        model.exclusion_reason = "the provider does not list this model"
        return model

    if model.capabilities and not REQUIRED_CAPABILITIES <= set(model.capabilities):
        model.eligibility = Eligibility.ADAPTER_INCOMPATIBLE
        model.exclusion_reason = (
            f"the adapter needs {sorted(REQUIRED_CAPABILITIES)}; this model "
            f"declares {model.capabilities}"
        )
        return model

    if total_memory_bytes > 0:
        ceiling = int(total_memory_bytes * thresholds.max_model_size_fraction_of_ram)
        if model.size_bytes > ceiling:
            model.eligibility = Eligibility.RESOURCE_UNSUITABLE
            model.exclusion_reason = (
                f"on-disk size {model.size_gib} GiB exceeds the host ceiling of "
                f"{round(ceiling / BYTES_PER_GIB, 2)} GiB "
                f"({thresholds.max_model_size_fraction_of_ram:.0%} of "
                f"{round(total_memory_bytes / BYTES_PER_GIB, 2)} GiB physical memory)"
            )
            return model

    model.eligibility = Eligibility.ELIGIBLE
    model.exclusion_reason = ""
    return model


# --------------------------------------------------------------------------
# Baseline
# --------------------------------------------------------------------------


@dataclass
class ResourceBaseline:
    """The machine, immediately before any model was loaded."""

    host: dict[str, Any]
    swap: dict[str, Any]
    pages: dict[str, Any]
    pressure: dict[str, Any]
    resident_models: dict[str, int]
    measured_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "host": self.host,
            "swap": self.swap,
            "pages": self.pages,
            "pressure": self.pressure,
            "resident_models": self.resident_models,
            "resident_count": len(self.resident_models),
            "measured_at": self.measured_at,
        }


def collect_baseline(endpoint: str = DEFAULT_ENDPOINT) -> ResourceBaseline:
    """One reading of the host and the provider. Writes nothing."""
    from saathi.agentdev.host_probe import probe_host

    snapshot: HostSnapshot = host_snapshot()
    probes = probe_host()
    try:
        resident = parse_ps(_get(assert_loopback(endpoint), PS_PATH))
    except (urllib.error.URLError, OSError, json.JSONDecodeError, ValueError):
        resident = {}
    return ResourceBaseline(
        host=snapshot.to_dict(),
        swap=probes.swap,
        pages=probes.pages,
        pressure=probes.pressure,
        resident_models=resident,
    )


@dataclass
class SafetyDecision:
    """May a model be loaded right now? Every breach names its threshold."""

    safe: bool
    breaches: list[str] = field(default_factory=list)
    measurements: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["verdict"] = "proceed" if self.safe else "RESOURCE_LIMIT_EXCEEDED"
        return d


def assess_safety(
    baseline: ResourceBaseline,
    *,
    model: InstalledModel | None = None,
    thresholds: ResourceThresholds = THRESHOLDS,
) -> SafetyDecision:
    """Compare the measured baseline against the declared thresholds.

    An unavailable probe is *not* treated as a pass. It is recorded as a breach
    of the kind "this could not be measured", because proceeding on an
    unmeasured host is exactly what the thresholds exist to prevent — with one
    exception: a probe that reports no support for this platform is skipped
    rather than counted, since a missing Darwin tool on Linux is not a signal
    about memory.
    """
    breaches: list[str] = []
    measurements: dict[str, Any] = {}

    swap = baseline.swap
    if swap.get("available"):
        free_mib = float(swap.get("free_mib", 0.0))
        measurements["free_swap_mib"] = free_mib
        if free_mib < thresholds.min_free_swap_mib:
            breaches.append(
                f"free swap {free_mib} MiB is below the {thresholds.min_free_swap_mib} "
                "MiB floor; the host is already paging"
            )
    elif "no swap probe for" not in str(swap.get("reason", "")):
        breaches.append(f"swap could not be measured: {swap.get('reason')}")

    pages = baseline.pages
    if pages.get("available"):
        available_mib = float(pages.get("available_mib", 0.0))
        measurements["available_memory_mib"] = available_mib
        if available_mib < thresholds.min_available_memory_mib:
            breaches.append(
                f"reclaimable memory {available_mib} MiB is below the "
                f"{thresholds.min_available_memory_mib} MiB floor"
            )
    elif "no vm_stat probe for" not in str(pages.get("reason", "")):
        breaches.append(f"page statistics could not be measured: {pages.get('reason')}")

    pressure = baseline.pressure
    if pressure.get("available"):
        free_pct = int(pressure.get("free_percent", 0))
        measurements["free_memory_percent"] = free_pct
        if free_pct < thresholds.min_free_memory_percent:
            breaches.append(
                f"free memory {free_pct}% is below the "
                f"{thresholds.min_free_memory_percent}% floor"
            )

    free_disk_gib = float(baseline.host.get("disk_free_gib", 0.0))
    measurements["free_disk_gib"] = free_disk_gib
    if free_disk_gib < thresholds.min_free_disk_gib:
        breaches.append(
            f"free disk {free_disk_gib} GiB is below the "
            f"{thresholds.min_free_disk_gib} GiB reserve"
        )

    resident = baseline.resident_models
    measurements["resident_models"] = sorted(resident)
    if model is not None:
        others = sorted(n for n in resident if n != model.name)
        if len(resident) > thresholds.max_resident_models or (
            others and len(others) >= thresholds.max_resident_models
        ):
            breaches.append(
                f"{len(resident)} model(s) already resident ({', '.join(sorted(resident))}); "
                f"the ceiling is {thresholds.max_resident_models}"
            )
        if model.eligibility != Eligibility.ELIGIBLE:
            breaches.append(f"{model.name} is {model.eligibility}: {model.exclusion_reason}")
        measurements["candidate"] = model.name
        measurements["candidate_expected_memory_gib"] = round(
            model.expected_memory_bytes / BYTES_PER_GIB, 2
        )
    elif len(resident) > thresholds.max_resident_models:
        breaches.append(
            f"{len(resident)} model(s) resident; the ceiling is "
            f"{thresholds.max_resident_models}"
        )

    return SafetyDecision(safe=not breaches, breaches=breaches, measurements=measurements)


# --------------------------------------------------------------------------
# The whole inventory
# --------------------------------------------------------------------------


def collect_inventory(
    endpoint: str = DEFAULT_ENDPOINT,
    *,
    thresholds: ResourceThresholds = THRESHOLDS,
    describe: bool = True,
) -> dict[str, Any]:
    """Every installed model, the baseline, and who is eligible to be evaluated.

    Downloads nothing, updates nothing, deletes nothing, loads nothing. An
    unreachable provider is a reported result rather than an exception.
    """
    started = time.perf_counter()
    baseline = collect_baseline(endpoint)
    report: dict[str, Any] = {
        "inventory": INVENTORY_VERSION,
        "endpoint": endpoint,
        "thresholds": thresholds.to_dict(),
        "baseline": baseline.to_dict(),
        "read_only": True,
        "endpoints_read": [TAGS_PATH, PS_PATH, SHOW_PATH],
    }

    try:
        resolved = assert_loopback(endpoint)
        tags = _get(resolved, TAGS_PATH)
    except (urllib.error.URLError, OSError, json.JSONDecodeError, ValueError) as exc:
        report["provider_reachable"] = False
        report["error"] = f"{type(exc).__name__}: {exc}"[:200]
        report["models"] = []
        report["eligible"] = []
        report["duration_ms"] = round((time.perf_counter() - started) * 1000, 3)
        return report

    report["provider_reachable"] = True
    models = parse_tags(tags)
    resident = baseline.resident_models
    total_memory = int(baseline.host.get("total_memory_bytes") or 0)

    for model in models:
        if describe:
            try:
                enrich_from_show(model, _post(resolved, SHOW_PATH, {"model": model.name}))
            except (urllib.error.URLError, OSError, json.JSONDecodeError):
                pass  # detail is optional; the tags entry already stands
        model.running = model.name in resident
        model.resident_size_bytes = resident.get(model.name, 0)
        classify_eligibility(model, total_memory_bytes=total_memory, thresholds=thresholds)

    report["models"] = [m.to_dict() for m in models]
    report["model_count"] = len(models)
    report["eligible"] = [m.name for m in models if m.eligibility == Eligibility.ELIGIBLE]
    report["excluded"] = [
        {"model": m.name, "eligibility": m.eligibility, "reason": m.exclusion_reason}
        for m in models if m.eligibility != Eligibility.ELIGIBLE
    ]
    report["duplicate_digests"] = find_duplicate_digests(models)
    report["missing_digest"] = sorted(m.name for m in models if not m.digest)
    report["safety"] = assess_safety(baseline, thresholds=thresholds).to_dict()
    report["duration_ms"] = round((time.perf_counter() - started) * 1000, 3)
    report["limitation"] = (
        "One reading of one host. Eligibility is a statement about this "
        "machine's memory at this moment, never about a model's quality: a "
        "model excluded as resource_unsuitable_on_current_host has not been "
        "evaluated and nothing here suggests how it would score."
    )
    return report
