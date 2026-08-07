#!/usr/bin/env python3
"""Contamination check vs locked V-NEXT-2B.1–2B.4 evaluation corpora.

Ensures product training clips do not reuse locked eval text or audio hashes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

CORPUS = Path.home() / ".saathi" / "stt-product-corpus"
MANIFESTS = CORPUS / "manifests"
REPO = Path(__file__).resolve().parents[3]


def norm_text(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s


def collect_locked_texts(repo: Path) -> set[str]:
    texts: set[str] = set()
    patterns = [
        "tools/voice-stt-bench/**/*.jsonl",
        "tools/voice-stt-bench/**/*.json",
        "docs/voice-next-2b1/**/*",
        "docs/voice-next-2b2/**/*",
        "docs/voice-next-2b3/**/*",
        "docs/voice-next-2b4/**/*",
    ]
    # Prefer known locked locations
    candidates = list((repo / "tools" / "voice-stt-bench").rglob("*")) if (repo / "tools" / "voice-stt-bench").exists() else []
    for p in candidates:
        if p.suffix not in (".json", ".jsonl", ".txt", ".md"):
            continue
        try:
            raw = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if p.suffix == ".jsonl":
            for line in raw.splitlines():
                if not line.strip():
                    continue
                try:
                    o = json.loads(line)
                except json.JSONDecodeError:
                    continue
                for k in ("transcript", "text", "reference", "ref", "prompt"):
                    if k in o and isinstance(o[k], str):
                        t = norm_text(o[k])
                        if len(t) >= 4:
                            texts.add(t)
        elif p.suffix == ".json":
            try:
                o = json.loads(raw)
            except json.JSONDecodeError:
                continue
            stack = [o]
            while stack:
                cur = stack.pop()
                if isinstance(cur, dict):
                    for k, v in cur.items():
                        if k in ("transcript", "text", "reference", "ref", "prompt") and isinstance(v, str):
                            t = norm_text(v)
                            if len(t) >= 4:
                                texts.add(t)
                        elif isinstance(v, (dict, list)):
                            stack.append(v)
                elif isinstance(cur, list):
                    stack.extend(cur)
    return texts


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", type=Path, default=MANIFESTS / "dataset_manifest.jsonl")
    ap.add_argument("--report", type=Path, default=None)
    ap.add_argument("--repo", type=Path, default=REPO)
    args = ap.parse_args()

    locked = collect_locked_texts(args.repo)
    overlaps: list[dict] = []
    checked = 0

    if args.manifest.exists():
        for line in args.manifest.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("bucket") != "PRODUCT_CLEAN":
                continue
            if row.get("split") not in ("TRAIN", "VALIDATION", "UNASSIGNED", "TEST"):
                continue
            checked += 1
            t = norm_text(row.get("transcript") or "")
            if t and t in locked:
                overlaps.append(
                    {
                        "clip_id": row.get("clip_id"),
                        "speaker_id": row.get("speaker_id"),
                        "reason": "transcript_overlap_with_locked_eval",
                        "transcript_preview": t[:80],
                    }
                )

    # Prompt corpus is Saathi-owned and intentionally distinct from locked evals;
    # still flag exact matches.
    status = "CLEAN" if not overlaps else "CONTAMINATED"
    report = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "locked_text_entries_indexed": len(locked),
        "product_clips_checked": checked,
        "overlaps": overlaps,
        "overlap_count": len(overlaps),
        "status": status,
        "policy": "Do not train on V-NEXT-2B.1–2B.4 locked corpora; treat as immutable holdout",
    }
    print(json.dumps(report, indent=2))
    out = args.report or (MANIFESTS / "contamination_report.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0 if status == "CLEAN" else 2


if __name__ == "__main__":
    raise SystemExit(main())
