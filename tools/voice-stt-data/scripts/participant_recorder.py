#!/usr/bin/env python3
"""
Product-clean multi-speaker local recorder.

- Local only: ~/.saathi/stt-product-corpus/
- One prompt at a time; re-record supported
- No auto-upload; raw audio never intended for Git
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import wave
from datetime import datetime, timezone
from pathlib import Path

CORPUS = Path.home() / ".saathi" / "stt-product-corpus"
SPEAKERS = CORPUS / "speakers"
CONSENTS = CORPUS / "consents"
MANIFESTS = CORPUS / "manifests"
REPO_PROMPTS = Path(__file__).resolve().parents[1] / "prompts" / "all_prompts.jsonl"

CONSENT_VERSION = "saathi-product-speech-consent-v1"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def wav_meta(path: Path) -> dict:
    with wave.open(str(path), "rb") as w:
        return {
            "channels": w.getnchannels(),
            "sample_rate": w.getframerate(),
            "duration": w.getnframes() / float(w.getframerate() or 1),
            "sampwidth": w.getsampwidth(),
        }


def record_wav(out: Path, seconds: float) -> bool:
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-f", "avfoundation", "-i", ":0",
        "-t", str(seconds), "-ac", "1", "-ar", "16000", "-sample_fmt", "s16",
        str(out),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode == 0 and out.exists() and out.stat().st_size > 1000


def load_prompts(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def cmd_register(speaker_id: str, commercial: bool, research: bool, evaluation: bool, redistribute: bool) -> int:
    if not speaker_id.startswith("spk_"):
        print("speaker_id must look like spk_001")
        return 2
    CORPUS.mkdir(parents=True, exist_ok=True)
    CONSENTS.mkdir(parents=True, exist_ok=True)
    SPEAKERS.mkdir(parents=True, exist_ok=True)
    (SPEAKERS / speaker_id / "wav").mkdir(parents=True, exist_ok=True)
    consent = {
        "speaker_id": speaker_id,
        "consent_version": CONSENT_VERSION,
        "commercial_model_training_allowed": commercial,
        "internal_research_allowed": research,
        "evaluation_allowed": evaluation,
        "redistribution_allowed": redistribute,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "withdrawal_reference": "contact operator with speaker_id",
        "notes": "",
        "region_group": None,
    }
    path = CONSENTS / f"{speaker_id}.json"
    path.write_text(json.dumps(consent, indent=2) + "\n", encoding="utf-8")
    print("Registered", path)
    if not commercial:
        print("NOTE: commercial_model_training_allowed=false → clips cannot enter PRODUCT_CLEAN train")
    return 0


def append_manifest(row: dict) -> None:
    MANIFESTS.mkdir(parents=True, exist_ok=True)
    path = MANIFESTS / "dataset_manifest.jsonl"
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def cmd_record(speaker_id: str, prompt_id: str | None, seconds: float, device: str, noise: str) -> int:
    consent_path = CONSENTS / f"{speaker_id}.json"
    if not consent_path.exists():
        print("Register consent first:", speaker_id)
        return 2
    consent = json.loads(consent_path.read_text(encoding="utf-8"))
    prompts = load_prompts(REPO_PROMPTS)
    if prompt_id:
        prompt = next((p for p in prompts if p["prompt_id"] == prompt_id), None)
        if not prompt:
            print("Unknown prompt_id")
            return 2
    else:
        # next unfinished for speaker
        done = set()
        man = MANIFESTS / "dataset_manifest.jsonl"
        if man.exists():
            for line in man.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                o = json.loads(line)
                if o.get("speaker_id") == speaker_id and o.get("qa_status") != "FAIL":
                    done.add(o.get("prompt_id"))
        prompt = next((p for p in prompts if p["prompt_id"] not in done), None)
        if not prompt:
            print("No remaining prompts for speaker")
            return 0

    clip_id = f"{speaker_id}_{prompt['prompt_id']}_t01"
    out = SPEAKERS / speaker_id / "wav" / f"{clip_id}.wav"
    print("\n=== RECORD ===")
    print("speaker:", speaker_id)
    print("prompt:", prompt["prompt_id"])
    print("TEXT:", prompt["text"])
    print(f"Recording {seconds}s from default mic…")
    if not record_wav(out, seconds):
        print("RECORD_FAILED")
        return 1
    meta = wav_meta(out)
    digest = sha256_file(out)
    bucket = (
        "PRODUCT_CLEAN"
        if consent.get("commercial_model_training_allowed")
        else "OWNER_PRIVATE"
    )
    row = {
        "clip_id": clip_id,
        "speaker_id": speaker_id,
        "prompt_id": prompt["prompt_id"],
        "audio_path": str(out),
        "transcript": prompt["text"],  # default; human may correct later
        "language_class": prompt.get("language_class", "MIX"),
        "contains_numbers": bool(prompt.get("contains_numbers")),
        "contains_financial_terms": bool(prompt.get("contains_financial_terms")),
        "duration": meta["duration"],
        "sample_rate": meta["sample_rate"],
        "channels": meta["channels"],
        "device_label": device,
        "noise_class": noise,
        "split": "UNASSIGNED",
        "consent_ref": str(consent_path),
        "sha256": digest,
        "qa_status": "PENDING",
        "qa_errors": [],
        "bucket": bucket,
        "human_verified": False,
        "canonical_number": prompt.get("canonical_number"),
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "take": 1,
    }
    append_manifest(row)
    print("Saved", out)
    print("sha256", digest[:16], "…")
    print("bucket", bucket, "qa_status PENDING (run qa_clips.py)")
    return 0


def cmd_rerecord(clip_id: str, seconds: float) -> int:
    man = MANIFESTS / "dataset_manifest.jsonl"
    if not man.exists():
        print("No manifest")
        return 2
    rows = [json.loads(l) for l in man.read_text(encoding="utf-8").splitlines() if l.strip()]
    row = next((r for r in rows if r["clip_id"] == clip_id), None)
    if not row:
        print("clip not found")
        return 2
    out = Path(row["audio_path"])
    take = int(row.get("take") or 1) + 1
    new_id = f"{row['speaker_id']}_{row['prompt_id']}_t{take:02d}"
    new_out = out.parent / f"{new_id}.wav"
    print("Re-record", clip_id, "→", new_id)
    print("TEXT:", row["transcript"])
    if not record_wav(new_out, seconds):
        return 1
    meta = wav_meta(new_out)
    row = {
        **row,
        "clip_id": new_id,
        "audio_path": str(new_out),
        "duration": meta["duration"],
        "sample_rate": meta["sample_rate"],
        "channels": meta["channels"],
        "sha256": sha256_file(new_out),
        "qa_status": "PENDING",
        "qa_errors": [],
        "human_verified": False,
        "take": take,
        "replaces": clip_id,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    append_manifest(row)
    print("Saved", new_out)
    return 0


def cmd_status() -> int:
    man = MANIFESTS / "dataset_manifest.jsonl"
    consents = list(CONSENTS.glob("spk_*.json")) if CONSENTS.exists() else []
    n = 0
    speakers = set()
    if man.exists():
        for line in man.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            o = json.loads(line)
            n += 1
            speakers.add(o.get("speaker_id"))
    print(f"consents={len(consents)} clips_in_manifest={n} speakers_with_clips={len(speakers)}")
    for c in sorted(consents):
        d = json.loads(c.read_text(encoding="utf-8"))
        print(
            f"  {d['speaker_id']}: commercial={d.get('commercial_model_training_allowed')} "
            f"redistribute={d.get('redistribution_allowed')}"
        )
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Product-clean multi-speaker recorder")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("register")
    r.add_argument("--speaker-id", required=True)
    r.add_argument("--commercial", action="store_true")
    r.add_argument("--research", action="store_true", default=True)
    r.add_argument("--evaluation", action="store_true", default=True)
    r.add_argument("--redistribute", action="store_true", default=False)

    rec = sub.add_parser("record")
    rec.add_argument("--speaker-id", required=True)
    rec.add_argument("--prompt-id")
    rec.add_argument("--seconds", type=float, default=5.0)
    rec.add_argument("--device", default="mac_builtin")
    rec.add_argument("--noise", default="quiet")

    rr = sub.add_parser("rerecord")
    rr.add_argument("--clip-id", required=True)
    rr.add_argument("--seconds", type=float, default=5.0)

    sub.add_parser("status")

    args = ap.parse_args()
    if args.cmd == "register":
        return cmd_register(
            args.speaker_id,
            args.commercial,
            args.research,
            args.evaluation,
            args.redistribute,
        )
    if args.cmd == "record":
        return cmd_record(args.speaker_id, args.prompt_id, args.seconds, args.device, args.noise)
    if args.cmd == "rerecord":
        return cmd_rerecord(args.clip_id, args.seconds)
    if args.cmd == "status":
        return cmd_status()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
