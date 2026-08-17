#!/usr/bin/env python3
"""Local collection campaign progress (no fabrication)."""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

CORPUS = Path.home() / ".saathi" / "stt-product-corpus"
MANIFESTS = CORPUS / "manifests"
CONSENTS = CORPUS / "consents"
CAMPAIGN = CORPUS / "campaign"
REPO = Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", type=Path, default=CAMPAIGN / "PROGRESS_REPORT.json")
    ap.add_argument("--md", type=Path, default=CAMPAIGN / "PROGRESS_REPORT.md")
    args = ap.parse_args()

    consents = []
    if CONSENTS.exists():
        for p in CONSENTS.glob("spk_*.json"):
            consents.append(json.loads(p.read_text(encoding="utf-8")))

    rows = []
    man = MANIFESTS / "dataset_manifest.jsonl"
    if man.exists():
        rows = [json.loads(l) for l in man.read_text(encoding="utf-8").splitlines() if l.strip()]

    commercial = [c for c in consents if c.get("commercial_model_training_allowed")]
    clean_pass = [r for r in rows if r.get("bucket") == "PRODUCT_CLEAN" and r.get("qa_status") == "PASS"]
    rejected = [r for r in rows if r.get("qa_status") == "FAIL" or r.get("bucket") == "REJECTED"]
    pending = [r for r in rows if r.get("qa_status") == "PENDING"]

    by_spk = Counter(r.get("speaker_id") for r in clean_pass)
    mix = sum(1 for r in clean_pass if r.get("language_class") == "MIX")
    # numeric may also be MIX
    numeric = sum(1 for r in clean_pass if r.get("contains_numbers"))
    en = sum(1 for r in clean_pass if r.get("language_class") == "EN")
    ne = sum(1 for r in clean_pass if r.get("language_class") == "NE")
    # interrupt heuristic: short or category
    interrupt = sum(
        1
        for r in clean_pass
        if (r.get("prompt_id") or "").startswith("int_")
        or (r.get("duration") or 99) < 1.5
        and r.get("language_class") in ("EN", "NE", "MIX")
        and len((r.get("transcript") or "").split()) <= 4
    )
    hours = sum(float(r.get("duration") or 0) for r in clean_pass) / 3600.0
    qa_total = len(rows)
    qa_pass = sum(1 for r in rows if r.get("qa_status") == "PASS")
    qa_rate = (qa_pass / qa_total) if qa_total else 0.0
    human_v = sum(1 for r in clean_pass if r.get("human_verified"))
    devices = Counter(r.get("device_label") or "unknown" for r in clean_pass)
    noise = Counter(r.get("noise_class") or "unknown" for r in clean_pass)

    split_report = {}
    if (MANIFESTS / "split_report.json").exists():
        split_report = json.loads((MANIFESTS / "split_report.json").read_text(encoding="utf-8"))
    contam = {}
    if (MANIFESTS / "contamination_report.json").exists():
        contam = json.loads((MANIFESTS / "contamination_report.json").read_text(encoding="utf-8"))
    auth = {}
    if (MANIFESTS / "training_authorization_report.json").exists():
        auth = json.loads((MANIFESTS / "training_authorization_report.json").read_text(encoding="utf-8"))

    assignment = {}
    apath = CAMPAIGN / "speaker_assignment_plan.json"
    if apath.exists():
        a = json.loads(apath.read_text(encoding="utf-8"))
        assignment = a.get("summary", {})

    blockers = []
    if len(commercial) < 5:
        blockers.append("need_>=5_commercial_consents")
    if len({r["speaker_id"] for r in clean_pass}) < 5:
        blockers.append("need_>=5_speakers_with_pass_clips")
    if mix < 500:
        blockers.append(f"mix_clean_{mix}_of_500")
    if numeric < 200:
        blockers.append(f"numeric_clean_{numeric}_of_200")
    if human_v < len(clean_pass) or (clean_pass and human_v == 0):
        if clean_pass:
            blockers.append(f"human_verified_{human_v}_of_{len(clean_pass)}")
        else:
            blockers.append("no_clips_to_verify")
    if not split_report.get("speaker_disjoint"):
        blockers.append("speaker_disjoint_holdout_not_ready")
    if contam and contam.get("status") not in (None, "CLEAN"):
        blockers.append("contamination_not_clean")
    if not rows and not commercial:
        blockers.append("no_human_speakers_recorded_yet")

    report = {
        "campaign": "V-NEXT-2B.6A",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "commercial_speakers_registered": len(commercial),
        "speakers_registered": len(consents),
        "speakers_with_pass_clips": len(by_spk),
        "clips_by_speaker_pass": dict(by_spk),
        "total_clips_manifest": len(rows),
        "accepted_product_clean_pass": len(clean_pass),
        "rejected_or_fail": len(rejected),
        "pending_qa": len(pending),
        "MIX_accepted": mix,
        "numeric_accepted": numeric,
        "EN_accepted": en,
        "NE_accepted": ne,
        "interrupt_accepted_est": interrupt,
        "hours_accepted": round(hours, 4),
        "qa_pass_rate": round(qa_rate, 4),
        "human_verified_pass_clips": human_v,
        "device_distribution": dict(devices),
        "noise_environment_distribution": dict(noise),
        "validation_test_speaker_availability": {
            "split_report_status": split_report.get("status"),
            "speaker_disjoint": split_report.get("speaker_disjoint"),
            "train_speakers": split_report.get("train_speakers"),
            "val_speakers": split_report.get("val_speakers"),
            "test_speakers": split_report.get("test_speakers"),
        },
        "contamination_status": contam.get("status"),
        "authorization_verdict": auth.get("verdict") or "NOT_RUN",
        "assignment_plan_summary": assignment,
        "blockers": blockers,
        "gate_thresholds": {
            "min_speakers": 5,
            "min_mix": 500,
            "min_numeric": 200,
        },
        "raw_audio_root": str(CORPUS),
        "fabricated": False,
        "note": (
            "Progress reflects only real consents/clips under the local corpus. "
            "Autonomous agent cannot recruit multi-speaker humans; recording requires live participants."
        ),
    }

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    md = [
        "# V-NEXT-2B.6A Collection Progress",
        "",
        f"Updated: `{report['updated_at']}`",
        "",
        f"**Authorization:** `{report['authorization_verdict']}`",
        "",
        "## Counts",
        "",
        f"- Commercial consents: **{report['commercial_speakers_registered']}**",
        f"- Speakers with PASS clips: **{report['speakers_with_pass_clips']}**",
        f"- Accepted PRODUCT_CLEAN PASS: **{report['accepted_product_clean_pass']}**",
        f"- Rejected/FAIL: **{report['rejected_or_fail']}**",
        f"- MIX accepted: **{mix}** / 500",
        f"- Numeric accepted: **{numeric}** / 200",
        f"- EN / NE: **{en}** / **{ne}**",
        f"- Hours (accepted): **{report['hours_accepted']}**",
        f"- QA pass rate: **{report['qa_pass_rate']}**",
        f"- Human verified (pass clips): **{human_v}**",
        f"- Contamination: **{report['contamination_status']}**",
        "",
        "## Blockers",
        "",
    ]
    for b in blockers:
        md.append(f"- `{b}`")
    if not blockers:
        md.append("- none")
    md.append("")
    md.append("## Note")
    md.append("")
    md.append(report["note"])
    md.append("")
    args.md.write_text("\n".join(md) + "\n", encoding="utf-8")

    # repo snapshot (no audio)
    repo_md = REPO.parents[1] / "docs" / "voice-next-2b6" / "COLLECTION_CAMPAIGN_2B6A_PROGRESS.md"
    # REPO is tools/voice-stt-data
    repo_md = Path(__file__).resolve().parents[3] / "docs" / "voice-next-2b6" / "COLLECTION_CAMPAIGN_2B6A_PROGRESS.md"
    repo_md.parent.mkdir(parents=True, exist_ok=True)
    repo_md.write_text("\n".join(md) + "\n", encoding="utf-8")
    (repo_md.parent / "COLLECTION_CAMPAIGN_2B6A_PROGRESS.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )

    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
