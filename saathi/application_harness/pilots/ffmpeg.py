"""M17.3 FFmpeg/FFprobe pilot harness — WRAPS the existing canonical tools.

SaathiOS already uses ffmpeg/ffprobe (M13 Studio); this wraps them in the harness
contract rather than building a new media pipeline. Argv is built from trusted
constants + validated inputs (never a shell string). Operations: probe_media
(risk 0), transcode (risk 1, output confined to the pilot workspace). Output is
independently verified with ffprobe + checksum.
"""
from __future__ import annotations

import shutil

from saathi.application_harness.models import (
    HarnessDefinition, HarnessOperation, TrustStatus, SideEffect,
)


def ffmpeg_path() -> str | None:
    return shutil.which("ffmpeg")


def ffprobe_path() -> str | None:
    return shutil.which("ffprobe")


def available() -> dict:
    return {"ffmpeg": ffmpeg_path(), "ffprobe": ffprobe_path(),
            "available": bool(ffmpeg_path() and ffprobe_path())}


def definition() -> HarnessDefinition:
    d = HarnessDefinition(
        harness_id="ffmpeg", display_name="FFmpeg Media", application_name="ffmpeg",
        application_vendor="FFmpeg", version="system", source_type="local",
        license="LGPL/GPL (system)", install_method="system_executable",
        entrypoint=ffmpeg_path() or "ffmpeg",
        required_executables=["ffmpeg", "ffprobe"], risk_ceiling=1,
        supported_operations=["probe_media", "transcode"],
        verification_strategy="ffprobe+checksum",
        # this is a first-party wrap of an already-trusted tool → trusted
        trust_status=TrustStatus.TRUSTED.value, validation_status="wrapped_canonical")
    return d


def operations() -> list[HarnessOperation]:
    return [
        HarnessOperation("probe_media", "ffmpeg", "Probe media",
                         description="Read container/streams/duration via ffprobe.",
                         risk=0, approval_requirement="auto",
                         side_effect_type=SideEffect.NONE.value,
                         allowed_file_access="roots", idempotency_behavior="idempotent",
                         expected_artifacts=[], verification_rules=["media"]),
        HarnessOperation("transcode", "ffmpeg", "Transcode/remux",
                         description="Transcode a source to an output in the pilot workspace.",
                         risk=1, approval_requirement="auto",
                         side_effect_type=SideEffect.LOCAL_REVERSIBLE.value,
                         allowed_file_access="roots", idempotency_behavior="conditional",
                         expected_artifacts=["output"], verification_rules=["media", "checksum"]),
    ]


# ── argv builders (trusted constants + validated inputs; NEVER shell) ────────
def build_probe_argv(*, input_path: str) -> list[str]:
    return [ffprobe_path() or "ffprobe", "-v", "error", "-show_format",
            "-show_streams", "-of", "json", input_path]


def build_transcode_argv(*, input_path: str, output_path: str,
                         codec: str = "libx264") -> list[str]:
    # codec is validated against an allow-list by the operation input schema
    return [ffmpeg_path() or "ffmpeg", "-y", "-v", "error", "-i", input_path,
            "-c:v", codec, "-t", "1", output_path]


ALLOWED_CODECS = {"libx264", "libx265", "copy", "mpeg4", "vp9"}


def validate_transcode_args(args: dict) -> tuple[bool, str]:
    codec = args.get("codec", "libx264")
    if codec not in ALLOWED_CODECS:
        return False, "HARNESS_ARGUMENT_REJECTED:codec"
    for k in ("input_path", "output_path"):
        v = str(args.get(k, ""))
        if not v or any(c in v for c in (";", "|", "&", "`", "$", "\n")):
            return False, f"HARNESS_ARGUMENT_REJECTED:{k}"
    return True, "ok"
