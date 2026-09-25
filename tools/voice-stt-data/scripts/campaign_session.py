#!/usr/bin/env python3
"""Guided single-clip recording from pre-built speaker assignment.

Requires a live human at the microphone. Does not synthesize speech.
Does not auto-verify transcripts as human_verified.

Usage:
  python3 campaign_session.py next --speaker-id spk_001
  python3 campaign_session.py record-next --speaker-id spk_001 --seconds 5
  python3 campaign_session.py status --speaker-id spk_001
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

CORPUS = Path.home() / ".saathi" / "stt-product-corpus"
CAMPAIGN = CORPUS / "campaign"
MANIFESTS = CORPUS / "manifests"
SCRIPTS = Path(__file__).resolve().parent


def load_assignment(speaker_id: str) -> list[dict]:
    path = CAMPAIGN / f"{speaker_id}_assignment.jsonl"
    if not path.exists():
        print("No assignment for", speaker_id, "- run assign_prompts.py first", file=sys.stderr)
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def done_prompt_ids(speaker_id: str) -> set[str]:
    man = MANIFESTS / "dataset_manifest.jsonl"
    done = set()
    if not man.exists():
        return done
    for line in man.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        o = json.loads(line)
        if o.get("speaker_id") == speaker_id and o.get("qa_status") != "FAIL":
            if o.get("prompt_id"):
                done.add(o["prompt_id"])
    return done


def next_item(speaker_id: str) -> dict | None:
    done = done_prompt_ids(speaker_id)
    for row in load_assignment(speaker_id):
        if row["prompt_id"] not in done:
            return row
    return None


def cmd_next(speaker_id: str) -> int:
    item = next_item(speaker_id)
    if not item:
        print("COMPLETE_OR_EMPTY", speaker_id)
        return 0
    print(json.dumps(item, ensure_ascii=False, indent=2))
    return 0


def cmd_status(speaker_id: str) -> int:
    assign = load_assignment(speaker_id)
    done = done_prompt_ids(speaker_id)
    remaining = [r for r in assign if r["prompt_id"] not in done]
    print(
        json.dumps(
            {
                "speaker_id": speaker_id,
                "assigned": len(assign),
                "done": len(done),
                "remaining": len(remaining),
                "next_prompt_id": remaining[0]["prompt_id"] if remaining else None,
            },
            indent=2,
        )
    )
    return 0


def cmd_record_next(speaker_id: str, seconds: float, device: str, noise: str) -> int:
    item = next_item(speaker_id)
    if not item:
        print("No remaining assigned prompts for", speaker_id)
        return 0
    # ensure registered
    consent = CORPUS / "consents" / f"{speaker_id}.json"
    if not consent.exists():
        print("Register commercial consent first:", speaker_id)
        return 2
    cmd = [
        sys.executable,
        str(SCRIPTS / "participant_recorder.py"),
        "record",
        "--speaker-id",
        speaker_id,
        "--prompt-id",
        item["prompt_id"],
        "--seconds",
        str(seconds),
        "--device",
        device,
        "--noise",
        noise,
    ]
    print("TEXT TO SPEAK:", item["text"])
    print("Running recorder… (live mic required)")
    return subprocess.call(cmd)


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    for name in ("next", "status", "record-next"):
        p = sub.add_parser(name)
        p.add_argument("--speaker-id", required=True)
        if name == "record-next":
            p.add_argument("--seconds", type=float, default=5.0)
            p.add_argument("--device", default="mac_builtin")
            p.add_argument("--noise", default="quiet")

    args = ap.parse_args()
    if args.cmd == "next":
        return cmd_next(args.speaker_id)
    if args.cmd == "status":
        return cmd_status(args.speaker_id)
    if args.cmd == "record-next":
        return cmd_record_next(args.speaker_id, args.seconds, args.device, args.noise)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
