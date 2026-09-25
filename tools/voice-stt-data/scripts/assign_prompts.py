#!/usr/bin/env python3
"""Generate balanced per-speaker prompt assignments BEFORE recording.

Preferred split plan (speaker-disjoint):
  spk_001, spk_002, spk_003 → TRAIN
  spk_004                   → VALIDATION
  spk_005                   → TEST

Does not record audio. Does not invent clips.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PROMPTS = REPO / "prompts" / "all_prompts.jsonl"
CORPUS = Path.home() / ".saathi" / "stt-product-corpus"
CAMPAIGN = CORPUS / "campaign"

# Per-speaker accepted targets (approximate)
TARGETS = {
    "MIX": (100, 110),
    "numeric": (40, 45),
    "NE": (15, 20),
    "EN": (15, 20),
    "interrupt": (5, 10),
}

SPEAKER_SPLIT = {
    "spk_001": "TRAIN",
    "spk_002": "TRAIN",
    "spk_003": "TRAIN",
    "spk_004": "VALIDATION",
    "spk_005": "TEST",
}


def load_prompts() -> list[dict]:
    rows = []
    with PROMPTS.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def bucket_prompt(p: dict) -> str:
    if p.get("category") == "interrupt":
        return "interrupt"
    if p.get("contains_numbers"):
        return "numeric"
    lang = p.get("language_class") or "MIX"
    if lang == "NE":
        return "NE"
    if lang == "EN":
        return "EN"
    return "MIX"


def prioritize(pools: dict[str, list[dict]]) -> list[str]:
    # Collection priority: MIX+numeric, MIX, financial, NE, EN, interrupt
    return ["numeric", "MIX", "NE", "EN", "interrupt"]


def assign(speakers: list[str], seed: int = 42) -> dict:
    prompts = load_prompts()
    # stable shuffle by seed without random module variability across py versions:
    # rotate by seed
    prompts = prompts[seed % max(len(prompts), 1) :] + prompts[: seed % max(len(prompts), 1)]
    # sort then re-bucket for determinism with offset
    by_id = sorted(prompts, key=lambda p: p["prompt_id"])
    # salt order
    by_id = sorted(by_id, key=lambda p: (hash(p["prompt_id"] + str(seed)) % 10_000, p["prompt_id"]))

    pools: dict[str, list[dict]] = defaultdict(list)
    for p in by_id:
        pools[bucket_prompt(p)].append(p)

    # per-bucket targets use mid of range
    take = {
        "MIX": 105,
        "numeric": 42,
        "NE": 18,
        "EN": 18,
        "interrupt": 8,
    }

    assignments: dict[str, list[dict]] = {s: [] for s in speakers}
    used_global: set[str] = set()

    # Round-robin unique prompts across speakers first (no cross-speaker identical prompt_id preferred)
    for cat in prioritize(pools):
        pool = [p for p in pools[cat] if p["prompt_id"] not in used_global]
        # If pool too small for unique-per-speaker, allow reuse across speakers (same text, different speaker OK)
        for i, spk in enumerate(speakers):
            n = take[cat]
            # slice disjoint chunks when enough
            if len(pool) >= n * len(speakers):
                chunk = pool[i * n : (i + 1) * n]
            else:
                # wrap with offset so speakers get different starts
                chunk = []
                for j in range(n):
                    if not pool:
                        break
                    chunk.append(pool[(i * 7 + j) % len(pool)])
            for p in chunk:
                used_global.add(p["prompt_id"])
                assignments[spk].append(
                    {
                        "speaker_id": spk,
                        "planned_split": SPEAKER_SPLIT.get(spk, "UNASSIGNED"),
                        "prompt_id": p["prompt_id"],
                        "language_class": p.get("language_class"),
                        "category": p.get("category"),
                        "contains_numbers": bool(p.get("contains_numbers")),
                        "contains_financial_terms": bool(p.get("contains_financial_terms")),
                        "assignment_bucket": cat,
                        "text": p["text"],
                        "canonical_number": p.get("canonical_number"),
                        "priority": {
                            "numeric": 1,
                            "MIX": 2,
                            "NE": 4,
                            "EN": 5,
                            "interrupt": 6,
                        }.get(cat, 9),
                    }
                )

    # Sort each speaker's list by priority then prompt_id
    for spk in speakers:
        assignments[spk].sort(key=lambda r: (r["priority"], r["prompt_id"]))

    summary = {}
    for spk, rows in assignments.items():
        c = defaultdict(int)
        for r in rows:
            c[r["assignment_bucket"]] += 1
            if r["language_class"] == "MIX":
                c["lang_MIX"] += 1
            if r["contains_numbers"]:
                c["flag_numeric"] += 1
        summary[spk] = {
            "planned_split": SPEAKER_SPLIT.get(spk),
            "total_assigned": len(rows),
            "by_bucket": dict(c),
        }

    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "campaign": "V-NEXT-2B.6A",
        "speaker_split_plan": SPEAKER_SPLIT,
        "targets_per_speaker": TARGETS,
        "take_per_speaker": take,
        "summary": summary,
        "assignments": assignments,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--speakers", nargs="+", default=list(SPEAKER_SPLIT.keys()))
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out-dir", type=Path, default=CAMPAIGN)
    args = ap.parse_args()

    plan = assign(args.speakers, seed=args.seed)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    plan_path = args.out_dir / "speaker_assignment_plan.json"
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # per-speaker jsonl for session use
    for spk, rows in plan["assignments"].items():
        p = args.out_dir / f"{spk}_assignment.jsonl"
        with p.open("w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # also repo-relative campaign plan (no audio) for git if desired
    repo_campaign = REPO / "campaign"
    repo_campaign.mkdir(parents=True, exist_ok=True)
    slim = {
        "created_at": plan["created_at"],
        "campaign": plan["campaign"],
        "speaker_split_plan": plan["speaker_split_plan"],
        "targets_per_speaker": plan["targets_per_speaker"],
        "take_per_speaker": plan["take_per_speaker"],
        "summary": plan["summary"],
        # store only prompt_ids per speaker (not full text dump optional - keep ids)
        "prompt_ids_by_speaker": {
            spk: [r["prompt_id"] for r in rows] for spk, rows in plan["assignments"].items()
        },
    }
    (repo_campaign / "SPEAKER_ASSIGNMENT_PLAN.json").write_text(
        json.dumps(slim, indent=2) + "\n", encoding="utf-8"
    )

    print(json.dumps(plan["summary"], indent=2, ensure_ascii=False))
    print("wrote", plan_path)
    print("wrote", repo_campaign / "SPEAKER_ASSIGNMENT_PLAN.json")
    total = sum(v["total_assigned"] for v in plan["summary"].values())
    print(f"total_assigned_slots={total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
