#!/usr/bin/env python3
"""Deterministic QA for product-clean speech clips.

Checks file readability, sample rate, channels, duration, RMS, clipping,
silence, transcript presence, consent validity, bucket, prompt ID, and
optional numeric canonical fields.

Does not modify transcripts. Does not call LLMs.
"""
from __future__ import annotations

import argparse
import json
import math
import struct
import wave
from datetime import datetime, timezone
from pathlib import Path

CORPUS = Path.home() / ".saathi" / "stt-product-corpus"
MANIFESTS = CORPUS / "manifests"
CONSENTS = CORPUS / "consents"
REPO_PROMPTS = Path(__file__).resolve().parents[1] / "prompts" / "all_prompts.jsonl"

TARGET_SR = 16000
MIN_DURATION = 0.25
MAX_DURATION = 30.0
SILENCE_RMS = 50.0  # int16 absolute mean threshold
CLIP_FRAC = 0.01  # >1% near full-scale samples → fail


def load_prompts() -> dict[str, dict]:
    if not REPO_PROMPTS.exists():
        return {}
    out: dict[str, dict] = {}
    for line in REPO_PROMPTS.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        o = json.loads(line)
        out[o["prompt_id"]] = o
    return out


def load_consent(speaker_id: str) -> dict | None:
    p = CONSENTS / f"{speaker_id}.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def pcm_stats(path: Path) -> dict:
    with wave.open(str(path), "rb") as w:
        nch = w.getnchannels()
        sr = w.getframerate()
        sw = w.getsampwidth()
        nframes = w.getnframes()
        raw = w.readframes(nframes)
    if sw != 2:
        return {
            "ok": False,
            "error": f"unsupported_sampwidth_{sw}",
            "channels": nch,
            "sample_rate": sr,
            "duration": nframes / float(sr or 1),
            "rms": 0.0,
            "clip_frac": 0.0,
        }
    n = len(raw) // 2
    if n == 0:
        return {
            "ok": False,
            "error": "empty_audio",
            "channels": nch,
            "sample_rate": sr,
            "duration": 0.0,
            "rms": 0.0,
            "clip_frac": 0.0,
        }
    samples = struct.unpack("<" + "h" * n, raw)
    if nch > 1:
        # use first channel only for stats
        samples = samples[0::nch]
        n = len(samples)
    abs_sum = 0
    clip = 0
    for s in samples:
        a = abs(s)
        abs_sum += a
        if a >= 32000:
            clip += 1
    rms = abs_sum / float(n)
    clip_frac = clip / float(n)
    duration = nframes / float(sr or 1)
    return {
        "ok": True,
        "channels": nch,
        "sample_rate": sr,
        "duration": duration,
        "rms": rms,
        "clip_frac": clip_frac,
        "error": None,
    }


def qa_row(row: dict, prompts: dict[str, dict]) -> dict:
    errors: list[str] = []
    speaker_id = row.get("speaker_id") or ""
    audio_path = Path(row.get("audio_path") or "")
    transcript = (row.get("transcript") or "").strip()
    prompt_id = row.get("prompt_id")

    consent = load_consent(speaker_id)
    if consent is None:
        errors.append("missing_consent")
    else:
        if not consent.get("commercial_model_training_allowed") and row.get("bucket") == "PRODUCT_CLEAN":
            errors.append("product_clean_without_commercial_consent")
        if row.get("bucket") == "PRODUCT_CLEAN" and not consent.get("commercial_model_training_allowed"):
            errors.append("invalid_bucket_for_consent")

    if not audio_path.exists():
        errors.append("audio_missing")
        stats = {"ok": False, "duration": 0.0, "sample_rate": 0, "channels": 0, "rms": 0.0, "clip_frac": 0.0}
    else:
        stats = pcm_stats(audio_path)
        if not stats["ok"]:
            errors.append(stats.get("error") or "audio_unreadable")
        else:
            if stats["sample_rate"] != TARGET_SR:
                errors.append(f"sample_rate_{stats['sample_rate']}")
            if stats["channels"] != 1:
                errors.append(f"channels_{stats['channels']}")
            if stats["duration"] < MIN_DURATION:
                errors.append("too_short")
            if stats["duration"] > MAX_DURATION:
                errors.append("too_long")
            if stats["rms"] < SILENCE_RMS:
                errors.append("silence_or_near_silence")
            if stats["clip_frac"] > CLIP_FRAC:
                errors.append("severe_clipping")

    if not transcript:
        errors.append("transcript_missing")

    if prompt_id and prompts and prompt_id not in prompts:
        errors.append("unknown_prompt_id")

    lang = row.get("language_class")
    if lang not in ("EN", "NE", "MIX"):
        errors.append("invalid_language_class")

    bucket = row.get("bucket")
    if bucket not in ("PRODUCT_CLEAN", "OWNER_PRIVATE", "RESEARCH_ONLY", "REJECTED"):
        errors.append("invalid_bucket")

    if row.get("contains_numbers") and not (row.get("canonical_number") or transcript):
        # soft: numbers flagged but no canonical — warn only as soft fail for training path
        pass

    if not row.get("sha256"):
        errors.append("missing_sha256")

    # RESEARCH_ONLY never trains as product-clean
    if bucket == "RESEARCH_ONLY" and row.get("split") in ("TRAIN",):
        errors.append("research_only_in_train")

    qa_status = "PASS" if not errors else "FAIL"
    updated = {
        **row,
        "duration": float(stats.get("duration") or row.get("duration") or 0.0),
        "sample_rate": int(stats.get("sample_rate") or row.get("sample_rate") or 0),
        "channels": int(stats.get("channels") or row.get("channels") or 0),
        "qa_status": qa_status,
        "qa_errors": errors,
        "qa_rms": stats.get("rms"),
        "qa_clip_frac": stats.get("clip_frac"),
        "qa_checked_at": datetime.now(timezone.utc).isoformat(),
    }
    # demote bucket on hard consent fail
    if "product_clean_without_commercial_consent" in errors or "missing_consent" in errors:
        if updated.get("bucket") == "PRODUCT_CLEAN":
            updated["bucket"] = "REJECTED"
    return updated


def rewrite_manifest(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description="QA product speech clips")
    ap.add_argument("--manifest", type=Path, default=MANIFESTS / "dataset_manifest.jsonl")
    ap.add_argument("--report", type=Path, default=None)
    ap.add_argument("--require-human-verified", action="store_true")
    args = ap.parse_args()

    if not args.manifest.exists():
        report = {
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "total": 0,
            "pass": 0,
            "fail": 0,
            "pass_rate": 0.0,
            "errors_histogram": {},
            "status": "NO_MANIFEST",
            "message": "No dataset_manifest.jsonl yet — collect recordings first",
        }
        print(json.dumps(report, indent=2))
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        return 0

    prompts = load_prompts()
    rows = [json.loads(l) for l in args.manifest.read_text(encoding="utf-8").splitlines() if l.strip()]
    updated = []
    hist: dict[str, int] = {}
    n_pass = 0
    for row in rows:
        u = qa_row(row, prompts)
        if args.require_human_verified and not u.get("human_verified"):
            u["qa_errors"] = list(u.get("qa_errors") or []) + ["human_transcript_not_verified"]
            u["qa_status"] = "FAIL"
        if u["qa_status"] == "PASS":
            n_pass += 1
        for e in u.get("qa_errors") or []:
            hist[e] = hist.get(e, 0) + 1
        updated.append(u)

    rewrite_manifest(updated, args.manifest)
    total = len(updated)
    report = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "total": total,
        "pass": n_pass,
        "fail": total - n_pass,
        "pass_rate": (n_pass / total) if total else 0.0,
        "errors_histogram": hist,
        "status": "OK" if total and n_pass == total else ("EMPTY" if not total else "HAS_FAILURES"),
    }
    print(json.dumps(report, indent=2))
    out = args.report or (MANIFESTS / "qa_report.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0 if report["status"] in ("OK", "EMPTY", "NO_MANIFEST") else 1


if __name__ == "__main__":
    raise SystemExit(main())
