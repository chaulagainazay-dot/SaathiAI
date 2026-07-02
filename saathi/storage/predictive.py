"""Predictive Storage Engine — no render starts unless it can finish (SES-019A Part 4).

Smarter than a byte-count guess: it estimates peak disk from the actual render
plan — scene count, duration, fps, resolution — multiplied by a per-renderer
temporary-storage profile, because LTX, Wan, Open-Sora, ComfyUI, and FFmpeg all
leave very different amounts of intermediate data on disk.

    Storyboard → scenes → duration → fps → resolution → renderer
        → expected frame count → expected temp files → peak disk usage → decision

Profiles are a calibratable registry: today they are sensible defaults; later
they get tuned from observed `actual_peak_bytes` in `storage_jobs` (the model
self-corrects, SES-019A §4.1). Testable in isolation (AP-12): free-space reader
and event publisher are injected.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from saathi.events import STORAGE_EVENTS

SAFETY_MARGIN = 1.15
AUDIO_BYTES_PER_SEC = 192_000       # ~wav stereo working audio
FINAL_VIDEO_BYTES_PER_SEC = 1_500_000  # ~12 Mbps encoded output


@dataclass
class RendererProfile:
    name: str
    # intermediate frame footprint, bytes per megapixel per frame
    bytes_per_frame_per_megapixel: float
    # temp/cache kept alongside frames, as a fraction of frame bytes
    cache_multiplier: float
    # whether it writes full frame sequences to disk (vs. streaming latents)
    keeps_frame_sequences: bool = True


# Calibratable registry. Rough profiles — tuned later from real job history.
RENDERER_PROFILES: dict[str, RendererProfile] = {
    "ltx":        RendererProfile("ltx", 3_000_000, 0.4),
    "wan":        RendererProfile("wan", 3_500_000, 0.6),
    "open-sora":  RendererProfile("open-sora", 4_000_000, 0.5),
    "comfyui":    RendererProfile("comfyui", 3_000_000, 1.2),   # heavy latent/cache
    "ffmpeg":     RendererProfile("ffmpeg", 0.0, 0.1, keeps_frame_sequences=False),  # muxing only
}
_DEFAULT_PROFILE = RendererProfile("generic", 3_000_000, 0.6)


@dataclass
class RenderPlan:
    scene_count: int
    avg_scene_duration_s: float
    fps: int
    width: int
    height: int
    renderer: str

    @property
    def total_duration_s(self) -> float:
        return self.scene_count * self.avg_scene_duration_s

    @property
    def frame_count(self) -> int:
        return int(round(self.total_duration_s * self.fps))

    @property
    def megapixels(self) -> float:
        return (self.width * self.height) / 1_000_000


@dataclass
class StorageEstimate:
    frame_count: int
    frames_bytes: int
    audio_bytes: int
    video_bytes: int
    cache_bytes: int
    peak_bytes: int          # sum × safety margin


@dataclass
class RenderDecision:
    estimate: StorageEstimate
    free_bytes: int
    safe: bool
    shortfall_bytes: int      # 0 if safe


def profile_for(renderer: str) -> RendererProfile:
    return RENDERER_PROFILES.get(renderer.lower(), _DEFAULT_PROFILE)


def estimate_plan(plan: RenderPlan) -> StorageEstimate:
    prof = profile_for(plan.renderer)
    frames = 0
    if prof.keeps_frame_sequences:
        frames = int(plan.frame_count * plan.megapixels * prof.bytes_per_frame_per_megapixel)
    cache = int(frames * prof.cache_multiplier) if frames else int(
        plan.total_duration_s * FINAL_VIDEO_BYTES_PER_SEC * prof.cache_multiplier
    )
    audio = int(plan.total_duration_s * AUDIO_BYTES_PER_SEC)
    video = int(plan.total_duration_s * FINAL_VIDEO_BYTES_PER_SEC)
    peak = int((frames + cache + audio + video) * SAFETY_MARGIN)
    return StorageEstimate(plan.frame_count, frames, audio, video, cache, peak)


class PredictiveStorageEngine:
    def __init__(
        self,
        free_reader: Callable[[], int],
        publish: Callable[[str, dict], None] | None = None,
    ):
        self._free = free_reader
        self._publish_fn = publish

    def _publish(self, key: str, payload: dict) -> None:
        if self._publish_fn is not None:
            self._publish_fn(STORAGE_EVENTS[key], payload)

    def decide(self, plan: RenderPlan) -> RenderDecision:
        est = estimate_plan(plan)
        free = self._free()
        safe = est.peak_bytes <= free
        shortfall = 0 if safe else est.peak_bytes - free
        decision = RenderDecision(est, free, safe, shortfall)
        if safe:
            self._publish("render_allowed", {"peak_bytes": est.peak_bytes, "free_bytes": free})
        else:
            self._publish("render_blocked", {
                "required_bytes": est.peak_bytes,
                "free_bytes": free,
                "shortfall_bytes": shortfall,
            })
        return decision
